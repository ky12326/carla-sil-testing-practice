# carla_simAvoidance 原版代码分析报告

> 分析日期: 2026-08-10 | 分析者: SIL 仿真测试学习项目

---

## 代码度量

| 文件 | 行数 | 全局变量 | 已知Bug |
|------|------|---------|---------|
| carla_da_static.py | 207 | 4 (actor_list, collision_flag, is_avoiding, target_lane) + vehicle | 6 |
| carla_da_dynamic.py | 188 | 同上 | 6 |
| carla_da_dynamic_with_camera.py | 245 | 同上 | 7 |
| util/camera.py | 128 | 4 (Front, Rear, Left, Right) | 1 |
| util/recorder.py | 0 | 空文件(TODO) | - |

**总计**: 768 行 Python，其中 ~650 行为重复逻辑

---

## Bug 清单

### BUG-001: collision_flag 死锁 (🔴 Critical)

**位置**: 所有三个主文件的 `callback()` 函数
**问题**: 
- `collision_flag` 设为 True 后永不重置
- 更严重的是: callback 中的 `vehicle.apply_control(brake=1.0)` 是一次性的，下一个 tick 主循环会覆盖刹车指令
- 也就是说碰撞检测**实际上不生效**

**修复**: 
1. 主循环中检查 `collision_flag`，碰撞后执行紧急停车逻辑
2. 添加碰撞恢复机制（碰撞后 3 秒尝试重新行驶，或直接终止场景）

### BUG-002: 全局变量污染 (🟡 Medium)

**位置**: 所有三个主文件顶部
**问题**: `actor_list`, `collision_flag`, `is_avoiding`, `target_lane`, `vehicle` 均为模块级全局变量
**影响**: 无法在一个进程中运行多个场景；callback 函数与主循环通过全局变量隐式耦合
**修复**: 封装为 `ScenarioRunner` 类，用实例变量替代全局变量

### BUG-003: 障碍物坐标系错误 (🟡 Medium)

**位置**: 所有三个主文件的 `spawn_obstacles()` 函数
**问题**:
```python
obstacle_x = vehicle_location.x + offset_x  # 未考虑车辆朝向!
obstacle_y = vehicle_location.y + offset_y  # 未考虑车辆朝向!
```
代码计算并打印了 `math.radians(vehicle_yaw)` 但从未使用！
**影响**: 当车辆朝向非正东方向（yaw ≠ 0）时，障碍物生成位置错误
**修复**: 使用旋转矩阵将偏移量转换到车辆局部坐标系

### BUG-004: 卡死阈值过敏感 (🟡 Low)

**位置**: 所有三个主文件的主循环
**问题**: `stuck_timer > 5` 在 50Hz 循环中等于 0.1 秒
**影响**: 任何短暂减速都会触发避障，产生大量误报
**修复**: 将阈值提高到 50-100 ticks (1-2 秒)

### BUG-005: Ego 生成点硬编码 (🟡 Medium)

**位置**: 所有三个主文件的 `try` 块
**问题**: `location = carla.Location(x=-15.73557, y=200.606361, z=0.275307)` 是 Town03 特定坐标
**影响**: 换地图后生成位置可能无效
**修复**: 使用 `map.get_spawn_points()` 或将其提取为配置参数

### BUG-006: 摄像头 stop 方法未调用 (🟢 Low)

**位置**: `util/camera.py:127`
**问题**: `cam.stop` 应为 `cam.stop()` — 只访问了方法对象，未实际调用
**影响**: 摄像头传感器可能未正确停止
**修复**: 改为 `cam.stop()`

### BUG-007: 重复代码 (🟡 Medium)

**位置**: 三个主文件
**问题**: `spawn_obstacles()`, `pure_pursuit()`, `destroy_actor()`, `get_new_lane()`, `callback()`, `callback2()` 在三个文件中完全重复
**影响**: 修改一个 bug 需要在三处同步修改
**修复**: 提取公共模块

### BUG-008: 数据记录模块未实现 (🟢 Info)

**位置**: `util/recorder.py`
**问题**: `util/recorder.py` 是 **0 字节空文件**，
设计文档中承诺的"数据记录"能力完全未实现 ——
脚本运行完只往控制台打印，**不产生任何可复核的数据文件**。

**影响**: 无法做量化分析，测试结果不可追溯（R01 基线因此只有控制台观察，
没有逐帧数据）。

**修复**: 实现 `TestRecorder`（CSV + JSON 双输出），即 R02 的重构目标之一。

> ⚠️ **更正**：本条早期版本写作「config.yaml 和 recorder.py 为空」，但实测
> `config.yaml` 是 **364 字节的非空文件**（含 `map: 'Town05'`、
> `egoCar_spawn_point`、`control.base_speed` 等），真正缺失的实现只有 recorder。
> 此外该项目自身的 config 与代码不一致：config 声明 Town05，
> 而代码里的硬编码生成点是 Town03 专用的。

---

## 代码质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 功能可用性 | ⭐⭐⭐ | 基本功能可用，但有致命 Bug |
| 代码可读性 | ⭐⭐⭐⭐ | 中文注释清晰，结构简单 |
| 可扩展性 | ⭐ | 全局变量 + 重复代码，难以扩展 |
| 可测试性 | ⭐ | 无测试框架，无法自动化 |
| 配置管理 | ⭐⭐ | 有 config.yaml 但代码未读取，参数仍硬编码在源码里 |
| 数据记录 | ⭐ | recorder.py 为 0 字节空文件，无任何数据产出 |

**综合**: 这是一个"能跑"的教学项目，但距离工程化标准差距很大——这正是我们重构的价值所在。
