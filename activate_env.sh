#!/bin/bash
# CARLA 官方工具链（ScenarioRunner + Leaderboard）环境激活脚本
#
# 使用前请先设置路径（脚本不写死任何本机路径，也不激活特定 venv）：
#
#     export CARLA_ROOT=/path/to/CARLA_0.9.11
#     export SCENARIO_RUNNER_ROOT=/path/to/scenario_runner      # 可选
#     export LEADERBOARD_ROOT=/path/to/leaderboard              # 可选
#     source activate_env.sh
#
# 本项目的跟车测试脚本只需要 CARLA_ROOT；另外两个仓库仅用于跑官方场景与评测。

# --- 必需：CARLA 本体 ---
if [ -z "${CARLA_ROOT:-}" ]; then
    echo "❌ 请先设置 CARLA_ROOT，例如：" >&2
    echo "     export CARLA_ROOT=~/CARLA_0.9.11" >&2
    return 1 2>/dev/null || exit 1
fi

CARLA_PYAPI="$CARLA_ROOT/PythonAPI/carla"
# 自动定位 carla-*.egg（版本号与 Python 版本随 CARLA 发行版而变，故不写死）
CARLA_EGG="$(ls "$CARLA_PYAPI"/dist/carla-*.egg 2>/dev/null | head -1)"

# --- 组装 PYTHONPATH（顺序重要：CARLA 在最前）---
_new_path="$CARLA_PYAPI"
[ -n "$CARLA_EGG" ]            && _new_path="$CARLA_EGG:$_new_path"
[ -n "${SCENARIO_RUNNER_ROOT:-}" ] && _new_path="$_new_path:$SCENARIO_RUNNER_ROOT"
[ -n "${LEADERBOARD_ROOT:-}" ]     && _new_path="$_new_path:$LEADERBOARD_ROOT"
export PYTHONPATH="$_new_path${PYTHONPATH:+:$PYTHONPATH}"

# 本项目脚本与 pytest 读取此变量来定位 carla
export CARLA_EGG

echo "CARLA 工具链环境已配置"
echo "  CARLA_ROOT           = $CARLA_ROOT"
if [ -n "$CARLA_EGG" ]; then
    echo "  carla egg            = $(basename "$CARLA_EGG")"
else
    echo "  ⚠️  未在 $CARLA_PYAPI/dist/ 下找到 carla-*.egg"
fi
[ -n "${SCENARIO_RUNNER_ROOT:-}" ] && echo "  SCENARIO_RUNNER_ROOT = $SCENARIO_RUNNER_ROOT"
[ -n "${LEADERBOARD_ROOT:-}" ]     && echo "  LEADERBOARD_ROOT     = $LEADERBOARD_ROOT"

# --- 自检 ---
python3 - <<'PY' 2>&1
import os, sys
egg = os.environ.get("CARLA_EGG")
if egg:
    sys.path.insert(0, egg)
try:
    import carla                      # noqa: F401
    print("  ✅ carla 可导入")
except ImportError as exc:
    print(f"  ❌ carla 导入失败：{exc}")
    print("     （若尚未启动 CARLA server，导入成功但连接会失败，属正常）")
PY
