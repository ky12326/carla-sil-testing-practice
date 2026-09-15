"""
Pure Pursuit 控制器 — 单元测试

**这些测试完全不依赖 CARLA**：
`src/pure_pursuit.py` 只在类型注解里提到 `carla`（已用 TYPE_CHECKING 守卫），
测试侧用下面三个本地 dataclass 替代 `carla.Location` / `Rotation` / `Transform`。
因此本文件在任何 Python 3.8+ 环境都能运行，无需安装 CARLA、无需启动 server。
"""

from dataclasses import dataclass

import pytest

from src.pure_pursuit import PurePursuitController


# --- CARLA 类型的本地替身 ----------------------------------------------------
# pure_pursuit 只读取 location.x/.y 与 rotation.yaw，其余字段保持默认即可。

@dataclass
class Location:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Rotation:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0


@dataclass
class Transform:
    location: Location
    rotation: Rotation


def make_transform(x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> Transform:
    """构造车辆位姿（默认原点、朝向 +X）"""
    return Transform(Location(x=x, y=y), Rotation(yaw=yaw))


# --- fixture -----------------------------------------------------------------

@pytest.fixture
def controller(config):
    """按 config/default.yaml 的 pure_pursuit 段构造控制器。

    参数取自配置文件而非写死，这样测试与仿真运行时用的是同一组参数。
    """
    pp_cfg = config['pure_pursuit']
    return PurePursuitController(
        wheelbase=pp_cfg['wheelbase'],
        max_steer_angle=pp_cfg['max_steer_angle'],
    )


# --- 转向计算 ----------------------------------------------------------------

class TestPurePursuitSteering:
    """Pure Pursuit 转向计算测试"""

    def test_target_straight_ahead(self, controller):
        """目标在正前方: 转向角应为 0"""
        steer = controller.compute_steering(
            Location(x=10, y=0), make_transform()
        )
        assert steer == pytest.approx(0.0, abs=0.01), f"正前方目标应该返回 steer≈0, 实际: {steer}"

    def test_target_to_the_right(self, controller):
        """目标在右前方: 应该右转 (steer > 0)"""
        steer = controller.compute_steering(
            Location(x=10, y=5), make_transform()
        )
        assert steer > 0, f"右前方目标应该右转 (steer > 0), 实际: {steer}"

    def test_target_to_the_left(self, controller):
        """目标在左前方: 应该左转 (steer < 0)"""
        steer = controller.compute_steering(
            Location(x=10, y=-5), make_transform()
        )
        assert steer < 0, f"左前方目标应该左转 (steer < 0), 实际: {steer}"

    def test_steer_within_bounds(self, controller):
        """随机位姿下转向角应始终落在 [-1, 1]"""
        import random
        random.seed(42)
        for _ in range(100):
            transform = make_transform(
                x=random.uniform(-100, 100),
                y=random.uniform(-100, 100),
                yaw=random.uniform(-180, 180),
            )
            target = Location(x=random.uniform(0, 50), y=random.uniform(-20, 20))
            steer = controller.compute_steering(target, transform)
            assert -1.0 <= steer <= 1.0, f"steer={steer} 超出范围 [-1, 1]"

    @pytest.mark.parametrize("wheelbase", [2.0, 2.875, 3.5])
    def test_different_wheelbases(self, controller, wheelbase):
        """不同轴距下转向角都应该在合法范围内"""
        pp = PurePursuitController(
            wheelbase=wheelbase, max_steer_angle=controller.max_steer_angle
        )
        steer = pp.compute_steering(Location(x=10, y=3), make_transform())
        assert -1.0 <= steer <= 1.0, f"wheelbase={wheelbase}: steer={steer}"

    def test_vehicle_facing_south_target_east(self, controller):
        """车辆朝南 (yaw=90), 目标在东 (+X): 应该左转 (steer < 0)

        CARLA 坐标系: yaw=0 朝 +X (东), yaw=90 朝 +Y (南)。
        """
        steer = controller.compute_steering(
            Location(x=10, y=0), make_transform(yaw=90)
        )
        assert steer < 0, f"车辆朝南, 目标在东, 应该左转, 实际 steer={steer}"

    def test_zero_distance_target(self, controller):
        """目标与车辆重合: 不应崩溃，返回 0"""
        steer = controller.compute_steering(Location(), make_transform())
        assert steer == 0.0, f"目标在原点应该返回 0, 实际: {steer}"


class TestPurePursuitEdgeCases:
    """Pure Pursuit 边界情况测试"""

    def test_far_target(self, controller):
        """极远目标: 转向角应很小"""
        steer = controller.compute_steering(
            Location(x=1000, y=10), make_transform()
        )
        assert abs(steer) < 0.1, f"极远目标转向角应很小, 实际: {steer}"

    def test_negative_coordinates(self, controller):
        """负坐标应正常工作"""
        steer = controller.compute_steering(
            Location(x=-45, y=-25), make_transform(x=-50, y=-30, yaw=45)
        )
        assert -1.0 <= steer <= 1.0
