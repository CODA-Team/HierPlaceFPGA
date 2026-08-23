import os
import sys
import json
import subprocess
import tempfile
import re
from pathlib import Path
import logging

from hpbandster.core.worker import Worker

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tuner.tuner_configs import (
    CLUSTERING_BASE_CONFIG,
    CLUSTERING_BASE_PPA,
    CLUSTERING_BAD_RATIO,
    CLUSTERING_BEST_CFG,
)

import ConfigSpace as CS
import ConfigSpace.hyperparameters as CSH
from ConfigSpace.read_and_write import json as CS_JSON

opj = os.path.join


class ClusteringPipelineWorker(Worker):
    """Worker for tuning fpga_clustering_pipline_gift parameters"""
    
    def __init__(
        self,
        log_dir,
        *args,
        default_config,
        hpwl_ratio=1.0,
        runtime_ratio=0.5,
        overflow_ratio=0.5,
        multiobj=False,
        nameserver_port=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.log_dir = log_dir
        self.hpwl_ratio = hpwl_ratio
        self.runtime_ratio = runtime_ratio
        self.overflow_ratio = overflow_ratio
        self.multiobj = multiobj
        # Explicitly set nameserver_port if provided
        if nameserver_port is not None:
            self.nameserver_port = nameserver_port
        
        # Load best parameters if provided
        path_reuse = Path(default_config.get("reuse_params", ""))
        if path_reuse.suffix == ".json" and path_reuse.is_file():
            with path_reuse.open() as f:
                best_params = json.load(f)
        else:
            benchmark_name = default_config.get("reuse_params", "")
            best_params = CLUSTERING_BEST_CFG.get(benchmark_name, {})
        
        print(f"Reusing best parameters: {best_params}")
        self.default_config = {**CLUSTERING_BASE_CONFIG, **best_params, **default_config}
        
        # Setup PPA reference
        path_ppa = Path(default_config.get("base_ppa", ""))
        if path_ppa.suffix == ".json" and path_ppa.is_file():
            with path_ppa.open() as f:
                self.base_ppa = json.load(f)
        else:
            benchmark_name = default_config.get("base_ppa", "FPGA03")
            self.base_ppa = CLUSTERING_BASE_PPA.get(benchmark_name, CLUSTERING_BASE_PPA["FPGA03"])
        
        print(f"PPA reference: {self.base_ppa}")
        self.bad_run = {
            k: float(v * CLUSTERING_BAD_RATIO) for k, v in self.base_ppa.items()
        }
        
        # Path to run_complete_flow_with_json.py
        self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.run_script = opj(self.script_dir, "run_complete_flow_with_json_area.py")
        
        if not os.path.exists(self.run_script):
            raise FileNotFoundError(f"Cannot find run script: {self.run_script}")
    
    def _create_config_json(self, config, output_dir):
        """Create a JSON config file with tuned parameters"""
        # Merge default config with tuned parameters
        full_config = {**self.default_config, **config}
        
        # Structure the config in the expected format
        structured_config = {
            "benchmark_dir": full_config["benchmark_dir"],
            "output_dir": output_dir,
            "aux": full_config.get("aux"),
            "dreamplace_path": full_config["dreamplace_path"],
            "clustering": {
                "top_k": full_config.get("top_k", 5),
                "min_cluster_size": int(full_config.get("min_cluster_size", 50)),
                "resolution": float(full_config.get("resolution", 1.0)),
                "gift_scale": float(full_config.get("gift_scale", 0.5)),
                "ub_factor": int(full_config.get("ub_factor", 10)),
                "num_trees": int(full_config.get("num_trees", 5)),
                "best_solns": int(full_config.get("best_solns", 5)),
                "max_cluster_size": int(full_config.get("max_cluster_size", 2000)),
            },
            "cluster_placement": {
                "run_cluster_placement": full_config.get("run_cluster_placement", True),
                "cluster_iteration": int(full_config.get("cluster_iteration", 1000)),
                "place_density_lb_addon": float(full_config.get("place_density_lb_addon", 1.5)),
                "sigma_ratio": float(full_config.get("sigma_ratio", 0.9)),
                "gpu": int(full_config.get("gpu", 0)),
                "cluster_base_weight": float(full_config.get("cluster_base_weight", 1.0)),
                "cluster_fixed_cluster_weight": float(full_config.get("cluster_fixed_cluster_weight", 5.0)),
                "cluster_random_seed": int(full_config.get("cluster_random_seed", 5000)),
                "max_fanout": int(full_config.get("max_fanout", 200)),
            },
            "net_reweighting": {
                "intra_sub": float(full_config.get("intra_sub", 1.2)),
                "intra": float(full_config.get("intra", 1.0)),
                "inter": float(full_config.get("inter", 0.8)),
            },
            "final_placement": {
                "final_iteration": int(full_config.get("final_iteration", 2000)),
                "learning_rate": float(full_config.get("learning_rate", 0.01)),
                "net_weight_anneal_iters": int(full_config.get("net_weight_anneal_iters", 200)),
                "density_weight": float(full_config.get("density_weight", 0.602)),
                "node_area_adjust_overflow": float(full_config.get("node_area_adjust_overflow", 0.15)),
                "random_seed": int(full_config.get("random_seed", 500)),
                "gamma": float(full_config.get("gamma", 1.155)),
            },
            "misc": {
                "visualize": full_config.get("visualize", False),
                "run_final_placement": full_config.get("run_final_placement", True),
                "skip_clustering": full_config.get("skip_clustering", False),
            }
        }
        
        return structured_config
    
    def _parse_output(self, output_dir):
        """Parse the results from the flow output"""
        results = {}
        
        # Try to find the final placement log
        final_log = opj(output_dir, "4_final_input", "final_placement.log")
        if not os.path.exists(final_log):
            # Alternative location
            results_dir = opj(output_dir, "4_final_input", "results")
            if os.path.exists(results_dir):
                for f in os.listdir(results_dir):
                    if f.endswith(".log"):
                        final_log = opj(results_dir, f)
                        break
        
        if os.path.exists(final_log):
            with open(final_log, 'r') as f:
                log_content = f.read()
                
                # Extract HPWL from the last iteration (format: iter: XXX, HPWL Y.YYYE+ZZ)
                # This ensures we get the actual last iteration value, not stopping criteria values
                # Match only standard iteration lines: "iter: XXX, HPWL Y.YYYE+ZZ" (with comma after iter number)
                iter_hpwl_matches = re.findall(r'iter:\s*\d+,.*?HPWL\s+([\d.e+]+)', log_content, re.IGNORECASE)
                if iter_hpwl_matches:
                    # Use the last iteration's HPWL value
                    results['hpwl'] = float(iter_hpwl_matches[-1])
                else:
                    # Fallback: try general HPWL pattern (but prefer iteration-based)
                    hpwl_matches = re.findall(r'HPWL[:\s]*([\d.e+]+)', log_content, re.IGNORECASE)
                    if hpwl_matches:
                        results['hpwl'] = float(hpwl_matches[-1])
                
                # Extract overflow from the last iteration (format: Overflow [val1, val2, val3, val4])
                overflow_arrays = re.findall(r'Overflow\s*\[([^\]]+)\]', log_content, re.IGNORECASE)
                if overflow_arrays:
                    # Get the last overflow array (from final iteration)
                    last_overflow_str = overflow_arrays[-1]
                    # Parse the array values
                    overflow_values = [float(x.strip()) for x in last_overflow_str.split(',')]
                    # Use maximum overflow value (worst case)
                    results['overflow'] = max(overflow_values)
                else:
                    # Fallback: try to match single overflow value
                    overflow_match = re.search(r'overflow[:\s]*([\d.e+\-]+)', log_content, re.IGNORECASE)
                    if overflow_match:
                        results['overflow'] = float(overflow_match.group(1))
        
        # If we didn't find HPWL, try to get it from the placement file
        if 'hpwl' not in results:
            # Look for placement results in the output directory
            pl_file = opj(output_dir, "4_final_input", "results", "design.pl")
            if os.path.exists(pl_file):
                # At least we know the flow completed
                results['hpwl'] = self.base_ppa['hpwl']  # Use baseline as fallback
        
        return results
    
    def compute(self, config_id, config, budget, working_directory, **kwargs):
        """Run the clustering pipeline with given configuration"""
        config_identifier = "run-" + "_".join([str(x) for x in config_id])
        
        working_directory = opj(self.log_dir, config_identifier)
        os.makedirs(working_directory, exist_ok=True)
        
        # Convert to absolute path to avoid path issues
        working_directory = os.path.abspath(working_directory)
        
        # Create config JSON
        config_dict = self._create_config_json(config, working_directory)
        config_file = opj(working_directory, "params.json")
        with open(config_file, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        # Setup logging
        log_file = opj(working_directory, "flow.log")
        
        # Run the flow
        cmd = [
            sys.executable,
            self.run_script,
            "--params_json", config_file
        ]
        
        print(f"Running: {' '.join(cmd)}")
        
        import time
        start_time = time.time()
        
        try:
            with open(log_file, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=self.script_dir
                    # No timeout - let it run as long as needed
                )
            
            runtime = time.time() - start_time
            
            if result.returncode != 0:
                print(f"Warning: Flow returned non-zero exit code: {result.returncode}")
                ppa = self.bad_run.copy()
                ppa['runtime'] = runtime
            else:
                # Parse results
                parsed_results = self._parse_output(working_directory)
                ppa = {
                    'hpwl': parsed_results.get('hpwl', self.bad_run['hpwl']),
                    'overflow': parsed_results.get('overflow', self.bad_run['overflow']),
                    'runtime': runtime
                }
                
                # Check if results are valid
                if ppa['hpwl'] == float('inf') or ppa['hpwl'] <= 0:
                    ppa = self.bad_run.copy()
                    ppa['runtime'] = runtime
        
        except subprocess.TimeoutExpired:
            print(f"Warning: Flow timed out")
            runtime = time.time() - start_time
            ppa = self.bad_run.copy()
            ppa['runtime'] = runtime
        
        except Exception as e:
            print(f"Error running flow: {e}")
            runtime = time.time() - start_time
            ppa = self.bad_run.copy()
            ppa['runtime'] = runtime
        
        # Normalize metrics
        hpwl_norm = ppa['hpwl'] / self.base_ppa['hpwl']
        overflow_norm = ppa.get('overflow', 0.1) / self.base_ppa.get('overflow', 0.15)
        runtime_norm = ppa['runtime'] / self.base_ppa['runtime']
        
        if self.multiobj:
            return {
                "loss": (hpwl_norm, overflow_norm, runtime_norm),
                "info": ppa,
            }
        else:
            # Single objective: weighted combination
            cost = (
                self.hpwl_ratio * hpwl_norm
                + self.overflow_ratio * overflow_norm
                + self.runtime_ratio * runtime_norm
            )
            ppa.update({"cost": float(cost)})
            return {
                "loss": float(cost),
                "info": ppa,
            }
    
    @staticmethod
    def get_configspace(config_file: str, seed=None):
        """Define the configuration space for tuning"""
        # Read JSON config if provided
        if config_file and os.path.isfile(config_file):
            with open(config_file, "r") as f:
                cs = CS_JSON.read(f.read())
                cs.seed(seed)
            return cs
        
        # Otherwise, setup default config space
        cs = CS.ConfigurationSpace(seed)
        
        # Clustering parameters
        min_cluster_size = CSH.UniformIntegerHyperparameter(
            "min_cluster_size", lower=30, upper=100, default_value=50
        )
        resolution = CSH.UniformFloatHyperparameter(
            "resolution", lower=0.5, upper=2.0, default_value=1.0
        )
        gift_scale = CSH.UniformFloatHyperparameter(
            "gift_scale", lower=0.3, upper=0.8, default_value=0.5
        )
        
        # Clustering parameters (additional)
        best_solns = CSH.UniformIntegerHyperparameter(
            "best_solns", lower=3, upper=6, default_value=5
        )
        max_cluster_size = CSH.CategoricalHyperparameter(
            "max_cluster_size",
            choices=[500, 1000, 1500, 2000, 2500, 3000],
            default_value=2000
        )
        ub_factor = CSH.UniformIntegerHyperparameter(
            "ub_factor", lower=5, upper=20, default_value=10
        )
        
        # Cluster placement parameters
        max_fanout = CSH.CategoricalHyperparameter(
            "max_fanout", choices=[100, 200, 300, 400], default_value=200
        )
        place_density_lb_addon = CSH.UniformFloatHyperparameter(
            "place_density_lb_addon", lower=1.0, upper=3.0, default_value=1.5
        )
        sigma_ratio = CSH.UniformFloatHyperparameter(
            "sigma_ratio", lower=0.2, upper=1.0, default_value=0.9
        )
        cluster_base_weight = CSH.UniformFloatHyperparameter(
            "cluster_base_weight", lower=0.1, upper=5.0, default_value=1.0
        )
        cluster_fixed_cluster_weight = CSH.UniformFloatHyperparameter(
            "cluster_fixed_cluster_weight", lower=1.0, upper=60.0, default_value=5.0
        )
        
        # Net reweighting parameters
        intra_sub = CSH.UniformFloatHyperparameter(
            "intra_sub", lower=1.0, upper=2.0, default_value=1.2
        )
        intra = CSH.UniformFloatHyperparameter(
            "intra", lower=0.8, upper=1.3, default_value=1.0
        )
        inter = CSH.UniformFloatHyperparameter(
            "inter", lower=0.5, upper=1.0, default_value=0.8
        )
        
        # Final placement parameters
        learning_rate = CSH.UniformFloatHyperparameter(
            "learning_rate", lower=0.001, upper=0.05, default_value=0.01, log=True
        )
        net_weight_anneal_iters = CSH.CategoricalHyperparameter(
            "net_weight_anneal_iters",
            choices=[50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700],
            default_value=200
        )
        
        # Add all hyperparameters to the configuration space
        cs.add_hyperparameters([
            best_solns,
            max_fanout,
            min_cluster_size,
            resolution,
            gift_scale,
            ub_factor,
            max_cluster_size,
            place_density_lb_addon,
            sigma_ratio,
            cluster_base_weight,
            cluster_fixed_cluster_weight,
            intra_sub,
            intra,
            inter,
            learning_rate,
            net_weight_anneal_iters,
        ])
        
        return cs


# Keep alias for backward compatibility
AutoDMPWorker = ClusteringPipelineWorker
