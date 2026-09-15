"""
Ego Vehicle 封装

修复内容 (vs 原版):
- 封装为 EgoVehicle 类, 消除全局变量 (BUG-002)
- collision 事件由实例管理, 主循环可检查 (BUG-001)
- 添加碰撞后恢复机制 (cooldown)
- 添加避障完成后的冷却期 (修复振荡问题)
- 传感器生命周期自动管理
"""

import math
import time
import carla
from typing import Optional, Callable, List, Dict
from dataclasses import dataclass, field


@dataclass
class EgoState:
    """Ego 车辆状态快照 (用于数据记录)"""
    timestamp: float
    location: carla.Location
    rotation: carla.Rotation
    velocity: carla.Vector3D
    speed: float
    control_mode: str  # 'autopilot' | 'pure_pursuit' | 'stopped'
    collision: bool
    lane_invasion: bool


class EgoVehicle:
    """封装 CARLA ego 车辆及其传感器

    管理:
    - 车辆生成与销毁
    - 传感器 (collision, lane_invasion, camera)
    - 控制模式切换 (autopilot ↔ manual)
    - 事件回调

    Attributes:
        vehicle: CARLA Vehicle actor
        collision_history: 碰撞事件列表
        lane_invasion_count: 车道入侵计数
        state_history: 车辆状态历史记录
    """

    # 碰撞恢复配置
    COLLISION_COOLDOWN = 3.0      # 碰撞后冷却时间 (秒)
    AVOIDANCE_COOLDOWN = 5.0      # 避障完成后冷却时间 (秒) — 修复振荡!

    def __init__(self, world: carla.World, vehicle_bp: carla.ActorBlueprint,
                 spawn_point: carla.Transform,
                 collision_cooldown: Optional[float] = None,
                 avoidance_cooldown: Optional[float] = None):
        self.world = world
        self.vehicle: Optional[carla.Vehicle] = None
        self._vehicle_bp = vehicle_bp
        self._spawn_point = spawn_point

        # 冷却时间：优先取传入值（来自 config/default.yaml），否则用类常量默认值。
        # 这两个值过去是写死的类常量，导致 YAML 里的 cooldown_seconds 从未生效。
        self.collision_cooldown = (
            self.COLLISION_COOLDOWN if collision_cooldown is None else collision_cooldown
        )
        self.avoidance_cooldown = (
            self.AVOIDANCE_COOLDOWN if avoidance_cooldown is None else avoidance_cooldown
        )

        # 传感器
        self._sensors: List[carla.Sensor] = []
        self._camera_sensors: Dict[str, carla.Sensor] = {}

        # 事件状态
        self.collision_flag = False
        self.collision_history: List[float] = []  # 碰撞时间戳列表
        self.collision_intensity: float = 0.0
        self.lane_invasion_flag = False
        self.lane_invasion_count = 0

        # 控制状态
        self._control_mode: str = 'autopilot'
        self._last_avoidance_end_time = 0.0   # 上次避障完成时间
        self._last_collision_time = 0.0       # 上次碰撞时间
        self._is_avoiding = False
        self._target_lane: Optional[carla.Waypoint] = None

        # 数据记录
        self.state_history: List[EgoState] = []

        # 回调
        self._on_collision_callback: Optional[Callable] = None
        self._on_lane_invasion_callback: Optional[Callable] = None

    # ========== 生命周期 ==========

    def spawn(self) -> carla.Vehicle:
        """生成 ego 车辆"""
        self.vehicle = self.world.spawn_actor(self._vehicle_bp, self._spawn_point)
        return self.vehicle

    def attach_collision_sensor(self) -> carla.Sensor:
        """附加碰撞传感器"""
        bp = self.world.get_blueprint_library().find('sensor.other.collision')
        transform = carla.Transform(carla.Location(x=0.8, z=1.7))
        sensor = self.world.spawn_actor(bp, transform, attach_to=self.vehicle)
        sensor.listen(self._on_collision)
        self._sensors.append(sensor)
        return sensor

    def attach_lane_invasion_sensor(self) -> carla.Sensor:
        """附加车道入侵传感器"""
        bp = self.world.get_blueprint_library().find('sensor.other.lane_invasion')
        transform = carla.Transform(carla.Location(x=0.8, z=1.7))
        sensor = self.world.spawn_actor(bp, transform, attach_to=self.vehicle)
        sensor.listen(self._on_lane_invasion)
        self._sensors.append(sensor)
        return sensor

    def attach_camera(self, name: str, transform: carla.Transform,
                       resolution: tuple = (800, 600), fov: str = '90'
                       ) -> carla.Sensor:
        """附加 RGB 相机传感器"""
        bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
        bp.set_attribute('image_size_x', str(resolution[0]))
        bp.set_attribute('image_size_y', str(resolution[1]))
        bp.set_attribute('fov', fov)
        sensor = self.world.spawn_actor(bp, transform, attach_to=self.vehicle)
        self._camera_sensors[name] = sensor
        self._sensors.append(sensor)
        return sensor

    def destroy(self):
        """安全销毁车辆和所有传感器"""
        # 销毁传感器
        for sensor in self._sensors:
            if sensor.is_alive:
                sensor.stop()
                sensor.destroy()
        self._sensors.clear()
        self._camera_sensors.clear()

        # 销毁车辆
        if self.vehicle and self.vehicle.is_alive:
            self.vehicle.set_autopilot(False)
            self.vehicle.destroy()
            self.vehicle = None

    # ========== 传感器回调 (实例方法, 不使用全局变量!) ==========

    def _on_collision(self, event: carla.CollisionEvent):
        """碰撞事件回调"""
        now = time.time()

        # 检查是否在冷却期内
        if now - self._last_collision_time < self.collision_cooldown:
            return  # 忽略冷却期内的重复碰撞

        self.collision_flag = True
        self.collision_history.append(now)
        self.collision_intensity = math.sqrt(
            event.normal_impulse.x ** 2 +
            event.normal_impulse.y ** 2 +
            event.normal_impulse.z ** 2
        )
        self._last_collision_time = now

        # 紧急制动
        if self.vehicle and self.vehicle.is_alive:
            self.vehicle.apply_control(carla.VehicleControl(brake=1.0))

        actor_name = 'unknown'
        if event.other_actor:
            actor_name = event.other_actor.type_id
        print(f"碰撞! 对象={actor_name}, 强度={self.collision_intensity:.1f}")

        if self._on_collision_callback:
            self._on_collision_callback(event)

    def _on_lane_invasion(self, event: carla.LaneInvasionEvent):
        """车道入侵事件回调"""
        self.lane_invasion_flag = True
        self.lane_invasion_count += 1

        lane_types = [str( marking.type) for marking in event.crossed_lane_markings]
        print(f"穿越车道! 标记类型: {lane_types}")

        if self._on_lane_invasion_callback:
            self._on_lane_invasion_callback(event)

    # ========== 控制接口 ==========

    @property
    def control_mode(self) -> str:
        return self._control_mode

    @property
    def is_avoiding(self) -> bool:
        return self._is_avoiding

    def set_autopilot(self, enabled: bool = True):
        """启用/禁用 autopilot"""
        if self.vehicle and self.vehicle.is_alive:
            self.vehicle.set_autopilot(enabled)
            self._control_mode = 'autopilot' if enabled else 'manual'

    def apply_control(self, throttle: float = 0.0, steer: float = 0.0,
                      brake: float = 0.0):
        """手动控制车辆"""
        if self.vehicle and self.vehicle.is_alive:
            self.vehicle.apply_control(carla.VehicleControl(
                throttle=throttle, steer=steer, brake=brake
            ))
            self._control_mode = 'pure_pursuit'

    def emergency_stop(self):
        """紧急停车"""
        if self.vehicle and self.vehicle.is_alive:
            self.set_autopilot(False)
            self.vehicle.apply_control(carla.VehicleControl(brake=1.0))
            self._control_mode = 'stopped'

    def start_avoidance(self, target_lane: carla.Waypoint):
        """开始避障"""
        now = time.time()

        # 检查避障冷却期 (修复振荡!)
        if now - self._last_avoidance_end_time < self.avoidance_cooldown:
            return False

        self.set_autopilot(False)
        self._is_avoiding = True
        self._target_lane = target_lane
        print(f"开始绕行 → 目标车道: lane_{target_lane.lane_id}")
        return True

    def complete_avoidance(self):
        """完成避障, 恢复 autopilot"""
        self._is_avoiding = False
        self._target_lane = None
        self._last_avoidance_end_time = time.time()
        self.set_autopilot(True)
        print("绕行完成，恢复正常行驶")

    @property
    def target_lane(self) -> Optional[carla.Waypoint]:
        return self._target_lane

    # ========== 状态查询 ==========

    def get_speed(self) -> float:
        """获取当前速度 (m/s)"""
        if self.vehicle and self.vehicle.is_alive:
            v = self.vehicle.get_velocity()
            return math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2)
        return 0.0

    def get_transform(self) -> Optional[carla.Transform]:
        """获取当前变换"""
        if self.vehicle and self.vehicle.is_alive:
            return self.vehicle.get_transform()
        return None

    def get_location(self) -> Optional[carla.Location]:
        """获取当前位置"""
        if self.vehicle and self.vehicle.is_alive:
            return self.vehicle.get_location()
        return None

    def record_state(self):
        """记录当前状态到历史"""
        if not (self.vehicle and self.vehicle.is_alive):
            return
        state = EgoState(
            timestamp=time.time(),
            location=self.vehicle.get_location(),
            rotation=self.vehicle.get_transform().rotation,
            velocity=self.vehicle.get_velocity(),
            speed=self.get_speed(),
            control_mode=self._control_mode,
            collision=self.collision_flag,
            lane_invasion=self.lane_invasion_flag,
        )
        self.state_history.append(state)

        # 重置瞬时标志
        self.lane_invasion_flag = False

    def reset_collision_flag(self):
        """重置碰撞标志 (例如: 场景结束后)"""
        self.collision_flag = False

    def reset_lane_invasion_flag(self):
        """重置车道入侵瞬时标志。

        必须在每次读取该标志后调用：回调只负责置位，读取方负责复位，
        否则一旦压线，之后每一个 tick 都会被计入 lane_invasion_events。
        （累计次数请用 lane_invasion_count，它在回调里按事件边沿自增。）
        """
        self.lane_invasion_flag = False
