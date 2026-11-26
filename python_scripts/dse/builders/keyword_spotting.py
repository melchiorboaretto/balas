import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from python_scripts.dse.builders._graph import (
    ACTIVATION_GRID_KEYS,
    GraphSpec,
    build_keras,
    canonicalize_activation,
    quantize_to_tflite,
    resolve_activation,
)


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
# O grid controla canais, kernel e stride da primeira convolução, a quantidade
# de blocos DS, a largura e o kernel desses blocos, um downsample opcional
# dentro dos blocos e a função de ativação (global).
GRID_KEYS = (
    "first_conv_channels",
    "first_kernel_row",
    "first_kernel_col",
    "ds_blocks",
    "ds_channels",
    "ds_kernel_size",
)

# Chaves opcionais: quando ausentes, o default reproduz a referência.
OPTIONAL_GRID_KEYS = (
    "first_stride_row",
    "first_stride_col",
    "ds_downsample_block",
) + ACTIVATION_GRID_KEYS

# Nomes legados aceitos para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "channels",
    "kernel",
    "first_kernel",
)

CONTROL_KEYS = ("activation", "ds_blocks", "ds_downsample_block")

DEFAULT_INPUT_SHAPE = (49, 10, 1)
DEFAULT_NUM_CLASSES = 12

# Valores que reproduzem o DS-CNN de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "first_conv_channels": 64,
    "first_kernel_row": 10,
    "first_kernel_col": 4,
    "ds_blocks": 4,
    "ds_channels": 64,
    "ds_kernel_size": 3,
    "first_stride_row": 2,
    "first_stride_col": 2,
    # 0 = sem downsample dentro dos blocos; k = o depthwise do bloco k usa stride 2.
    "ds_downsample_block": 0,
}


def _get(config: dict, key: str, default):
    value = config.get(key)
    return default if value is None else value


def _parse_first_kernel(first_kernel_param) -> tuple[int, int]:
    """Converte parâmetros de filtro como '10x4' ou [10, 4] para tupla (10, 4)."""
    if isinstance(first_kernel_param, (list, tuple)):
        return int(first_kernel_param[0]), int(first_kernel_param[1])
    if isinstance(first_kernel_param, str) and "x" in first_kernel_param:
        parts = first_kernel_param.split("x")
        return int(parts[0]), int(parts[1])
    k = int(first_kernel_param)
    return k, k


def _resolve_params(config: dict) -> dict:
    """Resolve os hiperparâmetros suportando chaves canônicas e legadas."""
    first_channels = _get(
        config, "first_conv_channels", _get(config, "channels", _DEFAULTS["first_conv_channels"])
    )

    row = config.get("first_kernel_row")
    col = config.get("first_kernel_col")
    if row is None or col is None:
        legacy_h, legacy_w = _parse_first_kernel(_get(config, "first_kernel", "10x4"))
        first_k_h = legacy_h if row is None else int(row)
        first_k_w = legacy_w if col is None else int(col)
    else:
        first_k_h, first_k_w = int(row), int(col)

    params = {
        "first_channels": int(first_channels),
        "first_kernel": (first_k_h, first_k_w),
        "first_strides": (
            int(_get(config, "first_stride_row", _DEFAULTS["first_stride_row"])),
            int(_get(config, "first_stride_col", _DEFAULTS["first_stride_col"])),
        ),
        "ds_blocks": int(_get(config, "ds_blocks", _DEFAULTS["ds_blocks"])),
        "ds_channels": int(
            _get(config, "ds_channels", _get(config, "channels", _DEFAULTS["ds_channels"]))
        ),
        "ds_kernel_size": int(
            _get(config, "ds_kernel_size", _get(config, "kernel", _DEFAULTS["ds_kernel_size"]))
        ),
        "ds_downsample_block": int(
            _get(config, "ds_downsample_block", _DEFAULTS["ds_downsample_block"])
        ),
    }
    if params["ds_blocks"] < 1:
        raise ValueError(f"ds_blocks deve ser >= 1; recebido {params['ds_blocks']}.")
    if params["ds_downsample_block"] < 0:
        raise ValueError("ds_downsample_block deve ser >= 0.")
    return params


def canonicalize(config: dict) -> dict:
    """Anula/normaliza chaves inativas para que modelos iguais tenham o mesmo hash."""
    config = canonicalize_activation(dict(config))
    value = config.get("ds_downsample_block")
    if value is not None:
        blocks = int(_get(config, "ds_blocks", _DEFAULTS["ds_blocks"]))
        if int(value) > blocks:
            # Downsample num bloco que não existe equivale a não ter downsample.
            config["ds_downsample_block"] = 0
    return config


def resolve_input_shape(config: dict, input_shape=None) -> tuple[int, ...]:
    return tuple(int(d) for d in (input_shape or DEFAULT_INPUT_SHAPE))


def architecture(config: dict, input_shape=None, num_classes=None) -> GraphSpec:
    p = _resolve_params(config)
    input_shape = resolve_input_shape(config, input_shape)
    num_classes = int(num_classes or DEFAULT_NUM_CLASSES)
    act = resolve_activation(config)
    g = GraphSpec(input_shape, name="ds_cnn_variant")

    # 1. Convolução inicial retangular com stride e BatchNorm.
    x = g.conv("first_conv", g.input, p["first_channels"], p["first_kernel"], p["first_strides"])
    x = g.bn("first_conv_bn", x)
    x = g.act("first_conv_relu", x, act)

    # 2. Blocos Depthwise Separable.
    k = p["ds_kernel_size"]
    for b in range(1, p["ds_blocks"] + 1):
        strides = 2 if b == p["ds_downsample_block"] else 1
        x = g.dwconv(f"ds_block_{b}_dw", x, (k, k), strides)
        x = g.bn(f"ds_block_{b}_dw_bn", x)
        x = g.act(f"ds_block_{b}_dw_relu", x, act)
        x = g.conv(f"ds_block_{b}_pw", x, p["ds_channels"], (1, 1))
        x = g.bn(f"ds_block_{b}_pw_bn", x)
        x = g.act(f"ds_block_{b}_pw_relu", x, act)

    # 3. Cabeça igual à referência oficial: AveragePooling2D do tamanho do mapa
    # final + Flatten + Dense. GlobalAveragePooling2D viraria MEAN no .tflite.
    x = g.avgpool("head_pool", x, g.shape(x)[:2])
    x = g.flatten("head_flatten", x)
    # Bias aleatório: com bias zero o conversor o descarta, e o oficial tem bias.
    g.dense("logits", x, num_classes, activation="softmax", bias_initializer="random_normal")
    return g


def estimate_cost(config: dict, input_shape=None, num_classes=None) -> dict:
    """Custo analítico (params, MACs, pico de ativação, ops) sem TensorFlow."""
    return architecture(config, input_shape, num_classes).summary()


def build_keras_model(config: dict, input_shape=None, num_classes=None, model_name="ds_cnn_variant"):
    import tensorflow as tf

    tf.keras.backend.clear_session()
    return build_keras(architecture(config, input_shape, num_classes), model_name)


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = DEFAULT_INPUT_SHAPE,
    num_classes: int = DEFAULT_NUM_CLASSES,
) -> Path:
    """Constrói o DS-CNN configurável do MLPerf Tiny e quantiza para TFLite int8."""
    model = build_keras_model(config, input_shape, num_classes)
    return quantize_to_tflite(model, variant_name, tmp_dir)
