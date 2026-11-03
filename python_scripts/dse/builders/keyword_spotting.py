import hashlib
import os
from pathlib import Path

import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


# Builder DSE de Keyword Spotting baseado no DS-CNN do MLPerf Tiny.
#
# A topologia oficial do MLPerf Tiny (Speech Commands v0.02) é um DS-CNN com:
#   - Entrada: (49, 10, 1) [49 time steps, 10 coeficientes MFCC]
#   - Convolução Inicial: Conv2D(64, (10, 4), strides=(2, 2), padding='same') + BatchNorm + ReLU
#   - 4 Blocos Depthwise Separable:
#       - DepthwiseConv2D(3x3, padding='same') + BatchNorm + ReLU
#       - Pointwise Conv2D(64, 1x1, padding='same') + BatchNorm + ReLU
#   - Cabeça: AveragePooling2D 25x5 + Flatten + Dense(12, softmax)
#
# O grid controla os canais e dimensões do kernel da primeira convolução, a quantidade
# de blocos Depthwise Separable (profundidade), a largura desses blocos e o tamanho do kernel.
GRID_KEYS = (
    "first_conv_channels",
    "first_kernel_row",
    "first_kernel_col",
    "ds_blocks",
    "ds_channels",
    "ds_kernel_size",
)

# Nomes legados aceitos para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "channels",
    "kernel",
    "first_kernel",
)

# Valores que reproduzem o DS-CNN de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "first_conv_channels": 64,
    "first_kernel_row": 10,
    "first_kernel_col": 4,
    "ds_blocks": 4,
    "ds_channels": 64,
    "ds_kernel_size": 3,
}

_REPRESENTATIVE_SAMPLES = 100
_REPRESENTATIVE_SEED = 72


def _safe_tflite_filename(variant_name: str) -> str:
    """Gera um nome de arquivo seguro e limitado para o .tflite."""
    sanitized = "".join(
        c if (c.isalnum() or c in ("-", "_", ".")) else "_"
        for c in variant_name
    )
    if not sanitized:
        sanitized = "model"
    if len(sanitized) > 180:
        digest = hashlib.sha1(variant_name.encode("utf-8")).hexdigest()[:16]
        sanitized = f"model_{digest}"
    return f"{sanitized}.tflite"


def _parse_first_kernel(first_kernel_param) -> tuple[int, int]:
    """Converte parâmetros de filtro como '10x4' ou [10, 4] para tupla (10, 4)."""
    if isinstance(first_kernel_param, (list, tuple)):
        return int(first_kernel_param[0]), int(first_kernel_param[1])
    if isinstance(first_kernel_param, str) and "x" in first_kernel_param:
        parts = first_kernel_param.split("x")
        return int(parts[0]), int(parts[1])
    k = int(first_kernel_param)
    return k, k


def _resolve_params(config: dict) -> tuple[int, int, int, int, int, int]:
    """Resolve os hiperparâmetros suportando chaves canônicas e legadas."""
    first_channels = config.get(
        "first_conv_channels",
        config.get("channels", _DEFAULTS["first_conv_channels"]),
    )
    first_channels = int(first_channels)

    row = config.get("first_kernel_row")
    col = config.get("first_kernel_col")
    if row is None or col is None:
        legacy_h, legacy_w = _parse_first_kernel(config.get("first_kernel", "10x4"))
        first_k_h = legacy_h if row is None else int(row)
        first_k_w = legacy_w if col is None else int(col)
    else:
        first_k_h = int(row)
        first_k_w = int(col)

    ds_blocks = int(config.get("ds_blocks", _DEFAULTS["ds_blocks"]))
    ds_channels = int(config.get("ds_channels", config.get("channels", _DEFAULTS["ds_channels"])))
    ds_kernel_size = int(config.get("ds_kernel_size", config.get("kernel", _DEFAULTS["ds_kernel_size"])))

    return first_channels, first_k_h, first_k_w, ds_blocks, ds_channels, ds_kernel_size


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (49, 10, 1),
    num_classes: int = 12,
) -> Path:
    """Constrói o DS-CNN configurável do MLPerf Tiny e quantiza para TFLite int8."""
    tf.keras.backend.clear_session()

    (
        first_channels,
        first_k_h,
        first_k_w,
        ds_blocks,
        ds_channels,
        ds_kernel_size,
    ) = _resolve_params(config)

    input_shape = tuple(int(dim) for dim in input_shape)
    num_classes = int(num_classes or 12)

    # batch_size=1 deixa todas as formas estáticas, como nos .tflite oficiais;
    # sem isso o Flatten vira SHAPE/STRIDED_SLICE/PACK/RESHAPE no grafo.
    inputs = tf.keras.Input(shape=input_shape, batch_size=1, name="input")

    # 1. Convolução Inicial Retangular com strides (2, 2) e BatchNorm (como no MLPerf Tiny)
    x = tf.keras.layers.Conv2D(
        first_channels,
        (first_k_h, first_k_w),
        strides=(2, 2),
        padding="same",
        name="first_conv",
    )(inputs)
    x = tf.keras.layers.BatchNormalization(name="first_conv_bn")(x)
    x = tf.keras.layers.Activation("relu", name="first_conv_relu")(x)

    # 2. Blocos Depthwise Separable
    for b in range(ds_blocks):
        x = tf.keras.layers.DepthwiseConv2D(
            (ds_kernel_size, ds_kernel_size),
            padding="same",
            name=f"ds_block_{b+1}_dw",
        )(x)
        x = tf.keras.layers.BatchNormalization(name=f"ds_block_{b+1}_dw_bn")(x)
        x = tf.keras.layers.Activation("relu", name=f"ds_block_{b+1}_dw_relu")(x)

        x = tf.keras.layers.Conv2D(
            ds_channels,
            (1, 1),
            padding="same",
            name=f"ds_block_{b+1}_pw",
        )(x)
        x = tf.keras.layers.BatchNormalization(name=f"ds_block_{b+1}_pw_bn")(x)
        x = tf.keras.layers.Activation("relu", name=f"ds_block_{b+1}_pw_relu")(x)

    # 3. Cabeça de Classificação, igual à referência oficial (keras_model.py do
    # MLPerf Tiny): AveragePooling2D do tamanho do mapa final + Flatten + Dense.
    # GlobalAveragePooling2D faz a mesma conta, mas vira MEAN no .tflite em vez
    # de AVERAGE_POOL_2D, o que muda o que CPU/NPU executam.
    x = tf.keras.layers.AveragePooling2D(
        pool_size=tuple(int(d) for d in x.shape[1:3]), name="head_pool"
    )(x)
    x = tf.keras.layers.Flatten(name="head_flatten")(x)
    # Bias aleatório: com bias zero (inicialização padrão) o conversor o
    # descarta, e o modelo treinado oficial tem bias.
    outputs = tf.keras.layers.Dense(
        num_classes,
        activation="softmax",
        bias_initializer="random_normal",
        name="logits",
    )(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name=variant_name)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset_gen():
        rng = np.random.default_rng(_REPRESENTATIVE_SEED)
        for _ in range(_REPRESENTATIVE_SAMPLES):
            data = rng.uniform(
                0.0,
                1.0,
                size=(1,) + input_shape,
            ).astype(np.float32)
            yield [data]

    converter.representative_dataset = representative_dataset_gen
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    # Os .tflite oficiais têm FULLY_CONNECTED quantizado por tensor; o TF atual
    # quantiza camadas densas por canal por padrão.
    converter._experimental_disable_per_channel_quantization_for_dense_layers = True

    tflite_bytes = converter.convert()
    tflite_path = tmp_dir / _safe_tflite_filename(variant_name)
    tflite_path.write_bytes(tflite_bytes)

    return tflite_path
