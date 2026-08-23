#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "[metis_script] usage: $0 <graph_file> <num_parts> <ub_factor> <seed> <log_file>" >&2
  exit 2
fi

graph_file="$1"
num_parts="$2"
ub_factor="$3"
seed="$4"
log_file="$5"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve gpmetis executable in a portable order:
# 1) explicit env var GPMETIS_EXEC
# 2) PATH
# 3) local bundled locations under K_SpecPart
# 4) legacy hardcoded /usr/bin/gpmetis
gpmetis_exec=""
if [ -n "${GPMETIS_EXEC:-}" ] && [ -x "${GPMETIS_EXEC:-}" ]; then
  gpmetis_exec="$GPMETIS_EXEC"
elif command -v gpmetis >/dev/null 2>&1; then
  gpmetis_exec="$(command -v gpmetis)"
else
  for cand in \
    "$script_dir/gpmetis" \
    "$script_dir/bin/gpmetis" \
    "$script_dir/../gpmetis" \
    "/usr/bin/gpmetis"
  do
    if [ -x "$cand" ]; then
      gpmetis_exec="$cand"
      break
    fi
  done
fi

if [ -z "$gpmetis_exec" ]; then
  echo "[metis_script] ERROR: gpmetis not found." >&2
  echo "[metis_script] Set GPMETIS_EXEC=/abs/path/to/gpmetis, or put gpmetis in PATH." >&2
  exit 127
fi

# If gpmetis is bundled with a local lib directory, prefer it for libmetis.so.
local_lib_dir=""
for d in \
  "$script_dir/lib" \
  "$script_dir/../lib" \
  "$(cd "$(dirname "$gpmetis_exec")"/.. && pwd)/lib"
do
  if [ -d "$d" ] && ls "$d"/libmetis.so* >/dev/null 2>&1; then
    local_lib_dir="$d"
    break
  fi
done

if [ -n "$local_lib_dir" ]; then
  LD_LIBRARY_PATH="$local_lib_dir:${LD_LIBRARY_PATH:-}" \
    "$gpmetis_exec" "$graph_file" "$num_parts" \
      -ptype=rb -ufactor="$ub_factor" -seed="$seed" -dbglvl=0 > "$log_file"
else
  "$gpmetis_exec" "$graph_file" "$num_parts" \
    -ptype=rb -ufactor="$ub_factor" -seed="$seed" -dbglvl=0 > "$log_file"
fi
