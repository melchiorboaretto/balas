import hashlib
import os
from pathlib import Path

import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


# Builder DSE de Visual Wake Words baseado no MobileNetV1 (alpha=0.25) do MLPerf Tiny.
#
# A topologia oficial do MLPerf Tiny (Visual Wake Words / Person Detection) é uma
# MobileNetV1 com resolução 96x96x3 e fator de largura alpha=0.25:
#   - Convolução Inicial: Conv2D(8, 3x3, strides=2, padding='same') + BatchNorm + ReLU
#   - 13 Blocos Depthwise Separable (todos com BatchNorm e ReLU):
#       1. DW(3x3, s=1) -> PW(16)
#       2. DW(3x3, s=2) -> PW(32)
#       3. DW(3x3, s=1) -> PW(32)
#       4. DW(3x3, s=2) -> PW(64)
#       5. DW(3x3, s=1) -> PW(64)
#       6. DW(3x3, s=2) -> PW(128)
#       7-11. 5 blocos repetidos: DW(3x3, s=1) -> PW(128)
#       12. DW(3x3, s=2) -> PW(256)
#       13. DW(3x3, s=1) -> PW(256)
#   - Cabeça: AveragePooling2D 3x3 + Flatten + Dense(2, softmax)
#
# O grid controla a largura geral (alpha / largura base), a profundidade dos blocos centrais
# (middle_blocks, onde o padrão é 5 para totalizar 13 blocos) e o kernel depthwise.
GRID_KEYS = (
    "alpha",
    "middle_blocks",
    "kernel_size",
)

# Nomes legados aceitos para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "initial_channels",
    "channels_multiplier",
    "kernel",
)

# Valores que reproduzem o MobileNetV1 de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "alpha": 0.25,
    "middle_blocks": 5,
    "kernel_size": 3,
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


def _resolve_params(config: dict) -> tuple[float, int, int]:
    """Resolve os hiperparâmetros suportando chaves canônicas e legadas."""
    alpha = config.get("alpha")
    if alpha is None:
        init_ch = config.get("initial_channels")
        if init_ch is not None:
            alpha = float(init_ch) / 32.0
        else:
            alpha = _DEFAULTS["alpha"]
    alpha = float(alpha)

    middle_blocks = int(config.get("middle_blocks", _DEFAULTS["middle_blocks"]))
    kernel_size = int(config.get("kernel_size", config.get("kernel", _DEFAULTS["kernel_size"])))

    return alpha, middle_blocks, kernel_size


def _round_filters(filters: int, alpha: float, min_depth: int = 8) -> int:
    """Calcula quantidade de filtros com base no multiplicador alpha."""
    filters = int(filters * alpha)
    return max(min_depth, int(filters))


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (96, 96, 3),
    num_classes: int = 2,
) -> Path:
    """Constrói o MobileNetV1 configurável do MLPerf Tiny e quantiza para TFLite int8."""
    tf.keras.backend.clear_session()

    alpha, middle_blocks, kernel_size = _resolve_params(config)

    input_shape = tuple(int(dim) for dim in input_shape)
    num_classes = int(num_classes or 2)

    # batch_size=1 deixa todas as formas estáticas, como nos .tflite oficiais;
    # sem isso o Flatten vira SHAPE/STRIDED_SLICE/PACK/RESHAPE no grafo.
    inputs = tf.keras.Input(shape=input_shape, batch_size=1, name="input")

    # 1. Convolução Inicial pura: 32 * alpha (8 no caso de alpha=0.25)
    first_filters = _round_filters(32, alpha)
    x = tf.keras.layers.Conv2D(
        first_filters,
        kernel_size=3,
        strides=2,
        padding="same",
        name="initial_conv",
    )(inputs)
    x = tf.keras.layers.BatchNormalization(name="initial_conv_bn")(x)
    x = tf.keras.layers.Activation("relu", name="initial_conv_relu")(x)

    def depthwise_block(tensor, point_filters: int, stride: int, block_id: int):
        pw_ch = _round_filters(point_filters, alpha)
        # Depthwise
        tensor = tf.keras.layers.DepthwiseConv2D(
            kernel_size=kernel_size,
            strides=stride,
            padding="same",
            name=f"block_{block_id}_dw",
        )(tensor)
        tensor = tf.keras.layers.BatchNormalization(name=f"block_{block_id}_dw_bn")(tensor)
        tensor = tf.keras.layers.Activation("relu", name=f"block_{block_id}_dw_relu")(tensor)

        # Pointwise
        tensor = tf.keras.layers.Conv2D(
            pw_ch,
            kernel_size=1,
            strides=1,
            padding="same",
            name=f"block_{block_id}_pw",
        )(tensor)
        tensor = tf.keras.layers.BatchNormalization(name=f"block_{block_id}_pw_bn")(tensor)
        tensor = tf.keras.layers.Activation("relu", name=f"block_{block_id}_pw_relu")(tensor)
        return tensor

    # 2. Sequência de Blocos MobileNetV1
    # Bloco 1 (stride 1, 64 * alpha -> 16)
    x = depthwise_block(x, 64, stride=1, block_id=1)
    # Bloco 2 (stride 2, 128 * alpha -> 32)
    x = depthwise_block(x, 128, stride=2, block_id=2)
    # Bloco 3 (stride 1, 128 * alpha -> 32)
    x = depthwise_block(x, 128, stride=1, block_id=3)
    # Bloco 4 (stride 2, 256 * alpha -> 64)
    x = depthwise_block(x, 256, stride=2, block_id=4)
    # Bloco 5 (stride 1, 256 * alpha -> 64)
    x = depthwise_block(x, 256, stride=1, block_id=5)
    # Bloco 6 (stride 2, 512 * alpha -> 128)
    x = depthwise_block(x, 512, stride=2, block_id=6)

    # Blocos Centrais repetidos (padrão 5 blocos, stride 1, 512 * alpha -> 128)
    curr_id = 7
    for _ in range(middle_blocks):
        x = depthwise_block(x, 512, stride=1, block_id=curr_id)
        curr_id += 1

    # Bloco Penúltimo (stride 2, 1024 * alpha -> 256)
    x = depthwise_block(x, 1024, stride=2, block_id=curr_id)
    curr_id += 1
    # Bloco Final (stride 1, 1024 * alpha -> 256)
    x = depthwise_block(x, 1024, stride=1, block_id=curr_id)

    # 3. Cabeça de Classificação, igual à referência oficial (vww_model.py do
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
