"""
pytest fixtures for CARLA simulation testing

fixture 分两类：

- **无 CARLA 依赖** —— `config`：读取 `config/default.yaml`，纯本地，任何机器可用。
  纯单元测试（`test_pure_pursuit.py`）只依赖它。
- **需要 CARLA server** —— 其余全部。CARLA 不可用时这些 fixture 会 **skip**
  （注意：skip 判定写在 fixture 函数体内，因为 pytest 不支持把 mark 标在 fixture 上）。

CARLA 的导入是**惰性**的：没有安装 CARLA 的机器上本文件仍可正常加载，
纯单元测试照常收集与运行。指定 CARLA PythonAPI 路径请设置环境变量 `CARLA_EGG`。
"""

import os
import random
import sys

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# --- CARLA 可选导入 ----------------------------------------------------------
# CARLA_EGG 指向 carla-<版本>-py3.x-<平台>.egg；未设置时直接尝试 import
# （适用于已 pip install carla 或已把 PythonAPI 配进 PYTHONPATH 的情况）。
_CARLA_EGG = os.environ.get('CARLA_EGG')
if _CARLA_EGG and os.path.exists(_CARLA_EGG) and _CARLA_EGG not in sys.path:
    sys.path.insert(0, _CARLA_EGG)

try:
    import carla
    CARLA_AVAILABLE = True
except ImportError:  # pragma: no cover - 取决于运行环境
    carla = None
    CARLA_AVAILABLE = False

SKIP_REASON = (
    "需要 CARLA：请设置 CARLA_EGG 环境变量指向 carla-*.egg，"
    "并启动 CARLA server (localhost:2000)"
)

# 供测试函数使用的 marker（mark 对 fixture 无效，故 fixture 内部单独判定）
requires_carla = pytest.mark.skipif(not CARLA_AVAILABLE, reason=SKIP_REASON)


def _require_carla():
    """fixture 内调用：CARLA 不可用则 skip 当前测试"""
    if not CARLA_AVAILABLE:
        pytest.skip(SKIP_REASON)


# --- 无 CARLA 依赖 -----------------------------------------------------------

@pytest.fixture(scope='session')
def config():
    """加载 config/default.yaml（纯本地读取，不需要 CARLA）"""
    with open(os.path.join(PROJECT_ROOT, 'config', 'default.yaml')) as f:
        return yaml.safe_load(f)


# --- 需要 CARLA server -------------------------------------------------------

@pytest.fixture(scope='session')
def carla_client():
    """CARLA 客户端（session 级）。连不上时 skip 而非报错。"""
    _require_carla()
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    try:
        world = client.get_world()
    except RuntimeError as exc:
        pytest.skip(f"无法连接 CARLA server (localhost:2000)：{exc}")
    if not world.get_map().name:
        pytest.skip("已连接 CARLA server，但未返回有效地图")
    return client


@pytest.fixture(scope='function')
def carla_world(carla_client):
    """CARLA 世界对象（function 级，用完恢复原始 settings）"""
    world = carla_client.get_world()
    original_settings = world.get_settings()
    yield world
    world.apply_settings(original_settings)


@pytest.fixture(scope='function')
def ego_spawn_point(carla_world, config):
    """选择一个生成点（按 config 的 runtime.seed 固定，保证可复现）"""
    seed = (config.get('runtime') or {}).get('seed')
    if seed is not None:
        random.seed(seed)
    return random.choice(carla_world.get_map().get_spawn_points())


@pytest.fixture(scope='function')
def vehicle_blueprint(carla_world, config):
    """获取 ego 车辆蓝图（车型取自 config，而非写死）"""
    model = (config.get('ego_vehicle') or {}).get('model', 'model3')
    return carla_world.get_blueprint_library().filter(model)[0]


@pytest.fixture(scope='function')
def obstacle_blueprint(carla_world):
    """获取障碍车辆蓝图"""
    return carla_world.get_blueprint_library().filter('vehicle.*')[0]


@pytest.fixture(scope='function')
def carla_actors(carla_world):
    """管理测试中创建的 actors，测试结束后自动清理"""
    actors = []
    yield actors
    for actor in actors:
        if actor.is_alive:
            if 'vehicle' in actor.type_id:
                actor.set_autopilot(False)
            actor.destroy()
