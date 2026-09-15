# CARLA 仿真测试实践

> **CARLA SIL Testing Practice**
>
> 一次完整的 SIL 仿真测试练习：基线运行 → 缺陷定位 → 重构 → 单元测试 → 回归对比；
> 另附对 CARLA 官方测试工具链（ScenarioRunner / Leaderboard）的学习记录。

---

## 这是什么

本仓库记录我在 CARLA 0.9.11 上做的一次仿真测试练习，分两阶段：

### 阶段一：自建测试框架与缺陷定位 —— `01-self-built-harness/`

以一个开源避障项目为**被测系统**，完整走一遍 SIL 测试流程：

```
R01 基线运行（不改任何代码，只观察）
  → 逐帧核对运行日志 + 静态代码分析
  → 识别 6 项运行时异常（FIND）+ 8 类代码缺陷（BUG）
  → R02 重构：分层架构 + YAML 参数化 + 数据记录
  → 11 个单元测试（不依赖 CARLA）
  → 回归对比
```

**为什么选一个"简单"的项目**：复杂项目里缺陷容易被复杂度掩盖，
用一个规模可控的避障项目，才能把「现象 → 定位 → 根因 → 修复 → 复测」
这条链路干净地走完。这个练习的重点是流程，不是算法难度。

### 阶段二：官方工具链的学习 —— `02-industry-toolchain/`

搭建 CARLA 官方 ScenarioRunner + Leaderboard，阅读源码理解 OpenSCENARIO
场景描述格式与 Driving Score 评测逻辑，并写了一个跟车安全性测试脚本。

> **范围说明**：阶段二以「理解工具链」为主，产出一个测试脚本 + 学习笔记。
> **没有**做「自建指标 vs Driving Score」的对标实验 —— 那需要两侧跑同一批场景
> 并对照评分，本次未完成，本仓库不作此声称。

---

## 开发方式

本仓库的代码实现由 AI 编程助手（Claude Code）完成；测试用例与场景矩阵的设计、
缺陷的定位与验证、重构方案的取舍由本人完成。

---

## 目录结构

```
├── 01-self-built-harness/          # 阶段一：自建框架
│   ├── src/                        # R02 重构产物（环境 / 车辆 / 障碍物 / 记录器）
│   ├── scenarios/                  # 场景基类与静态、动态两个场景
│   ├── tests/                      # 11 个单元测试 + CARLA 集成测试
│   ├── config/default.yaml         # 参数配置
│   ├── outputs/data/               # 3 组运行的 CSV + JSON（回归证据）
│   ├── outputs/reports/            # R01 基线报告 + R01/R02 对比报告
│   ├── docs/                       # 缺陷清单（CODE_ANALYSIS）+ 测试计划草案
│   └── baseline-r01/               # 被测系统的原始代码与来源说明
├── 02-industry-toolchain/          # 阶段二：工具链学习
│   ├── follow_vehicle_test.py      # 跟车安全性测试脚本
│   └── notes-toolchain.md          # 工具链学习笔记
├── activate_env.sh                 # 环境配置脚本（不写死任何本机路径）
└── requirements.txt
```

---

## 环境准备

### 纯单元测试（不需要 CARLA）

```bash
pip install -r requirements.txt
cd 01-self-built-harness && pytest tests/ -v
```

11 个用例全绿，端到端约 0.1 秒。**无需安装 CARLA、无需启动仿真器。**

### 需要 CARLA 的部分

```bash
# 在仓库根目录执行
export CARLA_ROOT=/path/to/CARLA_0.9.11
source activate_env.sh              # 自动定位 carla-*.egg 并配置 PYTHONPATH

# 另开终端启动仿真器
"$CARLA_ROOT/CarlaUE4.sh" -opengl
```

然后按需运行（`scenarios` 包内的导入是绝对的，**需在 `01-self-built-harness/` 目录下执行**）：

```bash
cd 01-self-built-harness

# 集成测试（CARLA 不可用时自动 skip，不会失败）
pytest tests/test_scenario_integration.py -v

# 跑一次完整场景，结果写入 outputs/
python -m scenarios.static_obstacle
python -m scenarios.dynamic_obstacle
```

阶段二的跟车测试**不依赖本仓库的其他模块**，可在任意目录运行：

```bash
python 02-industry-toolchain/follow_vehicle_test.py
```

---

## 测试流程与发现

### 流程

| SIL 环节 | 本项目的做法 |
|---|---|
| 需求分析 | 从上游 README 提取功能与性能指标 |
| 测试策划 | 设计 21 个用例的场景矩阵（**设计草案，实际执行 3 次**，见 `docs/TEST_PLAN.md`） |
| 场景设计 | YAML 配置驱动的静态 / 动态障碍物场景 |
| 用例开发 | 11 个 Pure Pursuit 单元测试 + CARLA 集成测试 |
| 仿真执行 | CARLA server + 逐帧控制循环 |
| 数据采集 | `TestRecorder` 输出 CSV（每帧 9 列）+ JSON 摘要 |
| 结果分析 | 基线报告 + 重构对比报告 |
| 缺陷报告 | 8 类代码缺陷的定位→分析→修复（见下表） |
| 回归验证 | 重构后复测，振荡由 13 次降至 4 次 |

### R01 基线发现的缺陷

**运行时观察（FIND）** —— 详细分析见 [`outputs/reports/BASELINE_R01.md`](01-self-built-harness/outputs/reports/BASELINE_R01.md)：

| ID | 现象 | 严重度 |
|---|---|---|
| FIND-001 | Pure Pursuit 在 35 s 内触发 13 次「开始绕行→完成」循环，实际没有解决动态障碍 | 🔴 |
| FIND-002 | 静态场景前两次运行 autopilot 直接绕过障碍，Pure Pursuit 从未触发 —— 项目宣称的避障率主要是 autopilot 的功劳 | 🟡 |
| FIND-003 | 3 次运行触发次数 0/0/2，行为不一致（无随机种子） | 🟡 |
| FIND-004 | 速度归零但 `collision_flag` 仍为 False | 🟢 |
| FIND-005 | `collision_flag` 在回调中置位，但主循环从不检查 —— 刹车只生效 1 tick | 🔴 |
| FIND-006 | 硬编码生成点在该地图下导致 spawn 失败 | 🟡 |

**代码缺陷（BUG）** —— 详细分析见 [`docs/CODE_ANALYSIS.md`](01-self-built-harness/docs/CODE_ANALYSIS.md)：

| ID | 缺陷 | 根因 | 严重度 |
|---|---|---|---|
| BUG-001 | 碰撞检测实际不生效 | flag 只置位不复位 + 主循环不检查 + 刹车被下一帧覆盖 | 🔴 |
| BUG-002 | 全局变量污染，无法并发跑多场景 | 5 个模块级全局变量 + 回调隐式耦合 | 🟡 |
| BUG-003 | 障碍物生成位置在车辆非正东朝向时错误 | 算了 yaw 却从未参与坐标变换 | 🟡 |
| BUG-004 | 任何短暂减速都误触发避障 | `stuck_timer > 5` @50 Hz = 0.1 s | 🟢 |
| BUG-005 | 换地图后 ego 生成失败 | 硬编码 Town03 专用坐标 | 🟡 |
| BUG-006 | 摄像头传感器未正确停止 | `cam.stop` 缺括号，只取到方法对象 | 🟢 |
| BUG-007 | 改一处 bug 要在三个文件同步改 | 三个主脚本约 650 行重复逻辑 | 🟡 |
| BUG-008 | 无任何数据产出 | `util/recorder.py` 是 0 字节空文件 | 🟢 |

> **关于编号**：FIND 是「跑起来看到什么」，BUG 是「读代码看出什么」，是两套并行体系，
> 同一问题可能同时出现（如 FIND-005 与 BUG-001）。文档中已说明，避免误读为矛盾。

---

## 数据与结果

`01-self-built-harness/outputs/data/` 下有三组运行的完整数据（CSV + JSON 摘要）：

| 运行 | 场景 | 结果 | 耗时 |
|---|---|---|---|
| `20260810_214906` | 静态障碍物 | PASS | 达到 30 s 上限 |
| `20260810_215036` | 动态障碍物 | **FAIL**（3 次碰撞） | 14.2 s |
| `20260810_215153` | 动态障碍物 | PASS | 35.0 s |

> 两次动态运行结果不同，**不是代码变化，而是场景随机性**（当时无随机种子）——
> 这正是 FIND-003 与下方「本次补充修复」第 3 条要解决的问题。

**重构前后对比**（详见 [`outputs/reports/BASELINE_R01_vs_R02.md`](01-self-built-harness/outputs/reports/BASELINE_R01_vs_R02.md)）：

| 指标 | R01 | R02 |
|---|---|---|
| 全局变量 | 8 个 | 0 个 |
| 单元测试 | 无 | 11 个（不依赖 CARLA） |
| 数据产出 | 无（recorder 为空文件） | 3 组 CSV + JSON |
| 振荡 | ⚠️ 13 次 / 35 s | **4 次 / 35 s** |
| 可复现性 | 无种子，同配置两次结果不同 | 固定种子 |

> ⚠️ 「13 次」由控制台计数得出，**无逐帧数据佐证** —— R01 时 recorder 尚未实现。
> R02 侧的「4 次」有 JSON 的 events 数组可逐条核对。

---

## 本次补充修复

整理本仓库时发现并修复了三个遗留问题（详见对比报告末节）：

| # | 问题 | 修复 |
|---|---|---|
| 1 | `lane_invasion_events` 指标失真（1410/1619，87%）—— 标志位读取后从不复位 | 新增 `reset_lane_invasion_flag()`，读后即复位 |
| 2 | `config/default.yaml` 的 `cooldown_seconds` **从未生效**（代码里是写死的类常量，且与 YAML 值不一致） | 改为构造参数并读取 YAML；YAML 对齐 5.0（该值是产出「4 次/35 s」的真实值） |
| 3 | 同一份配置两次运行结果不同 | `runtime.seed: 42` + 启动时播种 |

> 修复 1 与 3 的**实测验证需要重跑场景**（需 CARLA server），本仓库未附带修复后的运行数据。
> 修复 2 属配置接线，不改变既有产物的解释。

---

## 已知限制

- **测试矩阵的执行覆盖率低** —— 设计了 21 个用例，实际只跑了 3 次；
  天气预设与其他地图的组合从未执行
- **R01 基线数据无逐帧记录** —— 当时 recorder 尚未实现，基线数字来自控制台观察，
  仅 R02 侧的数据可逐条核对
- **阶段二未完成对标** —— 跟车测试脚本不依赖 ScenarioRunner（是裸 CARLA API），
  与官方工具链是脱钩的；脚本也不落盘，当时的运行结果未保存
- **Leaderboard 评测未跑通** —— 当时只启动了 evaluator，结果停在空检查点
  （`progress: [0,4]`、`records: []`），从未完整评测过一个 Agent

---

## English Summary

A hands-on **CARLA SIL testing practice**, in two stages.

**Stage 1 — self-built harness** (`01-self-built-harness/`): treated an open-source
obstacle-avoidance project as the system under test and ran a full SIL workflow —
baseline run without touching the code, frame-by-frame log review plus static code
analysis, 6 runtime findings and 8 code defects identified, refactor into a layered
architecture with YAML-driven config and data recording, 11 unit tests, and a
regression comparison. Oscillation events dropped from 13 to 4 per 35 s run.

**Stage 2 — official toolchain** (`02-industry-toolchain/`): set up CARLA's
ScenarioRunner and Leaderboard, read the source to understand OpenSCENARIO scene
description and the Driving Score formula, and wrote a car-following safety test
script. This stage is about **understanding the toolchain** — no cross-validation
between the self-built metrics and Driving Score was carried out.

The 11 unit tests **do not require CARLA** (the controller module has no runtime
CARLA dependency) and complete in about 0.1 s.

---

## 许可

本仓库按 MIT License 发布。目录 `01-self-built-harness/baseline-r01/upstream-sut/`
下是被测系统的原始代码，属于第三方开源项目，版权归其作者所有，
来源与范围见该目录下的 [PROVENANCE.md](01-self-built-harness/baseline-r01/PROVENANCE.md)。
