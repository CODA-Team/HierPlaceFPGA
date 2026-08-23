#!/usr/bin/env python3
"""Adaptive parameter selection for the FPGA clustering pipeline.

Given a new design, automatically selects good pipeline parameters based on
design characteristics using K=3 nearest-neighbor interpolation from 12 known
ISPD2016 benchmark profiles stored in adaptive_profiles.json.

Usage (standalone smoke test):
    python adaptive_params.py --benchmark_dir data/ispd2016/FPGA03

Usage (from pipeline):
    from adaptive_params import compute_adaptive_params
    params = compute_adaptive_params(benchmark_dir)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

_PROFILES_CACHE: Optional[dict] = None
_PROFILES_CACHE_PATH: Optional[str] = None


def _default_profiles_path() -> str:
    """Return the path to adaptive_profiles.json next to this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "adaptive_profiles.json")


def _load_profiles(profiles_path: Optional[str] = None) -> dict:
    """Load benchmark profiles from JSON.  Cached for the session."""
    global _PROFILES_CACHE, _PROFILES_CACHE_PATH
    path = profiles_path or _default_profiles_path()
    if _PROFILES_CACHE is not None and _PROFILES_CACHE_PATH == path:
        return _PROFILES_CACHE
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _PROFILES_CACHE = data
    _PROFILES_CACHE_PATH = path
    return data


# ---------------------------------------------------------------------------
# Design feature extraction
# ---------------------------------------------------------------------------

# Node type classification
_FF_TYPES = {"FDRE", "FDSE", "FDCE", "FDPE", "SEQ"}
_DSP_TYPES = {"DSP48E2", "DSP48E1", "DSP"}
_BRAM_TYPES = {"RAMB36E2", "RAMB18E2", "RAMB36E1", "RAMB18E1", "RAMA", "RAMB"}
_IO_TYPES = {"IBUF", "OBUF", "BUFGCE", "BUFG", "IBUFDS", "OBUFDS", "IOA", "IOB", "GCLK", "IPPIN"}
_LUT_PATTERN = re.compile(r"^LUT\d")


def extract_design_features(benchmark_dir: str) -> Dict[str, int]:
    """Lightweight parser: reads .nodes and .nets to extract design features.

    Returns dict with keys:
        num_nodes, num_lut, num_ff, num_dsp, num_bram, num_io,
        num_nets, num_hf_nets
    """
    # --- Find the .nodes file ---
    nodes_file = _find_file(benchmark_dir, ".nodes")
    nets_file = _find_file(benchmark_dir, ".nets")

    num_nodes = 0
    num_lut = 0
    num_ff = 0
    num_dsp = 0
    num_bram = 0
    num_io = 0

    with open(nodes_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("UCLA"):
                continue
            # Header lines like "NumNodes : 105273"
            if line.startswith("NumNodes") or line.startswith("NumTerminals"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            cell_type = parts[1]
            num_nodes += 1
            if _LUT_PATTERN.match(cell_type):
                num_lut += 1
            elif cell_type in _FF_TYPES:
                num_ff += 1
            elif cell_type in _DSP_TYPES:
                num_dsp += 1
            elif cell_type in _BRAM_TYPES:
                num_bram += 1
            elif cell_type in _IO_TYPES:
                num_io += 1

    # --- Parse .nets file for net count and high-fanout ---
    num_nets = 0
    num_hf_nets = 0
    hf_threshold = 500

    with open(nets_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("UCLA"):
                continue
            if line.startswith("NumNets") or line.startswith("NumPins"):
                continue
            # Net header lines: "net <name> <degree>"
            if line.startswith("net "):
                parts = line.split()
                if len(parts) >= 3:
                    num_nets += 1
                    try:
                        # public_release net headers can append attributes, e.g. "net n 123 clock".
                        degree = int(parts[2])
                        if degree > hf_threshold:
                            num_hf_nets += 1
                    except ValueError:
                        pass

    return {
        "num_nodes": num_nodes,
        "num_lut": num_lut,
        "num_ff": num_ff,
        "num_dsp": num_dsp,
        "num_bram": num_bram,
        "num_io": num_io,
        "num_nets": num_nets,
        "num_hf_nets": num_hf_nets,
    }


def _find_file(benchmark_dir: str, extension: str) -> str:
    """Find a file with given extension in the benchmark directory."""
    for fname in os.listdir(benchmark_dir):
        if fname.endswith(extension):
            return os.path.join(benchmark_dir, fname)
    raise FileNotFoundError(
        f"No {extension} file found in {benchmark_dir}")


# ---------------------------------------------------------------------------
# KNN adaptive parameter computation
# ---------------------------------------------------------------------------

# Parameters that use nearest-neighbor only (categorical / too noisy)
_NEAREST_ONLY = {"density_weight", "max_fanout", "max_cluster_size"}

# Parameters interpolated in log-space
_LOG_SPACE = {"learning_rate"}

# Parameters rounded to nearest 50
_ROUND_50 = {"net_weight_anneal_iters"}

# Integer parameters (round after weighted average)
_INTEGER = {"min_cluster_size", "ub_factor", "best_solns",
            "max_cluster_size", "max_fanout", "net_weight_anneal_iters"}

# Feature weights for distance computation
_FEATURE_WEIGHTS = {
    "num_nodes": 3.0,  # dominant design-size signal
    "ff_lut_ratio": 1.0,  # design structure
    "num_macros": 1.0,  # macro complexity
}

K = 3  # number of nearest neighbors
EPSILON = 1e-9  # avoid division by zero


def _feature_vector(features: Dict[str, int]) -> List[float]:
    """Compute the normalized, weighted feature vector."""
    num_nodes_norm = features["num_nodes"] / 1e6
    ff = features.get("num_ff", 0)
    lut = features.get("num_lut", 1)  # avoid div-by-zero
    ff_lut_ratio = ff / max(lut, 1)
    num_macros = (features.get("num_dsp", 0) + features.get("num_bram", 0))
    num_macros_norm = num_macros / 2000.0

    return [
        num_nodes_norm * _FEATURE_WEIGHTS["num_nodes"],
        ff_lut_ratio * _FEATURE_WEIGHTS["ff_lut_ratio"],
        num_macros_norm * _FEATURE_WEIGHTS["num_macros"],
    ]


def _euclidean_distance(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def compute_adaptive_params(
    benchmark_dir: str,
    profiles_path: Optional[str] = None,
) -> dict:
    """Main entry point: compute adaptive parameters for a new design.

    1. Loads profiles from adaptive_profiles.json
    2. Extracts features from the design
    3. Finds K=3 nearest benchmarks by weighted Euclidean distance
    4. Interpolates parameters using inverse-distance weighting

    Returns a flat dict of parameter names -> values.
    """
    profiles = _load_profiles(profiles_path)
    features = extract_design_features(benchmark_dir)
    query_vec = _feature_vector(features)

    # Compute distances to all known benchmarks
    distances: List[Tuple[str, float]] = []
    for name, profile in profiles.items():
        prof_vec = _feature_vector(profile["features"])
        dist = _euclidean_distance(query_vec, prof_vec)
        distances.append((name, dist))

    distances.sort(key=lambda x: x[1])

    # Take K nearest
    nearest = distances[:K]
    nearest_names = [n for n, _ in nearest]
    nearest_dists = [d for _, d in nearest]

    # Compute inverse-distance weights
    raw_weights = [1.0 / (d + EPSILON) for d in nearest_dists]
    total_weight = sum(raw_weights)
    weights = [w / total_weight for w in raw_weights]

    # Collect best_params from nearest neighbors
    neighbor_params = [profiles[name]["best_params"] for name in nearest_names]

    # Get the full set of parameter keys from the nearest neighbor
    all_keys = set()
    for p in neighbor_params:
        all_keys.update(p.keys())

    # Interpolate each parameter
    result = {}
    for key in sorted(all_keys):
        if key in _NEAREST_ONLY:
            # Use nearest neighbor's value only
            result[key] = neighbor_params[0][key]
        elif key in _LOG_SPACE:
            # Weighted average in log-space
            log_vals = []
            ws = []
            for i, p in enumerate(neighbor_params):
                if key in p and p[key] > 0:
                    log_vals.append(math.log(p[key]))
                    ws.append(weights[i])
            if log_vals:
                w_total = sum(ws)
                log_avg = sum(lv * w for lv, w in zip(log_vals, ws)) / w_total
                result[key] = math.exp(log_avg)
            else:
                result[key] = neighbor_params[0].get(key, 0.01)
        else:
            # Weighted average
            vals = []
            ws = []
            for i, p in enumerate(neighbor_params):
                if key in p:
                    vals.append(p[key])
                    ws.append(weights[i])
            if vals:
                w_total = sum(ws)
                avg = sum(v * w for v, w in zip(vals, ws)) / w_total
            else:
                avg = neighbor_params[0].get(key, 0)
            result[key] = avg

    # Post-process: rounding
    for key in _ROUND_50:
        if key in result:
            result[key] = int(round(result[key] / 50.0) * 50)

    for key in _INTEGER:
        if key in result:
            result[key] = max(1, int(round(result[key])))

    # Round float params to reasonable precision
    for key in result:
        if isinstance(result[key], float):
            result[key] = round(result[key], 4)

    # --- Print summary ---
    _print_summary(features, nearest_names, nearest_dists, weights, result)

    return result


def _print_summary(
    features: dict,
    nearest_names: List[str],
    nearest_dists: List[float],
    weights: List[float],
    params: dict,
):
    """Print a human-readable summary of adaptive parameter selection."""
    print("\n" + "=" * 70)
    print("[adaptive] Adaptive Parameter Selection")
    print("=" * 70)

    print("\nDesign features:")
    print(f"  num_nodes   = {features['num_nodes']:>10,}")
    print(f"  num_lut     = {features['num_lut']:>10,}")
    print(f"  num_ff      = {features['num_ff']:>10,}")
    print(f"  num_dsp     = {features['num_dsp']:>10,}")
    print(f"  num_bram    = {features['num_bram']:>10,}")
    ff_lut = features['num_ff'] / max(features['num_lut'], 1)
    macros = features['num_dsp'] + features['num_bram']
    print(f"  ff/lut      = {ff_lut:>10.3f}")
    print(f"  macros      = {macros:>10,}")
    print(f"  num_nets    = {features['num_nets']:>10,}")
    print(f"  num_hf_nets = {features['num_hf_nets']:>10,}")

    print(f"\nK={K} nearest benchmarks:")
    for i, (name, dist) in enumerate(zip(nearest_names, nearest_dists)):
        print(f"  {i+1}. {name:8s}  dist={dist:.4f}  weight={weights[i]:.4f}")

    print("\nSelected parameters:")
    # Group for readability
    groups = [
        ("Clustering", ["min_cluster_size", "resolution", "gift_scale",
                        "ub_factor", "best_solns", "max_cluster_size"]),
        ("Cluster Placement", ["max_fanout", "sigma_ratio",
                               "cluster_base_weight",
                               "cluster_fixed_cluster_weight",
                               "place_density_lb_addon"]),
        ("Net Reweighting", ["intra_sub", "intra", "inter"]),
        ("Final Placement", ["learning_rate", "density_weight", "gamma",
                             "net_weight_anneal_iters"]),
    ]
    for group_name, keys in groups:
        print(f"  [{group_name}]")
        for key in keys:
            if key in params:
                val = params[key]
                tag = ""
                if key in _NEAREST_ONLY:
                    tag = "  (nearest)"
                elif key in _LOG_SPACE:
                    tag = "  (log-interp)"
                print(f"    {key:36s} = {val}{tag}")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Adaptive parameter selection smoke test")
    parser.add_argument("--benchmark_dir", type=str, required=True,
                        help="Path to FPGA benchmark directory")
    parser.add_argument("--profiles", type=str, default=None,
                        help="Path to custom adaptive_profiles.json")
    args = parser.parse_args()

    params = compute_adaptive_params(args.benchmark_dir, args.profiles)

    # Also dump as JSON for easy inspection
    print("JSON output:")
    print(json.dumps(params, indent=2))


if __name__ == "__main__":
    main()
