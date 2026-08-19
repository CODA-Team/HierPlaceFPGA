#!/usr/bin/env python3
"""Convert batch partition outputs into HyperCutNet training rawdata."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import List, Sequence, Tuple


PART_RE = re.compile(r"^(?P<prefix>baseline|guided)_ub(?P<ub>\d+)_seed(?P<seed>\d+)\.part\.2$")


def parse_hgr(hgr_path: Path) -> Tuple[int, List[List[int]], List[int]]:
    lines: List[str] = []
    with hgr_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if s and not s.startswith("%"):
                lines.append(s)
    if not lines:
        raise ValueError(f"empty hgr: {hgr_path}")

    header = lines[0].split()
    if len(header) < 2:
        raise ValueError(f"invalid hgr header: {hgr_path}")
    num_hyperedges = int(header[0])
    num_vertices = int(header[1])

    nets: List[List[int]] = []
    vertex_degree = [0] * num_vertices
    for line_no, line in enumerate(lines[1 : 1 + num_hyperedges], start=2):
        pins = [int(x) - 1 for x in line.split()]
        for p in pins:
            if p < 0 or p >= num_vertices:
                raise ValueError(f"pin id out of range in {hgr_path}:{line_no}: {p + 1}")
            vertex_degree[p] += 1
        nets.append(pins)
    if len(nets) != num_hyperedges:
        raise ValueError(f"hgr edge count mismatch in {hgr_path}")
    return num_vertices, nets, vertex_degree


def read_part(part_path: Path, expected_len: int) -> List[int]:
    vec: List[int] = []
    with part_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if s:
                vec.append(int(s))
    if len(vec) != expected_len:
        raise ValueError(f"part length mismatch: {part_path} has {len(vec)}, expected {expected_len}")
    return vec


def labels_from_part(nets: Sequence[Sequence[int]], part_vec: Sequence[int]) -> Tuple[List[int], int]:
    labels: List[int] = []
    cutsize = 0
    for pins in nets:
        cut = int(len({part_vec[p] for p in pins}) > 1)
        labels.append(cut)
        cutsize += cut
    return labels, cutsize


def write_nodes(path: Path, vertex_degree: Sequence[int]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for v, deg in enumerate(vertex_degree):
            f.write(f"{v} 1.0 {deg}\n")


def write_hedges(path: Path, nets: Sequence[Sequence[int]], labels: Sequence[int]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for net_id, (pins, label) in enumerate(zip(nets, labels)):
            pin_str = " ".join(str(p) for p in pins)
            f.write(f"{net_id}; {pin_str}; {label}\n")


def parse_case_name(ub_sweep_dir: Path) -> str:
    name = ub_sweep_dir.name
    if not name.startswith("ub_sweep_"):
        raise ValueError(f"unexpected case dir name: {ub_sweep_dir}")
    return name[len("ub_sweep_") :]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-root", type=Path, required=True)
    ap.add_argument("--hgr-dir", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True)
    ap.add_argument("--part-prefix", choices=["baseline", "guided"], default="baseline")
    ap.add_argument("--cases", default="", help="Optional comma-separated case names.")
    args = ap.parse_args()

    case_filter = {c.strip() for c in args.cases.split(",") if c.strip()}
    args.out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    case_dirs = sorted(args.batch_root.glob("ub_sweep_*"), key=lambda p: p.name)
    for case_dir in case_dirs:
        if not case_dir.is_dir():
            continue
        case = parse_case_name(case_dir)
        if case_filter and case not in case_filter:
            continue

        hgr_path = args.hgr_dir / f"{case}.hgr"
        if not hgr_path.exists():
            raise FileNotFoundError(f"missing hgr for {case}: {hgr_path}")
        num_vertices, nets, vertex_degree = parse_hgr(hgr_path)

        parts_dir = case_dir / "parts"
        part_infos = []
        for part_path in parts_dir.glob(f"{args.part_prefix}_ub*_seed*.part.2"):
            m = PART_RE.match(part_path.name)
            if not m or m.group("prefix") != args.part_prefix:
                continue
            part_infos.append((int(m.group("ub")), int(m.group("seed")), part_path))
        part_infos.sort(key=lambda x: (x[0], x[1]))

        seeds_by_ub = {}
        for ub, seed, _ in part_infos:
            seeds_by_ub.setdefault(ub, []).append(seed)

        for ub, seed, part_path in part_infos:
            run = sorted(set(seeds_by_ub[ub])).index(seed) + 1
            sample_name = f"{case}_ub{ub:02d}_run{run:02d}"
            sample_dir = args.out_root / sample_name
            sample_dir.mkdir(parents=True, exist_ok=True)

            part_vec = read_part(part_path, num_vertices)
            labels, cutsize = labels_from_part(nets, part_vec)
            write_nodes(sample_dir / "nodes.txt", vertex_degree)
            write_hedges(sample_dir / "hedges.txt", nets, labels)
            (sample_dir / "quality.txt").write_text(f"{cutsize}\n", encoding="utf-8")

            rows.append(
                {
                    "case": case,
                    "ub": ub,
                    "seed": seed,
                    "run": run,
                    "cutsize": cutsize,
                    "num_vertices": num_vertices,
                    "num_nets": len(nets),
                    "source_part": str(part_path),
                    "sample_dir": str(sample_dir),
                }
            )

    summary_path = args.out_root / "conversion_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "ub",
                "seed",
                "run",
                "cutsize",
                "num_vertices",
                "num_nets",
                "source_part",
                "sample_dir",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Converted samples: {len(rows)}")
    print(f"Output root: {args.out_root}")
    print(f"Summary CSV: {summary_path}")


if __name__ == "__main__":
    main()
