#!/usr/bin/env python3
"""
UB sweep compare (baseline vs ML-guided) with multi-seed evaluation.

For each UB in [ub_start, ub_end]:
1) run HyperCutNet inference (per UB or once-for-all)
2) run guided TritonPart for a seed set
3) run baseline TritonPart for the same seed set
4) compare BEST cutsize (minimum) of guided vs baseline
5) write CSV summary (with best seed and per-seed cuts)
"""

from __future__ import annotations

import argparse
import contextlib
import concurrent.futures
import csv
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False


@dataclass
class RunResult:
    ub: int
    mode: str
    seed: int
    returncode: int
    cutsize: Optional[int]
    part_file: Optional[Path]
    log_file: Path
    elapsed_sec: float


def parse_hgr(hgr_path: Path) -> Tuple[int, int, int, List[List[int]]]:
    lines = [ln.strip() for ln in hgr_path.read_text().splitlines() if ln.strip()]
    header = lines[0].split()
    num_nets = int(header[0])
    num_nodes = int(header[1])
    fmt = int(header[2]) if len(header) > 2 else 0
    edge_weighted = fmt in (1, 11)

    nets: List[List[int]] = []
    for i in range(1, num_nets + 1):
        toks = lines[i].split()
        if not toks:
            nets.append([])
            continue
        pins = toks[1:] if edge_weighted else toks
        nets.append([int(x) for x in pins])
    return num_nets, num_nodes, fmt, nets


def compute_cutsize(nets: List[List[int]], part_vector: List[int]) -> int:
    cut = 0
    for pins in nets:
        if len(pins) < 2:
            continue
        parts = {part_vector[p - 1] for p in pins}
        if len(parts) > 1:
            cut += 1
    return cut


def make_tcl(
    tcl_path: Path,
    hgr_file: Path,
    num_parts: int,
    ub: int,
    seed: int,
    cut_prob_file: Optional[Path] = None,
    guide_coarsening: Optional[int] = None,
    guide_refinement: Optional[int] = None,
    guide_cutoverlay: Optional[int] = None,
) -> None:
    cmd = [
        "triton_part_hypergraph",
        f"-hypergraph_file {{{hgr_file}}}",
        f"-num_parts {num_parts}",
        f"-balance_constraint {ub}",
        f"-seed {seed}",
    ]
    if cut_prob_file is not None:
        cmd.append(f"-cut_prob_file {{{cut_prob_file}}}")
    if guide_coarsening is not None:
        cmd.append(f"-guide_coarsening {guide_coarsening}")
    if guide_refinement is not None:
        cmd.append(f"-guide_refinement {guide_refinement}")
    if guide_cutoverlay is not None:
        cmd.append(f"-guide_cutoverlay {guide_cutoverlay}")
    tcl_path.write_text(" \\\n+  ".join(cmd) + "\nexit\n")


def build_openroad_env(args: argparse.Namespace) -> Dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "USER": os.environ.get("USER", ""),
        "PATH": "/usr/bin:/bin",
        "LD_LIBRARY_PATH": args.ld_library_path,
        "LD_PRELOAD": args.ld_preload,
        "TCL_LIBRARY": os.environ.get("TCL_LIBRARY", ""),
        "OPENROAD_LAUNCHER": os.environ.get("OPENROAD_LAUNCHER", ""),
    }


def resolve_external_cutprob_file(external_cutprob_dir: Path, ub: int) -> Path:
    return external_cutprob_dir / f"cut_prob_ub{ub:02d}.txt"


def run_openroad(
    openroad_bin: Path,
    tcl_path: Path,
    log_path: Path,
    env: Dict[str, str],
    cwd: Optional[Path] = None,
) -> Tuple[int, float]:
    launcher = env.get("OPENROAD_LAUNCHER", "").strip()
    if launcher:
        cmd = [launcher, str(openroad_bin), str(tcl_path)]
    else:
        cmd = [str(openroad_bin), "-no_init", "-exit", str(tcl_path)]
    t0 = time.perf_counter()
    with log_path.open("w") as logf:
        p = subprocess.run(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
        )
    return p.returncode, time.perf_counter() - t0


def run_inference_for_ub(
    args: argparse.Namespace,
    ub: int,
    cut_prob_out: Path,
    infer_log: Path,
) -> Tuple[int, float]:
    cmd = [
        args.infer_python,
        str(args.inference_script),
        "--graph_dir",
        str(args.graph_dir),
        "--checkpoint",
        str(args.checkpoint),
        "-o",
        str(cut_prob_out),
        "--ub_factor",
        str(ub),
        "--ub_max",
        str(args.ub_max),
    ]
    if args.use_node2vec_disk_cache:
        cmd.append("--use_node2vec_disk_cache")

    launcher = os.environ.get("INFERENCE_LAUNCHER", "").strip()
    if launcher:
        cmd = [launcher, *cmd]

    t0 = time.perf_counter()
    with infer_log.open("w") as logf:
        p = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, text=True)
    return p.returncode, time.perf_counter() - t0


def parse_infer_timing(infer_log: Optional[Path]) -> Dict[str, float]:
    if infer_log is None or not infer_log.exists():
        return {}
    timing: Dict[str, float] = {}
    try:
        for line in infer_log.read_text(errors="replace").splitlines():
            if not line.startswith("TIMING_JSON "):
                continue
            payload = line[len("TIMING_JSON "):].strip()
            data = json.loads(payload)
            timing = {
                str(k): float(v)
                for k, v in data.items()
                if isinstance(v, (int, float))
            }
    except Exception:
        return {}
    return timing


def load_run_inference_fn(inference_script: Path):
    spec = importlib.util.spec_from_file_location("hypercutnet_inference", str(inference_script))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load inference module from {inference_script}")
    module = importlib.util.module_from_spec(spec)
    module_dir = str(inference_script.parent)
    sys.path.insert(0, module_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == module_dir:
            sys.path.pop(0)
    if not hasattr(module, "run_inference"):
        raise RuntimeError("inference module has no run_inference()")
    return module.run_inference


def run_inference_for_ub_inprocess(
    args: argparse.Namespace,
    ub: int,
    cut_prob_out: Path,
    infer_log: Path,
    run_inference_fn,
) -> Tuple[int, float]:
    base_kwargs = {
        "graph_dir": str(args.graph_dir),
        "checkpoint_path": str(args.checkpoint),
        "output_path": str(cut_prob_out),
        "ub_factor": ub,
        "ub_max": args.ub_max,
        "use_node2vec_disk_cache": args.use_node2vec_disk_cache,
        "use_node2vec": args.use_node2vec,
        "use_pagerank": args.use_pagerank,
        "use_ubfactor": args.use_ubfactor,
        "ub_isolate": args.ub_isolate,
        "hidden_dim": args.hidden_dim,
        "layers": args.layers,
    }
    sig = inspect.signature(run_inference_fn)
    accepts_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_var_kw:
        call_kwargs = base_kwargs
    else:
        call_kwargs = {k: v for k, v in base_kwargs.items() if k in sig.parameters}

    t0 = time.perf_counter()
    rc = 0
    with infer_log.open("w") as logf, contextlib.redirect_stdout(logf), contextlib.redirect_stderr(logf):
        try:
            run_inference_fn(**call_kwargs)
        except Exception as e:
            print(f"[ERROR] in-process inference failed at UB={ub}: {e}")
            rc = 1
    return rc, time.perf_counter() - t0


def load_part(part_path: Path, expected_n: int) -> Optional[List[int]]:
    if not part_path.exists():
        return None
    vec = [int(ln.strip()) for ln in part_path.read_text().splitlines() if ln.strip()]
    if len(vec) != expected_n:
        return None
    return vec


def one_mode(
    ub: int,
    mode: str,
    seed: int,
    openroad_bin: Path,
    hgr_file: Path,
    num_parts: int,
    tcl_dir: Path,
    log_dir: Path,
    part_dir: Path,
    work_root: Path,
    nets: List[List[int]],
    num_nodes: int,
    env: Dict[str, str],
    cut_prob_file: Optional[Path],
    guide_coarsening: Optional[int] = None,
    guide_refinement: Optional[int] = None,
    guide_cutoverlay: Optional[int] = None,
) -> RunResult:
    tag = f"{mode}_ub{ub:02d}_seed{seed}"
    tcl_path = tcl_dir / f"{tag}.tcl"
    log_path = log_dir / f"{tag}.log"

    work_dir = Path(tempfile.mkdtemp(prefix=f"{tag}_", dir=str(work_root)))
    local_hgr = work_dir / hgr_file.name
    shutil.copy2(hgr_file, local_hgr)

    cut_prob_abs = cut_prob_file.resolve() if cut_prob_file is not None else None
    make_tcl(
        tcl_path,
        local_hgr.resolve(),
        num_parts,
        ub,
        seed,
        cut_prob_file=cut_prob_abs,
        guide_coarsening=guide_coarsening,
        guide_refinement=guide_refinement,
        guide_cutoverlay=guide_cutoverlay,
    )

    rc, elapsed = run_openroad(openroad_bin, tcl_path, log_path, env, cwd=work_dir)

    generated = Path(f"{local_hgr}.part.{num_parts}")
    saved_part = part_dir / f"{tag}.part.{num_parts}"
    cutsize: Optional[int] = None

    if generated.exists():
        shutil.copy2(generated, saved_part)
        vec = load_part(saved_part, num_nodes)
        if vec is not None:
            cutsize = compute_cutsize(nets, vec)
        generated.unlink(missing_ok=True)

    shutil.rmtree(work_dir, ignore_errors=True)

    return RunResult(
        ub=ub,
        mode=mode,
        seed=seed,
        returncode=rc,
        cutsize=cutsize,
        part_file=saved_part if saved_part.exists() else None,
        log_file=log_path,
        elapsed_sec=elapsed,
    )


def parse_seed_list(args: argparse.Namespace) -> List[int]:
    if args.seeds:
        return [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    return [args.seed_start + i * args.seed_step for i in range(args.num_seeds)]


def choose_best(results: List[RunResult]) -> Optional[RunResult]:
    valid = [r for r in results if r.cutsize is not None]
    if not valid:
        return None
    return min(valid, key=lambda r: (r.cutsize, r.seed))


def fmt_seed_cuts(results: List[RunResult]) -> str:
    parts = []
    for r in sorted(results, key=lambda x: x.seed):
        parts.append(f"{r.seed}:{r.cutsize if r.cutsize is not None else 'None'}")
    return ";".join(parts)


def plot_results(csv_path: Path, out_dir: Path, benchmark_name: str = "") -> Optional[Path]:
    if not _MATPLOTLIB_AVAILABLE:
        print("[WARN] matplotlib not available, skipping plot.")
        return None

    ub_list: List[int] = []
    guided_list: List[Optional[int]] = []
    baseline_list: List[Optional[int]] = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ub_list.append(int(row["ub_factor"]))
            g = row["guided_best_cutsize"]
            b = row["baseline_best_cutsize"]
            guided_list.append(int(g) if str(g).strip() not in ("", "None") else None)
            baseline_list.append(int(b) if str(b).strip() not in ("", "None") else None)

    ub_g = [u for u, v in zip(ub_list, guided_list) if v is not None]
    val_g = [v for v in guided_list if v is not None]
    ub_b = [u for u, v in zip(ub_list, baseline_list) if v is not None]
    val_b = [v for v in baseline_list if v is not None]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(ub_b, val_b, marker="o", linewidth=2, label="Baseline (best of seeds)")
    ax.plot(ub_g, val_g, marker="s", linewidth=2, label="ML-Guided (best of seeds)")

    common_ub = sorted(set(ub_g) & set(ub_b))
    g_dict = dict(zip(ub_g, val_g))
    b_dict = dict(zip(ub_b, val_b))
    g_vals = [g_dict[u] for u in common_ub]
    b_vals = [b_dict[u] for u in common_ub]
    improve_mask = [g < b for g, b in zip(g_vals, b_vals)]
    # Use intersection interpolation so the filled region follows the true
    # crossing points between curves, avoiding jagged wedge artifacts.
    ax.fill_between(
        common_ub,
        g_vals,
        b_vals,
        where=improve_mask,
        interpolate=True,
        alpha=0.15,
        label="ML improvement",
    )

    title = f"Cutsize vs UBFactor{' — ' + benchmark_name if benchmark_name else ''}"
    ax.set_title(title, fontsize=13)
    ax.set_xlabel("UBFactor", fontsize=11)
    ax.set_ylabel("Cutsize", fontsize=11)
    ax.set_xticks(ub_list)
    ax.legend(fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()

    png_path = out_dir / "ub_sweep_compare_with_inference.png"
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return png_path


def run_seed_pair(
    ub: int,
    seed: int,
    args: argparse.Namespace,
    nets: List[List[int]],
    num_nodes: int,
    env: Dict[str, str],
    cut_prob_file: Optional[Path],
    tcl_dir: Path,
    log_dir: Path,
    part_dir: Path,
    work_root: Path,
) -> Tuple[RunResult, RunResult]:
    guided = one_mode(
        ub,
        "guided",
        seed,
        args.guided_openroad,
        args.hgr_file,
        args.num_parts,
        tcl_dir,
        log_dir,
        part_dir,
        work_root,
        nets,
        num_nodes,
        env,
        cut_prob_file,
        guide_coarsening=args.guide_coarsening,
        guide_refinement=args.guide_refinement,
        guide_cutoverlay=args.guide_cutoverlay,
    )
    baseline = one_mode(
        ub,
        "baseline",
        seed,
        args.baseline_openroad,
        args.hgr_file,
        args.num_parts,
        tcl_dir,
        log_dir,
        part_dir,
        work_root,
        nets,
        num_nodes,
        env,
        None,
        guide_coarsening=None,
        guide_refinement=None,
        guide_cutoverlay=None,
    )
    return guided, baseline


def main() -> None:
    case_t0 = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    default_inference = project_root / "HyperCutNet" / "src" / "inference.py"
    default_openroad = project_root / "TritonPart" / "build" / "src" / "openroad"
    parser = argparse.ArgumentParser(description="UB sweep compare with multi-seed best-of-seeds")
    parser.add_argument("--hgr-file", type=Path, required=True)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--external-cutprob-dir",
        type=Path,
        default=None,
        help="Directory containing precomputed cut_prob_ubXX.txt files. If set, skip model inference and use these files directly.",
    )
    parser.add_argument("--inference-script", type=Path, default=default_inference)
    parser.add_argument("--infer-python", default=sys.executable)

    parser.add_argument("--guided-openroad", type=Path, default=default_openroad)
    parser.add_argument("--baseline-openroad", type=Path, default=default_openroad)

    parser.add_argument("--ub-start", type=int, default=1)
    parser.add_argument("--ub-end", type=int, default=20)
    parser.add_argument("--num-parts", type=int, default=2)

    parser.add_argument("--guide-coarsening", type=int, choices=[0, 1], default=1)
    parser.add_argument("--guide-refinement", type=int, choices=[0, 1], default=1)
    parser.add_argument("--guide-cutoverlay", type=int, choices=[0, 1], default=1)

    parser.add_argument("--seeds", type=str, default="", help="Comma-separated seed list, e.g. 1000,1100,1200")
    parser.add_argument("--num-seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument("--seed-step", type=int, default=100)
    parser.add_argument(
        "--seed-workers",
        type=int,
        default=0,
        help="Parallel workers per UB for seed runs. 0 means auto=min(num_seeds, CPU cores).",
    )

    parser.add_argument("--hidden_dim", type=int, default=128)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--use_node2vec", action="store_true")
    parser.add_argument("--use_node2vec_disk_cache", action="store_true")
    parser.add_argument("--use_pagerank", action="store_true")
    parser.add_argument("--use_ubfactor", action="store_true")
    parser.add_argument("--ub_max", type=int, default=20)
    parser.add_argument("--ub_isolate", action="store_true")
    parser.add_argument("--inference-once-for-all-ub", action="store_true")
    parser.add_argument("--reuse-node2vec-inprocess", action="store_true")

    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ld-library-path", default="")
    parser.add_argument("--ld-preload", default="")

    args = parser.parse_args()

    inference_launcher = os.environ.get("INFERENCE_LAUNCHER", "").strip()
    if inference_launcher and args.reuse_node2vec_inprocess:
        raise ValueError(
            "INFERENCE_LAUNCHER cannot be combined with "
            "--reuse-node2vec-inprocess"
        )

    seeds = parse_seed_list(args)
    if len(seeds) == 0:
        raise ValueError("No seeds provided.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    tcl_dir = args.out_dir / "tcl"
    log_dir = args.out_dir / "logs"
    part_dir = args.out_dir / "parts"
    cutprob_dir = args.out_dir / "cut_probs"
    inferlog_dir = args.out_dir / "infer_logs"
    for d in (tcl_dir, log_dir, part_dir, cutprob_dir, inferlog_dir):
        d.mkdir(parents=True, exist_ok=True)
    work_root = args.out_dir / "work"
    work_root.mkdir(parents=True, exist_ok=True)

    if not args.hgr_file.exists():
        raise FileNotFoundError(f"hgr not found: {args.hgr_file}")
    if args.external_cutprob_dir is None and not args.graph_dir.exists():
        raise FileNotFoundError(f"graph-dir not found: {args.graph_dir}")
    if args.external_cutprob_dir is None and not args.checkpoint.exists():
        raise FileNotFoundError(f"checkpoint not found: {args.checkpoint}")
    if args.external_cutprob_dir is None and not args.inference_script.exists():
        raise FileNotFoundError(f"inference script not found: {args.inference_script}")
    if not args.guided_openroad.exists():
        raise FileNotFoundError(f"guided openroad not found: {args.guided_openroad}")
    if not args.baseline_openroad.exists():
        raise FileNotFoundError(f"baseline openroad not found: {args.baseline_openroad}")
    if args.external_cutprob_dir is not None and not args.external_cutprob_dir.exists():
        raise FileNotFoundError(f"external cutprob dir not found: {args.external_cutprob_dir}")

    _, num_nodes, _, nets = parse_hgr(args.hgr_file)
    env = build_openroad_env(args)

    run_inference_fn = None
    if args.external_cutprob_dir is None and args.reuse_node2vec_inprocess:
        run_inference_fn = load_run_inference_fn(args.inference_script)
        print("[INFO] Using in-process inference.")

    print(f"[INFO] Seeds: {seeds}")
    print(
        "[INFO] Inference scheduler: "
        + (f"launcher={inference_launcher}" if inference_launcher else "local")
    )
    print(
        f"[INFO] Guided flags: coarsening={args.guide_coarsening}, "
        f"refinement={args.guide_refinement}, cutoverlay={args.guide_cutoverlay}"
    )

    shared_infer_rc: Optional[int] = None
    shared_infer_sec: Optional[float] = None
    shared_cut_prob_file: Optional[Path] = None
    shared_infer_log: Optional[Path] = None

    if args.external_cutprob_dir is None and args.inference_once_for_all_ub and not args.use_ubfactor:
        shared_cut_prob_file = cutprob_dir / "cut_prob_shared.txt"
        shared_infer_log = inferlog_dir / "infer_once.log"
        if args.reuse_node2vec_inprocess:
            shared_infer_rc, shared_infer_sec = run_inference_for_ub_inprocess(
                args, args.ub_start, shared_cut_prob_file, shared_infer_log, run_inference_fn
            )
        else:
            shared_infer_rc, shared_infer_sec = run_inference_for_ub(
                args, args.ub_start, shared_cut_prob_file, shared_infer_log
            )

    rows: List[Dict[str, object]] = []

    for ub in range(args.ub_start, args.ub_end + 1):
        if args.external_cutprob_dir is not None:
            cut_prob_file = resolve_external_cutprob_file(args.external_cutprob_dir, ub)
            infer_log = inferlog_dir / f"infer_ub{ub:02d}.log"
            if not cut_prob_file.exists():
                raise FileNotFoundError(f"missing external cut probability file: {cut_prob_file}")
            infer_rc = 0
            infer_sec = 0.0
            infer_timing: Dict[str, float] = {}
        elif shared_cut_prob_file is not None:
            cut_prob_file = shared_cut_prob_file
            infer_log = shared_infer_log
            infer_rc = int(shared_infer_rc)
            infer_sec = float(shared_infer_sec)
            infer_timing = parse_infer_timing(infer_log)
        else:
            cut_prob_file = cutprob_dir / f"cut_prob_ub{ub:02d}.txt"
            infer_log = inferlog_dir / f"infer_ub{ub:02d}.log"
            if args.reuse_node2vec_inprocess:
                infer_rc, infer_sec = run_inference_for_ub_inprocess(
                    args, ub, cut_prob_file, infer_log, run_inference_fn
                )
            else:
                infer_rc, infer_sec = run_inference_for_ub(args, ub, cut_prob_file, infer_log)
            infer_timing = parse_infer_timing(infer_log)

        guided_runs: List[RunResult] = []
        baseline_runs: List[RunResult] = []
        cut_prob_for_guided = cut_prob_file if infer_rc == 0 else None
        auto_workers = min(len(seeds), os.cpu_count() or len(seeds))
        workers = args.seed_workers if args.seed_workers > 0 else auto_workers
        workers = max(1, workers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [
                ex.submit(
                    run_seed_pair,
                    ub,
                    seed,
                    args,
                    nets,
                    num_nodes,
                    env,
                    cut_prob_for_guided,
                    tcl_dir,
                    log_dir,
                    part_dir,
                    work_root,
                )
                for seed in seeds
            ]
            for fut in concurrent.futures.as_completed(futs):
                g, b = fut.result()
                guided_runs.append(g)
                baseline_runs.append(b)

        gbest = choose_best(guided_runs)
        bbest = choose_best(baseline_runs)

        imp = None
        if gbest is not None and bbest is not None:
            imp = bbest.cutsize - gbest.cutsize

        rows.append(
            {
                "ub_factor": ub,
                "infer_returncode": infer_rc,
                "infer_sec": round(infer_sec, 6),
                "feature_sec": round(float(infer_timing.get("feature_sec", 0.0)), 6),
                "feature_structure_sec": round(float(infer_timing.get("feature_structure_sec", 0.0)), 6),
                "feature_ub_sec": round(float(infer_timing.get("feature_ub_sec", 0.0)), 6),
                "feature_normalize_overlap_sec": round(float(infer_timing.get("feature_normalize_overlap_sec", 0.0)), 6),
                "model_load_sec": round(float(infer_timing.get("model_load_sec", 0.0)), 6),
                "model_forward_sec": round(float(infer_timing.get("model_forward_sec", 0.0)), 6),
                "model_inference_sec": round(float(infer_timing.get("inference_sec", 0.0)), 6),
                "write_sec": round(float(infer_timing.get("write_sec", 0.0)), 6),
                "guided_best_seed": gbest.seed if gbest is not None else "",
                "guided_best_cutsize": gbest.cutsize if gbest is not None else "",
                "guided_best_sec": round(gbest.elapsed_sec, 6) if gbest is not None else "",
                "guided_seed_cuts": fmt_seed_cuts(guided_runs),
                "baseline_best_seed": bbest.seed if bbest is not None else "",
                "baseline_best_cutsize": bbest.cutsize if bbest is not None else "",
                "baseline_best_sec": round(bbest.elapsed_sec, 6) if bbest is not None else "",
                "baseline_seed_cuts": fmt_seed_cuts(baseline_runs),
                "improvement_baseline_minus_guided": imp,
                "guide_coarsening": args.guide_coarsening,
                "guide_refinement": args.guide_refinement,
                "guide_cutoverlay": args.guide_cutoverlay,
                "cut_prob_file": str(cut_prob_file),
                "infer_log": str(infer_log),
            }
        )

        print(
            f"[UB={ub}] infer_rc={infer_rc} "
            f"guided_best={gbest.cutsize if gbest else None}(seed={gbest.seed if gbest else None}) "
            f"baseline_best={bbest.cutsize if bbest else None}(seed={bbest.seed if bbest else None}) "
            f"imp={imp}"
        )

    csv_path = args.out_dir / "ub_sweep_compare_with_inference_multiseed_best.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ub_factor",
                "infer_returncode",
                "infer_sec",
                "feature_sec",
                "feature_structure_sec",
                "feature_ub_sec",
                "feature_normalize_overlap_sec",
                "model_load_sec",
                "model_forward_sec",
                "model_inference_sec",
                "write_sec",
                "guided_best_seed",
                "guided_best_cutsize",
                "guided_best_sec",
                "guided_seed_cuts",
                "baseline_best_seed",
                "baseline_best_cutsize",
                "baseline_best_sec",
                "baseline_seed_cuts",
                "improvement_baseline_minus_guided",
                "guide_coarsening",
                "guide_refinement",
                "guide_cutoverlay",
                "cut_prob_file",
                "infer_log",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved CSV: {csv_path}")
    case_wall_sec = time.perf_counter() - case_t0
    timing_summary = {
        "case": args.hgr_file.stem,
        "wall_sec": round(case_wall_sec, 6),
        "ub_count": len(rows),
        "seed_count": len(seeds),
        "infer_sec_sum": round(sum(float(r.get("infer_sec") or 0.0) for r in rows), 6),
        "feature_sec_sum": round(sum(float(r.get("feature_sec") or 0.0) for r in rows), 6),
        "feature_structure_sec_sum": round(sum(float(r.get("feature_structure_sec") or 0.0) for r in rows), 6),
        "feature_ub_sec_sum": round(sum(float(r.get("feature_ub_sec") or 0.0) for r in rows), 6),
        "feature_normalize_overlap_sec_sum": round(sum(float(r.get("feature_normalize_overlap_sec") or 0.0) for r in rows), 6),
        "model_load_sec_sum": round(sum(float(r.get("model_load_sec") or 0.0) for r in rows), 6),
        "model_forward_sec_sum": round(sum(float(r.get("model_forward_sec") or 0.0) for r in rows), 6),
        "model_inference_sec_sum": round(sum(float(r.get("model_inference_sec") or 0.0) for r in rows), 6),
        "write_sec_sum": round(sum(float(r.get("write_sec") or 0.0) for r in rows), 6),
        "guided_best_sec_sum": round(sum(float(r.get("guided_best_sec") or 0.0) for r in rows), 6),
        "baseline_best_sec_sum": round(sum(float(r.get("baseline_best_sec") or 0.0) for r in rows), 6),
    }
    ub_count = max(int(timing_summary["ub_count"]), 1)
    for key in (
        "infer_sec",
        "feature_sec",
        "feature_structure_sec",
        "feature_ub_sec",
        "feature_normalize_overlap_sec",
        "model_load_sec",
        "model_forward_sec",
        "model_inference_sec",
        "write_sec",
        "guided_best_sec",
        "baseline_best_sec",
    ):
        sum_key = f"{key}_sum"
        avg_key = f"{key}_avg_per_ub"
        timing_summary[avg_key] = round(float(timing_summary.get(sum_key, 0.0)) / ub_count, 6)
    timing_json = args.out_dir / "case_timing.json"
    timing_json.write_text(json.dumps(timing_summary, indent=2, sort_keys=True) + "\n")
    timing_csv = args.out_dir / "case_timing.csv"
    with timing_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(timing_summary.keys()))
        writer.writeheader()
        writer.writerow(timing_summary)
    print(f"Saved Timing: {timing_json}")
    benchmark_name = args.hgr_file.stem
    png_path = plot_results(csv_path, args.out_dir, benchmark_name=benchmark_name)
    if png_path:
        print(f"Saved Plot: {png_path}")


if __name__ == "__main__":
    main()
