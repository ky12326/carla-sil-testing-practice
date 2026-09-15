"""动态障碍物跟车/超车场景"""

from scenarios.base_scenario import BaseScenario


class DynamicObstacleScenario(BaseScenario):
    """动态障碍物跟车/超车场景

    验证: ego 车辆跟随前方动态障碍物时,
    保持安全距离, 必要时换道超车。
    """

    def _setup_scenario(self):
        cfg = self.config['dynamic_scenario']
        self.obstacle_mgr.spawn_dynamic_obstacles(
            ego_vehicle=self.ego.vehicle,
            num_obstacles=cfg['num_obstacles'],
            distance=cfg['distance'],
            spacing=cfg['spacing'],
            speeds=cfg.get('speeds'),
            lateral_offsets=cfg.get('lateral_offsets'),
        )
        msg = f"已生成 {cfg['num_obstacles']} 个动态障碍物, 距离={cfg['distance']}m"
        print(msg)
        self.recorder.metadata['scenario_type'] = 'dynamic'
        self.recorder.metadata['config'] = cfg


def run_scenario(config_path: str = None, max_duration: float = None):
    """便捷入口"""
    scenario = DynamicObstacleScenario(config_path)
    return scenario.run(max_duration)


if __name__ == '__main__':
    result = run_scenario()
    print(f"Result: success={result.success}, collisions={result.collision_count}")
