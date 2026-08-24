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

if [[ "$BALAS_TARGET" == "stm32" ]]; then
    STM32_PROJECT_DIR="${STM32_PROJECT_DIR:-$REPO_ROOT/cpp-project/stm32-tflite-test}"
    STM32_BUILD_DIR="${STM32_BUILD_DIR:-$STM32_PROJECT_DIR/build}"
    STM32_FIRMWARE_FILE="${STM32_FIRMWARE_FILE:-$STM32_BUILD_DIR/stm32-tflite-test.elf}"
    STM32_PROGRAMMER_CLI="${STM32_PROGRAMMER_CLI:-STM32_Programmer_CLI}"

    if [[ ! -f "$STM32_FIRMWARE_FILE" ]]; then
        echo "STM32 firmware image not found: $STM32_FIRMWARE_FILE" >&2
        echo "Build first with BALAS_TARGET=stm32 ./compile.sh or set STM32_FIRMWARE_FILE." >&2
        exit 1
    fi

    "$STM32_PROGRAMMER_CLI" -c port=SWD -w "$STM32_FIRMWARE_FILE" -v -rst
    exit 0
fi

if [[ "$BALAS_TARGET" == "nordic" ]]; then
    NORDIC_PROJECT_DIR="${NORDIC_PROJECT_DIR:-$REPO_ROOT/cpp-project/nrf52840-tflite-test}"
    NORDIC_BUILD_DIR="${NORDIC_BUILD_DIR:-$NORDIC_PROJECT_DIR/build}"
    NORDIC_FIRMWARE_FILE="${NORDIC_FIRMWARE_FILE:-$NORDIC_BUILD_DIR/zephyr/zephyr.hex}"
    NORDIC_PROBE_SERIAL="${NORDIC_PROBE_SERIAL:-}"
    NRFUTIL_BIN="${NRFUTIL_BIN:-nrfutil}"

    if ! command -v "$NRFUTIL_BIN" >/dev/null 2>&1; then
        echo "nRF Util not found: $NRFUTIL_BIN" >&2
        exit 1
    fi
    if [[ ! -f "$NORDIC_FIRMWARE_FILE" ]]; then
        echo "Nordic firmware image not found: $NORDIC_FIRMWARE_FILE" >&2
        echo "Build first with BALAS_TARGET=nordic ./compile.sh or set NORDIC_FIRMWARE_FILE." >&2
        exit 1
    fi

    nordic_program_cmd=(
        "$NRFUTIL_BIN" device program
        --firmware "$NORDIC_FIRMWARE_FILE"
        --family nrf52
        --options chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,verify=VERIFY_READ,reset=RESET_SYSTEM
    )
    if [[ -n "$NORDIC_PROBE_SERIAL" ]]; then
        nordic_program_cmd+=(--serial-number "$NORDIC_PROBE_SERIAL")
    fi
    "${nordic_program_cmd[@]}"
    exit 0
fi

if [[ "$BALAS_TARGET" != "nxp" ]]; then
    echo "Unsupported BALAS_TARGET: $BALAS_TARGET" >&2
    echo "Use BALAS_TARGET=nxp, BALAS_TARGET=stm32, or BALAS_TARGET=nordic." >&2
    exit 1
fi

PROJECT_NAME="${PROJECT_NAME:-tflite-test}"
WORKSPACE_DIR="${WORKSPACE_DIR:-$REPO_ROOT/cpp-project}"
PROJECT_DIR="${PROJECT_DIR:-$WORKSPACE_DIR/$PROJECT_NAME}"
BUILD_DIR="${BUILD_DIR:-$PROJECT_DIR/Debug}"
AXF_FILE="${AXF_FILE:-$BUILD_DIR/$PROJECT_NAME.axf}"

TARGET_DEVICE="${TARGET_DEVICE:-MCXN947}"
CORE_INDEX="${CORE_INDEX:-0}"
BOOTROM_STALL="${BOOTROM_STALL:-0x50000040}"

LINKSERVER_ROOT="${LINKSERVER_ROOT:-/usr/local/LinkServer}"
REDLINK_BIN="${REDLINK_BIN:-$LINKSERVER_ROOT/binaries/crt_emu_cm_redlink}"
LINKSERVER_FLASH_DIR="${LINKSERVER_FLASH_DIR:-$LINKSERVER_ROOT/binaries/Flash}"
PACKAGE_SUPPORT_DIR="${PACKAGE_SUPPORT_DIR:-$WORKSPACE_DIR/.mcuxpressoide_packages_support/MCXN947_support}"
PACKAGE_FLASH_DIR="${PACKAGE_FLASH_DIR:-$PACKAGE_SUPPORT_DIR/Flash}"
PRECONNECT_SCRIPT="${PRECONNECT_SCRIPT:-$LINKSERVER_ROOT/binaries/ToolScripts/LS_preconnect_MCXN9XX.scp}"

# Optional. If omitted, LinkServer will auto-select the probe when possible.
PROBE_SERIAL="${PROBE_SERIAL:-${1:-}}"

if [[ ! -f "$REDLINK_BIN" ]]; then
    echo "crt_emu_cm_redlink not found: $REDLINK_BIN" >&2
    echo "Set REDLINK_BIN or LINKSERVER_ROOT to match your local LinkServer installation." >&2
    exit 1
fi

if [[ ! -f "$AXF_FILE" ]]; then
    echo "Firmware image not found: $AXF_FILE" >&2
    echo "Build the project first or override AXF_FILE/BUILD_DIR/PROJECT_NAME." >&2
    exit 1
fi

cmd=(
    "$REDLINK_BIN"
    --flash-load-exec "$AXF_FILE"
    -p "$TARGET_DEVICE"
    --bootromstall "$BOOTROM_STALL"
    -CoreIndex="$CORE_INDEX"
    --flash-driver=
    -x "$BUILD_DIR"
    --flash-hashing
)

if [[ -n "$PROBE_SERIAL" ]]; then
    cmd+=(--probeserial "$PROBE_SERIAL")
fi

if [[ -d "$LINKSERVER_FLASH_DIR" ]]; then
    cmd+=(--flash-dir "$LINKSERVER_FLASH_DIR")
fi

if [[ -d "$PACKAGE_FLASH_DIR" ]]; then
    cmd+=(--flash-dir "$PACKAGE_FLASH_DIR")
fi

if [[ -f "$PRECONNECT_SCRIPT" ]]; then
    cmd+=(--PreconnectScript "$PRECONNECT_SCRIPT")
fi

"${cmd[@]}"
