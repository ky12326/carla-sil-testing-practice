"""
障碍物管理器

修复内容 (vs 原版):
- 修复坐标系统: 使用车辆局部坐标系 (考虑 yaw 角度)
- 封装为类, 管理障碍物生命周期
- 支持静态和动态障碍物
"""

import math
import carla
from typing import List, Optional


class ObstacleManager:
    """管理障碍车辆的生成和生命周期

    使用车辆局部坐标系计算障碍物位置, 支持:
    - 静态障碍物 (autopilot disabled)
    - 动态障碍物 (固定油门)
    """

    def __init__(self, world: carla.World, blueprint_library: carla.BlueprintLibrary):
        self.world = world
        self.bp_lib = blueprint_library
        self.obstacles: List[carla.Vehicle] = []

    def spawn_static_obstacles(self, ego_vehicle: carla.Vehicle,
                                num_obstacles: int = 3,
                                distance: float = 30.0,
                                spacing: float = 15.0,
                                lateral_offsets: Optional[List[float]] = None
                                ) -> List[carla.Vehicle]:
        """在 ego 车辆前方生成静态障碍物

        Args:
            ego_vehicle: 主车
            num_obstacles: 障碍物数量
            distance: 第一个障碍物距离 (m)
            spacing: 障碍物之间的纵向间距 (m)
            lateral_offsets: 各障碍物的横向偏移 (m), None 则自动计算

        Returns:
            生成的障碍车辆列表
        """
        if lateral_offsets is None:
            # 默认在相邻车道上分布
            lateral_offsets = [0, -3.5, 3.5]

        ego_transform = ego_vehicle.get_transform()
        ego_loc = ego_transform.location
        ego_yaw_rad = math.radians(ego_transform.rotation.yaw)

        for i in range(num_obstacles):
            # 纵向距离 (在车辆局部坐标中 = 前方)
            dx = distance + i * spacing
            # 横向偏移
            dy = lateral_offsets[i % len(lateral_offsets)]

            # 坐标变换到全局坐标系 (修复 BUG-003!)
            obstacle_x = ego_loc.x + dx * math.cos(ego_yaw_rad) - dy * math.sin(ego_yaw_rad)
            obstacle_y = ego_loc.y + dx * math.sin(ego_yaw_rad) + dy * math.cos(ego_yaw_rad)

            obstacle_bp = self.bp_lib.filter('vehicle.*')[0]
            spawn_point = carla.Transform(
                carla.Location(x=obstacle_x, y=obstacle_y, z=0.5)
            )

            try:
                obstacle = self.world.spawn_actor(obstacle_bp, spawn_point)
                obstacle.set_autopilot(False)  # 静态障碍物
                self.obstacles.append(obstacle)
            except RuntimeError as e:
                print(f"Warning: Failed to spawn obstacle {i} at ({obstacle_x:.1f}, {obstacle_y:.1f}): {e}")

        return self.obstacles

    def spawn_dynamic_obstacles(self, ego_vehicle: carla.Vehicle,
                                 num_obstacles: int = 2,
                                 distance: float = 20.0,
                                 spacing: float = 10.0,
                                 speeds: Optional[List[float]] = None,
                                 lateral_offsets: Optional[List[float]] = None
                                 ) -> List[carla.Vehicle]:
        """在 ego 车辆前方生成动态障碍物

        Args:
            ego_vehicle: 主车
            num_obstacles: 障碍物数量
            distance: 第一个障碍物距离 (m)
            spacing: 障碍物之间的纵向间距 (m)
            speeds: 各障碍物的油门量 (0-1), None 则自动计算
            lateral_offsets: 各障碍物的横向偏移 (m)

        Returns:
            生成的障碍车辆列表
        """
        if speeds is None:
            speeds = [0.15 * (i + 1) for i in range(num_obstacles)]
        if lateral_offsets is None:
            lateral_offsets = [0, -3.5]

        ego_transform = ego_vehicle.get_transform()
        ego_loc = ego_transform.location
        ego_yaw_rad = math.radians(ego_transform.rotation.yaw)

        for i in range(num_obstacles):
            dx = distance + i * spacing
            dy = lateral_offsets[i % len(lateral_offsets)]

            # 坐标变换 (修复 BUG-003!)
            obstacle_x = ego_loc.x + dx * math.cos(ego_yaw_rad) - dy * math.sin(ego_yaw_rad)
            obstacle_y = ego_loc.y + dx * math.sin(ego_yaw_rad) + dy * math.cos(ego_yaw_rad)

            obstacle_bp = self.bp_lib.filter('vehicle.*')[0]
            spawn_point = carla.Transform(
                carla.Location(x=obstacle_x, y=obstacle_y, z=0.5)
            )

            try:
                obstacle = self.world.spawn_actor(obstacle_bp, spawn_point)
                obstacle.apply_control(carla.VehicleControl(
                    throttle=speeds[i % len(speeds)], steer=0.0
                ))
                self.obstacles.append(obstacle)
            except RuntimeError as e:
                print(f"Warning: Failed to spawn obstacle {i} at ({obstacle_x:.1f}, {obstacle_y:.1f}): {e}")

        return self.obstacles

    def get_positions(self) -> List[carla.Location]:
        """获取所有障碍物的当前位置"""
        return [obs.get_location() for obs in self.obstacles if obs.is_alive]

    def destroy_all(self):
        """安全销毁所有障碍物"""
        for obs in self.obstacles:
            if obs.is_alive:
                obs.set_autopilot(False)
                obs.destroy()
        self.obstacles.clear()
