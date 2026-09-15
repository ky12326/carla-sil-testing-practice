"""
场景基类

提供所有场景的通用基础设施:
- CARLA 客户端连接
- Ego 车辆创建
- 控制循环
- 避障逻辑
- 数据记录
"""

import sys
import os

# CARLA 的导入路径来自环境变量 CARLA_EGG（必须在 import carla 之前生效）。
# 未设置时会直接尝试 import —— 适用于已 pip install carla 或
# 已把 PythonAPI 配进 PYTHONPATH 的情况。设置方法见 README「环境准备」。
_CARLA_EGG = os.environ.get('CARLA_EGG')
if _CARLA_EGG and os.path.exists(_CARLA_EGG) and _CARLA_EGG not in sys.path:
    sys.path.insert(0, _CARLA_EGG)

import time
import math
import random
import yaml
import carla

from src.ego_vehicle import EgoVehicle
from src.obstacle_manager import ObstacleManager
from src.pure_pursuit import PurePursuitController
from src.recorder import TestRecorder


class ScenarioResult:
    """场景运行结果"""

    def __init__(self):
        self.success: bool = False
        self.collision_count: int = 0
        self.lane_change_completed: bool = False
        self.control_switches: int = 0
        self.elapsed_time: float = 0.0
        self.total_ticks: int = 0
        self.reason: str = ""


class BaseScenario:
    """场景基类"""

    def __init__(self, config_path: str = None):
        # 加载配置
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config', 'default.yaml'
            )
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        # CARLA 客户端
        self.client: carla.Client = None
        self.world: carla.World = None
        self.map: carla.Map = None

        # 核心组件
        self.ego: EgoVehicle = None
        self.obstacle_mgr: ObstacleManager = None
        self.controller: PurePursuitController = None
        self.recorder: TestRecorder = None

        # 场景状态
        self.result = ScenarioResult()
        self._stuck_timer = 0
        self._avoidance_count = 0
        self._start_time = 0.0
        self._tick_count = 0

    # ========== 初始化 ==========

    def connect(self):
        """连接 CARLA"""
        cfg = self.config['carla']
        self.client = carla.Client(cfg['host'], cfg['port'])
        self.client.set_timeout(cfg['timeout'])
        self.world = self.client.get_world()
        self.map = self.world.get_map()

    def setup_ego(self) -> carla.Vehicle:
        """创建 ego 车辆"""
        bp_lib = self.world.get_blueprint_library()
        model = self.config['ego_vehicle']['model']
        v_bp = bp_lib.filter(model)[0]

        # 固定随机种子：spawn_index 为 null 时走 random.choice 分支，
        # 没有种子则同一份 config 每次运行落点都不同，结果不可复现。
        seed = self.config.get('runtime', {}).get('seed')
        if seed is not None:
            random.seed(seed)

        spawn_idx = self.config['ego_vehicle'].get('spawn_index')
        if spawn_idx is not None:
            spawn_point = self.map.get_spawn_points()[spawn_idx]
        else:
            spawn_point = random.choice(self.map.get_spawn_points())

        # 冷却时间从配置读取（此前是 EgoVehicle 的类常量写死，
        # 导致 config/default.yaml 里的 cooldown_seconds 从未生效）
        self.ego = EgoVehicle(
            self.world, v_bp, spawn_point,
            collision_cooldown=self.config['collision']['cooldown_seconds'],
            avoidance_cooldown=self.config['avoidance']['cooldown_seconds'],
        )
        vehicle = self.ego.spawn()

        # 附加传感器
        self.ego.attach_collision_sensor()
        self.ego.attach_lane_invasion_sensor()

        # Pure Pursuit 控制器
        pp_cfg = self.config['pure_pursuit']
        self.controller = PurePursuitController(
            wheelbase=pp_cfg['wheelbase'],
            max_steer_angle=pp_cfg['max_steer_angle'],
        )

        # 障碍物管理器
        self.obstacle_mgr = ObstacleManager(self.world, bp_lib)

        # 数据记录器
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            self.config['output']['data_dir']
        )
        self.recorder = TestRecorder(output_dir, self.__class__.__name__)

        return vehicle

    def set_weather(self, preset_name: str = "ClearNoon"):
        """设置天气"""
        presets = self.config.get('weather_presets', {})
        if preset_name in presets:
            p = presets[preset_name]
            weather = carla.WeatherParameters(
                cloudiness=p.get('cloudiness', 10),
                precipitation=p.get('precipitation', 0),
                sun_altitude_angle=p.get('sun_altitude_angle', 45),
                fog_density=p.get('fog_density', 10),
            )
            self.world.set_weather(weather)

    # ========== 避障逻辑 ==========

    def check_stagnation(self, speed: float) -> bool:
        """检查是否卡死 (速度持续低于阈值)"""
        stag_cfg = self.config['stagnation']
        if speed < stag_cfg['speed_threshold']:
            self._stuck_timer += 1
            return self._stuck_timer > stag_cfg['tick_threshold']
        else:
            self._stuck_timer = 0
            return False

    def try_avoidance(self) -> bool:
        """尝试触发避障换道。返回 True 如果成功开始避障"""
        current_waypoint = self.map.get_waypoint(self.ego.get_location())

        # 优先尝试右车道
        target = current_waypoint.get_right_lane()
        if target and (target.lane_type & carla.LaneType.Driving):
            return self.ego.start_avoidance(target)

        # 再尝试左车道
        target = current_waypoint.get_left_lane()
        if target and (target.lane_type & carla.LaneType.Driving):
            return self.ego.start_avoidance(target)

        # 无可用车道 → 紧急停车 (仅首次)
        if self.ego.control_mode != 'stopped':
            print(f"无可用车道 (lane_id={current_waypoint.lane_id}), 紧急停车！")
            self.ego.emergency_stop()
            self.recorder.record_event(
                'emergency_stop', time.time() - self._start_time,
                detail=f"no_available_lane, lane_id={current_waypoint.lane_id}"
            )
        return False

    def update_avoidance(self):
        """更新避障状态"""
        if not self.ego.is_avoiding or self.ego.target_lane is None:
            return

        # Pure Pursuit 控制
        transform = self.ego.get_transform()
        target_loc = self.ego.target_lane.transform.location
        steer = self.controller.compute_steering(target_loc, transform)
        self.ego.apply_control(
            throttle=self.config['avoidance']['throttle'],
            steer=steer,
        )

        # 检查是否完成换道
        current_loc = self.ego.get_location()
        target_distance = current_loc.distance(target_loc)
        current_waypoint = self.map.get_waypoint(current_loc)

        threshold = self.config['avoidance']['target_distance_threshold']
        if target_distance < threshold or current_waypoint.lane_id == self.ego.target_lane.lane_id:
            self._avoidance_count += 1
            self.result.control_switches = self._avoidance_count
            self.result.lane_change_completed = True
            completed_lane = self.ego.target_lane.lane_id  # 先保存 (complete 会清空)
            self.ego.complete_avoidance()
            self.recorder.record_event(
                'avoidance_complete', time.time() - self._start_time,
                detail=f"target_lane={completed_lane}, count={self._avoidance_count}"
            )

    # ========== 主循环 ==========

    def run(self, max_duration: float = None) -> ScenarioResult:
        """运行场景主循环"""
        self.connect()
        self.setup_ego()

        if max_duration is None:
            max_duration = self.config['runtime']['max_duration']

        # 子类实现具体的场景设置 (生成障碍物等)
        self._setup_scenario()

        # 启动 autopilot
        self.ego.set_autopilot(True)
        time.sleep(2)

        self._start_time = time.time()
        self._tick_count = 0
        tick_rate = self.config['runtime']['tick_rate']

        while time.time() - self._start_time < max_duration:
            self._tick_count += 1

            # 更新视角
            self._update_spectator()

            # 获取状态
            speed = self.ego.get_speed()
            loc = self.ego.get_location()

            # 记录数据
            self.recorder.record_tick(
                tick=self._tick_count,
                timestamp=time.time() - self._start_time,
                speed=speed,
                location_x=loc.x if loc else 0,
                location_y=loc.y if loc else 0,
                control_mode=self.ego.control_mode,
                collision=self.ego.collision_flag,
                lane_invasion=self.ego.lane_invasion_flag,
                is_avoiding=self.ego.is_avoiding,
            )

            # 车道入侵标志必须「读后重置」：回调只负责置位，读取方负责复位。
            # 此前缺少这一步，导致一旦压线，之后每个 tick 都被计入
            # lane_invasion_events（静态场景实测 1410/1619，指标完全失真）。
            self.ego.reset_lane_invasion_flag()

            # 碰撞检查 (修复 BUG-001!)
            if self.ego.collision_flag:
                self.result.collision_count += 1
                self.recorder.record_event('collision', time.time() - self._start_time)
                self.ego.reset_collision_flag()
                # 碰撞后不立即退出, 等待一段时间看恢复情况
                if self.result.collision_count >= 3:
                    self.recorder.set_result('FAIL', '多次碰撞')
                    break

            # 避障逻辑 (仅在 autopilot 模式下检查)
            if not self.ego.is_avoiding and self.ego.control_mode != 'stopped':
                if self.check_stagnation(speed):
                    if self.try_avoidance():
                        print(f"前方障碍！speed={speed:.1f}m/s")
                        self.recorder.record_event(
                            'avoidance_start', time.time() - self._start_time,
                            detail=f"speed={speed:.1f}m/s"
                        )
                    else:
                        self._stuck_timer = 0  # 冷却期/无可用车道, 重置卡死计时器
            else:
                self.update_avoidance()

            time.sleep(tick_rate)

        # 结束处理
        self.result.elapsed_time = time.time() - self._start_time
        self.result.total_ticks = self._tick_count

        if self.result.collision_count == 0:
            self.result.success = True
            self.recorder.set_result('PASS')
        else:
            self.recorder.set_result('FAIL', f'{self.result.collision_count} 次碰撞')

        self._cleanup()
        return self.result

    def _setup_scenario(self):
        """子类重写: 设置具体场景 (生成障碍物等)"""
        raise NotImplementedError

    def _update_spectator(self):
        """更新观察者视角 (跟随 ego)"""
        transform = self.ego.get_transform()
        if transform is None:
            return
        spectator = self.world.get_spectator()
        forward = transform.get_forward_vector()
        spectator.set_transform(carla.Transform(
            transform.location - forward * 6.0 + carla.Location(z=2.5),
            transform.rotation,
        ))

    def _cleanup(self):
        """清理资源"""
        if self.obstacle_mgr:
            self.obstacle_mgr.destroy_all()
        if self.ego:
            self.ego.destroy()
        if self.recorder:
            self.recorder.save_csv()
            self.recorder.save_summary()
        print(f"\n场景结束: {self.recorder.metadata.get('result', 'unknown')}")
        print(f"运行时间: {self.result.elapsed_time:.1f}s")
        print(f"碰撞: {self.result.collision_count}次")
        print(f"避障触发: {self.result.control_switches}次")
