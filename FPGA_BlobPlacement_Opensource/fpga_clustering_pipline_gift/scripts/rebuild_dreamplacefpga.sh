#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DP="$ROOT/tools/DREAMPlaceFPGA"
JOBS="${JOBS:-$(nproc)}"
ABI="${CMAKE_CXX_ABI:-0}"

cd "$DP"
rm -rf build
mkdir -p build
cd build
cmake .. \
  -DCMAKE_INSTALL_PREFIX="$(pwd)/.." \
  -DPYTHON_EXECUTABLE="$(command -v python)" \
  -DCMAKE_CXX_ABI="$ABI"
make -j"$JOBS"
make install

echo "DREAMPlaceFPGA rebuild finished. Now run: scripts/check_environment_new_server.sh"
