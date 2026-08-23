#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, List, Tuple
import argparse
import re

import matplotlib.pyplot as plt


MACRO_KEYWORDS = [
    "BRAM", "URAM", "DSP", "RAM", "PLL", "MMCM", "FIFO", "IO"
]


def is_macro(name: str) -> bool:
    u = name.upper()
    return any(k in u for k in MACRO_KEYWORDS)


def read_pl(path: str, name_regex: Optional[str] = None):
    pat = re.compile(name_regex) if name_regex else None

    macro_x, macro_y = [], []
    cell_x, cell_y = [], []
    bad = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 3:
                bad += 1
                continue

            name = parts[0]
            if pat and not pat.search(name):
                continue

            try:
                x = float(parts[1])
                y = float(parts[2])
            except ValueError:
                bad += 1
                continue

            if is_macro(name):
                macro_x.append(x)
                macro_y.append(y)
            else:
                cell_x.append(x)
                cell_y.append(y)

    return cell_x, cell_y, macro_x, macro_y, bad


def main():
    ap = argparse.ArgumentParser("Visualize ALL cells from .pl")
    ap.add_argument("pl", help=".pl placement file")
    ap.add_argument("-o", "--out", default="", help="output image")
    ap.add_argument("--title", default="Placement (All Cells)", help="title")
    ap.add_argument("--invert-y", action="store_true")
    ap.add_argument("--regex", default="", help="filter instance name by regex")
    ap.add_argument("--density", action="store_true",
                    help="use hexbin for standard cells")
    ap.add_argument("--gridsize", type=int, default=120)
    args = ap.parse_args()

    cell_x, cell_y, macro_x, macro_y, bad = read_pl(
        args.pl, args.regex or None
    )

    print(f"[info] cells: {len(cell_x)}, macros: {len(macro_x)}")
    if bad:
        print(f"[warn] skipped {bad} malformed lines")

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_title(args.title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")

    # ---- 普通单元 ----
    if args.density:
        hb = ax.hexbin(
            cell_x, cell_y,
            gridsize=args.gridsize,
            mincnt=1,
            linewidths=0
        )
        fig.colorbar(hb, ax=ax, label="cell density")
    else:
        ax.scatter(
            cell_x, cell_y,
            s=0.03,
            #c="lightgray",
            c="blue",
            alpha=0.8,
            label="std cells"
        )

    # ---- 宏 ----
    if macro_x:
        ax.scatter(
            macro_x, macro_y,
            s=10,
            c="red",
            alpha=0.9,
            label="macros"
        )

    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.3, alpha=0.3)

    if args.invert_y:
        ax.invert_yaxis()

    ax.legend(loc="best", fontsize=9)

    plt.tight_layout()
    if args.out:
        fig.savefig(args.out, dpi=300)
        print(f"[ok] saved to {args.out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
