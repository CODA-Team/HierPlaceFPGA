#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./rebuild_par.sh                  # build par (default)
#   ./rebuild_par.sh par              # build par
#   ./rebuild_par.sh openroad         # build openroad
#   ./rebuild_par.sh all              # build par + openroad
#   ./rebuild_par.sh openroad 16      # build with 16 jobs

TARGET="${1:-par}"
JOBS="${2:-8}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OR_SRC="${SCRIPT_DIR}/OpenROAD"
BUILD_DIR="${SCRIPT_DIR}/build_gcc13"
GCC13_PREFIX="/home/thermal/.local/share/mamba/envs/gcc13"

case "${TARGET}" in
  par|openroad|all) ;;
  *)
    echo "Error: target must be one of: par | openroad | all"
    exit 1
    ;;
esac

echo "[INFO] Configuring CMake in ${BUILD_DIR}"
cmake -S "${OR_SRC}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=RELEASE \
  -DCMAKE_CXX_COMPILER="${GCC13_PREFIX}/bin/g++" \
  -DCMAKE_C_COMPILER="${GCC13_PREFIX}/bin/gcc" \
  -DCMAKE_PREFIX_PATH="${GCC13_PREFIX}" \
  -DBoost_ROOT="${GCC13_PREFIX}" \
  -DBoost_DIR="${GCC13_PREFIX}/lib/cmake/Boost-1.85.0" \
  -DBoost_NO_SYSTEM_PATHS=ON \
  -DBUILD_PYTHON=OFF \
  -DBUILD_GUI=OFF \
  -DBUILD_TCLX=ON \
  -DBUILD_DST=OFF

if [[ "${TARGET}" == "par" || "${TARGET}" == "all" ]]; then
  echo "[INFO] Building target: par"
  cmake --build "${BUILD_DIR}" --target par -j"${JOBS}"
fi

if [[ "${TARGET}" == "openroad" || "${TARGET}" == "all" ]]; then
  echo "[INFO] Building target: openroad"
  cmake --build "${BUILD_DIR}" --target openroad -j"${JOBS}"
  mkdir -p "${BUILD_DIR}/bin"
  ln -sf ../src/openroad "${BUILD_DIR}/bin/openroad"
  echo "[INFO] openroad path: ${BUILD_DIR}/bin/openroad"
fi

echo "[INFO] Done."
