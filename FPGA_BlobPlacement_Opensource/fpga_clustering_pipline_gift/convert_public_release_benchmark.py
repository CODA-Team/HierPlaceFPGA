#!/usr/bin/env python3
"""Convert the public_release benchmark format to this pipeline's bookshelf input.

The public_release cases store placement in the first column of *.nodes:

    X80Y133Z0 CARRY4 inst_0 FIXED

The existing pipeline expects canonical rows:

    design.nodes: inst_0 CARRY4
    design.pl:    inst_0 80 133 0 FIXED

This script creates a self-contained benchmark directory with design.{aux,nodes,
nets,wts,pl,scl,lib} plus sidecar clock/timing metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


_LOC_RE = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)Z(?P<z>\d+)$")
_SITE_RE = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)$")


def _strip_comment(line: str) -> str:
    return line.strip()


def _iter_data_lines(path: Path) -> Iterable[Tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, 1):
            line = _strip_comment(raw)
            if not line or line.startswith("#"):
                continue
            yield lineno, line


def _parse_case_nodes(nodes_path: Path) -> Tuple[List[dict], Counter]:
    nodes: List[dict] = []
    type_counts: Counter = Counter()
    seen_names = set()

    for lineno, line in _iter_data_lines(nodes_path):
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"{nodes_path}:{lineno}: expected '<XxYyZz> <type> <inst> [FIXED]'")

        loc, cell_type, inst_name = parts[:3]
        m = _LOC_RE.match(loc)
        if not m:
            raise ValueError(f"{nodes_path}:{lineno}: invalid location token: {loc}")
        if inst_name in seen_names:
            raise ValueError(f"{nodes_path}:{lineno}: duplicate instance name: {inst_name}")
        seen_names.add(inst_name)

        is_fixed = any(tok.upper() == "FIXED" for tok in parts[3:])
        rec = {
            "name": inst_name,
            "cell_type": cell_type,
            "x": int(m.group("x")),
            "y": int(m.group("y")),
            "z": int(m.group("z")),
            "fixed": is_fixed,
            "source_location": loc,
        }
        nodes.append(rec)
        type_counts[cell_type] += 1

    if not nodes:
        raise ValueError(f"No nodes parsed from {nodes_path}")
    return nodes, type_counts


def _write_nodes_and_pl(nodes: List[dict], out_dir: Path) -> None:
    with (out_dir / "design.nodes").open("w", encoding="utf-8") as nf, \
            (out_dir / "design.pl").open("w", encoding="utf-8") as pf:
        for rec in nodes:
            nf.write(f"{rec['name']} {rec['cell_type']}\n")
            fixed = " FIXED" if rec["fixed"] else ""
            pf.write(f"{rec['name']} {rec['x']} {rec['y']} {rec['z']}{fixed}\n")


def _convert_nets(nets_path: Path, out_dir: Path, valid_nodes: set) -> dict:
    net_count = 0
    pin_count = 0
    clock_nets: List[str] = []
    max_fanout = 0
    bad_pins: List[Tuple[int, str, str]] = []

    current_name: Optional[str] = None
    current_declared_degree: Optional[int] = None
    current_attr: List[str] = []
    current_pins: List[Tuple[str, str, int]] = []

    def flush(out_f) -> None:
        nonlocal net_count, pin_count, max_fanout
        if current_name is None:
            return
        degree = len(current_pins)
        if current_declared_degree is not None and current_declared_degree != degree:
            raise ValueError(
                f"{nets_path}: net {current_name} declared degree {current_declared_degree}, "
                f"actual pins {degree}"
            )
        if any(attr.lower() == "clock" for attr in current_attr):
            clock_nets.append(current_name)
        out_f.write(f"net {current_name} {degree}\n")
        for inst, pin, _lineno in current_pins:
            out_f.write(f"  {inst} {pin}\n")
        out_f.write("endnet\n")
        net_count += 1
        pin_count += degree
        max_fanout = max(max_fanout, degree)

    with nets_path.open("r", encoding="utf-8", errors="ignore") as inf, \
            (out_dir / "design.nets").open("w", encoding="utf-8") as outf:
        for lineno, raw in enumerate(inf, 1):
            line = _strip_comment(raw)
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if not parts:
                continue
            key = parts[0].lower()
            if key == "net":
                flush(outf)
                if len(parts) < 3:
                    raise ValueError(f"{nets_path}:{lineno}: malformed net header")
                current_name = parts[1]
                try:
                    current_declared_degree = int(parts[2])
                except ValueError as exc:
                    raise ValueError(f"{nets_path}:{lineno}: invalid net degree {parts[2]}") from exc
                current_attr = parts[3:]
                current_pins = []
            elif key == "endnet":
                flush(outf)
                current_name = None
                current_declared_degree = None
                current_attr = []
                current_pins = []
            else:
                if current_name is None:
                    raise ValueError(f"{nets_path}:{lineno}: pin line outside a net")
                if len(parts) < 2:
                    raise ValueError(f"{nets_path}:{lineno}: malformed pin line")
                inst, pin = parts[0], parts[1]
                if inst not in valid_nodes:
                    bad_pins.append((lineno, current_name, inst))
                    if len(bad_pins) <= 10:
                        continue
                current_pins.append((inst, pin, lineno))
        flush(outf)

    if bad_pins:
        sample = ", ".join(f"line {ln}: {net}/{inst}" for ln, net, inst in bad_pins[:10])
        raise ValueError(f"{nets_path}: {len(bad_pins)} pin instances not found in nodes. Sample: {sample}")

    with (out_dir / "design.clock_nets").open("w", encoding="utf-8") as f:
        for name in clock_nets:
            f.write(f"{name}\n")

    return {
        "num_nets": net_count,
        "num_pins": pin_count,
        "num_clock_nets": len(clock_nets),
        "max_fanout": max_fanout,
    }


def _convert_lib(src_lib: Path, out_dir: Path) -> List[str]:
    cell_names: List[str] = []
    with src_lib.open("r", encoding="utf-8", errors="ignore") as inf, \
            (out_dir / "design.lib").open("w", encoding="utf-8") as outf:
        for raw in inf:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("CELL "):
                parts = stripped.split()
                if len(parts) >= 2:
                    cell_names.append(parts[1])
            if stripped == "END_CELL":
                outf.write("END CELL\n")
            else:
                outf.write(line + "\n")
    return cell_names


def _site_defs_for_new_arch() -> str:
    return """SITE PLB
  LUT 8
  FF 16
  CARRY4 2
  DRAM 2
END SITE

SITE DSP
  DSP 1
END SITE

SITE RAMA
  RAMA 1
END SITE

SITE RAMB
  RAMB 1
END SITE

SITE GCLK
  GCLK 28
END SITE

SITE IOA
  IOA 2
END SITE

SITE IOB
  IOB 2
END SITE

SITE IPPIN
  IPPIN 256
END SITE

RESOURCES
  LUT LUT1 LUT2 LUT3 LUT4 LUT5 LUT6 LUT6X F7MUX F8MUX
  FF SEQ
  CARRY4 CARRY4
  DRAM DRAM
  DSP DSP
  RAMA RAMA
  RAMB RAMB
  IO IOA IOB IPPIN GCLK
END RESOURCES

"""


def _convert_scl(src_scl: Path, out_dir: Path) -> dict:
    width = height = None
    site_entries = 0
    site_type_counts: Counter = Counter()
    in_sitemap = False

    with src_scl.open("r", encoding="utf-8", errors="ignore") as inf, \
            (out_dir / "design.scl").open("w", encoding="utf-8") as outf:
        outf.write("# Converted from public_release Arch/fpga.scl\n")
        outf.write(_site_defs_for_new_arch())
        for _lineno, line in enumerate(inf, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("SITEMAP"):
                parts = s.split()
                if len(parts) < 3:
                    raise ValueError(f"{src_scl}: malformed SITEMAP line")
                width, height = int(parts[1]), int(parts[2])
                outf.write(f"SITEMAP {width} {height}\n")
                in_sitemap = True
                continue
            if s in {"END_SITEMAP", "END SITEMAP"}:
                outf.write("END SITEMAP\n")
                in_sitemap = False
                continue
            if not in_sitemap:
                # The new arch uses comments for site definitions; they are emitted above.
                continue
            parts = s.split()
            if len(parts) < 2:
                continue
            m = _SITE_RE.match(parts[0])
            if not m:
                raise ValueError(f"{src_scl}: invalid site coordinate token: {parts[0]}")
            x, y, site_type = int(m.group("x")), int(m.group("y")), parts[1]
            outf.write(f"{x} {y} {site_type}\n")
            site_entries += 1
            site_type_counts[site_type] += 1

    if width is None or height is None:
        raise ValueError(f"No SITEMAP parsed from {src_scl}")
    return {
        "chip_width": width,
        "chip_height": height,
        "site_entries": site_entries,
        "site_type_counts": dict(site_type_counts),
    }


def _write_aux_and_sidecars(
    out_dir: Path,
    arch_dir: Path,
    timing_path: Optional[Path],
    metadata: dict,
) -> None:
    (out_dir / "design.wts").write_text("# Intentionally left empty\n", encoding="utf-8")
    (out_dir / "design.aux").write_text(
        "design : design.nodes design.nets design.wts design.pl design.scl design.lib\n",
        encoding="utf-8",
    )

    clk_src = arch_dir / "fpga.clk"
    if clk_src.exists():
        shutil.copy2(clk_src, out_dir / "design.clk")
    if timing_path and timing_path.exists():
        shutil.copy2(timing_path, out_dir / "design.timing")

    (out_dir / "design.metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_macros(nodes: List[dict], out_dir: Path) -> int:
    macro_types = {"DSP", "RAMA", "RAMB"}
    names = [rec["name"] for rec in nodes if rec["cell_type"] in macro_types]
    with (out_dir / "design.macros").open("w", encoding="utf-8") as f:
        for name in names:
            f.write(f"{name}\n")
    return len(names)


def infer_public_release_case(
    benchmark_path: Path,
    case_name: Optional[str] = None,
) -> Tuple[Path, str]:
    """Return (public_release_dir, case_name) from CLI inputs."""
    benchmark_path = benchmark_path.resolve()

    if benchmark_path.is_file() and benchmark_path.suffix == ".nodes":
        return benchmark_path.parent, benchmark_path.stem

    if benchmark_path.is_dir():
        if case_name:
            return benchmark_path, case_name
        nodes_files = sorted(benchmark_path.glob("case_*.nodes"))
        if len(nodes_files) == 1:
            return benchmark_path, nodes_files[0].stem
        raise ValueError(
            f"Cannot infer case from directory {benchmark_path}. "
            "Pass --convert_case case_N."
        )

    # Treat a non-existing path as a case prefix: /path/public_release/case_1
    if case_name:
        return benchmark_path, case_name
    if (benchmark_path.with_suffix(".nodes")).exists():
        return benchmark_path.parent, benchmark_path.name

    raise ValueError(f"Cannot infer public_release case from {benchmark_path}")


def convert_public_release_case(
    public_release_dir: str,
    arch_dir: str,
    case_name: str,
    output_dir: str,
    overwrite: bool = True,
) -> str:
    public_dir = Path(public_release_dir).resolve()
    arch = Path(arch_dir).resolve()
    out = Path(output_dir).resolve()

    nodes_path = public_dir / f"{case_name}.nodes"
    nets_path = public_dir / f"{case_name}.nets"
    timing_path = public_dir / f"{case_name}.timing"
    src_scl = arch / "fpga.scl"
    src_lib = arch / "fpga.lib"

    for required in (nodes_path, nets_path, src_scl, src_lib):
        if not required.exists():
            raise FileNotFoundError(required)

    if out.exists() and overwrite:
        for child in out.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out.mkdir(parents=True, exist_ok=True)

    nodes, type_counts = _parse_case_nodes(nodes_path)
    valid_nodes = {rec["name"] for rec in nodes}
    _write_nodes_and_pl(nodes, out)
    net_summary = _convert_nets(nets_path, out, valid_nodes)
    lib_cells = _convert_lib(src_lib, out)
    scl_summary = _convert_scl(src_scl, out)
    macro_count = _write_macros(nodes, out)

    metadata = {
        "format": "converted_public_release",
        "source_case": case_name,
        "source_nodes": str(nodes_path),
        "source_nets": str(nets_path),
        "source_timing": str(timing_path) if timing_path.exists() else None,
        "arch_dir": str(arch),
        "node_count": len(nodes),
        "fixed_count": sum(1 for rec in nodes if rec["fixed"]),
        "movable_count": sum(1 for rec in nodes if not rec["fixed"]),
        "type_counts": dict(type_counts),
        "macro_count": macro_count,
        "lib_cell_count": len(lib_cells),
        **net_summary,
        **scl_summary,
    }
    _write_aux_and_sidecars(out, arch, timing_path if timing_path.exists() else None, metadata)

    print(f"[convert] public_release case: {case_name}")
    print(f"[convert] output_dir: {out}")
    print(f"[convert] nodes={metadata['node_count']} fixed={metadata['fixed_count']} "
          f"movable={metadata['movable_count']}")
    print(f"[convert] nets={metadata['num_nets']} pins={metadata['num_pins']} "
          f"clock_nets={metadata['num_clock_nets']} max_fanout={metadata['max_fanout']}")
    print(f"[convert] chip={metadata['chip_width']}x{metadata['chip_height']} "
          f"site_entries={metadata['site_entries']}")
    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert public_release benchmark case to pipeline bookshelf format")
    parser.add_argument("--public_release_dir", required=True)
    parser.add_argument("--arch_dir", required=True)
    parser.add_argument("--case", required=True, dest="case_name")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--no_overwrite", action="store_true")
    args = parser.parse_args()

    convert_public_release_case(
        public_release_dir=args.public_release_dir,
        arch_dir=args.arch_dir,
        case_name=args.case_name,
        output_dir=args.output_dir,
        overwrite=not args.no_overwrite,
    )


if __name__ == "__main__":
    main()
