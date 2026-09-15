#!/usr/bin/env python3
"""
carla_simAvoidance 静态障碍物避障 — 基线测试适配版

相比原版的改动:
1. 使用随机生成点替代硬编码坐标
2. 添加 CARLA egg 路径注入
3. 添加基本的运行日志

其他 Bug 保持原样, 用于记录基线行为。
"""
import os
import sys

# CARLA 导入路径来自环境变量 CARLA_EGG（原版此处写死为本机绝对路径）
_EGG = os.environ.get('CARLA_EGG')
if _EGG and _EGG not in sys.path:
    sys.path.insert(0, _EGG)

import carla
import time
import numpy as np
import math
import random
from datetime import datetime

# ========== 原版全局变量 (保留, 用于基线记录) ==========
actor_list = []
collision_flag = False
is_avoiding = False
target_lane = None

# ========== 原版函数 (未修改) ==========

def image_process(image):
    img = np.array(image.raw_data)
    img = img.reshape((1080, 1920, 4))
    img = img[:, :, :3]

def callback(event):
    global collision_flag
    if not collision_flag:
        vehicle.apply_control(carla.VehicleControl(brake=1.0))
        collision_flag = True
        print("碰撞！")

def callback2(event):
    print("穿越车道!")

def spawn_obstacles(world, blueprint_library, vehicle, num_obstacles=3, distance=30.0):
    obstacles = []
    vehicle_transform = vehicle.get_transform()
    vehicle_location = vehicle_transform.location
    vehicle_yaw = vehicle_transform.rotation.yaw
    offset_ys = [0, 3.0, 7] * num_obstacles
    for i in range(num_obstacles):
        offset_x = distance + i * 15.0
        offset_y = offset_ys[i]
        obstacle_x = vehicle_location.x + offset_x
        obstacle_y = vehicle_location.y + offset_y
        spawn_point = carla.Transform(carla.Location(x=obstacle_x, y=obstacle_y, z=0.5))
        obstacle_bp = blueprint_library.filter('vehicle.*')[0]
        obstacle = world.spawn_actor(obstacle_bp, spawn_point)
        actor_list.append(obstacle)
        obstacles.append(obstacle)
    return obstacles

def pure_pursuit(tar_location, v_transform):
    L = 2.875
    yaw = v_transform.rotation.yaw * (math.pi / 180)
    x = v_transform.location.x - L / 2 * math.cos(yaw)
    y = v_transform.location.y - L / 2 * math.sin(yaw)
    dx = tar_location.x - x
    dy = tar_location.y - y
    ld = math.sqrt(dx ** 2 + dy ** 2)
    alpha = math.atan2(dy, dx) - yaw
    delta = math.atan(2 * math.sin(alpha) * L / ld) * 180 / math.pi
    steer = delta / 90
    if steer > 1:
        steer = 1
    elif steer < -1:
        steer = -1
    return steer

def destroy_actor(world, actor):
    if 'vehicle' in actor.type_id:
        actor.set_autopilot(False)
    if 'walker' in actor.type_id and hasattr(actor, 'controller'):
        actor.controller.stop()
        world.try_destroy_actor(actor.controller)
    actor.destroy()

def get_new_lane(current_waypoint):
    right_lane = current_waypoint.get_right_lane()
    if right_lane and (right_lane.lane_type & carla.LaneType.Driving):
        return right_lane
    left_lane = current_waypoint.get_left_lane()
    if left_lane and (left_lane.lane_type & carla.LaneType.Driving):
        return left_lane
    return None

# ========== 主程序 ==========

print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting static obstacle scenario...")
start_time = time.time()
collision_count = 0
lane_invasion_count = 0

try:
    client = carla.Client('localhost', 2000)
    client.set_timeout(5.0)
    world = client.get_world()
    map = world.get_map()
    blueprint_library = world.get_blueprint_library()

    # 适配: 使用随机生成点
    spawn_points = world.get_map().get_spawn_points()
    spawn_point = random.choice(spawn_points)
    print(f"Ego spawn: {spawn_point.location}")

    v_bp = blueprint_library.filter("model3")[0]
    vehicle = world.spawn_actor(v_bp, spawn_point)
    actor_list.append(vehicle)

    # 相机传感器 (原版配置)
    blueprint = blueprint_library.find('sensor.camera.rgb')
    blueprint.set_attribute('image_size_x', '1920')
    blueprint.set_attribute('image_size_y', '1080')
    blueprint.set_attribute('fov', '110')
    blueprint.set_attribute('sensor_tick', '1.0')
    transform = carla.Transform(carla.Location(x=0.8, z=1.7))
    sensor = world.spawn_actor(blueprint, transform, attach_to=vehicle)
    actor_list.append(sensor)
    sensor.listen(lambda image: image_process(image))

    # 碰撞传感器
    blueprint_cd = blueprint_library.find('sensor.other.collision')
    sensor_collision = world.spawn_actor(blueprint_cd, carla.Transform(carla.Location(x=0.8, z=1.7)), attach_to=vehicle)
    actor_list.append(sensor_collision)
    sensor_collision.listen(callback)

    # 车道入侵传感器
    blueprint_li = blueprint_library.find('sensor.other.lane_invasion')
    sensor_li = world.spawn_actor(blueprint_li, carla.Transform(carla.Location(x=0.8, z=1.7)), attach_to=vehicle)
    actor_list.append(sensor_li)
    sensor_li.listen(callback2)

    # 生成障碍物
    obstacles = spawn_obstacles(world, blueprint_library, vehicle, num_obstacles=3, distance=30.0)

    vehicle.set_autopilot(True)
    time.sleep(2)

    stuck_timer = 0
    max_runtime = 30  # 最多运行 30 秒
    tick_count = 0

    while time.time() - start_time < max_runtime:
        tick_count += 1
        if tick_count % 50 == 0:
            elapsed = time.time() - start_time
            vel = vehicle.get_velocity()
            speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)
            print(f"  [{elapsed:.0f}s] speed={speed:.1f}m/s, avoiding={is_avoiding}, collision={collision_flag}")

        velocity = vehicle.get_velocity()
        speed = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)

        if not is_avoiding:
            if speed < 2.5:
                stuck_timer += 1
                if stuck_timer > 5:
                    print("前方障碍！")
                    current_waypoint = map.get_waypoint(vehicle.get_transform().location)
                    target_lane = get_new_lane(current_waypoint)
                    if target_lane:
                        print("开始绕行")
                        vehicle.set_autopilot(False)
                        is_avoiding = True
                        stuck_timer = 0
                    else:
                        print("无可用车道，紧急停车！")
                        vehicle.apply_control(carla.VehicleControl(brake=1.0))
        else:
            steer = pure_pursuit(target_lane.transform.location, vehicle.get_transform())
            vehicle.apply_control(carla.VehicleControl(throttle=0.4, steer=steer))
            current_loc = vehicle.get_location()
            target_distance = current_loc.distance(target_lane.transform.location)
            current_waypoint = map.get_waypoint(current_loc)
            if target_distance < 1.0 or current_waypoint.lane_id == target_lane.lane_id:
                print("绕行完成，恢复正常行驶")
                vehicle.set_autopilot(True)
                is_avoiding = False
                target_lane = None

        if collision_flag:
            collision_count += 1
            break  # 碰撞后终止

        time.sleep(0.02)

finally:
    elapsed = time.time() - start_time
    print(f"\n=== 测试结果 ===")
    print(f"运行时间: {elapsed:.1f}s")
    print(f"Tick 计数: {tick_count}")
    print(f"碰撞: {collision_flag}")
    print(f"避障触发: {'是' if is_avoiding else '否'}")
    print(f"结果: {'碰撞终止' if collision_flag else '正常结束'}")

    for actor in actor_list:
        destroy_actor(world, actor)
    print("程序结束，所有Actor已销毁")
