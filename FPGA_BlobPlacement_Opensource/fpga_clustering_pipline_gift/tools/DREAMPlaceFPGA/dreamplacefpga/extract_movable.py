#!/usr/bin/env python3
"""
Extract movable cells from design.final.pl for warm start
"""

import sys

def extract_movable(input_file, output_file):
    """Extract only movable cells (no FIXED keyword)"""
    
    movable_lines = []
    
    with open(input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if 'FIXED' not in line:
                movable_lines.append(line)
    
    with open(output_file, 'w') as f:
        for line in movable_lines:
            f.write(line + '\n')
    
    print(f"Extracted {len(movable_lines)} movable cells to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_movable.py <input.pl> <output_movable.pl>")
        sys.exit(1)
    
    extract_movable(sys.argv[1], sys.argv[2])
