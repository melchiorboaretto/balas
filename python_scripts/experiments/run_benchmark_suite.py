import argparse
import csv
import os
import re
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import tensorflow as tf

from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
from python_scripts.code_generator.generator import (
    generate_cpp_code,
    generate_nordic_tflm_code,
    generate_stm32_tflm_code,
)
from python_scripts.config import default_serial_port, repo_root
from python_scripts.deployer.deployer import compile_cpp_project, deploy_to_mcu
from python_scripts.experiments.common import (
    csv_append_row,
    iter_dataset_arrays,
    load_suite_manifest,
    relative_to_repo,
    resolve_path,
)
from python_scripts.mac_calculator.mac_calculator import count_macs
from python_scripts.profiler.profiler import send_array_and_get_int


CSV_FIELDNAMES = [
    "timestamp_utc",
    "suite_name",
    "family",
    "name",
    "target",
    "model_backend",
    "status",
    "error",
    "model_path",
    "dataset_path",
    "serial_device",
    "skip_compile",
    "skip_deploy",
    "attempts",
    "sample_count",
    "arena_source",
    "arena_estimated",
    "arena_initial",
    "arena_final",
    "arena_retry_step",
    "macs",
    "workstation_avg_us",
    "workstation_std_us",
    "mcu_avg_us",
    "mcu_std_us",
    "arena_time_ms",
    "mac_time_ms",
    "workstation_time_ms",
    "cpp_codegen_time_ms",
    "compile_time_ms",
    "deploy_time_ms",
    "profiling_time_ms",
]

STM32_EDGEAI_PARAMS = REPO_ROOT / "cpp-project/stm32-tflite-test/Core/Generated/EdgeAI/balas_model_data_params.h"


def parse_stm32_edgeai_activation_size() -> int:
    text = STM32_EDGEAI_PARAMS.read_text(encoding="utf-8")
    match = re.search(r"#define\s+AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZE\s+\((\d+)\)", text)
    if not match:
        raise RuntimeError(f"Could not parse activation size from {STM32_EDGEAI_PARAMS}")
    return int(match.group(1))


def resolve_target_config(entry: dict, default_options: dict) -> tuple[str, str, bool]:
    target = entry.get("target") or default_options["target"]
    model_backend = entry.get("model_backend") or default_options["model_backend"]
    if target == "nordic" and model_backend != "tflm":
        raise ValueError("The Nordic target currently supports only the tflm backend.")
    use_stm32_edgeai = target == "stm32" and model_backend == "stedgeai"
    return target, model_backend, use_stm32_edgeai


def quantize_for_model(float_input: np.ndarray, input_details: dict) -> np.ndarray:
    input_shape = tuple(int(dim) for dim in input_details["shape"])
    reshaped = float_input.reshape(input_shape)
    target_dtype = input_details["dtype"]
    if target_dtype == np.float32:
        return reshaped.astype(np.float32, copy=False)

    scale, zero_point = input_details["quantization"]
    if scale == 0:
        raise ValueError("Model input quantization scale is zero.")

    dtype_info = np.iinfo(target_dtype)
    quantized = np.round(reshaped / scale + zero_point)
    quantized = np.clip(quantized, dtype_info.min, dtype_info.max)
    return quantized.astype(target_dtype)


def measure_workstation_latency(
    model_path: Path,
    dataset_path: Path,
    repeats: int,
) -> tuple[float, float, int, float]:
    if repeats < 1:
        raise ValueError("workstation repeats must be at least 1")

    samples = iter_dataset_arrays(dataset_path)
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]

    expected_count = int(np.prod(input_details["shape"]))
    durations_us = []

    start = time.perf_counter_ns()
    for _, sample in samples:
        if sample.size != expected_count:
            raise ValueError(
                f"Dataset sample has {sample.size} float32 values, expected {expected_count}",
            )
        prepared_input = quantize_for_model(sample, input_details)
        for _ in range(repeats):
            interpreter.set_tensor(input_details["index"], prepared_input)
            invoke_start = time.perf_counter_ns()
            interpreter.invoke()
            invoke_end = time.perf_counter_ns()
            durations_us.append((invoke_end - invoke_start) / 1000.0)
    end = time.perf_counter_ns()

    return (
        float(np.mean(durations_us)),
        float(np.std(durations_us)),
        len(samples),
        (end - start) / 1_000_000.0,
    )


def measure_mcu_latency(
    serial_device: str,
    dataset_path: Path,
) -> tuple[float, float, int, float]:
    samples = iter_dataset_arrays(dataset_path)
    durations_us = []

    start = time.perf_counter_ns()
    for _, sample in samples:
        durations_us.append(send_array_and_get_int(serial_device, sample))
    end = time.perf_counter_ns()

    return (
        float(np.mean(durations_us)),
        float(np.std(durations_us)),
        len(samples),
        (end - start) / 1_000_000.0,
    )


def run_entry(
    suite_name: str,
    entry: dict,
    default_options: dict,
    manifest_dir: Path,
    output_csv: Path,
    workstation_repeats: int,
    max_attempts: int,
    arena_retry_step: int,
) -> dict:
    model_path = resolve_path(manifest_dir, entry["model_path"])
    dataset_path = resolve_path(manifest_dir, entry["profiling_dataset"])

    family = entry.get("family", "unclassified")
    name = entry.get("name", model_path.stem)
    target, model_backend, use_stm32_edgeai = resolve_target_config(entry, default_options)
    os.environ["BALAS_TARGET"] = target
    if target == "stm32":
        os.environ.setdefault("BALAS_STM32_ENABLE_MODEL", "ON")
        os.environ["BALAS_STM32_MODEL_BACKEND"] = model_backend
    elif target == "nordic":
        os.environ.setdefault("BALAS_NORDIC_ENABLE_MODEL", "ON")
        os.environ["BALAS_NORDIC_MODEL_BACKEND"] = model_backend
    serial_device = entry.get("serial_device") or default_options["serial_device"]
    skip_compile = bool(entry.get("skip_compile", default_options["skip_compile"]))
    skip_deploy = bool(entry.get("skip_deploy", default_options["skip_deploy"]))

    if entry.get("arena_size") is not None:
        arena_source = "manual"
    elif use_stm32_edgeai:
        arena_source = "stedgeai"
    else:
        arena_source = "stm32tflm"
    arena_estimated = None
    arena_initial = None
    arena_final = None
    attempts = 0

    arena_time_ms = 0.0
    mac_time_ms = 0.0
    workstation_time_ms = 0.0
    cpp_codegen_time_ms = 0.0
    compile_time_ms = 0.0
    deploy_time_ms = 0.0
    profiling_time_ms = 0.0
    macs = None
    workstation_avg_us = None
    workstation_std_us = None
    mcu_avg_us = None
    mcu_std_us = None
    sample_count = 0
    error = ""
    status = "ok"

    try:
        if entry.get("arena_size") is not None:
            arena_initial = int(entry["arena_size"])
            arena_estimated = arena_initial
        elif use_stm32_edgeai:
            arena_start = time.perf_counter_ns()
            arena_estimated = parse_stm32_edgeai_activation_size()
            arena_time_ms = (time.perf_counter_ns() - arena_start) / 1_000_000.0
            arena_initial = arena_estimated
        else:
            arena_start = time.perf_counter_ns()
            arena_estimated = estimate_tensor_arena_size(str(model_path))
            arena_time_ms = (time.perf_counter_ns() - arena_start) / 1_000_000.0
            arena_initial = arena_estimated

        mac_start = time.perf_counter_ns()
        macs = count_macs(str(model_path))
        mac_time_ms = (time.perf_counter_ns() - mac_start) / 1_000_000.0

        (
            workstation_avg_us,
            workstation_std_us,
            sample_count,
            workstation_time_ms,
        ) = measure_workstation_latency(model_path, dataset_path, workstation_repeats)

        current_arena = arena_initial
        while attempts < max_attempts:
            attempts += 1
            if not use_stm32_edgeai:
                codegen_start = time.perf_counter_ns()
                if target == "stm32" and model_backend == "tflm":
                    generate_stm32_tflm_code(str(model_path), current_arena)
                elif target == "nordic" and model_backend == "tflm":
                    generate_nordic_tflm_code(str(model_path), current_arena)
                else:
                    generate_cpp_code(str(model_path), current_arena)
                cpp_codegen_time_ms += (time.perf_counter_ns() - codegen_start) / 1_000_000.0

            if not skip_compile:
                compile_start = time.perf_counter_ns()
                compile_cpp_project()
                compile_time_ms += (time.perf_counter_ns() - compile_start) / 1_000_000.0

            if not skip_deploy:
                deploy_start = time.perf_counter_ns()
                deploy_to_mcu()
                deploy_time_ms += (time.perf_counter_ns() - deploy_start) / 1_000_000.0
                if target == "stm32":
                    time.sleep(float(os.environ.get("BALAS_STM32_POST_DEPLOY_DELAY_SEC", "3")))
                elif target == "nordic":
                    time.sleep(float(os.environ.get("BALAS_NORDIC_POST_DEPLOY_DELAY_SEC", "2")))

            try:
                (
                    mcu_avg_us,
                    mcu_std_us,
                    sample_count,
                    profiling_elapsed_ms,
                ) = measure_mcu_latency(serial_device, dataset_path)
                profiling_time_ms += profiling_elapsed_ms
                arena_final = current_arena
                break
            except Exception as profiling_error:
                profiling_time_ms += 0.0
                if skip_compile or skip_deploy or attempts >= max_attempts:
                    raise profiling_error
                current_arena += arena_retry_step

        if arena_final is None:
            arena_final = current_arena
    except Exception as exc:
        status = "failed"
        error = str(exc)
        if arena_final is None and arena_initial is not None:
            arena_final = current_arena

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite_name,
        "family": family,
        "name": name,
        "target": target,
        "model_backend": model_backend,
        "status": status,
        "error": error,
        "model_path": relative_to_repo(model_path),
        "dataset_path": relative_to_repo(dataset_path),
        "serial_device": serial_device,
        "skip_compile": str(skip_compile).lower(),
        "skip_deploy": str(skip_deploy).lower(),
        "attempts": attempts,
        "sample_count": sample_count,
        "arena_source": arena_source,
        "arena_estimated": arena_estimated,
        "arena_initial": arena_initial,
        "arena_final": arena_final,
        "arena_retry_step": arena_retry_step,
        "macs": macs,
        "workstation_avg_us": workstation_avg_us,
        "workstation_std_us": workstation_std_us,
        "mcu_avg_us": mcu_avg_us,
        "mcu_std_us": mcu_std_us,
        "arena_time_ms": arena_time_ms,
        "mac_time_ms": mac_time_ms,
        "workstation_time_ms": workstation_time_ms,
        "cpp_codegen_time_ms": cpp_codegen_time_ms,
        "compile_time_ms": compile_time_ms,
        "deploy_time_ms": deploy_time_ms,
        "profiling_time_ms": profiling_time_ms,
    }
    csv_append_row(output_csv, CSV_FIELDNAMES, row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a reduced benchmark suite inspired by the Bruno Silveira article.",
    )
    parser.add_argument("manifest", help="JSON manifest describing the models to benchmark")
    parser.add_argument("output_csv", help="CSV file that will receive one row per manifest entry")
    parser.add_argument(
        "--serial-device",
        default=default_serial_port(),
        help="Default serial device used when an entry does not override it",
    )
    parser.add_argument(
        "--workstation-repeats",
        type=int,
        default=1,
        help="How many times each dataset sample should be invoked on the workstation",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum attempts per model when retrying arena growth after profiling failures",
    )
    parser.add_argument(
        "--arena-retry-step",
        type=int,
        default=5000,
        help="How many bytes to add to the tensor arena after a profiling failure",
    )
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Default all entries to skip compile.sh unless the manifest overrides it",
    )
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Default all entries to skip deploy.sh unless the manifest overrides it",
    )
    args = parser.parse_args()

    os.chdir(repo_root())
    manifest, manifest_dir = load_suite_manifest(args.manifest)
    suite_name = manifest.get("suite_name", Path(args.manifest).stem)
    defaults = manifest.get("defaults", {})
    default_options = {
        "serial_device": defaults.get("serial_device", args.serial_device),
        "skip_compile": defaults.get("skip_compile", args.skip_compile),
        "skip_deploy": defaults.get("skip_deploy", args.skip_deploy),
        "target": defaults.get("target", os.environ.get("BALAS_TARGET", "nxp")),
        "model_backend": defaults.get("model_backend")
        or (
            os.environ.get("BALAS_NORDIC_MODEL_BACKEND", "tflm")
            if defaults.get("target", os.environ.get("BALAS_TARGET", "nxp")) == "nordic"
            else os.environ.get("BALAS_STM32_MODEL_BACKEND", "stedgeai")
        ),
    }

    output_csv = Path(args.output_csv).resolve()
    entries = manifest.get("entries", [])
    if not entries:
        raise ValueError("The manifest does not contain any entries.")

    rows = []
    for entry in entries:
        rows.append(
            run_entry(
                suite_name=suite_name,
                entry=entry,
                default_options=default_options,
                manifest_dir=manifest_dir,
                output_csv=output_csv,
                workstation_repeats=args.workstation_repeats,
                max_attempts=args.max_attempts,
                arena_retry_step=args.arena_retry_step,
            ),
        )

    succeeded = sum(1 for row in rows if row["status"] == "ok")
    print(f"Suite: {suite_name}")
    print(f"Rows written to {output_csv}")
    print(f"Successful entries: {succeeded}/{len(rows)}")


if __name__ == "__main__":
    main()
