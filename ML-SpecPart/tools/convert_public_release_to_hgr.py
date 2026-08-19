#!/usr/bin/env python3
"""Convert public_release case_*.nodes/.nets files to hMETIS .hgr files.

The output format is the unweighted hMETIS subset used by TritonPart:

    <num_hyperedges> <num_vertices>
    <1-indexed vertex ids in net 0>
    <1-indexed vertex ids in net 1>
    ...

Only .nodes and .nets are needed for this conversion. .timing and Arch files
are not used by hMETIS/TritonPart hypergraph partitioning.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CASE_RE = re.compile(r"^(case_\d+)\.nodes$")


@dataclass
class ConvertStats:
    case_name: str
    num_vertices: int
    num_hyperedges: int
    skipped_singleton_nets: int
    skipped_empty_nets: int
    skipped_unknown_pin_refs: int


def parse_nodes(nodes_path: Path) -> dict[str, int]:
    """Return instance name -> 1-indexed hMETIS vertex id."""

    inst_to_vid: dict[str, int] = {}
    with nodes_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            toks = line.split()
            if len(toks) < 3:
                raise ValueError(f"invalid nodes line {line_no} in {nodes_path}: {raw.rstrip()}")

            inst_name = toks[2]
            if inst_name in inst_to_vid:
                raise ValueError(f"duplicate instance {inst_name!r} in {nodes_path} line {line_no}")
            inst_to_vid[inst_name] = len(inst_to_vid) + 1

    if not inst_to_vid:
        raise ValueError(f"no instances parsed from {nodes_path}")
    return inst_to_vid


def parse_nets(
    nets_path: Path,
    inst_to_vid: dict[str, int],
    *,
    keep_singletons: bool,
) -> tuple[list[list[int]], int, int, int]:
    """Parse .nets and return hMETIS hyperedges plus skip counters."""

    hyperedges: list[list[int]] = []
    skipped_singleton = 0
    skipped_empty = 0
    skipped_unknown = 0

    in_net = False
    current_vertices: list[int] = []
    current_seen: set[int] = set()

    def finish_net() -> None:
        nonlocal skipped_singleton, skipped_empty
        if not current_vertices:
            skipped_empty += 1
            return
        if len(current_vertices) == 1 and not keep_singletons:
            skipped_singleton += 1
            return
        hyperedges.append(list(current_vertices))

    with nets_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            toks = line.split()
            if not toks:
                continue

            if toks[0] == "net":
                if in_net:
                    finish_net()
                in_net = True
                current_vertices = []
                current_seen = set()
                continue

            if toks[0] == "endnet":
                if not in_net:
                    raise ValueError(f"endnet without net in {nets_path} line {line_no}")
                finish_net()
                in_net = False
                current_vertices = []
                current_seen = set()
                continue

            if not in_net:
                raise ValueError(f"pin line outside net in {nets_path} line {line_no}: {raw.rstrip()}")

            inst_name = toks[0]
            vid = inst_to_vid.get(inst_name)
            if vid is None:
                skipped_unknown += 1
                continue
            if vid not in current_seen:
                current_seen.add(vid)
                current_vertices.append(vid)

    if in_net:
        finish_net()

    if not hyperedges:
        raise ValueError(f"no hyperedges parsed from {nets_path}")

    return hyperedges, skipped_singleton, skipped_empty, skipped_unknown


def write_hgr(path: Path, num_vertices: int, hyperedges: Iterable[list[int]]) -> int:
    edges = list(hyperedges)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(f"{len(edges)} {num_vertices}\n")
        for pins in edges:
            f.write(" ".join(str(pin) for pin in pins))
            f.write("\n")
    return len(edges)


def convert_one(case_name: str, input_dir: Path, output_dir: Path, keep_singletons: bool) -> ConvertStats:
    nodes_path = input_dir / f"{case_name}.nodes"
    nets_path = input_dir / f"{case_name}.nets"
    if not nodes_path.is_file():
        raise FileNotFoundError(nodes_path)
    if not nets_path.is_file():
        raise FileNotFoundError(nets_path)

    inst_to_vid = parse_nodes(nodes_path)
    hyperedges, skipped_singleton, skipped_empty, skipped_unknown = parse_nets(
        nets_path,
        inst_to_vid,
        keep_singletons=keep_singletons,
    )
    out_path = output_dir / f"{case_name}.hgr"
    num_hyperedges = write_hgr(out_path, len(inst_to_vid), hyperedges)
    return ConvertStats(
        case_name=case_name,
        num_vertices=len(inst_to_vid),
        num_hyperedges=num_hyperedges,
        skipped_singleton_nets=skipped_singleton,
        skipped_empty_nets=skipped_empty,
        skipped_unknown_pin_refs=skipped_unknown,
    )


def discover_cases(input_dir: Path) -> list[str]:
    cases: list[str] = []
    for path in input_dir.iterdir():
        m = CASE_RE.match(path.name)
        if m and (input_dir / f"{m.group(1)}.nets").is_file():
            cases.append(m.group(1))
    return sorted(cases, key=lambda x: int(x.split("_")[1]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert public_release .nodes/.nets cases to .hgr")
    ap.add_argument(
        "--input-dir",
        type=Path,
        required=True,
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    ap.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Case stem to convert, e.g. case_1. May be repeated. Default: all case_*.nodes.",
    )
    ap.add_argument(
        "--keep-singletons",
        action="store_true",
        help="Keep one-pin nets in the .hgr. Default skips them.",
    )
    args = ap.parse_args()

    cases = args.cases or discover_cases(args.input_dir)
    if not cases:
        raise SystemExit(f"No cases found in {args.input_dir}")

    summary_path = args.output_dir / "conversion_summary.csv"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stats_rows: list[ConvertStats] = []

    for case_name in cases:
        stats = convert_one(case_name, args.input_dir, args.output_dir, args.keep_singletons)
        stats_rows.append(stats)
        print(
            f"{case_name}: vertices={stats.num_vertices} hyperedges={stats.num_hyperedges} "
            f"skipped_singleton={stats.skipped_singleton_nets} "
            f"skipped_empty={stats.skipped_empty_nets} "
            f"unknown_pin_refs={stats.skipped_unknown_pin_refs}"
        )

    with summary_path.open("w", encoding="utf-8") as f:
        f.write(
            "case,num_vertices,num_hyperedges,skipped_singleton_nets,"
            "skipped_empty_nets,skipped_unknown_pin_refs\n"
        )
        for s in stats_rows:
            f.write(
                f"{s.case_name},{s.num_vertices},{s.num_hyperedges},"
                f"{s.skipped_singleton_nets},{s.skipped_empty_nets},{s.skipped_unknown_pin_refs}\n"
            )
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main()
