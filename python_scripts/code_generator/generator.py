import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import tensorflow as tf

from python_scripts.code_generator.resolver_map import resolver_map
from python_scripts.file_utils import find_and_replace, copy_file, replace_line

NXP_MODEL_DIR = Path("cpp-project/tflite-test/model")
STM32_MODEL_DIR = Path("cpp-project/stm32-tflite-test/Core/Model")
NORDIC_MODEL_DIR = Path("cpp-project/nrf52840-tflite-test/Model")

def analyze_model(model_file):
    interpreter = tf.lite.Interpreter(model_path=model_file)
    interpreter.allocate_tensors()
    ops_details = interpreter._get_ops_details()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    inputs = np.prod(input_details['shape'])
    outputs = np.prod(output_details['shape'])
    return inputs, outputs, ops_details

def get_resolver_function_names(ops_details):
    function_names = []
    for op in ops_details:
        if op['op_name'] not in resolver_map.keys():
            continue
        if resolver_map[op['op_name']] not in function_names:
            function_names.append(resolver_map[op['op_name']])
    return function_names

def get_resolver_function_calls_code(ops_details):
    function_names = get_resolver_function_names(ops_details)
    resolver_code = ""
    for name in function_names:
        resolver_code += f"\tresolver.{name}();\n"
    return (len(function_names), resolver_code)

def replace_define(file_path, name, value):
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^#define\s+{re.escape(name)}\s+.+$", re.MULTILINE)
    updated, count = pattern.subn(f"#define {name} {value}", content, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")


def replace_generated_block(file_path, begin_marker, end_marker, replacement):
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(// {re.escape(begin_marker)}\n)(.*?)(\n\s*// {re.escape(end_marker)})",
        re.DOTALL,
    )
    updated, count = pattern.subn(rf"\1{replacement}\3", content, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")


def generate_resolver_code(ops_details, model_dir=NXP_MODEL_DIR):
    n_ops, resolver_code = get_resolver_function_calls_code(ops_details)
    model_dir = Path(model_dir)
    model_h = model_dir / "model.h"
    model_cpp = model_dir / "model.cpp"
    find_and_replace(str(model_h), "GEN_N_OPS", str(n_ops))
    replace_define(model_h, "N_OPS", str(n_ops))
    find_and_replace(str(model_cpp), "GEN_RESOLVER_OPS", resolver_code)
    replace_generated_block(
        model_cpp,
        "BALAS_GENERATED_RESOLVER_OPS_BEGIN",
        "BALAS_GENERATED_RESOLVER_OPS_END",
        resolver_code.rstrip(),
    )

def generate_tensor_arena_code(tensor_arena_size, model_dir=NXP_MODEL_DIR):
    model_h = Path(model_dir) / "model.h"
    find_and_replace(str(model_h), "GEN_TENSOR_ARENA_SIZE", str(tensor_arena_size))
    replace_define(model_h, "TENSOR_ARENA_SIZE", str(tensor_arena_size))

def generate_io_code(inputs, outputs):
    find_and_replace("cpp-project/tflite-test/model/input.h", "GEN_INPUT_SIZE", str(inputs))
    find_and_replace("cpp-project/tflite-test/model/output.h", "GEN_OUTPUT_SIZE", str(outputs))

def generate_model_binary(model_file, model_dir=NXP_MODEL_DIR):
    model_data_path = Path(model_dir) / "model_data.h"
    try:
        with model_data_path.open("w", encoding="utf-8") as output:
            subprocess.run(["xxd", "-i", model_file], stdout=output, check=True)
    except subprocess.CalledProcessError as e:
        print(f"XDD Command failed with return code {e.returncode}")
        exit()
    updated_binary_header = """
#pragma once
alignas(16) const unsigned char model_data[] = {
"""
    replace_line(str(model_data_path), 1, updated_binary_header)
    with open(model_data_path, "r", encoding="utf-8") as file:
        content = file.read()
    normalized_content = re.sub(
        r"unsigned int [A-Za-z0-9_]+_len = (\d+);",
        r"unsigned int model_data_len = \1;",
        content,
    )
    with open(model_data_path, "w", encoding="utf-8") as file:
        file.write(normalized_content)


def generate_cpp_code(model_file, tensor_arena_size, model_dir=NXP_MODEL_DIR, copy_templates=True):
    model_dir = Path(model_dir)
    if copy_templates:
        copy_file("templates/model.h", str(model_dir))
        copy_file("templates/model.cpp", str(model_dir))
    generate_tensor_arena_code(tensor_arena_size, model_dir)
    inputs, outputs, ops_details = analyze_model(model_file)
    generate_resolver_code(ops_details, model_dir)
    generate_model_binary(model_file, model_dir)


def generate_stm32_tflm_code(model_file, tensor_arena_size):
    generate_cpp_code(
        model_file,
        tensor_arena_size,
        model_dir=STM32_MODEL_DIR,
        copy_templates=False,
    )


def generate_nordic_tflm_code(model_file, tensor_arena_size):
    generate_cpp_code(
        model_file,
        tensor_arena_size,
        model_dir=NORDIC_MODEL_DIR,
        copy_templates=False,
    )
