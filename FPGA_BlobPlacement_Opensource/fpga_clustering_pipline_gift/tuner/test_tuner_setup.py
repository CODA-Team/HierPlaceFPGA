#!/usr/bin/env python3
"""
测试tuner设置是否正确
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_imports():
    """测试所有必需的导入"""
    print("测试导入...")
    try:
        from tuner.tuner_configs import (
            CLUSTERING_BASE_CONFIG,
            CLUSTERING_BASE_PPA,
            CLUSTERING_BEST_CFG,
        )
        print("  ✓ tuner_configs 导入成功")
    except Exception as e:
        print(f"  ✗ tuner_configs 导入失败: {e}")
        return False
    
    try:
        from tuner.tuner_worker import ClusteringPipelineWorker
        print("  ✓ tuner_worker 导入成功")
    except Exception as e:
        print(f"  ✗ tuner_worker 导入失败: {e}")
        return False
    
    try:
        from tuner.tuner_utils import parse_dictionary, parse_int_list, str2bool
        print("  ✓ tuner_utils 导入成功")
    except Exception as e:
        print(f"  ✗ tuner_utils 导入失败: {e}")
        return False
    
    return True


def test_configspace():
    """测试配置空间定义"""
    print("\n测试配置空间...")
    try:
        from tuner.tuner_worker import ClusteringPipelineWorker
        
        # Test without config file (default configspace)
        cs = ClusteringPipelineWorker.get_configspace("", seed=42)
        print(f"  ✓ 默认配置空间创建成功")
        print(f"    参数数量: {len(cs.get_hyperparameters())}")
        print(f"    参数列表: {[hp.name for hp in cs.get_hyperparameters()]}")
        
        # Test with config file if it exists
        config_file = os.path.join(os.path.dirname(__file__), "configspace.json")
        if os.path.exists(config_file):
            cs_json = ClusteringPipelineWorker.get_configspace(config_file, seed=42)
            print(f"  ✓ JSON配置空间加载成功")
            print(f"    参数数量: {len(cs_json.get_hyperparameters())}")
        else:
            print(f"  ! configspace.json 未找到（可选）")
        
        return True
    except Exception as e:
        print(f"  ✗ 配置空间测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_merge():
    """测试配置合并"""
    print("\n测试配置合并...")
    try:
        from tuner.tuner_configs import CLUSTERING_BASE_CONFIG
        
        # Test configuration merge
        default_config = {
            "benchmark_dir": "/test/benchmark",
            "dreamplace_path": "/test/dreamplace",
            "base_ppa": "FPGA03",
            "gpu": 0,
        }
        
        tuned_config = {
            "min_cluster_size": 60,
            "resolution": 1.5,
            "learning_rate": 0.02,
        }
        
        merged = {**CLUSTERING_BASE_CONFIG, **default_config, **tuned_config}
        
        assert merged["benchmark_dir"] == "/test/benchmark"
        assert merged["min_cluster_size"] == 60
        assert merged["resolution"] == 1.5
        
        print("  ✓ 配置合并测试通过")
        return True
    except Exception as e:
        print(f"  ✗ 配置合并测试失败: {e}")
        return False


def test_run_script_exists():
    """检查run_complete_flow_with_json.py是否存在"""
    print("\n检查运行脚本...")
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_script = os.path.join(script_dir, "run_complete_flow_with_json_area.py")
    
    if os.path.exists(run_script):
        print(f"  ✓ 找到运行脚本: {run_script}")
        return True
    else:
        print(f"  ✗ 未找到运行脚本: {run_script}")
        return False


def test_hpbandster():
    """测试HPBandSter是否可用"""
    print("\n测试HPBandSter...")
    try:
        import hpbandster.core.nameserver as hpns
        import hpbandster.core.result as hpres
        from hpbandster.optimizers import BOHB
        print("  ✓ HPBandSter导入成功")
        return True
    except Exception as e:
        print(f"  ✗ HPBandSter导入失败: {e}")
        print("    请安装: pip install hpbandster")
        return False


def main():
    print("="*80)
    print("FPGA Clustering Pipeline Tuner 设置测试")
    print("="*80)
    
    results = []
    
    results.append(("导入测试", test_imports()))
    results.append(("配置空间测试", test_configspace()))
    results.append(("配置合并测试", test_config_merge()))
    results.append(("运行脚本检查", test_run_script_exists()))
    results.append(("HPBandSter检查", test_hpbandster()))
    
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + "="*80)
    if all_passed:
        print("✓ 所有测试通过！Tuner设置正确。")
        print("\n下一步:")
        print("  1. 编辑 tuner/run_tuner.sh 设置benchmark路径")
        print("  2. 更新 tuner/tuner_configs.py 中的基线PPA")
        print("  3. 运行: ./tuner/run_tuner.sh")
    else:
        print("✗ 部分测试失败，请检查上述错误信息")
        return 1
    print("="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

