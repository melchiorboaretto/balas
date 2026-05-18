#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${BALAS_CONFIG_FILE:-$SCRIPT_DIR/.balas.env}"
if [[ -f "$CONFIG_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
    set +a
fi

REPO_ROOT="${REPO_ROOT:-$SCRIPT_DIR}"
BALAS_TARGET="${BALAS_TARGET:-nxp}"
PROJECT_NAME="${PROJECT_NAME:-tflite-test}"
BUILD_CONFIG="${BUILD_CONFIG:-Debug}"

if [[ "$BALAS_TARGET" == "stm32" ]]; then
    STM32_PROJECT_DIR="${STM32_PROJECT_DIR:-$REPO_ROOT/cpp-project/stm32-tflite-test}"
    STM32_BUILD_DIR="${STM32_BUILD_DIR:-$STM32_PROJECT_DIR/build}"
    STM32_CMAKE_TOOLCHAIN_FILE="${STM32_CMAKE_TOOLCHAIN_FILE:-$STM32_PROJECT_DIR/cmake/arm-none-eabi-gcc.cmake}"
    CMAKE_GENERATOR="${CMAKE_GENERATOR:-Ninja}"

    cmake -S "$STM32_PROJECT_DIR" -B "$STM32_BUILD_DIR" \
      -G "$CMAKE_GENERATOR" \
      -DCMAKE_TOOLCHAIN_FILE="$STM32_CMAKE_TOOLCHAIN_FILE" \
      -DCMAKE_BUILD_TYPE="$BUILD_CONFIG" \
      -DBALAS_STM32_ENABLE_MODEL="${BALAS_STM32_ENABLE_MODEL:-OFF}"
    cmake --build "$STM32_BUILD_DIR"
    exit 0
fi

if [[ "$BALAS_TARGET" != "nxp" ]]; then
    echo "Unsupported BALAS_TARGET: $BALAS_TARGET" >&2
    echo "Use BALAS_TARGET=nxp or BALAS_TARGET=stm32." >&2
    exit 1
fi

MCUX_WORKSPACE_DIR="${MCUX_WORKSPACE_DIR:-${MCUX_WORKSPACE_LOC:-$REPO_ROOT/cpp-project}}"
MCUXPRESSO_IDE_BIN="${MCUXPRESSO_IDE_BIN:-${MCUXPRESSO:-/usr/local/mcuxpressoide/ide/mcuxpressoide}}"
MCUX_IMPORT_PROJECT="${MCUX_IMPORT_PROJECT:-1}"

if [[ ! -x "$MCUXPRESSO_IDE_BIN" ]]; then
    echo "MCUXpresso IDE not found or not executable: $MCUXPRESSO_IDE_BIN" >&2
    echo "Set MCUXPRESSO_IDE_BIN in the environment or in .balas.env." >&2
    exit 1
fi

if [[ ! -d "$MCUX_WORKSPACE_DIR/$PROJECT_NAME" ]]; then
    echo "Project directory not found: $MCUX_WORKSPACE_DIR/$PROJECT_NAME" >&2
    echo "Set MCUX_WORKSPACE_DIR to the directory that contains $PROJECT_NAME." >&2
    exit 1
fi

if [[ "$MCUX_IMPORT_PROJECT" == "1" || "$MCUX_IMPORT_PROJECT" == "true" ]]; then
    "$MCUXPRESSO_IDE_BIN" -nosplash -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
      -data "$MCUX_WORKSPACE_DIR" -import "$MCUX_WORKSPACE_DIR/$PROJECT_NAME"
fi

"$MCUXPRESSO_IDE_BIN" -nosplash -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data "$MCUX_WORKSPACE_DIR" -build "$PROJECT_NAME/$BUILD_CONFIG"
