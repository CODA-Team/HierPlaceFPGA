#!/usr/bin/env python3
"""Add shared nodes.txt files and per-sample symlinks to HyperCutNet rawdata."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SAMPLE_RE = re.compile(r"^(.+)_ub\d\d_run\d\d$")


def parse_vertex_degrees(hgr_path: Path) -> list[int]:
    lines: list[str] = []
    with hgr_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if s and not s.startswith("%"):
                lines.append(s)
    if not lines:
        raise ValueError(f"empty hgr: {hgr_path}")

    header = lines[0].split()
    num_hyperedges = int(header[0])
    num_vertices = int(header[1])
    degrees = [0] * num_vertices

    for line_no, line in enumerate(lines[1 : 1 + num_hyperedges], start=2):
        for token in line.split():
            vertex = int(token) - 1
            if vertex < 0 or vertex >= num_vertices:
                raise ValueError(f"pin id out of range in {hgr_path} line {line_no}: {vertex + 1}")
            degrees[vertex] += 1
    return degrees


def write_nodes(path: Path, degrees: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for node_id, degree in enumerate(degrees):
            f.write(f"{node_id} 1.0 {degree}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add shared nodes.txt symlinks to rawdata sample directories.")
    parser.add_argument("--rawdata-root", type=Path, required=True)
    parser.add_argument("--hgr-dir", type=Path, required=True)
    parser.add_argument("--shared-dir-name", default="_shared_nodes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rawdata_root = args.rawdata_root
    shared_root = rawdata_root / args.shared_dir_name

    samples_by_case: dict[str, list[Path]] = {}
    for sample_dir in rawdata_root.iterdir():
        if not sample_dir.is_dir() or sample_dir.name == args.shared_dir_name:
            continue
        match = SAMPLE_RE.match(sample_dir.name)
        if match:
            samples_by_case.setdefault(match.group(1), []).append(sample_dir)

    total_links = 0
    for case in sorted(samples_by_case):
        hgr_path = args.hgr_dir / f"{case}.hgr"
        if not hgr_path.is_file():
            raise FileNotFoundError(hgr_path)
        nodes_path = shared_root / case / "nodes.txt"
        write_nodes(nodes_path, parse_vertex_degrees(hgr_path))

        for sample_dir in samples_by_case[case]:
            link_path = sample_dir / "nodes.txt"
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(nodes_path)
            total_links += 1
        print(f"[nodes] case={case} samples={len(samples_by_case[case])} shared={nodes_path}", flush=True)

    print(f"Cases: {len(samples_by_case)}")
    print(f"Shared nodes files: {len(samples_by_case)}")
    print(f"Sample nodes links: {total_links}")


if __name__ == "__main__":
    main()
