"""
测试数据记录器

功能:
- 每 tick 记录关键指标
- 导出 CSV 格式数据
- 生成测试摘要 JSON
"""

import csv
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import asdict


class TestRecorder:
    """仿真测试数据记录器

    记录每帧的车辆状态和事件, 支持:
    - 实时 CSV 写入
    - JSON 摘要导出
    - 状态历史管理
    """

    def __init__(self, output_dir: str, scenario_name: str = "unknown"):
        self.output_dir = output_dir
        self.scenario_name = scenario_name
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(output_dir, exist_ok=True)

        # 时序数据缓冲
        self.records: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []

        # 场景元数据
        self.metadata: Dict[str, Any] = {
            'scenario': scenario_name,
            'session_id': self.session_id,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'total_ticks': 0,
            'result': 'unknown',
        }

    def record_tick(self, tick: int, timestamp: float,
                    speed: float, location_x: float, location_y: float,
                    control_mode: str, collision: bool, lane_invasion: bool,
                    **extra) -> None:
        """记录一帧数据"""
        record = {
            'tick': tick,
            'timestamp': timestamp,
            'speed_ms': round(speed, 2),
            'location_x': round(location_x, 2),
            'location_y': round(location_y, 2),
            'control_mode': control_mode,
            'collision': collision,
            'lane_invasion': lane_invasion,
            **extra,
        }
        self.records.append(record)
        self.metadata['total_ticks'] = tick

    def record_event(self, event_type: str, timestamp: float,
                     detail: str = "", **extra) -> None:
        """记录一个事件 (碰撞, 避障触发, 换道完成等)"""
        event = {
            'type': event_type,
            'timestamp': timestamp,
            'detail': detail,
            **extra,
        }
        self.events.append(event)

    def set_result(self, result: str, reason: str = ""):
        """设置测试结果"""
        self.metadata['result'] = result
        self.metadata['result_reason'] = reason
        self.metadata['end_time'] = datetime.now().isoformat()
        self.metadata['elapsed_seconds'] = (
            self.records[-1]['timestamp'] - self.records[0]['timestamp']
            if len(self.records) >= 2 else 0
        )

    def save_csv(self) -> str:
        """保存 CSV 数据文件"""
        if not self.records:
            return ""

        filename = f"{self.session_id}_{self.scenario_name}.csv"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.records[0].keys())
            writer.writeheader()
            writer.writerows(self.records)

        print(f"数据已保存: {filepath} ({len(self.records)} 条记录)")
        return filepath

    def save_summary(self) -> str:
        """保存 JSON 摘要"""
        filename = f"{self.session_id}_{self.scenario_name}_summary.json"
        filepath = os.path.join(self.output_dir, filename)

        # 计算统计指标
        speeds = [r['speed_ms'] for r in self.records]
        collision_count = sum(1 for r in self.records if r['collision'])
        avoidance_ticks = sum(1 for r in self.records if r['control_mode'] == 'pure_pursuit')

        summary = {
            **self.metadata,
            'statistics': {
                'max_speed_ms': max(speeds) if speeds else 0,
                'min_speed_ms': min(speeds) if speeds else 0,
                'avg_speed_ms': sum(speeds) / len(speeds) if speeds else 0,
                'collision_events': collision_count,
                'lane_invasion_events': sum(1 for r in self.records if r['lane_invasion']),
                'avoidance_ticks': avoidance_ticks,
                'avoidance_ratio': avoidance_ticks / len(self.records) if self.records else 0,
            },
            'events': self.events,
        }

        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"摘要已保存: {filepath}")
        return filepath

    def get_statistics(self) -> Dict[str, Any]:
        """返回统计指标字典"""
        if not self.records:
            return {}
        speeds = [r['speed_ms'] for r in self.records]
        return {
            'num_records': len(self.records),
            'max_speed_ms': max(speeds),
            'min_speed_ms': min(speeds),
            'avg_speed_ms': sum(speeds) / len(speeds),
            'num_collisions': sum(1 for r in self.records if r['collision']),
            'num_lane_invasions': sum(1 for r in self.records if r['lane_invasion']),
            'num_events': len(self.events),
        }
