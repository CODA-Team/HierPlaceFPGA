#!/usr/bin/env python3
"""
Batch runner for test-case lists.

It reads benchmark names from test list files and invokes an existing UB sweep
script (default: multiseed parallel) per benchmark.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def read_list_file(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"list file not found: {path}")
    cases: List[str] = []
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        cases.append(s)
    return cases


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def is_ibm_case(case_name: str) -> bool:
    return case_name.lower().startswith("ibm")


def build_case_paths(args: argparse.Namespace, case_name: str) -> Tuple[Path, Path]:
    hgr_name_map = {
        # Keep graph-dir case name as listed, but map to actual HGR filename.
        "cholesky_bdtii": "cholesky_bdti",
    }
    hgr_case_name = hgr_name_map.get(case_name, case_name)
    if is_ibm_case(case_name):
        hgr_file = args.ibm_hgr_dir / f"{hgr_case_name}.hgr"
        graph_dir = args.ibm_graph_root / case_name / "hypercutnet"
    else:
        hgr_file = args.titan_hgr_dir / f"{hgr_case_name}.hgr"
        graph_dir = args.titan_graph_root / case_name / "hypercutnet"
    return hgr_file, graph_dir


def add_flag(cmd: List[str], enabled: bool, flag: str) -> None:
    if enabled:
        cmd.append(flag)


def build_one_command(
    args: argparse.Namespace,
    case_name: str,
    hgr_file: Path,
    graph_dir: Path,
    out_dir: Path,
) -> List[str]:
    cmd = [
        args.python_bin,
        str(args.runner_script),
        "--checkpoint",
        str(args.checkpoint),
        "--hgr-file",
        str(hgr_file),
        "--graph-dir",
        str(graph_dir),
        "--ub-start",
        str(args.ub_start),
        "--ub-end",
        str(args.ub_end),
        "--num-parts",
        str(args.num_parts),
        "--guide-coarsening",
        str(args.guide_coarsening),
        "--guide-refinement",
        str(args.guide_refinement),
        "--guide-cutoverlay",
        str(args.guide_cutoverlay),
        "--out-dir",
        str(out_dir),
    ]

    external_cutprob_dir = None
    if is_ibm_case(case_name) and args.ibm_cutprob_root is not None:
        external_cutprob_dir = args.ibm_cutprob_root / f"ub_sweep_{case_name}" / args.cutprob_subdir
    elif (not is_ibm_case(case_name)) and args.titan_cutprob_root is not None:
        external_cutprob_dir = args.titan_cutprob_root / f"ub_sweep_{case_name}" / args.cutprob_subdir
    if external_cutprob_dir is not None:
        cmd.extend(["--external-cutprob-dir", str(external_cutprob_dir)])

    # model/inference related flags
    add_flag(cmd, args.use_node2vec, "--use_node2vec")
    add_flag(cmd, args.use_node2vec_disk_cache, "--use_node2vec_disk_cache")
    add_flag(cmd, args.use_pagerank, "--use_pagerank")
    add_flag(cmd, args.use_ubfactor, "--use_ubfactor")
    add_flag(cmd, args.ub_isolate, "--ub_isolate")
    add_flag(cmd, args.inference_once_for_all_ub, "--inference-once-for-all-ub")
    add_flag(cmd, args.reuse_node2vec_inprocess, "--reuse-node2vec-inprocess")

    cmd.extend(["--ub_max", str(args.ub_max)])

    # seed/multiseed related options (accepted by multiseed script)
    if args.seeds:
        cmd.extend(["--seeds", args.seeds])
    else:
        cmd.extend(
            [
                "--num-seeds",
                str(args.num_seeds),
                "--seed-start",
                str(args.seed_start),
                "--seed-step",
                str(args.seed_step),
            ]
        )
    cmd.extend(["--seed-workers", str(args.seed_workers)])

    # optional overrides if you changed binary paths
    if args.guided_openroad:
        cmd.extend(["--guided-openroad", str(args.guided_openroad)])
    if args.baseline_openroad:
        cmd.extend(["--baseline-openroad", str(args.baseline_openroad)])
    if args.inference_script:
        cmd.extend(["--inference-script", str(args.inference_script)])
    if args.infer_python:
        cmd.extend(["--infer-python", str(args.infer_python)])
    if args.ld_library_path:
        cmd.extend(["--ld-library-path", str(args.ld_library_path)])
    if args.ld_preload:
        cmd.extend(["--ld-preload", str(args.ld_preload)])

    return cmd


def run_one_case(case_name: str, cmd: List[str], out_dir: Path, hgr_file: Path, graph_dir: Path) -> Dict[str, str]:
    start_wall = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    p = subprocess.run(cmd, text=True)
    elapsed = time.perf_counter() - t0
    end_wall = datetime.now(timezone.utc)
    status = "ok" if p.returncode == 0 else "failed"
    row = {
        "case": case_name,
        "status": status,
        "returncode": str(p.returncode),
        "start_time_utc": start_wall.isoformat(),
        "end_time_utc": end_wall.isoformat(),
        "elapsed_sec": f"{elapsed:.2f}",
        "out_dir": str(out_dir),
        "hgr_file": str(hgr_file),
        "graph_dir": str(graph_dir),
        "command": " ".join(cmd),
    }
    timing_path = out_dir / "case_timing.json"
    if timing_path.exists():
        try:
            timing = json.loads(timing_path.read_text())
            for key in (
                "wall_sec",
                "infer_sec_sum",
                "feature_sec_sum",
                "feature_structure_sec_sum",
                "feature_ub_sec_sum",
                "feature_normalize_overlap_sec_sum",
                "model_load_sec_sum",
                "model_forward_sec_sum",
                "model_inference_sec_sum",
                "write_sec_sum",
                "guided_best_sec_sum",
                "baseline_best_sec_sum",
                "infer_sec_avg_per_ub",
                "feature_sec_avg_per_ub",
                "feature_structure_sec_avg_per_ub",
                "feature_ub_sec_avg_per_ub",
                "feature_normalize_overlap_sec_avg_per_ub",
                "model_load_sec_avg_per_ub",
                "model_forward_sec_avg_per_ub",
                "model_inference_sec_avg_per_ub",
                "write_sec_avg_per_ub",
                "guided_best_sec_avg_per_ub",
                "baseline_best_sec_avg_per_ub",
            ):
                row[key] = str(timing.get(key, ""))
        except Exception:
            pass
    return row


def empty_timing_row(
    case_name: str,
    status: str,
    out_dir: Path | str = "",
    hgr_file: Path | str = "",
    graph_dir: Path | str = "",
    command: str = "",
) -> Dict[str, str]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "case": case_name,
        "status": status,
        "returncode": "",
        "start_time_utc": now,
        "end_time_utc": now,
        "elapsed_sec": "0.00",
        "out_dir": str(out_dir),
        "hgr_file": str(hgr_file),
        "graph_dir": str(graph_dir),
        "command": command,
        "wall_sec": "",
        "infer_sec_sum": "",
        "feature_sec_sum": "",
        "feature_structure_sec_sum": "",
        "feature_ub_sec_sum": "",
        "feature_normalize_overlap_sec_sum": "",
        "model_load_sec_sum": "",
        "model_forward_sec_sum": "",
        "model_inference_sec_sum": "",
        "write_sec_sum": "",
        "guided_best_sec_sum": "",
        "baseline_best_sec_sum": "",
        "infer_sec_avg_per_ub": "",
        "feature_sec_avg_per_ub": "",
        "feature_structure_sec_avg_per_ub": "",
        "feature_ub_sec_avg_per_ub": "",
        "feature_normalize_overlap_sec_avg_per_ub": "",
        "model_load_sec_avg_per_ub": "",
        "model_forward_sec_avg_per_ub": "",
        "model_inference_sec_avg_per_ub": "",
        "write_sec_avg_per_ub": "",
        "guided_best_sec_avg_per_ub": "",
        "baseline_best_sec_avg_per_ub": "",
    }


def main() -> None:
    batch_start_wall = datetime.now(timezone.utc)
    batch_t0 = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    parser = argparse.ArgumentParser(
        description="Batch run UB-sweep script on benchmarks from test list files"
    )
    parser.add_argument(
        "--runner-script",
        type=Path,
        default=script_dir / "run_ub_sweep_compare_with_inference_multiseed_best_parallel.py",
        help="Underlying per-benchmark sweep script",
    )
    parser.add_argument("--python-bin", default="python")
    parser.add_argument("--checkpoint", type=Path, required=True)

    parser.add_argument(
        "--ibm-list",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--titan-list",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--ibm-hgr-dir",
        type=Path,
        default=project_root / "TritonPart" / "ISPD_benchmark",
    )
    parser.add_argument(
        "--titan-hgr-dir",
        type=Path,
        default=project_root / "TritonPart" / "titan23_benchmark",
    )
    parser.add_argument(
        "--ibm-graph-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--titan-graph-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--ibm-cutprob-root",
        type=Path,
        default=None,
        help="If set, use ub_sweep_<case>/<cutprob-subdir> from this experiment root for IBM cases instead of model inference.",
    )
    parser.add_argument(
        "--titan-cutprob-root",
        type=Path,
        default=None,
        help="If set, use ub_sweep_<case>/<cutprob-subdir> from this experiment root for Titan cases instead of model inference.",
    )
    parser.add_argument(
        "--cutprob-subdir",
        type=str,
        default="cut_probs_from_raw20",
        help="Subdirectory under ub_sweep_<case>/ that stores external cut_prob_ubXX.txt files.",
    )

    parser.add_argument("--ub-start", type=int, default=1)
    parser.add_argument("--ub-end", type=int, default=20)
    parser.add_argument("--num-parts", type=int, default=2)
    parser.add_argument("--ub_max", type=int, default=20)
    parser.add_argument("--guide-coarsening", type=int, choices=[0, 1], default=0)
    parser.add_argument("--guide-refinement", type=int, choices=[0, 1], default=1)
    parser.add_argument("--guide-cutoverlay", type=int, choices=[0, 1], default=1)

    parser.add_argument("--use_node2vec", action="store_true")
    parser.add_argument("--use_node2vec_disk_cache", action="store_true")
    parser.add_argument("--use_pagerank", action="store_true")
    parser.add_argument("--use_ubfactor", action="store_true")
    parser.add_argument("--ub_isolate", action="store_true")
    parser.add_argument("--inference-once-for-all-ub", action="store_true")
    parser.add_argument("--reuse-node2vec-inprocess", action="store_true")

    parser.add_argument("--seeds", type=str, default="")
    parser.add_argument("--num-seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--seed-step", type=int, default=500)
    parser.add_argument("--seed-workers", type=int, default=5)
    parser.add_argument(
        "--case-workers",
        type=int,
        default=1,
        help="Parallel workers across benchmark cases. 1 means sequential.",
    )

    parser.add_argument("--guided-openroad", type=Path, default=None)
    parser.add_argument("--baseline-openroad", type=Path, default=None)
    parser.add_argument("--inference-script", type=Path, default=None)
    parser.add_argument("--infer-python", default="")
    parser.add_argument("--ld-library-path", default="")
    parser.add_argument("--ld-preload", default="")

    parser.add_argument(
        "--out-root",
        type=Path,
        required=True,
        help="Root output directory; each case gets one subdir",
    )
    parser.add_argument(
        "--out-prefix",
        default="ub_sweep",
        help="Per-case out dir name prefix",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip case if its out_dir already contains ub_sweep_compare_with_inference.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands only",
    )
    args = parser.parse_args()

    ibm_cases = read_list_file(args.ibm_list)
    titan_cases = read_list_file(args.titan_list)
    cases = unique_keep_order(ibm_cases + titan_cases)

    args.out_root.mkdir(parents=True, exist_ok=True)
    summary_csv = args.out_root / "batch_summary.csv"
    timing_json = args.out_root / "batch_timing.json"

    rows: List[Dict[str, str]] = []
    runnable = []
    for idx, case_name in enumerate(cases, 1):
        hgr_file, graph_dir = build_case_paths(args, case_name)
        external_cutprob_dir = None
        if is_ibm_case(case_name) and args.ibm_cutprob_root is not None:
            external_cutprob_dir = args.ibm_cutprob_root / f"ub_sweep_{case_name}" / args.cutprob_subdir
        elif (not is_ibm_case(case_name)) and args.titan_cutprob_root is not None:
            external_cutprob_dir = args.titan_cutprob_root / f"ub_sweep_{case_name}" / args.cutprob_subdir
        out_dir = args.out_root / f"{args.out_prefix}_{case_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        csv_done = out_dir / "ub_sweep_compare_with_inference.csv"
        if args.skip_existing and csv_done.exists():
            print(f"[{idx}/{len(cases)}] skip existing: {case_name}")
            rows.append(empty_timing_row(case_name, "skipped_existing", out_dir, hgr_file, graph_dir))
            continue

        if not hgr_file.exists():
            print(f"[{idx}/{len(cases)}] missing hgr: {hgr_file}")
            rows.append(empty_timing_row(case_name, "missing_hgr", out_dir, hgr_file, graph_dir))
            continue

        if external_cutprob_dir is None and not graph_dir.exists():
            print(f"[{idx}/{len(cases)}] missing graph_dir: {graph_dir}")
            rows.append(empty_timing_row(case_name, "missing_graph_dir", out_dir, hgr_file, graph_dir))
            continue
        if external_cutprob_dir is not None and not external_cutprob_dir.exists():
            print(f"[{idx}/{len(cases)}] missing cutprob_dir: {external_cutprob_dir}")
            rows.append(empty_timing_row(case_name, "missing_cutprob_dir", out_dir, hgr_file, graph_dir))
            continue

        cmd = build_one_command(args, case_name, hgr_file, graph_dir, out_dir)
        cmd_str = " ".join(cmd)
        print(f"[{idx}/{len(cases)}] run case={case_name}")
        print("  " + cmd_str)

        if args.dry_run:
            rows.append(empty_timing_row(case_name, "dry_run", out_dir, hgr_file, graph_dir, cmd_str))
            continue

        runnable.append((case_name, cmd, out_dir, hgr_file, graph_dir))

    if not args.dry_run and len(runnable) > 0:
        workers = max(1, int(args.case_workers))
        workers = min(workers, len(runnable))
        print(f"[INFO] case-level parallel workers: {workers}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut_to_case = {
                ex.submit(run_one_case, case_name, cmd, out_dir, hgr_file, graph_dir): case_name
                for (case_name, cmd, out_dir, hgr_file, graph_dir) in runnable
            }
            for fut in concurrent.futures.as_completed(fut_to_case):
                case_name = fut_to_case[fut]
                try:
                    row = fut.result()
                except Exception as e:
                    now = datetime.now(timezone.utc).isoformat()
                    row = {
                        "case": case_name,
                        "status": "failed",
                        "returncode": "",
                        "start_time_utc": now,
                        "end_time_utc": now,
                        "elapsed_sec": "0.00",
                        "out_dir": "",
                        "hgr_file": "",
                        "graph_dir": "",
                        "command": "",
                        "wall_sec": "",
                        "infer_sec_sum": "",
                        "feature_sec_sum": "",
                        "feature_structure_sec_sum": "",
                        "feature_ub_sec_sum": "",
                        "feature_normalize_overlap_sec_sum": "",
                        "model_load_sec_sum": "",
                        "model_forward_sec_sum": "",
                        "model_inference_sec_sum": "",
                        "write_sec_sum": "",
                        "guided_best_sec_sum": "",
                        "baseline_best_sec_sum": "",
                        "infer_sec_avg_per_ub": "",
                        "feature_sec_avg_per_ub": "",
                        "feature_structure_sec_avg_per_ub": "",
                        "feature_ub_sec_avg_per_ub": "",
                        "feature_normalize_overlap_sec_avg_per_ub": "",
                        "model_load_sec_avg_per_ub": "",
                        "model_forward_sec_avg_per_ub": "",
                        "model_inference_sec_avg_per_ub": "",
                        "write_sec_avg_per_ub": "",
                        "guided_best_sec_avg_per_ub": "",
                        "baseline_best_sec_avg_per_ub": "",
                    }
                    print(f"[ERROR] case={case_name} raised exception: {e}")
                rows.append(row)
                print(
                    f"[DONE] case={row['case']} status={row['status']} "
                    f"rc={row['returncode']} sec={row['elapsed_sec']}"
                )

    summary_fields = [
        "case",
        "status",
        "returncode",
        "start_time_utc",
        "end_time_utc",
        "elapsed_sec",
        "out_dir",
        "hgr_file",
        "graph_dir",
        "command",
        "wall_sec",
        "infer_sec_sum",
        "feature_sec_sum",
        "feature_structure_sec_sum",
        "feature_ub_sec_sum",
        "feature_normalize_overlap_sec_sum",
        "model_load_sec_sum",
        "model_forward_sec_sum",
        "model_inference_sec_sum",
        "write_sec_sum",
        "guided_best_sec_sum",
        "baseline_best_sec_sum",
        "infer_sec_avg_per_ub",
        "feature_sec_avg_per_ub",
        "feature_structure_sec_avg_per_ub",
        "feature_ub_sec_avg_per_ub",
        "feature_normalize_overlap_sec_avg_per_ub",
        "model_load_sec_avg_per_ub",
        "model_forward_sec_avg_per_ub",
        "model_inference_sec_avg_per_ub",
        "write_sec_avg_per_ub",
        "guided_best_sec_avg_per_ub",
        "baseline_best_sec_avg_per_ub",
    ]
    for row in rows:
        for field in summary_fields:
            row.setdefault(field, "")

    with summary_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary_fields,
        )
        writer.writeheader()
        writer.writerows(rows)

    batch_end_wall = datetime.now(timezone.utc)
    batch_wall_sec = time.perf_counter() - batch_t0
    case_elapsed_sum = sum(float(r.get("elapsed_sec") or 0.0) for r in rows)
    runnable_count = sum(1 for r in rows if r["status"] in ("ok", "failed"))
    effective_parallelism = case_elapsed_sum / batch_wall_sec if batch_wall_sec > 0 else 0.0

    ok = sum(1 for r in rows if r["status"] == "ok")
    failed = sum(1 for r in rows if r["status"] == "failed")
    skipped = sum(1 for r in rows if r["status"] == "skipped_existing")
    missing = sum(1 for r in rows if r["status"] in ("missing_hgr", "missing_graph_dir", "missing_cutprob_dir"))
    dry = sum(1 for r in rows if r["status"] == "dry_run")
    timing = {
        "start_time_utc": batch_start_wall.isoformat(),
        "end_time_utc": batch_end_wall.isoformat(),
        "wall_sec": round(batch_wall_sec, 2),
        "case_elapsed_sum_sec": round(case_elapsed_sum, 2),
        "effective_parallelism": round(effective_parallelism, 3),
        "requested_case_workers": int(args.case_workers),
        "runnable_cases": runnable_count,
        "total_cases": len(rows),
        "ok": ok,
        "failed": failed,
        "skipped_existing": skipped,
        "missing": missing,
        "dry_run": dry,
        "ub_start": args.ub_start,
        "ub_end": args.ub_end,
        "num_seeds": args.num_seeds if not args.seeds else None,
        "seeds": args.seeds,
        "seed_start": args.seed_start,
        "seed_step": args.seed_step,
        "seed_workers": args.seed_workers,
        "checkpoint": str(args.checkpoint),
        "runner_script": str(args.runner_script),
        "out_root": str(args.out_root),
    }
    timing_json.write_text(json.dumps(timing, indent=2, sort_keys=True) + "\n")
    print(
        f"[DONE] total={len(rows)} ok={ok} failed={failed} "
        f"skipped={skipped} missing={missing} dry_run={dry} wall_sec={batch_wall_sec:.2f}"
    )
    print(f"[DONE] summary: {summary_csv}")
    print(f"[DONE] timing: {timing_json}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
