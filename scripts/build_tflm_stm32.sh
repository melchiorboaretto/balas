#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

TFLM_REPO_URL="${TFLM_REPO_URL:-https://github.com/tensorflow/tflite-micro.git}"
TFLM_COMMIT="${TFLM_COMMIT:-9f5ac257ee7f6a07f1f3c28aa1c86411c05f11e3}"
TFLM_TARGET="${TFLM_TARGET:-cortex_m_generic}"
TFLM_TARGET_ARCH="${TFLM_TARGET_ARCH:-cortex-m7+fp}"
TFLM_FPU="${TFLM_FPU:-fpv5-d16}"
TFLM_OPTIMIZED_KERNEL_DIR="${TFLM_OPTIMIZED_KERNEL_DIR:-none}"
TFLM_WORK_DIR="${TFLM_WORK_DIR:-$REPO_ROOT/external/tflm-stm32}"
TFLM_SRC_DIR="${TFLM_SRC_DIR:-$TFLM_WORK_DIR/src/tflite-micro}"
TFLM_PACKAGE_DIR="${TFLM_PACKAGE_DIR:-$TFLM_WORK_DIR/package}"
TFLM_PYTHON="${TFLM_PYTHON:-$REPO_ROOT/.venv/bin/python}"
TFLM_CORE_OPTIMIZATION_LEVEL="${TFLM_CORE_OPTIMIZATION_LEVEL:--O3}"
TFLM_KERNEL_OPTIMIZATION_LEVEL="${TFLM_KERNEL_OPTIMIZATION_LEVEL:--O3}"
TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL="${TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL:--O3}"
JOBS="${JOBS:-$(nproc)}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Required command not found: $1" >&2
        exit 1
    fi
}

require_command git
require_command make
require_command python3
require_command arm-none-eabi-gcc
require_command arm-none-eabi-g++
require_command arm-none-eabi-ar

TARGET_TOOLCHAIN_ROOT="${TARGET_TOOLCHAIN_ROOT:-$(dirname "$(command -v arm-none-eabi-gcc)")/}"

if [[ ! -x "$TFLM_PYTHON" ]]; then
    TFLM_PYTHON="$(command -v python3)"
fi

"$TFLM_PYTHON" - <<'PY'
import numpy  # noqa: F401
from PIL import Image  # noqa: F401
PY

PYTHON_SHIM_DIR="$TFLM_WORK_DIR/python-shim"
mkdir -p "$PYTHON_SHIM_DIR"
cat > "$PYTHON_SHIM_DIR/python3" <<EOF
#!/usr/bin/env bash
exec "$TFLM_PYTHON" "\$@"
EOF
chmod +x "$PYTHON_SHIM_DIR/python3"
export PATH="$PYTHON_SHIM_DIR:$PATH"

mkdir -p "$TFLM_WORK_DIR/src"

if [[ ! -d "$TFLM_SRC_DIR/.git" ]]; then
    git clone --filter=blob:none "$TFLM_REPO_URL" "$TFLM_SRC_DIR"
fi

git -C "$TFLM_SRC_DIR" fetch --depth 1 origin "$TFLM_COMMIT"
git -C "$TFLM_SRC_DIR" checkout --detach "$TFLM_COMMIT"

apply_stm32_tflm_patches() {
    local patch_file

    for patch_file in "$REPO_ROOT"/scripts/patches/tflm-stm32-*.patch; do
        if git -C "$TFLM_SRC_DIR" apply --check "$patch_file" >/dev/null 2>&1; then
            git -C "$TFLM_SRC_DIR" apply "$patch_file"
        elif git -C "$TFLM_SRC_DIR" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
            echo "STM32 TFLM patch already applied: $patch_file"
        else
            echo "Could not apply STM32 TFLM patch: $patch_file" >&2
            exit 1
        fi
    done
}

if [[ "$TFLM_OPTIMIZED_KERNEL_DIR" == "cmsis_nn" ]]; then
    apply_stm32_tflm_patches
fi

make_args=(
    -j"$JOBS"
    -f tensorflow/lite/micro/tools/make/Makefile
    "TARGET=$TFLM_TARGET"
    "TARGET_ARCH=$TFLM_TARGET_ARCH"
    "FPU=$TFLM_FPU"
    microlite
)

if [[ "$TFLM_OPTIMIZED_KERNEL_DIR" != "none" ]]; then
    make_args+=("OPTIMIZED_KERNEL_DIR=$TFLM_OPTIMIZED_KERNEL_DIR")
fi
if [[ -n "$TFLM_CORE_OPTIMIZATION_LEVEL" ]]; then
    make_args+=("CORE_OPTIMIZATION_LEVEL=$TFLM_CORE_OPTIMIZATION_LEVEL")
fi
if [[ -n "$TFLM_KERNEL_OPTIMIZATION_LEVEL" ]]; then
    make_args+=("KERNEL_OPTIMIZATION_LEVEL=$TFLM_KERNEL_OPTIMIZATION_LEVEL")
fi
if [[ -n "$TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL" ]]; then
    make_args+=("THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL=$TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL")
fi
make_args+=("TARGET_TOOLCHAIN_ROOT=$TARGET_TOOLCHAIN_ROOT")

make -C "$TFLM_SRC_DIR" "${make_args[@]}"

if [[ "$TFLM_OPTIMIZED_KERNEL_DIR" == "none" ]]; then
    tflm_gen_dir="$TFLM_SRC_DIR/gen/${TFLM_TARGET}_${TFLM_TARGET_ARCH}_default_gcc"
else
    tflm_gen_dir="$TFLM_SRC_DIR/gen/${TFLM_TARGET}_${TFLM_TARGET_ARCH}_default_${TFLM_OPTIMIZED_KERNEL_DIR}_gcc"
fi

built_lib="$tflm_gen_dir/lib/libtensorflow-microlite.a"
if [[ ! -f "$built_lib" ]]; then
    echo "Expected libtensorflow-microlite.a was not produced: $built_lib" >&2
    find "$TFLM_SRC_DIR/gen" \
        -path "*/lib/libtensorflow-microlite.a" \
        -type f \
        -print >&2
    exit 1
fi

rm -rf "$TFLM_PACKAGE_DIR"
mkdir -p "$TFLM_PACKAGE_DIR/lib"
cp "$built_lib" "$TFLM_PACKAGE_DIR/lib/libtensorflow-microlite.a"

cat > "$TFLM_PACKAGE_DIR/build-info.env" <<EOF
TFLM_REPO_URL=$TFLM_REPO_URL
TFLM_COMMIT=$TFLM_COMMIT
TFLM_TARGET=$TFLM_TARGET
TFLM_TARGET_ARCH=$TFLM_TARGET_ARCH
TFLM_FPU=$TFLM_FPU
TFLM_OPTIMIZED_KERNEL_DIR=$TFLM_OPTIMIZED_KERNEL_DIR
TFLM_CORE_OPTIMIZATION_LEVEL=$TFLM_CORE_OPTIMIZATION_LEVEL
TFLM_KERNEL_OPTIMIZATION_LEVEL=$TFLM_KERNEL_OPTIMIZATION_LEVEL
TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL=$TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL
TFLM_PYTHON=$TFLM_PYTHON
TARGET_TOOLCHAIN_ROOT=$TARGET_TOOLCHAIN_ROOT
TFLM_SOURCE_LIB=$built_lib
TFLM_PACKAGE_LIB=$TFLM_PACKAGE_DIR/lib/libtensorflow-microlite.a
ARM_NONE_EABI_GCC=$(arm-none-eabi-gcc --version | head -n 1)
EOF

echo "Built TFLM STM32 package:"
echo "  $TFLM_PACKAGE_DIR/lib/libtensorflow-microlite.a"
echo "Build metadata:"
echo "  $TFLM_PACKAGE_DIR/build-info.env"
