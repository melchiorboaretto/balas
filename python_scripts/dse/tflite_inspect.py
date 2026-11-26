"""Inspeção de um .tflite: operadores, parâmetros e pico de ativação.

Usa só a API do ``tf.lite.Interpreter``. Um tensor é considerado constante
(peso, bias, shape) quando não é entrada do modelo nem saída de nenhum op.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

_DTYPE_BYTES = {"int8": 1, "uint8": 1, "int16": 2, "float16": 2, "int32": 4,
                "float32": 4, "int64": 8, "bool": 1}


def _align(value: int, alignment: int = 16) -> int:
    return (value + alignment - 1) // alignment * alignment


def make_interpreter(model_path: str | Path, mode: str = "builtin", num_threads: int = 1):
    """Interpretador TFLite do PC *sem* o delegate XNNPACK.

    O XNNPACK (padrão do tf.lite.Interpreter) falha ao preparar alguns modelos
    int8 válidos (ex.: MobileNetV1 com TANH: "failed to create XNNPACK runtime").
    Para inspecionar modelos e para o dry-run usamos os kernels builtin
    otimizados (``builtin``) ou os de referência (``ref``), que aceitam todos
    os ops gerados pelos builders.
    """
    import tensorflow as tf

    resolver = {
        "builtin": tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES,
        "ref": tf.lite.experimental.OpResolverType.BUILTIN_REF,
    }
    kwargs = {"num_threads": num_threads}
    if mode != "xnnpack":
        kwargs["experimental_op_resolver_type"] = resolver[mode]
    interpreter = tf.lite.Interpreter(model_path=str(model_path), **kwargs)
    interpreter.allocate_tensors()
    return interpreter


def inspect_tflite(model_path: str | Path) -> dict:
    """Devolve ops, params, bytes do arquivo e pico de ativação (liveness)."""
    import numpy as np

    interpreter = make_interpreter(model_path)
    tensors = {t["index"]: t for t in interpreter.get_tensor_details()}
    ops = [op for op in interpreter._get_ops_details() if op["op_name"] != "DELEGATE"]
    model_inputs = [d["index"] for d in interpreter.get_input_details()]
    model_outputs = [d["index"] for d in interpreter.get_output_details()]

    produced = set(model_inputs)
    for op in ops:
        produced.update(int(i) for i in op["outputs"])

    def nbytes(index: int) -> int:
        t = tensors[index]
        itemsize = _DTYPE_BYTES.get(np.dtype(t["dtype"]).name, 4)
        return int(math.prod(int(d) for d in t["shape"])) * itemsize

    # Parâmetros = tensores constantes lidos por algum op. Os kernels builtin do
    # TFLite criam tensores temporários no Prepare (ex.: im2col de conv 5x5) que
    # não são entrada nem saída de op nenhum; eles não podem entrar na conta.
    consumed = set()
    for op in ops:
        consumed.update(int(i) for i in op["inputs"] if int(i) >= 0)
    params = 0
    for index in consumed - produced:
        params += int(math.prod(int(d) for d in tensors[index]["shape"]))

    # Liveness dos tensores de ativação.
    first = {i: -1 for i in model_inputs}
    last = {i: -1 for i in model_inputs}
    for k, op in enumerate(ops):
        for o in op["outputs"]:
            o = int(o)
            first.setdefault(o, k)
            last[o] = max(last.get(o, k), k)
        for i in op["inputs"]:
            i = int(i)
            if i in produced:
                last[i] = max(last.get(i, k), k)
    for o in model_outputs:
        last[o] = len(ops)

    peak = 0
    for k in range(len(ops)):
        live = sum(_align(nbytes(t)) for t in first if first[t] <= k <= last[t])
        peak = max(peak, live)

    # High-water mark real do GreedyMemoryPlanner do TFLM (AddBuffer em ordem
    # de índice de tensor). Pode passar do pico de liveness por fragmentação.
    from python_scripts.dse.builders._graph import greedy_memory_plan

    planned = greedy_memory_plan([(_align(nbytes(t)), first[t], last[t]) for t in sorted(first)])

    # Dados para o modelo de overhead do TFLM.
    out_channels = 0
    max_scratch = 0
    for op in ops:
        name = op["op_name"]
        inputs = [int(i) for i in op["inputs"]]
        if name in ("CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED") and len(inputs) > 1:
            w_shape = [int(d) for d in tensors[inputs[1]]["shape"]]
            out_channels += w_shape[-1] if name == "DEPTHWISE_CONV_2D" else w_shape[0]
            if name == "CONV_2D":
                _, kh, kw, cin = w_shape
                if kh * kw > 1:
                    # im2col de 2 colunas em int16 (CMSIS-NN arm_convolve_s8).
                    max_scratch = max(max_scratch, 2 * cin * kh * kw * 2)
            elif name == "DEPTHWISE_CONV_2D":
                _, kh, kw, cout = w_shape
                max_scratch = max(max_scratch, cout * kh * kw * 2)
        elif name == "AVERAGE_POOL_2D":
            cin = int(tensors[inputs[0]]["shape"][-1])
            max_scratch = max(max_scratch, cin * 4)

    return {
        "ops": [op["op_name"] for op in ops],
        "params": int(params),
        "tflite_bytes": Path(model_path).stat().st_size,
        "peak_activation_bytes": int(peak),
        "planned_activation_bytes": int(planned),
        # Só tensores do grafo (sem os temporários do interpretador do PC).
        "num_tensors": len(consumed | produced),
        "num_ops": len(ops),
        "per_channel_outputs": int(out_channels),
        "max_scratch_bytes": int(max_scratch),
        "input_shape": tuple(int(d) for d in tensors[model_inputs[0]]["shape"]),
        "input_elements": int(math.prod(int(d) for d in tensors[model_inputs[0]]["shape"])),
    }


def estimate_tflm_arena(info: dict) -> int:
    """Estimativa de arena do TFLM a partir do ``inspect_tflite``.

    arena = ativações planejadas (GreedyMemoryPlanner) + parâmetros persistentes por canal
    (multiplicador e shift int32) + metadados por tensor e por op + maior
    scratch do CMSIS-NN + margem. Calibrado com o ResNet8 de referência:
    stm32tflm = 56.832 B e ``arena_used_bytes()`` real no STM32 = 54.708 B
    (docs/010 e docs/020).
    """
    from python_scripts.dse.builders._graph import tflm_arena_from_parts

    return tflm_arena_from_parts(
        info["planned_activation_bytes"],
        info["per_channel_outputs"],
        info["num_tensors"],
        info["num_ops"],
        info["max_scratch_bytes"],
    )
