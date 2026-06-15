"""
Diagnostic script: sends exactly 2 samples with a persistent serial port.

Usage:
    python -m python_scripts.diag_two_samples \
        testdata/sanity-model/profiling_dataset \
        [--port /dev/ttyACM0] [--timeout 75]

Expected result when firmware is healthy:
    Sample 1: <positive int> us
    Sample 2: <positive int> us

If second inference hangs the MCU, one of two things will happen:
    - Firmware returns -1 (sentinel from Invoke failure → NVIC_SystemReset)
    - Script times out waiting for 4 bytes (infinite loop inside Invoke)
"""

import argparse
import os
import struct
import sys
import time

import numpy as np
import serial


def load_first_two_samples(dataset_dir: str):
    bins = sorted(f for f in os.listdir(dataset_dir) if f.endswith(".bin"))
    if len(bins) < 2:
        raise RuntimeError(f"Need at least 2 .bin files in {dataset_dir}, found {len(bins)}")
    samples = []
    for fname in bins[:2]:
        path = os.path.join(dataset_dir, fname)
        arr = np.fromfile(path, dtype=np.float32)
        samples.append((fname, arr))
    return samples


def send_and_recv(ser: serial.Serial, fname: str, array: np.ndarray) -> None:
    payload = array.tobytes()
    print(f"  Sending {fname}: {len(payload)} bytes ...", end="", flush=True)
    t0 = time.monotonic()
    ser.write(payload)

    resp = ser.read(4)
    elapsed = time.monotonic() - t0

    if len(resp) == 0:
        print(f"\n  TIMEOUT after {elapsed:.1f}s — no bytes received.")
        print("  → Firmware is in an infinite loop inside Invoke() or serial_read().")
        return

    if len(resp) < 4:
        print(f"\n  PARTIAL ({len(resp)}/4 bytes) after {elapsed:.1f}s: {resp.hex()}")
        print("  → Firmware may have reset mid-send.")
        return

    value = struct.unpack("<i", resp)[0]
    if value == -1:
        print(f"\n  ERROR SENTINEL (-1) after {elapsed:.1f}s")
        print("  → Invoke() returned kTfLiteError. Firmware has reset via NVIC_SystemReset().")
        print("  → Rebuild with BOOT_MARKER=ON and add soft-fallback logs to narrow down which op fails.")
    else:
        print(f" {value} µs  ({elapsed:.1f}s wall)")


def main():
    parser = argparse.ArgumentParser(description="Two-sample persistent-port diagnostic")
    parser.add_argument("dataset_dir", help="Directory with profiling .bin samples")
    parser.add_argument("--port", default=os.environ.get("BALAS_SERIAL_PORT", "/dev/ttyACM0"))
    parser.add_argument("--timeout", type=float, default=75.0, help="Per-sample timeout in seconds")
    args = parser.parse_args()

    samples = load_first_two_samples(args.dataset_dir)

    print(f"Port: {args.port}  timeout: {args.timeout}s")
    print(f"Samples: {[s[0] for s in samples]}")
    print()

    with serial.Serial(port=args.port, baudrate=115200, timeout=args.timeout) as ser:
        ser.reset_input_buffer()
        for i, (fname, array) in enumerate(samples, 1):
            print(f"Sample {i}:")
            send_and_recv(ser, fname, array)
            if i < len(samples):
                time.sleep(0.1)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
