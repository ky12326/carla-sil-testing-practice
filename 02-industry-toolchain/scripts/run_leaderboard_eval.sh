#!/bin/bash
# ============================================================================
# 跑一次 CARLA Leaderboard 评测
# ============================================================================
#
# 前置条件：
#   1. CARLA server 已启动（干净实例）
#   2. 环境变量 CARLA_ROOT / SCENARIO_RUNNER_ROOT / LEADERBOARD_ROOT 已设置
#   3. 使用 Python 3.8（见下方「为什么不能用 Python 3.10」）
#
# 用法：
#   export CARLA_ROOT=/path/to/CARLA_0.9.11
#   export SCENARIO_RUNNER_ROOT=/path/to/scenario_runner
#   export LEADERBOARD_ROOT=/path/to/leaderboard
#   ./scripts/run_leaderboard_eval.sh [路线集] [subset]
#
#   ./scripts/run_leaderboard_eval.sh devtest        # 官方 devtest 全部 4 条
#   ./scripts/run_leaderboard_eval.sh devtest 1      # 只跑 Town03 那条
#   ./scripts/run_leaderboard_eval.sh smoke          # 自造短路线（冒烟）
#
# ---------------------------------------------------------------------------
# 几个必须避开的坑（都是实测踩出来的）
# ---------------------------------------------------------------------------
#
# 1) **必须用 Python 3.8，不能用 3.10**
#    CARLA 0.9.11 的 PythonAPI 是 carla-0.9.11-py3.7-*.egg，内含
#    libcarla.cpython-37m 的 .so。pkg_resources 会把它解压后以显式路径加载，
#    因此真正的约束是 C-API ABI：3.8 兼容、3.10 会段错误。
#
# 2) **egg 必须自己放进 PYTHONPATH**
#    PythonAPI/carla 目录只提供 agents/ 源码，不含编译好的 carla 包。
#    不放 egg 的话，pkg_resources.get_distribution('carla') 会抛
#    DistributionNotFound，而 leaderboard_evaluator.py 开头的版本门禁会失败。
#
# 3) **不要传 --resume**
#    argparse 里它定义成 type=bool，所以 `--resume False` 会被解析成 True
#    （bool('False') == True），导致从 checkpoint 断点续跑而不是重跑。
#    要跑全新一轮就完全不要传这个参数。
#
# 4) **评测前重启 CARLA server**
#    上一轮遗留的 actor 会占满 spawn 点，导致背景车 spawn 失败 →
#    route_scenario.py 抛异常 → 整个进程 sys.exit(-1)。
#
# 5) **--debug 保持 0**
#    debug>0 会画上千个调试点（life_time=50000），明显拖慢仿真。
#
# 6) 输出的 checkpoint 会被**先 truncate 成 0 字节**再写入
#    （statistics_manager.clear_record()），所以不要拿它当"上一次的结果"。
# ============================================================================

set -e

ROUTES_SET="${1:-devtest}"
SUBSET="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"

# --- 环境检查 ---------------------------------------------------------------
: "${CARLA_ROOT:?请先 export CARLA_ROOT}"
: "${SCENARIO_RUNNER_ROOT:?请先 export SCENARIO_RUNNER_ROOT}"
: "${LEADERBOARD_ROOT:?请先 export LEADERBOARD_ROOT}"

CARLA_EGG="$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.11-py3.7-linux-x86_64.egg"
export CARLA_EGG
export PYTHONPATH="$CARLA_EGG:$CARLA_ROOT/PythonAPI/carla:$SCENARIO_RUNNER_ROOT:$LEADERBOARD_ROOT"

PYTHON="${PYTHON:-python3}"
mkdir -p "$RESULTS_DIR"

# --- 选择路线集 -------------------------------------------------------------
case "$ROUTES_SET" in
  smoke)
    ROUTES="$SCRIPT_DIR/../routes/smoke_town03_short.xml"
    OUT="$RESULTS_DIR/smoke_results.json"
    ;;
  devtest)
    ROUTES="$LEADERBOARD_ROOT/data/routes_devtest.xml"
    OUT="$RESULTS_DIR/devtest_results.json"
    ;;
  *)
    echo "未知路线集: $ROUTES_SET（可选 smoke / devtest）" >&2
    exit 1
    ;;
esac

SUBSET_ARG=()
[ -n "$SUBSET" ] && SUBSET_ARG=(--routes-subset "$SUBSET")

echo "=== CARLA Leaderboard 评测 ==="
echo "  路线集   : $ROUTES_SET  ($ROUTES)"
echo "  subset   : ${SUBSET:-全部}"
echo "  Python   : $($PYTHON --version 2>&1)"
echo "  输出     : $OUT"
echo ""

# --- 版本自检（对应坑 2）-----------------------------------------------------
$PYTHON - <<'PY'
import sys, pkg_resources
try:
    v = pkg_resources.get_distribution('carla').version
except Exception as e:
    sys.exit(f"❌ 找不到 carla 发行版：{e}\n   检查 egg 是否在 PYTHONPATH 上（见脚本注释坑 2）")
if v < '0.9.10':
    sys.exit(f"❌ carla {v} 低于 leaderboard 要求的 0.9.10")
print(f"✓ carla {v}")
PY

# --- 运行 -------------------------------------------------------------------
# 注意 --checkpoint 用绝对路径：它是相对 CWD 解析的
cd "$LEADERBOARD_ROOT"
exec "$PYTHON" leaderboard/leaderboard_evaluator.py \
  --routes "$ROUTES" \
  "${SUBSET_ARG[@]}" \
  --scenarios data/all_towns_traffic_scenarios_public.json \
  --agent leaderboard/autoagents/npc_agent.py \
  --track SENSORS \
  --checkpoint "$OUT" \
  --debug 0
