"""静态障碍物避障场景"""

from scenarios.base_scenario import BaseScenario


class StaticObstacleScenario(BaseScenario):
    """静态障碍物避障场景

    验证: ego 车辆遇到前方静止障碍物时,
    Pure Pursuit 控制器接管并完成换道避障。
    """

    def _setup_scenario(self):
        cfg = self.config['static_scenario']
        self.obstacle_mgr.spawn_static_obstacles(
            ego_vehicle=self.ego.vehicle,
            num_obstacles=cfg['num_obstacles'],
            distance=cfg['distance'],
            spacing=cfg['spacing'],
            lateral_offsets=cfg.get('lateral_offsets'),
        )
        msg = f"已生成 {cfg['num_obstacles']} 个静态障碍物, 距离={cfg['distance']}m"
        print(msg)
        self.recorder.metadata['scenario_type'] = 'static'
        self.recorder.metadata['config'] = cfg


def run_scenario(config_path: str = None, max_duration: float = None):
    """便捷入口"""
    scenario = StaticObstacleScenario(config_path)
    return scenario.run(max_duration)


if __name__ == '__main__':
    result = run_scenario()
    print(f"Result: success={result.success}, collisions={result.collision_count}")
