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
      -DBALAS_STM32_ENABLE_MODEL="${BALAS_STM32_ENABLE_MODEL:-OFF}" \
      -DBALAS_STM32_MODEL_BACKEND="${BALAS_STM32_MODEL_BACKEND:-stedgeai}" \
      -DBALAS_STM32_MODEL_BOOT_MARKER="${BALAS_STM32_MODEL_BOOT_MARKER:-OFF}" \
      -DSTEDGEAI_ROOT="${STEDGEAI_ROOT:-$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0}"
    cmake --build "$STM32_BUILD_DIR"
    exit 0
fi

if [[ "$BALAS_TARGET" == "nordic" ]]; then
    NORDIC_PROJECT_DIR="${NORDIC_PROJECT_DIR:-$REPO_ROOT/cpp-project/nrf52840-tflite-test}"
    NORDIC_BUILD_DIR="${NORDIC_BUILD_DIR:-$NORDIC_PROJECT_DIR/build}"
    NORDIC_BOARD="${NORDIC_BOARD:-nrf52840dk/nrf52840}"
    NORDIC_NCS_VERSION="${NORDIC_NCS_VERSION:-v3.4.0}"
    NORDIC_NCS_DIR="${NORDIC_NCS_DIR:-$HOME/ncs/$NORDIC_NCS_VERSION}"
    NORDIC_TFLM_MODULE_DIR="${NORDIC_TFLM_MODULE_DIR:-$NORDIC_NCS_DIR/optional/modules/lib/tflite-micro}"
    BALAS_NORDIC_ENABLE_MODEL="${BALAS_NORDIC_ENABLE_MODEL:-OFF}"
    NRFUTIL_BIN="${NRFUTIL_BIN:-nrfutil}"

    if ! command -v "$NRFUTIL_BIN" >/dev/null 2>&1; then
        echo "nRF Util not found: $NRFUTIL_BIN" >&2
        echo "Install nRF Util and its sdk-manager command, or set NRFUTIL_BIN." >&2
        exit 1
    fi
    if [[ ! -f "$NORDIC_PROJECT_DIR/CMakeLists.txt" ]]; then
        echo "Nordic project not found: $NORDIC_PROJECT_DIR" >&2
        exit 1
    fi
    nordic_sdk_list="$("$NRFUTIL_BIN" sdk-manager list)"
    if ! grep -Fq "$NORDIC_NCS_VERSION" <<< "$nordic_sdk_list"; then
        echo "nRF Connect SDK $NORDIC_NCS_VERSION is not installed." >&2
        echo "Install it with: $NRFUTIL_BIN sdk-manager install $NORDIC_NCS_VERSION" >&2
        exit 1
    fi
    if [[ ! -f "$NORDIC_NCS_DIR/.west/config" ]]; then
        echo "nRF Connect SDK workspace not found: $NORDIC_NCS_DIR" >&2
        echo "Set NORDIC_NCS_DIR to the installed SDK workspace." >&2
        exit 1
    fi

    nordic_cmake_args=(
        "-DBALAS_NORDIC_ENABLE_MODEL=$BALAS_NORDIC_ENABLE_MODEL"
        "-DCMAKE_BUILD_TYPE=$BUILD_CONFIG"
    )
    if [[ "$BALAS_NORDIC_ENABLE_MODEL" == "ON" || "$BALAS_NORDIC_ENABLE_MODEL" == "1" || "$BALAS_NORDIC_ENABLE_MODEL" == "true" ]]; then
        if [[ ! -f "$NORDIC_TFLM_MODULE_DIR/zephyr/module.yml" ]]; then
            echo "TensorFlow Lite Micro Zephyr module not found: $NORDIC_TFLM_MODULE_DIR" >&2
            echo "Install the module revision documented in docs/024_port-nrf52840-dk.md" >&2
            echo "or set NORDIC_TFLM_MODULE_DIR." >&2
            exit 1
        fi
        nordic_cmake_args+=(
            "-DEXTRA_CONF_FILE=$NORDIC_PROJECT_DIR/model.conf"
            "-DZEPHYR_EXTRA_MODULES=$NORDIC_TFLM_MODULE_DIR"
        )
    fi

    "$NRFUTIL_BIN" sdk-manager toolchain launch \
      --ncs-version "$NORDIC_NCS_VERSION" \
      --chdir "$NORDIC_NCS_DIR" \
      -- west build --no-sysbuild --pristine=always \
      -b "$NORDIC_BOARD" \
      -d "$NORDIC_BUILD_DIR" \
      "$NORDIC_PROJECT_DIR" \
      -- "${nordic_cmake_args[@]}"
    exit 0
fi

if [[ "$BALAS_TARGET" != "nxp" ]]; then
    echo "Unsupported BALAS_TARGET: $BALAS_TARGET" >&2
    echo "Use BALAS_TARGET=nxp, BALAS_TARGET=stm32, or BALAS_TARGET=nordic." >&2
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
