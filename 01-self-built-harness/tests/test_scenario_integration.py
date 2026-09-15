"""
CARLA 集成测试 — 需要运行中的 CARLA server

与 `test_pure_pursuit.py`（纯单元测试，不需要 CARLA）不同，本文件通过 conftest
提供的 CARLA fixtures 真实连接仿真器：

    carla_client / carla_world / ego_spawn_point /
    vehicle_blueprint / obstacle_blueprint / carla_actors

**未安装 CARLA 或未启动 server 时，这些测试会自动 skip，不会导致失败。**

运行方式：

    export CARLA_EGG="/path/to/carla-0.9.11-py3.7-linux-x86_64.egg"
    ./CarlaUE4.sh -opengl &          # 另开终端启动 server
    pytest tests/test_scenario_integration.py -v
"""


class TestCarlaConnection:
    """连接与配置一致性"""

    def test_world_has_map(self, carla_world):
        """连上的世界应当有有效地图"""
        assert carla_world.get_map().name

    def test_spawn_point_is_valid(self, ego_spawn_point):
        """生成点应当落在可用的高度上"""
        assert ego_spawn_point is not None
        assert ego_spawn_point.location.z >= -1.0

    def test_ego_blueprint_matches_config(self, vehicle_blueprint, config):
        """取到的蓝图应当与 config 中声明的车型一致"""
        model = config['ego_vehicle']['model']
        assert model in vehicle_blueprint.id, (
            f"config 声明 {model}，实际取到 {vehicle_blueprint.id}"
        )

    def test_obstacle_blueprint_is_vehicle(self, obstacle_blueprint):
        """障碍物蓝图应当是车辆类型"""
        assert 'vehicle' in obstacle_blueprint.id


class TestActorLifecycle:
    """actor 的创建与自动清理"""

    def test_spawn_and_auto_cleanup(self, carla_world, vehicle_blueprint,
                                    ego_spawn_point, carla_actors):
        """spawn 的 actor 应当存活，并在测试结束后由 carla_actors 自动销毁"""
        actor = carla_world.spawn_actor(vehicle_blueprint, ego_spawn_point)
        carla_actors.append(actor)

        assert actor.is_alive
        assert actor.get_transform() is not None
