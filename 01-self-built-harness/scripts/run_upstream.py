#!/usr/bin/env python3
"""
运行上游（R01 被测系统）场景脚本的启动器。

本文件本身来自上游项目，仅做了一处改动：把写死的路径改为从环境变量 /
相对位置推导，使其在任何机器上可运行。

用法:
    export CARLA_EGG="/path/to/carla-0.9.11-py3.7-linux-x86_64.egg"
    python scripts/run_upstream.py carla_da_static.py
"""
import sys
import os

# 注入 CARLA Python API（路径由环境变量提供）
CARLA_EGG = os.environ.get('CARLA_EGG', '')
if CARLA_EGG and CARLA_EGG not in sys.path:
    sys.path.insert(0, CARLA_EGG)

# 上游脚本目录：相对本文件定位到 ../baseline-r01/upstream-sut/
# （上游脚本的 import 是从脚本自身目录解析的，所以用 exec 前把该目录放进 sys.path）
UPSTREAM_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'baseline-r01', 'upstream-sut'
))
if UPSTREAM_DIR not in sys.path:
    sys.path.insert(0, UPSTREAM_DIR)

# 从命令行参数获取要运行的场景脚本
if len(sys.argv) < 2:
    print("Usage: python run_upstream.py <script_name>")
    print("  Available: carla_da_static.py, carla_da_dynamic.py, carla_da_dynamic_with_camera.py")
    sys.exit(1)

script_name = sys.argv[1]
script_path = os.path.join(UPSTREAM_DIR, script_name)

if not os.path.exists(script_path):
    print(f"Script not found: {script_path}")
    sys.exit(1)

print(f"Running: {script_name}")
print(f"CARLA egg: {CARLA_EGG}")
print("=" * 50)

# 执行场景脚本
with open(script_path) as f:
    code = compile(f.read(), script_path, 'exec')
    exec(code, {'__name__': '__main__'})
