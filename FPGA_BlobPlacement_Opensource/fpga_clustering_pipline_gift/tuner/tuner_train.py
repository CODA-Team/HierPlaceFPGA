import os
import argparse
import time
import torch
import shutil
import re
import sys
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import hpbandster.core.nameserver as hpns
import hpbandster.core.result as hpres
from hpbandster.optimizers import BOHB as BOHB
from hpbandster.optimizers import MOBOHB as MOBOHB

opj = os.path.join

from tuner.tuner_worker import ClusteringPipelineWorker
from tuner.tuner_utils import parse_dictionary, parse_int_list, str2bool
from tuner.tuner_analyze import get_candidates, plot_pareto


parser = argparse.ArgumentParser(
    description="Optimization of FPGA Clustering Pipeline parameters",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--multiobj",
    type=str2bool,
    help="Enable Multi-Objective BOHB",
    default=False,
)
parser.add_argument(
    "--cfgSearchFile",
    help="Search-space config file (JSON format)",
    default="",
)
parser.add_argument(
    "--min_points_in_model",
    type=int,
    help="Number of observations to start building a KDE",
    default=32,
)
parser.add_argument(
    "--min_budget",
    type=int,
    help="Minimum budget used during the optimization.",
    default=1,
)
parser.add_argument(
    "--max_budget",
    type=int,
    help="Maximum budget used during the optimization.",
    default=1,
)
parser.add_argument(
    "--n_iterations",
    type=int,
    help="Number of iterations performed by the optimizer",
    default=50,
)
parser.add_argument(
    "--n_workers",
    type=int,
    help="Number of parallel workers used by the optimizer",
    default=4,
)
parser.add_argument(
    "--n_samples", type=int, help="Number of samples per iteration", default=32
)
parser.add_argument(
    "--hpwl_ratio", type=float, help="HPWL cost ratio", default=1.0
)
parser.add_argument(
    "--runtime_ratio", type=float, help="Runtime cost ratio", default=0.5
)
parser.add_argument(
    "--overflow_ratio", type=float, help="Overflow cost ratio", default=0.5
)
parser.add_argument(
    "--num_pareto", type=int, help="Number of Pareto points to propose", default=5
)
parser.add_argument("--log_dir", help="Result log dir", default="logs_tuner")
parser.add_argument("--run_id", help="Run id for communication", default="0")
parser.add_argument(
    "--nameserver_port", type=int, help="Nameserver port (default: None = auto)", default=None
)
parser.add_argument(
    "--run_args", nargs="*", help="Args for clustering pipeline", action=parse_dictionary
)
parser.add_argument(
    "--worker", help="Flag to turn this into a worker process", action="store_true"
)
parser.add_argument("--worker_id", type=int, help="Worker id", default=0)
parser.add_argument(
    "--gpu_pool",
    type=parse_int_list,
    help="List of GPUs to use (e.g. 1,2,0-3)",
    default="-1",
)
args = parser.parse_args()


# Worker
if args.worker:
    time.sleep(5)  # artificial delay to make sure the nameserver is already running
    print(f"Starting worker process number {args.worker_id}")
    print(f"Worker args: {args}")

    # GPU assignment for workers
    if args.run_args.get("gpu", "0") != "0":
        if args.gpu_pool == [-1]:
            available_gpus = range(torch.cuda.device_count()) if torch.cuda.is_available() else [0]
        else:
            available_gpus = args.gpu_pool
            if torch.cuda.is_available():
                assert all(g < torch.cuda.device_count() for g in available_gpus)
        
        if len(available_gpus) > 0:
            gpu_id = available_gpus[args.worker_id % len(available_gpus)]
            args.run_args["gpu"] = gpu_id
            print(f"Assigning worker {args.worker_id} to GPU {gpu_id}")

    # Pass nameserver host and port separately
    # Worker class accepts nameserver_port as a keyword argument
    w = ClusteringPipelineWorker(
        nameserver="127.0.0.1",
        run_id=args.run_id,
        log_dir=args.log_dir,
        hpwl_ratio=args.hpwl_ratio,
        runtime_ratio=args.runtime_ratio,
        overflow_ratio=args.overflow_ratio,
        default_config=args.run_args,
        multiobj=args.multiobj,
        nameserver_port=args.nameserver_port,  # Pass port as keyword argument
    )
    w.run(background=False)
    exit(0)


# Master
print("Starting master process")
print(f"Master args: {args}")

# Create Log directory
os.makedirs(args.log_dir, exist_ok=True)
result_logger = hpres.json_result_logger(directory=args.log_dir, overwrite=True)

# Start a nameserver
# Use specified port or None (auto-select) to avoid conflicts
NS = hpns.NameServer(run_id=args.run_id, host="127.0.0.1", port=args.nameserver_port)
NS.start()

# Run an optimizer
if args.multiobj:
    motpe_params = {
        "init_method": "random",
        "num_initial_samples": 10,
        "num_candidates": 24,
        "gamma": 0.10,
    }
    bohb = MOBOHB(
        configspace=ClusteringPipelineWorker.get_configspace(args.cfgSearchFile),
        parameters=motpe_params,
        run_id=args.run_id,
        min_points_in_model=args.min_points_in_model,
        min_budget=args.min_budget,
        max_budget=args.max_budget,
        num_samples=args.n_samples,
        result_logger=result_logger,
        nameserver="127.0.0.1",
        nameserver_port=args.nameserver_port,  # Pass nameserver port to MOBOHB
    )
else:
    bohb = BOHB(
        configspace=ClusteringPipelineWorker.get_configspace(args.cfgSearchFile),
        run_id=args.run_id,
        min_points_in_model=args.min_points_in_model,
        min_budget=args.min_budget,
        max_budget=args.max_budget,
        num_samples=args.n_samples,
        result_logger=result_logger,
        nameserver="127.0.0.1",
        nameserver_port=args.nameserver_port,  # Pass nameserver port to BOHB
    )

print("\n" + "="*80)
print("Starting Hyperparameter Optimization")
print("="*80)
print(f"Configuration space: {ClusteringPipelineWorker.get_configspace(args.cfgSearchFile)}")
print(f"Number of iterations: {args.n_iterations}")
print(f"Number of workers: {args.n_workers}")
print(f"Multi-objective: {args.multiobj}")
print("="*80 + "\n")

res = bohb.run(n_iterations=args.n_iterations, min_n_workers=args.n_workers)

# Shutdown
bohb.shutdown(shutdown_workers=True)
NS.shutdown()

# Analysis
id2config = res.get_id2config_mapping()
incumbent = res.get_incumbent_id()

print("\n" + "="*80)
print("Optimization Completed!")
print("="*80)
print("A total of %i unique configurations were sampled." % len(id2config.keys()))
print("A total of %i runs were executed." % len(res.get_all_runs()))
all_runs = res.get_all_runs()
print(
    "The run took %.1f seconds to complete."
    % (all_runs[-1].time_stamps["finished"] - all_runs[0].time_stamps["started"])
)

# Get benchmark name for output
benchmark_name = "design"
if "benchmark_dir" in args.run_args:
    benchmark_name = os.path.basename(args.run_args["benchmark_dir"])

# Propose best configurations
result = hpres.logged_results_to_HBS_result(args.log_dir)

if args.multiobj:
    # Multi-objective: propose Pareto front
    candidates, paretos, df = get_candidates(result, num=args.num_pareto)
    print("\n" + "="*80)
    print("Pareto Candidates:")
    print("="*80)
    print(candidates.to_markdown())
    
    # Save Pareto configs
    dest = opj(args.log_dir, "best_cfgs")
    os.makedirs(dest, exist_ok=True)
    df.to_pickle(opj(dest, f"{benchmark_name}.dataframe.pkl"))
    
    for _, row in candidates.iterrows():
        cfg_id = "run-" + "_".join([s for s in re.findall(r"\b\d+\b", row["ID"])])
        print(f"\nCopying candidate {cfg_id}")
        src_cfg = opj(args.log_dir, cfg_id)
        dest_cfg = opj(dest, cfg_id)
        if os.path.exists(src_cfg):
            shutil.copytree(src_cfg, dest_cfg, dirs_exist_ok=True)
    
    # Plot Pareto curve
    plot_pareto(df, paretos, candidates, opj(dest, f"{benchmark_name}.pareto.png"))
    print(f"\nPareto curve saved to: {opj(dest, f'{benchmark_name}.pareto.png')}")
    
else:
    # Single objective: get best configuration
    all_runs = result.get_all_runs()
    id2config = res.get_id2config_mapping()
    best_run = None
    best_loss = float('inf')
    
    for run in all_runs:
        if run.loss < best_loss:
            best_loss = run.loss
            best_run = run
    
    if best_run:
        # Get configuration from id2config mapping
        best_config = id2config[best_run.config_id]['config']
        
        print("\n" + "="*80)
        print("Best Configuration:")
        print("="*80)
        print(f"Loss: {best_run.loss:.6f}")
        print(f"Info: {best_run.info}")
        print(f"Config: {best_config}")
        
        # Save best config
        dest = opj(args.log_dir, "best_cfgs")
        os.makedirs(dest, exist_ok=True)
        
        best_config_file = opj(dest, f"{benchmark_name}_best_config.json")
        with open(best_config_file, 'w') as f:
            json.dump(best_config, f, indent=2)
        print(f"\nBest config saved to: {best_config_file}")
        
        # Copy best run directory
        cfg_id = "run-" + "_".join([str(x) for x in best_run.config_id])
        src_cfg = opj(args.log_dir, cfg_id)
        dest_cfg = opj(dest, cfg_id)
        if os.path.exists(src_cfg):
            shutil.copytree(src_cfg, dest_cfg, dirs_exist_ok=True)
            print(f"Best run files copied to: {dest_cfg}")

print("\n" + "="*80)
print("All results saved to:", args.log_dir)
print("="*80)
