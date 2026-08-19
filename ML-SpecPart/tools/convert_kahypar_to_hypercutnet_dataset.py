#!/usr/bin/env python3
"""
Convert KaHyPar IBM bipartition outputs to HyperCutNet training data.

Each output sample has the standard HyperCutNet format:
  <out_root>/<case>_ub<UB>_run<RUN>/{nodes.txt, hedges.txt}

The graph structure comes from the original .hgr file, while hedges.txt labels
are recomputed from each KaHyPar .part vector.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Sequence


def parse_hgr(hgr_path: Path) -> tuple[int, list[list[int]], list[int]]:
    lines: list[str] = []
    with hgr_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if s and not s.startswith("%"):
                lines.append(s)
    if not lines:
        raise ValueError(f"empty hgr: {hgr_path}")

    header = lines[0].split()
    if len(header) < 2:
        raise ValueError(f"invalid hgr header in {hgr_path}: {lines[0]}")

    num_hyperedges = int(header[0])
    num_vertices = int(header[1])
    nets: list[list[int]] = []
    vertex_degree = [0] * num_vertices

    for line_no, line in enumerate(lines[1 : 1 + num_hyperedges], start=2):
        pins = [int(x) - 1 for x in line.split()]
        for pin in pins:
            if pin < 0 or pin >= num_vertices:
                raise ValueError(f"pin id out of range in {hgr_path} line {line_no}: {pin + 1}")
            vertex_degree[pin] += 1
        nets.append(pins)

    if len(nets) != num_hyperedges:
        raise ValueError(f"hgr edge count mismatch in {hgr_path}: header={num_hyperedges}, actual={len(nets)}")
    return num_vertices, nets, vertex_degree


def read_part_vector(part_path: Path, expected_len: int) -> list[int]:
    vec: list[int] = []
    with part_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if s:
                vec.append(int(s))
    if len(vec) != expected_len:
        raise ValueError(f"part length mismatch: {part_path} has {len(vec)} entries, expected {expected_len}")
    return vec


def compute_net_labels_and_cutsize(nets: Sequence[Sequence[int]], part_vec: Sequence[int]) -> tuple[list[int], int]:
    labels: list[int] = []
    cutsize = 0
    for pins in nets:
        is_cut = 1 if len({part_vec[p] for p in pins}) > 1 else 0
        labels.append(is_cut)
        cutsize += is_cut
    return labels, cutsize


def write_nodes(nodes_path: Path, vertex_degree: Sequence[int]) -> None:
    with nodes_path.open("w", encoding="utf-8") as f:
        for node_id, degree in enumerate(vertex_degree):
            f.write(f"{node_id} 1.0 {degree}\n")


def write_hedges(hedges_path: Path, nets: Sequence[Sequence[int]], labels: Sequence[int]) -> None:
    with hedges_path.open("w", encoding="utf-8") as f:
        for net_id, (pins, label) in enumerate(zip(nets, labels)):
            pin_str = " ".join(str(pin) for pin in pins)
            f.write(f"{net_id}; {pin_str}; {label}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert KaHyPar partition results to HyperCutNet rawdata format.")
    parser.add_argument(
        "--kahypar-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--hgr-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=None,
        help="Default: <kahypar-root>/cutsize_summary.csv. Use best_by_case_ub.csv for one best sample per UB.",
    )
    parser.add_argument(
        "--benchmarks",
        type=str,
        default="",
        help="Optional comma-separated case filter, e.g. ibm01,ibm02.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=None,
        help="Default: <out-root>/conversion_summary.csv",
    )
    parser.add_argument(
        "--hedges-only",
        action="store_true",
        help="Write only hedges.txt in each sample directory, matching Titan23 ub-only rawdata layout.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Check inputs and report counts without writing files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_csv = args.source_csv or (args.kahypar_root / "cutsize_summary.csv")
    summary_csv = args.summary_csv or (args.out_root / "conversion_summary.csv")
    bench_filter = {x.strip() for x in args.benchmarks.split(",") if x.strip()} if args.benchmarks.strip() else None

    if not source_csv.is_file():
        raise FileNotFoundError(source_csv)
    if not args.dry_run:
        args.out_root.mkdir(parents=True, exist_ok=True)

    hgr_cache: dict[str, tuple[int, list[list[int]], list[int]]] = {}
    run_counters: dict[tuple[str, int], int] = {}
    summary_rows: list[dict[str, object]] = []

    with source_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case = row["case"].strip()
            if bench_filter and case not in bench_filter:
                continue
            if row.get("status", "ok") != "ok":
                continue

            ub = int(row["ub"])
            seed = int(row["seed"])
            part_path = Path(row["partition_file"])
            if not part_path.is_file():
                raise FileNotFoundError(part_path)

            if case not in hgr_cache:
                hgr_path = args.hgr_dir / f"{case}.hgr"
                if not hgr_path.is_file():
                    raise FileNotFoundError(hgr_path)
                hgr_cache[case] = parse_hgr(hgr_path)
            num_vertices, nets, vertex_degree = hgr_cache[case]

            key = (case, ub)
            run_counters[key] = run_counters.get(key, 0) + 1
            run_id = run_counters[key]
            sample_name = f"{case}_ub{ub:02d}_run{run_id:02d}"
            sample_dir = args.out_root / sample_name
            hedges_path = sample_dir / "hedges.txt"
            nodes_path = sample_dir / "nodes.txt"

            if hedges_path.exists() and (args.hedges_only or nodes_path.exists()):
                summary_rows.append(
                    {
                        "benchmark": case,
                        "ub_factor": ub,
                        "run_id": run_id,
                        "seed": seed,
                        "reported_cutsize": row.get("cutsize", ""),
                        "recomputed_cutsize": "",
                        "imbalance": row.get("imbalance", ""),
                        "num_vertices": "",
                        "num_nets": "",
                        "source_part_file": str(part_path),
                        "dataset_graph_dir": str(sample_dir),
                    }
                )
                continue

            part_vec = read_part_vector(part_path, num_vertices)
            labels, recomputed_cutsize = compute_net_labels_and_cutsize(nets, part_vec)

            if not args.dry_run:
                sample_dir.mkdir(parents=True, exist_ok=True)
                if not args.hedges_only:
                    write_nodes(nodes_path, vertex_degree)
                write_hedges(hedges_path, nets, labels)

            summary_rows.append(
                {
                    "benchmark": case,
                    "ub_factor": ub,
                    "run_id": run_id,
                    "seed": seed,
                    "reported_cutsize": row.get("cutsize", ""),
                    "recomputed_cutsize": recomputed_cutsize,
                    "imbalance": row.get("imbalance", ""),
                    "num_vertices": num_vertices,
                    "num_nets": len(nets),
                    "source_part_file": str(part_path),
                    "dataset_graph_dir": str(sample_dir),
                }
            )
            if len(summary_rows) % 100 == 0:
                print(f"[convert] samples={len(summary_rows)} current={sample_name}", flush=True)

    if not args.dry_run:
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "benchmark",
                "ub_factor",
                "run_id",
                "seed",
                "reported_cutsize",
                "recomputed_cutsize",
                "imbalance",
                "num_vertices",
                "num_nets",
                "source_part_file",
                "dataset_graph_dir",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

    cases = sorted({str(r["benchmark"]) for r in summary_rows})
    print(f"Source CSV: {source_csv}")
    print(f"Cases: {len(cases)} {','.join(cases)}")
    print(f"Total samples: {len(summary_rows)}")
    print(f"Output root: {args.out_root}")
    print(f"Summary CSV: {summary_csv}")
    if args.dry_run:
        print("Dry-run mode: no files were written.")


if __name__ == "__main__":
    main()
