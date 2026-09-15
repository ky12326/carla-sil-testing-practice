# 被测系统来源说明（R01 baseline）

本目录下的 `upstream-sut/` 是**第三方开源项目**，不是本仓库作者的作品。

## 来源

| 项 | 值 |
|---|---|
| 上游仓库 | `https://github.com/OceanKI/carla_simAvoidance` |
| 克隆时的 HEAD | `058fc96 add config.md`（shallow clone） |
| 上游 README 声明的许可 | MIT License（见 `upstream-sut/README.md` 第 89 行） |
| 上游仓库内是否有 LICENSE 文件 | **无** —— 仅在 README 中声明 |

## 为什么放在这里

这个项目是本仓库的**被测系统（SUT）**。R01 基线阶段直接运行它的原始代码、
不做任何修复，用控制台观察记录其行为（见
[`../outputs/reports/BASELINE_R01.md`](../outputs/reports/BASELINE_R01.md)），
由此得到 FIND-001~006 六项观察与 BUG-001~008 八项代码缺陷。

保留源码是为了让「基线结论」可复核 —— 没有被测系统的代码，
R01 报告里的每一条发现都只能靠文字描述。

## 本目录包含 / 不包含什么

**包含**（共约 40 KB）：

- `carla_da_static.py`（207 行）、`carla_da_dynamic.py`（188 行）、
  `carla_da_dynamic_with_camera.py`（245 行）—— 三个近乎重复的主脚本
- `util/camera.py`（128 行）、`util/recorder.py`（**0 字节**，上游未实现的空文件）
- `README.md`、`config.yaml`（364 字节）

**已排除**：上游仓库的 `.git` 目录（103 MB）、`videos/` 目录（103 MB，6 个演示
gif/mp4）、根目录下由 `cv2.imwrite` 产生的 `car.png`。这些与基线复现无关。

## 作者自己写的部分（不在本目录）

为跑通基线，作者写了两个**适配版**脚本，放在 [`adapted/`](adapted/)：

- `carla_da_static_adapted.py`、`carla_da_dynamic_adapted.py`

改动仅有三处（**核心逻辑与全部已知 Bug 原样保留**，目的就是记录基线行为）：

1. 把硬编码的生成点坐标替换为 `random.choice(spawn_points)`
2. 注入 CARLA 的导入路径
3. 去掉会写文件的 `cv2.imwrite`，改为打印运行日志

> 这两个文件在整理本仓库时，把写死的本机绝对路径改成了读取 `CARLA_EGG`
> 环境变量；除此之外未改动。

## 许可

上游 README 声明 MIT。本仓库按 MIT 发布自写部分（见根目录 `LICENSE`），
`upstream-sut/` 内的代码版权归上游作者所有，按上游声明的 MIT 条款引用。
