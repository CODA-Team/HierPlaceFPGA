#!/usr/bin/env python3
"""
Convert hMETIS .hgr format to HyperCutNet format (nodes.txt + hedges.txt).
Usage: python hgr_to_hypercutnet.py <input.hgr> <output_dir>
"""
import os
import sys
from collections import defaultdict


def convert_hgr_to_hypercutnet(hgr_path: str, output_dir: str) -> None:
    """Convert .hgr file to HyperCutNet nodes.txt and hedges.txt."""
    os.makedirs(output_dir, exist_ok=True)

    with open(hgr_path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("%")]

    if not lines:
        raise ValueError("Empty hgr file")

    parts = lines[0].split()
    num_hyperedges = int(parts[0])
    num_vertices = int(parts[1])

    # hgr vertices are 1-indexed; HyperCutNet uses 0-indexed node ids
    vertex_degree = [0] * num_vertices
    hedges = []

    for i, line in enumerate(lines[1 : 1 + num_hyperedges]):
        parts = line.split()
        pins = [int(p) - 1 for p in parts]  # convert to 0-indexed
        for v in pins:
            if 0 <= v < num_vertices:
                vertex_degree[v] += 1
        hedges.append(pins)

    # nodes.txt: node_id weight degree (one line per vertex)
    nodes_path = os.path.join(output_dir, "nodes.txt")
    with open(nodes_path, "w") as f:
        for v in range(num_vertices):
            f.write(f"{v} 1.0 {vertex_degree[v]}\n")

    # hedges.txt: net_id; pin1 pin2 ...; label
    hedges_path = os.path.join(output_dir, "hedges.txt")
    with open(hedges_path, "w") as f:
        for net_idx, pins in enumerate(hedges):
            pin_str = " ".join(str(p) for p in pins)
            f.write(f"{net_idx}; {pin_str}; 0\n")

    print(f"Converted {hgr_path} -> {output_dir}")
    print(f"  Vertices: {num_vertices}, Hyperedges: {num_hyperedges}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python hgr_to_hypercutnet.py <input.hgr> <output_dir>")
        sys.exit(1)
    hgr_path = sys.argv[1]
    output_dir = sys.argv[2]
    convert_hgr_to_hypercutnet(hgr_path, output_dir)


if __name__ == "__main__":
    main()
