import argparse
import os
import re
from pathlib import Path
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
from python_scripts.code_generator.generator import generate_cpp_code
from python_scripts.deployer.deployer import compile_cpp_project, deploy_to_mcu
from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
from python_scripts.profiler.profiler import send_profiling_inputs
from python_scripts.mac_calculator.mac_calculator import count_macs
from python_scripts.report_writer.report import append_inference_report
from python_scripts.config import default_serial_port

REPO_ROOT = Path(__file__).resolve().parent
STM32_EDGEAI_PARAMS = REPO_ROOT / "cpp-project/stm32-tflite-test/Core/Generated/EdgeAI/balas_model_data_params.h"

def parse_stm32_edgeai_activation_size() -> int:
    text = STM32_EDGEAI_PARAMS.read_text(encoding="utf-8")
    match = re.search(r"#define\s+AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZE\s+\((\d+)\)", text)
    if not match:
        raise RuntimeError(f"Could not parse activation size from {STM32_EDGEAI_PARAMS}")
    return int(match.group(1))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_quant", help="Path to the quantized model file")
    parser.add_argument("profiling_dataset", help="Path to the dataset with .bin float32 inputs")
    parser.add_argument("report_file", help="Path to the csv file to append results")
    parser.add_argument(
        "--serial-device",
        default=default_serial_port(),
        help="Path to the serial device (default: BALAS_SERIAL_PORT or /dev/ttyACM0)",
    )
    parser.add_argument(
        "--arena-size",
        type=int,
        help="Manual tensor arena size in bytes. If provided, skips stm32tflm estimation.",
    )
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Skip compile.sh and reuse the existing firmware build.",
    )
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Skip deploy.sh and reuse the firmware already flashed on the board.",
    )
    args = parser.parse_args()

    target = os.environ.get("BALAS_TARGET", "nxp")
    stm32_backend = os.environ.get("BALAS_STM32_MODEL_BACKEND", "stedgeai")
    use_stm32_edgeai = target == "stm32" and stm32_backend == "stedgeai"

    if args.arena_size is not None:
        estimated_arena_size = args.arena_size
        print(f"Using manual tensor arena size: {estimated_arena_size}\n")
    elif use_stm32_edgeai:
        estimated_arena_size = parse_stm32_edgeai_activation_size()
        print(f"Using STM32 ST Edge AI activation size: {estimated_arena_size}\n")
    else:
        print("Estimating tensor arena size")
        estimated_arena_size = estimate_tensor_arena_size(args.model_quant)
        print(f"Estimated arena size: {estimated_arena_size}\n")
    print("Calculating MACs")
    macs = count_macs(args.model_quant)
    print(f"Number of MACs: {macs}")
    if use_stm32_edgeai:
        print("Skipping C++ code generation for STM32 ST Edge AI backend\n")
    else:
        print("Generating C++ code")
        generate_cpp_code(args.model_quant, estimated_arena_size)
        print("Generating C++ code done\n")
    if args.skip_compile:
        print("Skipping C++ project compilation\n")
    else:
        print("Compiling C++ project")
        compile_cpp_project()
        print("Compiling C++ project done\n")
    if args.skip_deploy:
        print("Skipping MCU deploy\n")
    else:
        print("Deploying to MCU")
        deploy_to_mcu()
        print("Deploy done\n")
    print("Sending profiling input data")
    inference_times = send_profiling_inputs(args.serial_device, args.profiling_dataset)
    append_inference_report(estimated_arena_size, macs, inference_times, args.report_file)
    print(f"Results saved to {args.report_file}")
