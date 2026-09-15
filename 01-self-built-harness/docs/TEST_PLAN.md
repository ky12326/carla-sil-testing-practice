# carla_simAvoidance — 仿真测试计划（设计草案）

> **项目**: 基于 CARLA 的混合控制避障测试
> **被测系统**: CARLA Autopilot + Pure Pursuit 手动控制
> **文档版本**: v1.0-draft | 2026-08-10
>
> ⚠️ **本文档是测试设计草案，矩阵中的绝大部分用例并未执行。**
> 实际执行的只有 3 次运行（1 次静态 + 2 次动态），
> 结果见 [`../outputs/reports/`](../outputs/reports/) 与 [`../outputs/data/`](../outputs/data/)。
> 保留本文档是为了记录测试设计思路（维度覆盖与判定标准），而不是宣称已完成的覆盖度。

---

## 1. 测试目标

验证「Autopilot 正常行驶 + Pure Pursuit 换道避障」混合控制策略的：

- **功能正确性**: 遇到障碍物时是否成功切换控制模式并换道
- **安全性**: 是否发生碰撞
- **稳定性**: 长时间运行是否稳定
- **性能指标**: 避障成功率、碰撞间隔（具体阈值待定，见 §4）

> 注：原始版本此处写「避障成功率 >85%, 碰撞间隔 >120s」，
> 但那两个数字抄自上游项目 README 的宣称值，并非本项目的实测基线。
> R01 基线实测碰撞率为 0%，成功率相关指标见 `outputs/reports/BASELINE_R01.md`。

---

## 2. 被测系统 (SUT) 描述

### 控制架构

```
正常行驶 → CARLA Autopilot (set_autopilot(True))
    ↓ (检测到卡死: speed < 速度阈值, 持续 > N ticks)
换道避障 → Pure Pursuit 控制器 (手动 throttle + steer)
    ↓ (换道完成)
正常行驶 → CARLA Autopilot
```

### 实际参数（取自 `config/default.yaml`）

| 参数 | 实际值 | 说明 |
|------|-------|------|
| `pure_pursuit.wheelbase` | 2.875 m | 车辆轴距 |
| `pure_pursuit.max_steer_angle` | 45.0° | 最大转向角 |
| `stagnation.speed_threshold` | 2.5 m/s | 卡死检测速度阈值 |
| `stagnation.tick_threshold` | **25** ticks（50 Hz 下 = 0.5 s） | 原版为 5 ticks（0.1 s），过于敏感，已修复 |

> ⚠️ **更正**：本文档早期版本列有 `lookahead_distance (ld) = 10.0 m` 一项，
> 但 `PurePursuitController` **没有这个参数** —— 前视距离是每帧按目标点实时算出的
> （见 `src/pure_pursuit.py` 中的 `lookahead`）。该行系误记，已删除。

---

## 3. 测试场景矩阵（设计，未执行）

### 3.1 静态障碍物场景 (Static)

```
场景: ego 车行驶在直道上, 前方 N 辆车静止停放
成功标准: ego 减速 → 检测卡死 → 切换 Pure Pursuit → 换道 → 恢复 autopilot → 无碰撞
```

| 用例ID | 障碍物数量 | 间距(m) | 横向偏移(m) | 天气 | 地图 | 执行 |
|--------|----------|---------|------------|------|------|------|
| STAT-001 | 1 | 20 | 0 | ClearNoon | — | ❌ |
| STAT-002 | 3 | 30 | 0 | ClearNoon | — | ✅ 对应实际运行 |
| STAT-003 | 5 | 30 | 0 | ClearNoon | — | ❌ |
| STAT-004 | 3 | 10 | 0 | ClearNoon | — | ❌ |
| STAT-005 | 3 | 40 | 0 | ClearNoon | — | ❌ |
| STAT-006 | 3 | 30 | 2 | ClearNoon | — | ❌ |
| STAT-007 | 3 | 30 | 0 | WetNoon | — | ❌ |
| STAT-008 | 3 | 30 | 0 | Night | — | ❌ |
| STAT-009 | 3 | 30 | 0 | ClearNoon | 其他地图 | ❌ |
| STAT-010 | 3 | 30 | 0 | ClearNoon | 其他地图 | ❌ |

> 「地图」列原填 Town03/Town01/Town02。实际运行的加载地图未在本项目中核实，
> 且上游 `config.yaml` 声明为 `Town05` 而代码中的硬编码坐标是 Town03 专用的
> （上游自身配置与代码不一致），故此处不填写具体地图名。

### 3.2 动态障碍物场景 (Dynamic)

```
场景: ego 车跟随前方 N 辆移动的障碍车
成功标准: 保持安全距离 / 必要时换道超车 / 无碰撞
```

| 用例ID | 障碍物数量 | 前车速度(km/h) | 天气 | 执行 |
|--------|----------|---------------|------|------|
| DYN-001 | 1 | 20 | ClearNoon | ❌ |
| DYN-002 | 1 | 40 | ClearNoon | ❌ |
| DYN-003 | 1 | 60 | ClearNoon | ❌ |
| DYN-004 | 2 | 30 | ClearNoon | ✅ 对应实际运行 |
| DYN-005 | 2 | 50 | ClearNoon | ❌ |
| DYN-006 | 1 | 40 | WetNoon | ❌ |
| DYN-007 | 1 | 40 | ClearNoon | ❌ |

### 3.3 边界/异常场景 (Edge Cases)

| 用例ID | 场景描述 | 预期行为 | 执行 |
|--------|---------|---------|------|
| EDGE-001 | 两侧均有障碍物，无换道空间 | ego 减速至停车，不碰撞 | ❌ |
| EDGE-002 | 弯道中的静态障碍物 | 合理减速或换道 | ❌ |
| EDGE-003 | 障碍物在 ego 后方 | 无影响，正常行驶 | ❌ |
| EDGE-004 | 多障碍物连续障碍 | 连续换道或停车 | ❌ |

---

## 4. 通过/失败标准 (Pass/Fail Criteria)

| ID | 指标 | 通过标准 | 严重级别 | 备注 |
|----|------|---------|---------|------|
| PF-01 | 无碰撞 | `collision_count == 0` | 🔴 Critical | 一次碰撞即失败 |
| PF-02 | 换道成功 | `lane_changed == True` | 🔴 Critical | 检测到卡死后 5s 内换道 |
| PF-03 | Pure Pursuit 激活 | `control_switch_count > 0` | 🟡 Warning | 避障功能是否触发 |
| PF-04 | 运行稳定性 | 无 crash、无 exception | 🔴 Critical | 程序不应异常退出 |
| PF-05 | 最小跟车距离 | > 2 m（动态场景） | 🟡 Warning | 安全距离保障 |

> 原版本的 PF-04（碰撞间隔 >120s）与 PF-07（预测轨迹偏差 <0.5m）已移除：
> 前者是抄自上游的宣称值，后者所需的轨迹预测数据本项目从未采集。

---

## 5. 执行记录

### 5.1 实际执行情况

**本矩阵共设计 21 个用例，实际执行 3 次运行**（均使用 R02 代码）：

| 场景 | 运行 | 结果 | 数据文件 |
|------|------|------|---------|
| 静态障碍物 | 1 次 | PASS | `outputs/data/20260810_214906_StaticObstacleScenario.*` |
| 动态障碍物 | 1 次 | FAIL（3 次碰撞，14.2 s） | `outputs/data/20260810_215036_DynamicObstacleScenario.*` |
| 动态障碍物 | 1 次 | PASS（35.0 s） | `outputs/data/20260810_215153_DynamicObstacleScenario.*` |

> 两次动态运行的差异不是代码变化，而是**场景随机性**（当时无随机种子）——
> 这正是 FIND-003 / 本次补充修复 #3 要解决的问题。修复后同一配置可复现。

### 5.2 缺陷记录

代码缺陷清单见 [`CODE_ANALYSIS.md`](CODE_ANALYSIS.md)（BUG-001~008），
修复状态见 [`../outputs/reports/BASELINE_R01_vs_R02.md`](../outputs/reports/BASELINE_R01_vs_R02.md)。

> 本文档早期版本此处列了 4 条 BUG 且状态全为 `Open`，与实际情况不符
> （8 条 BUG 在 R02 中均已修复）。为避免两处记录互相矛盾，此处改为指针。

---

## 6. 运行命令

```bash
# 1. 安装 Python 依赖（无需 CARLA，纯单元测试可在此步之后直接运行）
pip install -r requirements.txt

# 2. 纯单元测试（不需要 CARLA server）
pytest tests/ -v

# 3. 需要 CARLA 的部分：指定 PythonAPI 路径并启动 server
export CARLA_EGG="/path/to/carla-0.9.11-py3.7-linux-x86_64.egg"
"$CARLA_ROOT/CarlaUE4.sh" -opengl -nosound -quality-level=Low &
pytest tests/test_scenario_integration.py -v     # CARLA 不可用时自动 skip

# 4. 运行一次完整场景（需 CARLA server 已启动）
python -m scenarios.static_obstacle
python -m scenarios.dynamic_obstacle
```
