# CARLA 官方仿真测试工具链 — 学习笔记

> 2026-08-11 · CARLA 0.9.11 · ScenarioRunner `v0.9.11` · Leaderboard `leaderboard-1.0`
>
> 本文记录我在自建测试框架（见 [`../01-self-built-harness/`](../01-self-built-harness/)）之后，
> 转向 CARLA 官方工具链的学习过程：搭建、跑通、读源码。
>
> **范围说明**：这一阶段以「理解工具链」为主，产出一个跟车测试脚本（见 §4）。
> 没有做「自建指标 vs Driving Score」的对标实验 —— 那需要两侧跑同一批场景并对照评分，
> 本次未完成。本文不声称做过。

---

## 1. 三个东西的关系

| 组件 | 角色 | 一句话 |
|------|------|--------|
| **ScenarioRunner** | 场景执行引擎 | 「演什么」—— 读取 OpenSCENARIO 描述，驱动仿真器把场景跑出来 |
| **Leaderboard** | 标准化评测框架 | 「怎么评」—— 在同一套路线与场景下给不同 Agent 打分 |
| **OpenSCENARIO** | 场景描述格式（ASAM 标准，XML） | 行业通用语言，不同仿真器之间可迁移 |

两者都是 CARLA 官方团队维护的开源工具，工业界的自动驾驶仿真测试大多建立在其之上。

与我自建框架的差别：自建部分是「自己设计指标 + 自己写判定」，
这套工具链提供的是**已经形成行业共识的场景描述格式与评分方法**。

---

## 2. OpenSCENARIO：场景怎么描述

以 CARLA 自带的 `srunner/examples/FollowLeadingVehicle.xosc` 为例，结构分三层：

```
第 1 层: ParameterDeclarations（可调参数）
  └── $leadingSpeed = 2.0 m/s
      运行时可通过 --openscenarioparams leadingSpeed=5.0 覆盖

第 2 层: Entities（参与者 — 场景中有谁）
  ├── hero（ego 车）：vehicle.lincoln.mkz2017，角色 ego_vehicle
  └── adversary（前车）：vehicle.tesla.model3，角色 simulation

第 3 层: Storyboard（剧本 — 怎么演）
  ├── Init：天气、各车初始位置
  ├── Story → Act → Maneuver → Event
  │   ├── Event 1 "LeadingVehicleKeepsVelocity"
  │   │     触发条件：hero 距 adversary < 40 m → adversary 匀速行驶
  │   └── Event 2 "LeadingVehicleWaits"
  │         触发条件：Event 1 完成后 → adversary 减速到 0（急刹）
  └── StopTrigger：hero 走完 200 m / 碰撞 / 闯红灯 / 偏离车道
```

**关键设计是「事件驱动」而非「时间驱动」**：

```
不是「第 5 秒做什么」          ← 基于时间
而是「当 hero 距前车 < 40 m 时」← 基于条件
```

真实世界里你不知道被测车何时到达某位置，所以用固定时间的场景无法复用。

---

## 3. 行为树：场景是怎么被执行的

ScenarioRunner 用一个行为树执行场景。跑场景时加 `--debug` 可以看到实时输出：

```
--------- Tick ---------
OpenScenario [*]                          ← 根节点：场景运行中
[-] behavior [*]                          ← 并行节点：同时做多件事
    (o) behavior [*]                      ← 顺序节点：依次执行
        (-) EnvironmentBehavior [✓]       ← 环境已设置
            --> ChangeWeather [✓]
        (-) InitBehaviour [✓]             ← 演员已放置
        (o) Story [*]                     ← 剧本执行中
            [-] Act StartConditions [*]   ← 等待开始条件
                (o) OverallStartCondition [*]  ← 等 hero 走 1 米…
```

**我实际遇到的情况**：这里卡住了 —— `OverallStartCondition` 一直在等
「hero 走了 1 米」，而当时没有任何 Agent 在控制 hero，所以它永远不动、条件永远不满足。

这本身是理解行为树价值的最好例子：**场景"卡住"时，能从行为树输出定位到具体是哪个节点在等待**。
不看这个输出，只能看到仿真器一直跑但不发生任何事情。

---

## 4. Leaderboard 的评分：Driving Score

从 `leaderboard/leaderboard/utils/statistics_manager.py` 源码读出（行号为 v1.0）：

```python
# L135-136
score_penalty = 1.0     # 惩罚系数，从满分 1.0 开始
score_route   = 0.0     # 路线完成百分比

# L151-193：逐事件扣分
if event == COLLISION_PEDESTRIAN:      score_penalty *= 0.50
if event == COLLISION_VEHICLE:         score_penalty *= 0.60
if event == COLLISION_STATIC:          score_penalty *= 0.65
if event == RED_LIGHT_INFRACTION:      score_penalty *= 0.70
if event == STOP_SIGN_INFRACTION:      score_penalty *= 0.80
if event == OUTSIDE_ROUTE_LANES_INFRACTION:
    score_penalty *= (1 - percentage / 100)   # 按偏离比例部分扣分
if event == ROUTE_DEVIATION:           score_route = 0.0   # 直接判零

# L196
score_composed = max(score_route * score_penalty, 0.0)
```

**惩罚是连乘，不是累加**：

```
Agent 跑完 85% 路线，闯 1 次红灯、撞 1 辆车

连乘：85.0 × 0.70 × 0.60 = 35.7
累加（假想的另一种设计）：85.0 - 15 - 20 = 50.0   ← 惩罚明显偏轻
```

连乘的含义是**安全不是可选项而是前提**：任何一次安全违规都会按比例拉低总分，
跑得再远也补不回来。

**惩罚系数体现风险分级**：撞行人 0.50 最重（涉及生命安全），
撞车辆 0.60，撞静态物体 0.65（财产损失为主），
闯红灯 0.70，闯停止标志 0.80。

> **一处需要注意的区分**：偏离相关有两个不同事件，容易混淆 ——
> - `OUTSIDE_ROUTE_LANES_INFRACTION`：压线/驶出车道，按偏离**百分比部分扣分**
> - `ROUTE_DEVIATION`：彻底偏离路线，`score_route` 直接置 0，**终止评测**
>
> 我最初的学习材料把这两个混为一谈，并漏掉了百分比连乘这一类，此处已更正。

### 违规检测器

Leaderboard 扩展了 ScenarioRunner 的判定能力，每个检测器是一个独立的行为树节点，
**与场景并行运行**（碰撞检测器、车道偏离检测器、交通灯检测器、路线完成检测器等）。
理解这些检测器的工作方式，才能设计出能被正确判定的测试场景。

---

## 5. 我自己写的跟车测试脚本

`follow_vehicle_test.py` —— 测试问题：

> CARLA 内置 Autopilot 在不同前车减速强度下的跟车安全性是否有差异？

**测试矩阵**（5 个用例，2 因子非全交叉）：

| # | 前车速度 | 减速度 | 描述 |
|---|---------|--------|------|
| 1 | 5 m/s | 2 m/s² | 轻度减速 |
| 2 | 5 m/s | 4 m/s² | 中度减速 |
| 3 | 5 m/s | 7 m/s² | 紧急制动 |
| 4 | 10 m/s | 4 m/s² | 高速中度减速 |
| 5 | 10 m/s | 7 m/s² | 高速紧急制动 |

**脚本做法**：不依赖 ScenarioRunner，用裸 CARLA PythonAPI 实现
—— spawn ego（model3）与前车（audi.a2，前方 25 m）→ ego 开启 autopilot
→ 匀速 3 s → 前车按矩阵减速 → 逐帧记录车距 → 判定
`passed = not collision and min_distance > 1.0`。

> **诚实的现状说明**：
> - 脚本**已实现**，测试矩阵**已定义**，逻辑完整、可直接运行（需 CARLA server）。
> - 但脚本只往终端打印、**不落盘**，当时的运行结果没有保存成文件。
>   因此本仓库**不提供这张结果表** —— 没有产物支撑的数字，写出来就无法复核。
> - 要拿到可复核的结果，需要重跑一次并让脚本输出到文件（见「后续可做的事」）。

---

## 6. 后续可做的事

按价值排序：

1. **重跑跟车测试并落盘** —— 给脚本加 CSV 输出，跑一次，把真实结果存进 `results/`。
   这是把「写过脚本」变成「有可复核结论」的最小改动。
2. **用 ScenarioRunner 跑同一组场景** —— 让跟车场景变成 `.xosc`，
   由官方引擎执行，再与裸 API 版本的结论对照。这一步做了才谈得上「对标」。
3. **跑一次完整的 Leaderboard 评测** —— 需要一个合规的 Agent 接管 hero，
   对路线完成率与 Driving Score 做端到端验证。当时只启动了 evaluator 就停住了
   （`simulation_results.json` 停在 `progress: [0,4]`、`records: []`），未完成。

---

## 参考

- CARLA 0.9.11 文档：https://carla.readthedocs.io/en/0.9.11/
- ScenarioRunner：https://github.com/carla-simulator/scenario_runner （`v0.9.11`，MIT）
- Leaderboard：https://github.com/carla-simulator/leaderboard （`leaderboard-1.0`，MIT）
- OpenSCENARIO 1.0（ASAM 标准）：https://www.asam.net/standards/detail/openscenario/
