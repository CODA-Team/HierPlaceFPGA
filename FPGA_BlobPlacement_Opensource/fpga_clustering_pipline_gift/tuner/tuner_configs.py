# Clustering Pipeline Tuner Configuration
# This file defines the base configuration for fpga_clustering_pipline_gift parameter tuning

# Base configuration structure matching run_complete_flow_params_template.json
CLUSTERING_BASE_CONFIG = {
    "benchmark_dir": "",
    "output_dir": "",
    "aux": None,
    "dreamplace_path": "",
    
    # Clustering parameters
    "top_k": 5,
    "min_cluster_size": 50,
    "resolution": 1.0,
    "gift_scale": 0.5,
    "ub_factor": 10,
    "num_trees": 5,
    "best_solns": 5,
    "max_cluster_size": 2000,
    
    # Cluster placement parameters
    "run_cluster_placement": True,
    "cluster_iteration": 1000,
    "place_density_lb_addon": 1.5,
    "sigma_ratio": 0.9,
    "gpu": 0,
    "cluster_base_weight": 1.0,
    "cluster_fixed_cluster_weight": 5.0,
    "cluster_random_seed": 5000,
    "max_fanout": 200,
    
    # Net reweighting parameters
    "intra_sub": 1.2,
    "intra": 1.0,
    "inter": 0.8,
    
    # Final placement parameters
    "final_iteration": 2000,
    "learning_rate": 0.01,
    "net_weight_anneal_iters": 200,
    "density_weight": 0.602,
    "node_area_adjust_overflow": 0.15,
    "random_seed": 500,
    "gamma": 6.5,
    
    # Misc parameters
    "visualize": False,
    "run_final_placement": True,
    "skip_clustering": False,
}


# Cost ratio for bad runs (when flow fails)
CLUSTERING_BAD_RATIO = 10


# Base PPA (Performance, Power, Area) metrics for normalization
# Updated HPWL values from user-provided PPA results
CLUSTERING_BASE_PPA = {
    "FPGA01": {
        "hpwl": 2.18e5,      # HPWL: 2.18E+05
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA02": {
        "hpwl": 4.88e5,      # HPWL: 4.88E+05
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA03": {
        "hpwl": 2.02e6,      # HPWL: 2.02E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA04": {
        "hpwl": 4.02e6,      # HPWL: 4.02E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA05": {
        "hpwl": 7.99e6,      # HPWL: 7.99E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA06": {
        "hpwl": 3.39e6,      # HPWL: 3.39E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA07": {
        "hpwl": 6.24e6,      # HPWL: 6.24E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA08": {
        "hpwl": 6.60e6,      # HPWL: 6.60E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA09": {
        "hpwl": 8.07e6,      # HPWL: 8.07E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA10": {
        "hpwl": 3.31e6,      # HPWL: 3.31E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA11": {
        "hpwl": 8.96e6,      # HPWL: 8.96E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
    "FPGA12": {
        "hpwl": 4.29e6,      # HPWL: 4.29E+06
        "runtime": 1200,     # 20 minutes
        "overflow": 0.15,
    },
}


# Best found configurations (optional)
# This will be populated after tuning runs
CLUSTERING_BEST_CFG = {
    "FPGA03": {
        # Clustering parameters
        "min_cluster_size": 50,
        "resolution": 1.0,
        "gift_scale": 0.5,
        "ub_factor": 10,
        
        # Cluster placement parameters
        "cluster_iteration": 1000,
        "place_density_lb_addon": 1.5,
        "sigma_ratio": 0.9,
        "cluster_base_weight": 1.0,
        "cluster_fixed_cluster_weight": 50.0,
        
        # Net reweighting parameters
        "intra_sub": 1.2,
        "intra": 1.0,
        "inter": 0.8,
        
        # Final placement parameters
        "final_iteration": 2000,
        "learning_rate": 0.01,
    },
}
