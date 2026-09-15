"""
Pure Pursuit 路径跟踪控制器

修复内容 (vs 原版):
- 封装为类，消除全局变量
- 参数可配置 (wheelbase, max_steer_angle)
- 添加转向角限幅和调试信息

本模块是**纯数学模块，不依赖 CARLA**：函数体内不引用任何 `carla.*`，
`carla` 只在类型注解中出现，因此用 TYPE_CHECKING 守卫，运行时无需安装 CARLA。
这使得对应的单元测试可以在任何机器上运行。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型检查器可见；运行时不会导入 carla
    import carla


class PurePursuitController:
    """Pure Pursuit 控制器

    根据目标点和车辆当前姿态计算前轮转向角。
    公式: δ = atan(2L·sin(α) / ld)

    Attributes:
        wheelbase: 车辆轴距 (m), 默认 2.875
        max_steer_angle: 最大转向角 (度), 默认 45
    """

    def __init__(self, wheelbase: float = 2.875, max_steer_angle: float = 45.0):
        self.wheelbase = wheelbase
        self.max_steer_angle = max_steer_angle

    def compute_steering(self, target_location: carla.Location,
                         vehicle_transform: carla.Transform) -> float:
        """计算转向控制量

        Args:
            target_location: 目标路径点位置
            vehicle_transform: 车辆当前变换 (位置+朝向)

        Returns:
            steer: 转向量 ∈ [-1, 1] (负=左转, 正=右转)
        """
        yaw = vehicle_transform.rotation.yaw * (math.pi / 180)

        # 后轴中心位置 (前轴在车辆中心, 后轴在后方 L/2 处)
        rear_x = vehicle_transform.location.x - (self.wheelbase / 2) * math.cos(yaw)
        rear_y = vehicle_transform.location.y - (self.wheelbase / 2) * math.sin(yaw)

        # 目标点相对于后轴的位置
        dx = target_location.x - rear_x
        dy = target_location.y - rear_y

        # 前视距离
        lookahead = math.sqrt(dx ** 2 + dy ** 2)
        if lookahead < 0.01:
            return 0.0

        # 目标点相对于车辆朝向的角度
        alpha = math.atan2(dy, dx) - yaw

        # 角度规范化到 [-π, π]
        alpha = math.atan2(math.sin(alpha), math.cos(alpha))

        # Pure Pursuit 公式
        delta = math.atan(2 * math.sin(alpha) * self.wheelbase / lookahead)
        delta_deg = delta * 180 / math.pi

        # 转向角限幅
        delta_deg = max(-self.max_steer_angle, min(self.max_steer_angle, delta_deg))

        # 归一化到 CARLA 的 [-1, 1] 范围
        steer = delta_deg / self.max_steer_angle

        return steer

    def get_debug_info(self, target_location: carla.Location,
                       vehicle_transform: carla.Transform) -> dict:
        """返回调试信息 (用于数据记录)"""
        yaw = vehicle_transform.rotation.yaw * (math.pi / 180)
        rear_x = vehicle_transform.location.x - (self.wheelbase / 2) * math.cos(yaw)
        rear_y = vehicle_transform.location.y - (self.wheelbase / 2) * math.sin(yaw)

        dx = target_location.x - rear_x
        dy = target_location.y - rear_y
        lookahead = math.sqrt(dx ** 2 + dy ** 2)
        alpha = math.atan2(dy, dx) - yaw

        return {
            'rear_x': rear_x,
            'rear_y': rear_y,
            'lookahead': lookahead,
            'alpha_rad': alpha,
            'alpha_deg': alpha * 180 / math.pi,
            'steer': self.compute_steering(target_location, vehicle_transform),
        }
