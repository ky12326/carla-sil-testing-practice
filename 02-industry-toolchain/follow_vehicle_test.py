#!/usr/bin/env python3
"""
自定义跟车安全性测试

测试问题: CARLA autopilot 在不同前车减速强度下的跟车安全性
SIL 流程: 场景设计 → 用例开发 → 仿真执行 → 数据采集 → 结果分析

依赖：运行中的 CARLA server（默认 localhost:2000）。

用法:
    # 1. 让 Python 能 import carla（二选一）
    source ../activate_env.sh            # 需先 export CARLA_ROOT
    # 或手动指定:
    export CARLA_EGG="/path/to/CARLA_0.9.11/PythonAPI/carla/dist/carla-0.9.11-py3.7-linux-x86_64.egg"

    # 2. 另开终端启动 CARLA server
    "$CARLA_ROOT/CarlaUE4.sh" -opengl

    # 3. 运行
    python follow_vehicle_test.py

注意：本脚本目前只把结果打印到终端、**不写文件**。
若要留存可复核的结果，需自行增加输出（见 ../02-industry-toolchain/notes-toolchain.md §5）。
"""

import os
import sys

# CARLA 的导入路径来自环境变量（见文件头用法说明），不在源码里写死本机路径
_EGG = os.environ.get('CARLA_EGG')
if _EGG and _EGG not in sys.path:
    sys.path.insert(0, _EGG)

import carla
import time
import math
import random
from datetime import datetime

# ============================================================
# 第 2 步: 测试策划 — 定义测试参数（测试矩阵）
# ============================================================

TEST_MATRIX = [
    # (前车速度 m/s, 减速度 m/s², 描述)
    (5.0,  2.0,  "轻度减速"),
    (5.0,  4.0,  "中度减速"),
    (5.0,  7.0,  "紧急制动"),
    (10.0, 4.0,  "高速中度减速"),
    (10.0, 7.0,  "高速紧急制动"),
]

# 每次测试的参数
INITIAL_DISTANCE = 25.0   # 初始跟车距离 (m)
MAX_TEST_TIME = 15.0      # 每次测试最长运行时间 (s)
FRAME_RATE = 0.05         # 20 Hz

# ============================================================
# 第 3 步: 场景设计 — 定义场景执行函数
# ============================================================

class FollowVehicleTest:
    """跟车安全性测试场景"""

    def __init__(self, client, world):
        self.client = client
        self.world = world
        self.map = world.get_map()
        self.bp_lib = world.get_blueprint_library()
        self.actors = []

    def run_scenario(self, lead_speed, lead_deceleration, description):
        """运行一次跟车测试, 返回测试结果"""
        print(f"\n{'='*50}")
        print(f"测试: {description}")
        print(f"  前车速度={lead_speed}m/s ({lead_speed*3.6:.0f}km/h)")
        print(f"  前车减速度={lead_deceleration}m/s²")
        print(f"{'='*50}")

        # --- 场景布置 ---
        # 1. 选一个直道生成点
        spawn_points = self.map.get_spawn_points()
        ego_spawn = random.choice(spawn_points)
        ego_loc = ego_spawn.location
        ego_rot = ego_spawn.rotation

        # 2. 生成 ego 车 (被测系统: CARLA Autopilot)
        ego_bp = self.bp_lib.filter('model3')[0]
        ego = self.world.spawn_actor(ego_bp, ego_spawn)
        self.actors.append(ego)

        # 3. 挂载碰撞传感器 (数据采集)
        collision_bp = self.bp_lib.find('sensor.other.collision')
        collision_sensor = self.world.spawn_actor(
            collision_bp, carla.Transform(), attach_to=ego)
        self.actors.append(collision_sensor)

        collision_detected = [False]  # 用列表包裹以便在回调中修改
        collision_time = [0.0]

        def on_collision(event):
            collision_detected[0] = True
            collision_time[0] = time.time() - start_time
            print(f"  ⚠ 碰撞! 时间={collision_time[0]:.1f}s")

        collision_sensor.listen(on_collision)

        # 4. 在前方生成 lead 车
        lead_spawn = carla.Transform(
            carla.Location(
                x=ego_loc.x + INITIAL_DISTANCE * math.cos(math.radians(ego_rot.yaw)),
                y=ego_loc.y + INITIAL_DISTANCE * math.sin(math.radians(ego_rot.yaw)),
                z=ego_loc.z
            ),
            ego_rot
        )
        lead_bp = self.bp_lib.filter('vehicle.audi.a2')[0]
        lead = self.world.spawn_actor(lead_bp, lead_spawn)
        self.actors.append(lead)

        # 5. 启动 ego 的 autopilot
        ego.set_autopilot(True)

        # --- 仿真执行 ---
        start_time = time.time()
        records = []  # 每帧数据

        # Phase 1: 两车保持匀速 (前 3 秒)
        while time.time() - start_time < 3.0:
            lead.apply_control(carla.VehicleControl(throttle=0.3, steer=0.0))
            time.sleep(FRAME_RATE)

        # Phase 2: 前车开始减速
        decel_start_time = time.time()
        while time.time() - start_time < MAX_TEST_TIME:
            if collision_detected[0]:
                break

            # 前车减速控制
            lead.apply_control(carla.VehicleControl(
                throttle=0.0, brake=min(lead_deceleration / 10.0, 1.0)
            ))

            # 如果前车停下了，继续记录一段时间
            lead_vel = lead.get_velocity()
            lead_speed_now = math.sqrt(lead_vel.x**2 + lead_vel.y**2 + lead_vel.z**2)
            if lead_speed_now < 0.1 and (time.time() - decel_start_time) > 5.0:
                break

            # 记录数据
            ego_vel = ego.get_velocity()
            ego_speed = math.sqrt(ego_vel.x**2 + ego_vel.y**2 + ego_vel.z**2)
            ego_loc_now = ego.get_location()
            lead_loc_now = lead.get_location()
            distance = ego_loc_now.distance(lead_loc_now)

            records.append({
                'time': time.time() - start_time,
                'ego_speed': ego_speed,
                'lead_speed': lead_speed_now,
                'distance': distance,
            })

            time.sleep(FRAME_RATE)

        # --- 结果分析 ---
        elapsed = time.time() - start_time

        # 计算指标
        if records:
            distances = [r['distance'] for r in records]
            min_distance = min(distances) if distances else INITIAL_DISTANCE
            avg_distance = sum(distances) / len(distances)
            ego_speeds = [r['ego_speed'] for r in records]
            max_ego_speed = max(ego_speeds) if ego_speeds else 0
            min_ego_speed = min(ego_speeds) if ego_speeds else 0
        else:
            min_distance = INITIAL_DISTANCE
            avg_distance = INITIAL_DISTANCE
            max_ego_speed = 0
            min_ego_speed = 0

        # 判定
        passed = not collision_detected[0] and min_distance > 1.0

        result = {
            'description': description,
            'lead_speed': lead_speed,
            'lead_deceleration': lead_deceleration,
            'passed': passed,
            'collision': collision_detected[0],
            'collision_time': collision_time[0] if collision_detected[0] else None,
            'min_distance_m': round(min_distance, 2),
            'avg_distance_m': round(avg_distance, 2),
            'max_ego_speed_ms': round(max_ego_speed, 2),
            'min_ego_speed_ms': round(min_ego_speed, 2),
            'elapsed_s': round(elapsed, 1),
            'num_records': len(records),
        }

        return result

    def cleanup(self):
        """销毁所有 Actor"""
        for actor in reversed(self.actors):
            if actor.is_alive:
                if 'vehicle' in actor.type_id:
                    actor.set_autopilot(False)
                actor.destroy()
        self.actors.clear()


# ============================================================
# 第 4 步: 用例开发 — 主测试流程
# ============================================================

def main():
    print("=" * 60)
    print("跟车安全性测试 — CARLA Autopilot 评估")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试矩阵: {len(TEST_MATRIX)} 个测试点")
    print("=" * 60)

    # 连接 CARLA
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    world = client.get_world()
    print(f"地图: {world.get_map().name}")

    test = FollowVehicleTest(client, world)
    all_results = []

    try:
        random.seed(42)  # 固定随机种子，保证可重复

        for lead_speed, decel, desc in TEST_MATRIX:
            result = test.run_scenario(lead_speed, decel, desc)
            all_results.append(result)
            test.cleanup()
            time.sleep(1)  # 场景之间休息 1 秒

    finally:
        test.cleanup()

    # ============================================================
    # 第 7 步: 结果分析 — 输出对比报告
    # ============================================================

    print("\n")
    print("=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    # 表头
    header = f"{'场景':<16} {'速度':>6} {'减速度':>6} {'通过':>4} {'碰撞':>4} {'最近距离':>8} {'平均距离':>8} {'ego最低速':>9}"
    print(header)
    print("-" * 80)

    for r in all_results:
        row = (
            f"{r['description']:<16}"
            f"{r['lead_speed']:>5.0f}m/s"
            f"{r['lead_deceleration']:>5.0f}m/s²"
            f"{'✅' if r['passed'] else '❌':>5}"
            f"{'是' if r['collision'] else '否':>4}"
            f"{r['min_distance_m']:>7.1f}m"
            f"{r['avg_distance_m']:>7.1f}m"
            f"{r['min_ego_speed_ms']:>7.1f}m/s"
        )
        print(row)

    print("-" * 80)

    # 通过率
    passed_count = sum(1 for r in all_results if r['passed'])
    print(f"\n通过率: {passed_count}/{len(all_results)} ({passed_count/len(all_results)*100:.0f}%)")

    # 分析洞察
    print(f"\n📊 关键发现:")

    collisions = [r for r in all_results if r['collision']]
    if collisions:
        for c in collisions:
            print(f"  - {c['description']}: 发生碰撞 (t={c['collision_time']:.1f}s)")
    else:
        print(f"  - 所有场景均无碰撞 ✅")

    # 最小跟车距离分析
    print(f"\n  最小跟车距离对比:")
    for r in sorted(all_results, key=lambda x: x['min_distance_m']):
        bar = '█' * int(r['min_distance_m'] * 2)
        print(f"    {r['description']:<16} {r['min_distance_m']:>5.1f}m {bar}")

    # 结论
    print(f"\n📝 结论:")
    print(f"  被测系统: CARLA 0.9.11 内置 Autopilot (Traffic Manager)")
    print(f"  测试场景: 前车在不同速度下减速，ego 跟随反应")
    print(f"  通过标准: 无碰撞 且 最近跟车距离 > 1.0m")
    print(f"  测试日期: {datetime.now().strftime('%Y-%m-%d')}")

    # 对应 SIL 工作流环节
    print(f"\n📋 本次测试覆盖的 SIL 工作流环节:")
    print(f"  ✅ 第 2 步: 测试策划 (TEST_MATRIX 参数设计)")
    print(f"  ✅ 第 3 步: 场景设计 (FollowVehicleTest 类)")
    print(f"  ✅ 第 4 步: 用例开发 (main() 测试流程)")
    print(f"  ✅ 第 5 步: 仿真执行 (CARLA server + autopilot)")
    print(f"  ✅ 第 6 步: 数据采集 (每帧记录速度/距离)")
    print(f"  ✅ 第 7 步: 结果分析 (汇总表 + 通过率 + 关键发现)")


if __name__ == '__main__':
    main()
