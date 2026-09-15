# 自建测试指标 vs CARLA 官方 Driving Score —— 两套评测体系的对照

> 2026-09-15 · CARLA 0.9.11 · 本文用**真实跑出来的数据**说明两套体系的差异。
>
> 阅读目标：看完能回答「你自建的评测体系和 Leaderboard 各测什么、
> 差异在哪、为什么不能直接比分数」。

---

## 〇、先给结论

**两套体系在「事件检测」层是相通的，差异在「如何把事件聚合成结论」。**

| 层次 | 自建框架 | CARLA Leaderboard |
|---|---|---|
| 检测什么 | 碰撞、压线 | 碰撞、压线、闯红灯、闯停止牌 |
| 怎么检测 | 传感器回调 + 标志位 | `atomic_criteria.py` 的行为树节点 |
| **怎么聚合** | **二元判定**：碰撞数 == 0 → PASS，否则 FAIL | **连乘分数**：每次违规按系数打折，再乘路线完成率 |
| 输出什么 | 原始计数 + PASS/FAIL | `score_composed` + 12 项明细指标 |

所以「对标」的正确做法不是把两个数字并排放，而是**说清各自在哪个层次做了什么**。

---

## 一、两套体系分别是什么

### 1.1 自建框架（`01-self-built-harness/`）

为「多机器人协同避障」这个具体问题定制的验证框架。它要回答的问题是：

> 在瓶颈通道里，两台/多台机器人能否在不碰撞的前提下协调通过？

因此它的设计围绕**单一场景下的安全性**展开：
- 固定场景（Town03 的静态/动态障碍物）
- 一次运行 30–35 秒
- 输出碰撞次数、压线次数、跟车距离、振荡次数

**它的关键词是「深」** —— 在窄场景里把指标测细。

### 1.2 CARLA Leaderboard

CARLA 官方为自动驾驶**挑战赛**提供的标准化评测基准。它要回答的问题是：

> 一个自动驾驶 Agent 在开放路网中长距离行驶，整体表现有多好？

因此它的设计围绕**通用性与可比性**展开：
- 标准路线（官方 4 条 devtest / 26 条 testing / 50 条 training）
- 一次评测十几分钟到几小时
- 输出一个可以横向比较的分数

**它的关键词是「广」** —— 用统一口径横向比较不同的 Agent。

---

## 二、数据流对比

### 2.1 自建框架

```
CARLA server
   │
   ├─ 碰撞传感器 ──→ _on_collision()  ──→ collision_flag = True
   ├─ 车道入侵传感器 → _on_lane_invasion() → lane_invasion_flag = True
   │
   ▼  主循环（约 50 Hz，按墙钟时间推进）
每 tick:
   recorder.record_tick(collision=flag, lane_invasion=flag, ...)
   flag 读后复位                        ← 一个事件只被记一次
   │
   ▼  场景结束（达到 30s 上限 / 碰撞 3 次 / 到达目标）
recorder.save_summary()
   ├─ collision_events     = 数 tick（flag 为真的 tick 数）
   ├─ lane_invasion_events = 数 tick
   └─ result = 'PASS' if collision_count == 0 else 'FAIL'
```

**关键点**：判定是最后**一句话**定下来的 ——

```python
# scenarios/base_scenario.py:297-301
if self.result.collision_count == 0:
    self.result.success = True
    self.recorder.set_result('PASS')
else:
    self.recorder.set_result('FAIL', f'{self.result.collision_count} 次碰撞')
```

**没有分数，没有加权。碰撞一次和碰撞十次，结论都是 FAIL。**

### 2.2 CARLA Leaderboard

```
CARLA server（同步模式 20 Hz，固定步长 0.05s）
   │
   ▼  RouteScenario 加载路线 + 场景 + 120~200 台背景车
每个 tick:
   Agent.run_step() → carla.VehicleControl
   atomic_criteria 的各个检测器**并行运行**：
       CollisionTest            ← 撞了吗？
       OutsideRouteLanesTest    ← 压线了吗？
       RunningRedLightTest      ← 闯红灯了吗？
       RunningStopTest          ← 闯停止牌了吗？
       RouteCompletionTest      ← 路线跑完多少了？
       AgentBlockedTest         ← 卡住了吗？
   │
   ▼  路线结束
StatisticsManager 聚合：
   score_penalty  = 1.0
   每次碰撞行人   → score_penalty *= 0.50
   每次碰撞车辆   → score_penalty *= 0.60
   每次碰撞静态物 → score_penalty *= 0.65
   每次闯红灯     → score_penalty *= 0.70
   每次闯停止牌   → score_penalty *= 0.80
   压线           → score_penalty *= (1 - 偏离百分比/100)
   彻底偏离路线   → score_route = 0
   
   score_composed = score_route × score_penalty
```

**关键点**：每次违规都是**乘法**，不是加法。

---

## 三、差异的核心：二元判定 vs 连续分数

这是两套体系**最本质**的差异。用一个例子说明：

### 场景：一次行驶中发生 1 次撞车，路线跑完 85%

| | 自建框架 | Leaderboard |
|---|---|---|
| 判定过程 | 碰撞数 1 ≠ 0 → **FAIL** | `85.0 × 0.60 = 51.0` |
| 输出 | `FAIL`（附「1 次碰撞」） | `51.0` |
| 信息量 | 二元 —— 失败 | 连续 —— 比满分低 34 分 |

### 为什么会这样设计

**自建框架的假设**：这个场景的合格标准就是「不碰撞」。碰撞了就是失败，没有中间地带。这对**离线验证一个具体控制器**是合适的。

**Leaderboard 的假设**：自动驾驶系统的安全性不是二元的。跑了 85% 的路线有价值，撞了一次车要扣分，但两者要能同时体现。而且不同违规的风险等级不同（撞行人比闯停止牌严重得多）。

**所以 `score_penalty` 用连乘而不是累加**：
- 连乘：`85 × 0.7 × 0.6 = 35.7`（两次违规后分数急剧下降）
- 累加假如是 `85 - 15 - 20 = 50`（惩罚太轻）

连乘体现的是「**安全是前提条件，不是可选项**」—— 每一次违规都按比例削弱整体表现。

---

## 四、真实数据

### 4.1 自建框架的实测（Town03 静态障碍物场景）

见 `01-self-built-harness/outputs/data/20260915_*.json`：

```
result: FAIL
collision_events: 3
lane_invasion_events: 9
avoidance_ticks: 505 / 1225 (41.2%)
```

按自建的规则，`3 ≠ 0` → **FAIL**。信息到此为止。

### 4.2 Leaderboard 的实测（Town03 官方路线）

- **路线**：`routes_devtest.xml` 的 `RouteScenario_1`（Town03，全长 **1128.3 m**）
- **Agent**：`npc_agent.py` —— CARLA 官方 Dockerfile 默认的 baseline，
  用 CARLA 自带的 `BasicAgent`（规则控制，**不需要任何机器学习模型**）

```
成绩
  Driving Score (score_composed)      11.59
  ├─ score_route    (路线完成率)       38.64 %
  └─ score_penalty  (违规惩罚)         0.30

违规明细（原始记录）
  ✗ 撞行人 × 1   walker.pedestrian.0024   @ (x=64.5,  y=207.4)
  ✗ 撞车辆 × 1   vehicle.nissan.patrol    @ (x=242.7, y=88.4)
  ✗ 卡住   × 1                            @ (x=167.0, y=87.2)

结束原因：Failed - Agent got blocked
时长：298.0 game 秒 / 427.8 墙钟秒
```

**验算 —— 分数是怎么算出来的**：

```
38.635 × 0.50 × 0.60 = 11.59        ✅ 与 score_composed 完全吻合
         ↑     ↑
         │     └─ 撞车辆系数 0.60
         └─────── 撞行人系数 0.50
```

逐步看 `score_penalty` 的变化：

| 事件 | 系数 | 累计 penalty |
|---|---|---|
| 起始 | — | 1.00 |
| 撞行人 | × 0.50 | 0.50 |
| 撞车辆 | × 0.60 | **0.30** |

> **一个容易误读的地方**：上面 12 项指标里 `Collisions with pedestrians` 显示
> `2.294`，那**不是碰撞次数**，而是**按实际行驶距离归一化后的「每公里违规数」**
> （1 次 ÷ 0.436 km ≈ 2.294）。
> 原始次数要看 `infractions` 数组的长度 —— 那里各只有 1 条记录。

### 4.3 同一类事件在两套体系里的呈现

把「发生一次碰撞」这件事分别放进两套体系：

| | 自建框架 | Leaderboard |
|---|---|---|
| **记录方式** | 某一个 tick 的 `collision` 字段为 `True` | `infractions.collisions_vehicle` 数组追加一条，**含撞击对象类型与世界坐标** |
| **对结论的影响** | 把整体判定从 PASS 翻成 **FAIL** | 把分数从 38.64 乘成 **11.59** |
| **可追溯性** | CSV 里有那一帧的坐标与时间 | 记录了撞的是什么（`walker.pedestrian.0024`）和撞在哪 |
| **回答的问题** | 「**合格吗**」 | 「**有多好**」 |

**差异的实质**：

- **自建框架是二元的** —— 适合回答「这个控制器在这个场景里行不行」
- **Leaderboard 是连续的，且保留了事件语义** —— 适合回答「整体表现如何、
  问题出在哪一类违规」

两者都不是"更正确"的，它们服务的问题不同。

---

## 五、Driving Score 公式拆解

（数值取自 `leaderboard/utils/statistics_manager.py`，行号为 `leaderboard-1.0`）

```python
# L135-136
score_penalty = 1.0     # 从满分 1.0 开始
score_route   = 0.0     # 路线完成百分比

# L151-193：逐事件扣分
if event == COLLISION_PEDESTRIAN:   score_penalty *= 0.50
if event == COLLISION_VEHICLE:      score_penalty *= 0.60
if event == COLLISION_STATIC:       score_penalty *= 0.65
if event == RED_LIGHT_INFRACTION:   score_penalty *= 0.70
if event == STOP_SIGN_INFRACTION:   score_penalty *= 0.80
if event == OUTSIDE_ROUTE_LANES_INFRACTION:
    score_penalty *= (1 - percentage / 100)    # 按偏离比例部分扣分
if event == ROUTE_DEVIATION:
    score_route = 0.0                          # 直接判零

# L196
score_composed = max(score_route * score_penalty, 0.0)
```

**注意两个容易混淆的「偏离」事件**：
- `OUTSIDE_ROUTE_LANES_INFRACTION`：压线/驶出车道 → 按百分比**部分扣分**
- `ROUTE_DEVIATION`：彻底偏离路线 → `score_route` 置零，**终止评测**

---

## 六、各自的盲区

### 6.1 自建框架的盲区

| 盲区 | 说明 |
|---|---|
| **不测路线完成率** | 只测「有没有碰撞」，不测「到没到目标」的连续程度 |
| **不区分违规的风险等级** | 撞行人和压线在当前实现里都只通过「碰撞数」体现 |
| **没有「阻塞/超时」判定** | 机器人卡住不动会被 anti-stall 惩罚，但不会判 FAIL |
| **指标是「数 tick」而非「数事件」** | `save_summary()` 里 `collision_events = sum(1 for r in records if r['collision'])`，字段名叫 events 但实现是数 tick。它"碰巧"等于事件数，因为标志位每 tick 复位 —— 一个事件只占一个 tick。但这是**间接计数**，若同 tick 内发生两个事件就会漏记 |
| **场景单一** | 只覆盖瓶颈通道，不覆盖路口、行人、交通灯 |

### 6.2 Leaderboard 的盲区

| 盲区 | 说明 |
|---|---|
| **不测连续安全裕度** | 它记录「撞没撞」，不记录「离撞上还差多少」—— 而自建框架的最小跟车距离能给出这个 |
| **不测多智能体协同** | 它评的是单个 Agent，背景车是环境的一部分，不参与协同 |
| **分数不可分解** | `score_composed` 是个复合值，出问题时要知道是哪一项导致的，得去看 `infractions` 明细 |
| **对场景配置敏感** | 路线上随机采样的场景不同，分数会有波动 |

---

## 七、这次实践的意义

### 7.1 对项目本身：两条独立路径得到一致判断

- **自建框架**：CARLA 内置控制器在 Town03 避障场景 → `FAIL`（3 次碰撞）
- **Leaderboard**：CARLA 内置 `BasicAgent` 在 Town03 官方路线 → **11.59 分**（2 次碰撞 + 1 次卡死）

两者场景不同、Agent 不同、指标不同，但**指向同一个结论**：
**CARLA 内置的规则控制器在复杂交通环境下安全性不足。**

这条独立验证很有价值 —— 如果自建框架报"失败"而 Leaderboard 报"高分"，
那说明自建的判定标准可能有问题。现在两边一致，是对自建评测体系的一次**外部校验**。

### 7.2 对评测方法论：互补而非替代

| 要回答的问题 | 该用哪一套 |
|---|---|
| 控制器在这个瓶颈场景里安全吗？离撞上还有多少余量？ | **自建** —— 有连续距离指标 |
| 整体表现如何？能和其他 Agent 横向比较吗？ | **Leaderboard** —— 标准化分数 |
| 改了奖励函数后是变好还是变差？ | **自建** —— 固定场景、种子确定、可复现 |
| 违规的类型分布是什么？哪一类问题最多？ | **Leaderboard** —— 分级违规统计 |

### 7.3 对工程实践：跑通的过程本身就是经验

| 遇到的问题 | 学到的东西 |
|---|---|
| CARLA 0.9.11 的 egg 是 py3.7 编译的，在 Python 3.10 下**段错误** | 理解 Python 扩展模块的 C-API ABI 兼容性 —— 3.8 兼容 3.7，3.10 不兼容 |
| `pkg_resources` 找不到 carla 发行版 | 明白 egg 必须自己进 `PYTHONPATH`（`PythonAPI/carla` 目录只提供 `agents/` 源码） |
| 一条 1128 m 的路线跑了 298 game 秒就结束了 | 理解 `AgentBlockedTest` 的判定逻辑 —— 卡住不会等满超时，而是提前终止 |
| `score_penalty` 是连乘不是累加 | 读源码（`statistics_manager.py:151-196`）比看文档可靠 |

### 7.4 这次**没有**做到的（如实说明）

- **两套体系测的不是同一个东西** —— 自建测多机器人协同避障，
  Leaderboard 测单车在开放路网上的合规驾驶。
  **本文对照的是方法论，不是数值。**
  要做到数值对标，需要把自建场景改造成 Leaderboard 能识别的形式，
  或反过来把 Driving Score 的维度搬进自建框架 —— 这属于后续工作，本次未做。
- **只跑了 1 条路线** —— 官方 devtest 还有 3 条（Town01 / Town04 / Town06）
  未跑。本路线的 `RouteScenario_1` 是全 4 条中第二条。
- **单次运行的分数有波动** —— 路线上随机采样的场景不同，分数会有变化。
  严格的结论需要多次重复取统计量。

---

## 附：数据来源

| 数据 | 文件 |
|---|---|
| 自建框架指标 | `01-self-built-harness/outputs/data/*_summary.json` |
| 自建框架判定逻辑 | `01-self-built-harness/scenarios/base_scenario.py:297-301` |
| Leaderboard 评测结果 | `02-industry-toolchain/results/*.json` |
| Driving Score 公式 | `leaderboard/utils/statistics_manager.py:135-196` |
| 违规检测器 | `leaderboard/scenarios/scenarioatomics/atomic_criteria.py` |
