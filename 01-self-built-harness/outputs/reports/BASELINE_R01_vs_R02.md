# 重构前后对比报告：原版（R01）vs 重构版（R02）

> 日期: 2026-08-10
>
> **数据来源**：R02 侧的数字均有 `outputs/data/` 下的 CSV / JSON 佐证，可逐条核对；
> R01 侧的数字来自控制台观察，无逐帧数据（R01 时 recorder 尚未实现），
> 相关条目已标注 ⚠️。

---

## 关键指标对比

| 指标 | 原版 (R01) | 重构版 (R02) | 说明 |
|------|-----------|-------------|------|
| 代码规模 | 768 行 / 3 个近乎重复的文件 | 1097 行模块化实现 + 314 行测试 | 见下方说明 |
| 全局变量 | 8 个 | **0 个** | 全部收敛进 `EgoVehicle` / `ObstacleManager` / `TestRecorder` |
| Pure Pursuit 单元测试 | 无 | **11 个**（不依赖 CARLA） | 实测全绿，见 README |
| 碰撞检测有效性 | 形同虚设（刹车只生效 1 tick） | 冷却 3s + 累计 3 次碰撞退出 | 有 FAIL 运行记录佐证 |
| 振荡问题 | ⚠️ 13 次循环 / 35s | **4 次 / 35s** | R02 侧有 events 数组佐证 |
| 配置管理 | 硬编码 | YAML 配置驱动 | `config/default.yaml` |
| 数据记录 | `util/recorder.py` 是 0 字节空文件 | CSV + JSON 自动导出 | 3 组数据共 3811 行 |
| 坐标系 Bug | 存在（算了 yaw 却未使用） | 已修复（旋转矩阵） | `obstacle_manager.py` |
| 测试可复现性 | 不支持（无种子） | 固定种子（`runtime.seed`） | 见下方「本次补充修复」 |

### 关于「代码规模」

原始对比表写的是「768 → ~500，-35%」，**这个数字不准确**。

实际统计（`wc -l`）：

```
R01: 768 行，分布在 3 个几乎相同的文件里，其中约 650 行是重复的
R02: 1097 行实现（src 691 + scenarios 406） + 314 行测试
```

**行数没有减少，反而增加了。** 但这不是退步：
R01 的 768 行里真正独立的逻辑很少，改一处 bug 要在三个文件里同步改；
R02 把重复收敛为单一实现，多出来的行数是**抽象层次与测试**的成本。
衡量重构质量应该看「重复消除」「可测试性」「缺陷可定位性」，而不是行数增减。

---

## Bug 修复状态

编号体系见 `docs/CODE_ANALYSIS.md`（BUG-00X = 静态代码分析得出）；
`BASELINE_R01.md` 里的 FIND-00X 是运行时观察得出的现象，两套编号并存，同一问题可能同时出现。

| Bug ID | 描述 | 原版严重度 | 状态 |
|--------|------|----------|------|
| BUG-001 | collision_flag 死锁（只置位不复位，主循环不检查） | 🔴 Critical | ✅ 已修复（主循环检查 + 冷却 + 3 次退出） |
| BUG-002 | 全局变量污染 | 🟡 Medium | ✅ 已修复（封装为类） |
| BUG-003 | 障碍物坐标系错误（未用 yaw 做旋转） | 🟡 Medium | ✅ 已修复（旋转矩阵） |
| BUG-004 | 卡死阈值过敏（0.1s） | 🟢 Low | ✅ 已修复（→ 0.5s，写入 YAML） |
| BUG-005 | Ego 生成点硬编码 | 🟡 Medium | ✅ 已修复（随机 / 可配置） |
| BUG-006 | 摄像头 `stop()` 未调用 | 🟢 Low | ✅ 已修复（在 `destroy()` 中） |
| BUG-007 | 三个文件间大量重复代码 | 🟡 Medium | ✅ 已修复（模块化） |
| BUG-008 | 设计文档承诺的参数化与数据记录未实现 | 🟢 Info | ✅ 已实现 |

> **关于 BUG-008 的更正**：原表述为「config.yaml 与 recorder.py 为空」。
> 实测 `util/recorder.py` 确为 **0 字节**，但 `upstream/config.yaml` 是 **364 字节的非空文件**
> （含 `map: 'Town05'` 与硬编码生成点）。真正缺失的实现只有 recorder。

---

## 新增能力

- [x] YAML 配置驱动（参数 / 场景 / 天气预设）
- [x] CSV 数据记录（**每帧 9 列**：tick / timestamp / speed / location_x / location_y / control_mode / collision / lane_invasion / is_avoiding）
- [x] JSON 测试摘要（统计 + 事件流）
- [x] 11 个 Pure Pursuit 单元测试 —— **不依赖 CARLA**，任何 Python 3.8+ 环境可跑
- [x] 避障冷却机制（防止振荡）
- [x] 碰撞冷却机制（防止重复触发）
- [x] 固定随机种子（可复现）
- [x] 多种天气预设
- [x] EgoState 状态快照
- [x] pytest fixture 管理 CARLA 生命周期 —— 用于 `tests/test_scenario_integration.py`
      （需运行中的 CARLA server，不可用时自动 skip）

> **关于最后一条的更正**：原表述为「pytest fixture 管理 CARLA 生命周期」并列为已实现能力，
> 但当时的 7 个 fixture **从未被任何测试使用**（`test_pure_pursuit.py` 全部走 `setup_method`）。
> 本次补充了 `tests/test_scenario_integration.py` 真正使用这些 fixture。

---

## 本次补充修复（2026-09-15）

在整理本仓库时，发现三个 R01/R02 遗留问题，已一并修复：

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `summary.json` 的 `lane_invasion_events` 高达 1410/1619（87%），指标失真 | 回调把 `lane_invasion_flag` 置 True 后**从不复位**，主循环每 tick 都计入 | 新增 `reset_lane_invasion_flag()`，读后即复位 |
| 2 | `config/default.yaml` 的 `cooldown_seconds` **从未生效** | 代码里写死为类常量（避障 5.0，与 YAML 的 3.0 不一致） | 改为构造参数并读取 YAML；**YAML 对齐 5.0**（该值才是产出「4 次/35s」的真实值） |
| 3 | 同一份 config 两次运行结果不一致（一次 3 次碰撞 FAIL，一次 35s PASS） | `spawn_index: null` 时走 `random.choice`，全程无 `random.seed()` | `runtime.seed: 42` + `setup_ego()` 中播种 |

修复后的实测数据见 README「测试流程与发现」一节。
