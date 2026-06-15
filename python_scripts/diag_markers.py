"""
Marker-aware diagnostic for the STM32 TFLM firmware built with
BALAS_STM32_MODEL_BOOT_MARKER=ON.

Drains the boot preamble (I.../M.../size), then sends N samples on a single
persistent serial session, printing every byte received per sample so we can
see exactly where the second inference diverges.

Per-sample healthy sequence: R Q G C <N uint32 LE> D V <int32 LE> W
Invoke failure sentinel:     ... -1 (0xFFFFFFFF) then MCU resets
"""

import os
import sys
import time

import numpy as np
import serial

PORT = os.environ.get("BALAS_SERIAL_PORT", "/dev/ttyACM0")
DATASET = "testdata/sanity-model/profiling_dataset"
N_SAMPLES = int(os.environ.get("DIAG_N", "2"))
PER_SAMPLE_TIMEOUT = float(os.environ.get("DIAG_TIMEOUT", "75"))
CONV_DIAG_LABELS = [
    "calls",
    "cmsis_success",
    "fallback_int8",
    "error",
    "calls_1x1",
    "success_1x1",
    "fallback_1x1",
    "calls_3x3",
    "success_3x3",
    "fallback_3x3",
    "scratch_missing",
    "last_status",
    "persistent_scratch",
    "scratch_too_small",
    "arena_scratch",
    "buffer_idx_valid",
    "last_buffer_idx",
    "last_required_scratch",
    "max_required_scratch",
]


def load_samples(n):
    files = sorted(f for f in os.listdir(DATASET) if f.endswith(".bin"))[:n]
    return [(f, np.fromfile(os.path.join(DATASET, f), dtype=np.float32)) for f in files]


def drain_preamble(ser, settle=6.0):
    """Read whatever the firmware emits at boot until it goes quiet."""
    print(f"Draining boot preamble for up to {settle:.0f}s ...")
    deadline = time.monotonic() + settle
    counts = {}
    last_byte_time = time.monotonic()
    ser.timeout = 0.2
    while time.monotonic() < deadline:
        b = ser.read(64)
        if b:
            last_byte_time = time.monotonic()
            for ch in b:
                counts[chr(ch) if 32 <= ch < 127 else f"0x{ch:02x}"] = (
                    counts.get(chr(ch) if 32 <= ch < 127 else f"0x{ch:02x}", 0) + 1
                )
        elif time.monotonic() - last_byte_time > 1.0:
            break
    print(f"  preamble byte histogram: {counts}")


def run_sample(ser, idx, fname, array):
    print(f"\n=== Sample {idx}: {fname} ({array.nbytes} bytes) ===")
    ser.reset_input_buffer()
    ser.timeout = PER_SAMPLE_TIMEOUT
    t0 = time.monotonic()
    ser.write(array.tobytes())

    received = bytearray()
    result_int = None
    # Expect markers + 4-byte int. Read until we see 'W' or timeout.
    while True:
        b = ser.read(1)
        if not b:
            print(f"  TIMEOUT after {time.monotonic()-t0:.1f}s")
            break
        received += b
        # Detect the C marker -> next uint32 block is Conv2D CMSIS-NN counters.
        if received[-1:] == b"C":
            db = ser.read(4 * len(CONV_DIAG_LABELS))
            received += db
            if len(db) == 4 * len(CONV_DIAG_LABELS):
                vals = [
                    int.from_bytes(db[i : i + 4], "little")
                    for i in range(0, len(db), 4)
                ]
                pairs = " ".join(
                    f"{label}={value}"
                    for label, value in zip(CONV_DIAG_LABELS, vals)
                )
                print(f"  conv_diag: {pairs}")
        # Detect the V marker -> next 4 bytes are the int32 time
        if received[-1:] == b"V" and result_int is None:
            tb = ser.read(4)
            received += tb
            if len(tb) == 4:
                result_int = int.from_bytes(tb, "little", signed=True)
        if received[-1:] == b"W":
            break
        # Detect bare error sentinel (-1) when no markers around it
        if len(received) >= 4 and received[-4:] == b"\xff\xff\xff\xff":
            print(f"  ERROR SENTINEL (-1) after {time.monotonic()-t0:.1f}s")
            result_int = -1
            break

    printable = "".join(chr(c) if 32 <= c < 127 else f"[{c:02x}]" for c in received)
    print(f"  raw bytes ({len(received)}): {printable}")
    if result_int is not None:
        print(f"  inference time: {result_int} us")
    return result_int


def main():
    samples = load_samples(N_SAMPLES)
    print(f"Port={PORT}  samples={[s[0] for s in samples]}  timeout={PER_SAMPLE_TIMEOUT}s")
    with serial.Serial(PORT, baudrate=115200, timeout=PER_SAMPLE_TIMEOUT) as ser:
        drain_preamble(ser)
        for i, (fname, arr) in enumerate(samples, 1):
            run_sample(ser, i, fname, arr)
    print("\nDone.")


if __name__ == "__main__":
    main()
