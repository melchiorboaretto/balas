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

# Falha de ambiente (ferramenta, SDK ou projeto ausente), não do modelo.
# Sai com 3 e termina com uma linha "BALAS_ENV_ERROR:", que o deployer.py
# classifica como env_error e o run_all_benchmarks.py trata como crítica
# (repete a iteração em vez de gravar o modelo como "não compilou").
ENV_ERROR_EXIT=3
env_error() {
    local line
    for line in "$@"; do
        echo "$line" >&2
    done
    echo "BALAS_ENV_ERROR: $1" >&2
    exit "$ENV_ERROR_EXIT"
}

if [[ "$BALAS_TARGET" == "stm32" ]]; then
    STM32_PROJECT_DIR="${STM32_PROJECT_DIR:-$REPO_ROOT/cpp-project/stm32-tflite-test}"
    STM32_BUILD_DIR="${STM32_BUILD_DIR:-$STM32_PROJECT_DIR/build}"
    STM32_CMAKE_TOOLCHAIN_FILE="${STM32_CMAKE_TOOLCHAIN_FILE:-$STM32_PROJECT_DIR/cmake/arm-none-eabi-gcc.cmake}"
    CMAKE_GENERATOR="${CMAKE_GENERATOR:-Ninja}"

    if ! command -v cmake >/dev/null 2>&1; then
        env_error "cmake not found." "Install CMake (and Ninja) for the STM32 build."
    fi

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
        env_error "nRF Util not found: $NRFUTIL_BIN" \
            "Install nRF Util and its sdk-manager command, or set NRFUTIL_BIN."
    fi
    if [[ ! -f "$NORDIC_PROJECT_DIR/CMakeLists.txt" ]]; then
        env_error "Nordic project not found: $NORDIC_PROJECT_DIR"
    fi
    # O stderr do nrfutil segue para o stderr deste script (o Python captura).
    if ! nordic_sdk_list="$("$NRFUTIL_BIN" sdk-manager list)"; then
        env_error "'$NRFUTIL_BIN sdk-manager list' failed (see the output above)."
    fi
    if ! grep -Fq "$NORDIC_NCS_VERSION" <<< "$nordic_sdk_list"; then
        # Mostra o que o sdk-manager devolveu e o ambiente em que rodou, para
        # diagnosticar quando o SDK está instalado mas não aparece aqui.
        {
            echo "--- '$NRFUTIL_BIN sdk-manager list' output:"
            echo "$nordic_sdk_list"
            echo "--- HOME=$HOME USER=${USER:-<unset>} NRFUTIL_HOME=${NRFUTIL_HOME:-<unset>}"
            echo "--- PATH=$PATH"
        } >&2
        env_error "nRF Connect SDK $NORDIC_NCS_VERSION not listed by '$NRFUTIL_BIN sdk-manager list'." \
            "Install it with: $NRFUTIL_BIN sdk-manager install $NORDIC_NCS_VERSION"
    fi
    if [[ ! -f "$NORDIC_NCS_DIR/.west/config" ]]; then
        env_error "nRF Connect SDK workspace not found: $NORDIC_NCS_DIR" \
            "Set NORDIC_NCS_DIR to the installed SDK workspace."
    fi

    nordic_cmake_args=(
        "-DBALAS_NORDIC_ENABLE_MODEL=$BALAS_NORDIC_ENABLE_MODEL"
        "-DCMAKE_BUILD_TYPE=$BUILD_CONFIG"
    )
    if [[ "$BALAS_NORDIC_ENABLE_MODEL" == "ON" || "$BALAS_NORDIC_ENABLE_MODEL" == "1" || "$BALAS_NORDIC_ENABLE_MODEL" == "true" ]]; then
        if [[ ! -f "$NORDIC_TFLM_MODULE_DIR/zephyr/module.yml" ]]; then
            env_error "TensorFlow Lite Micro Zephyr module not found: $NORDIC_TFLM_MODULE_DIR" \
                "Install the module revision documented in docs/024_port-nrf52840-dk.md" \
                "or set NORDIC_TFLM_MODULE_DIR."
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
    env_error "Unsupported BALAS_TARGET: $BALAS_TARGET" \
        "Use BALAS_TARGET=nxp, BALAS_TARGET=stm32, or BALAS_TARGET=nordic."
fi

MCUX_WORKSPACE_DIR="${MCUX_WORKSPACE_DIR:-${MCUX_WORKSPACE_LOC:-$REPO_ROOT/cpp-project}}"
MCUXPRESSO_IDE_BIN="${MCUXPRESSO_IDE_BIN:-${MCUXPRESSO:-/usr/local/mcuxpressoide/ide/mcuxpressoide}}"
MCUX_IMPORT_PROJECT="${MCUX_IMPORT_PROJECT:-1}"

if [[ ! -x "$MCUXPRESSO_IDE_BIN" ]]; then
    env_error "MCUXpresso IDE not found or not executable: $MCUXPRESSO_IDE_BIN" \
        "Set MCUXPRESSO_IDE_BIN in the environment or in .balas.env."
fi

if [[ ! -d "$MCUX_WORKSPACE_DIR/$PROJECT_NAME" ]]; then
    env_error "Project directory not found: $MCUX_WORKSPACE_DIR/$PROJECT_NAME" \
        "Set MCUX_WORKSPACE_DIR to the directory that contains $PROJECT_NAME."
fi

if [[ "$MCUX_IMPORT_PROJECT" == "1" || "$MCUX_IMPORT_PROJECT" == "true" ]]; then
    "$MCUXPRESSO_IDE_BIN" -nosplash -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
      -data "$MCUX_WORKSPACE_DIR" -import "$MCUX_WORKSPACE_DIR/$PROJECT_NAME"
fi

"$MCUXPRESSO_IDE_BIN" -nosplash --launcher.suppressErrors -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data "$MCUX_WORKSPACE_DIR" -build "$PROJECT_NAME/$BUILD_CONFIG"
