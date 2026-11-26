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


# Builder DSE de Visual Wake Words baseado no MobileNetV1 (alpha=0.25) do MLPerf Tiny.
#
# A topologia oficial do MLPerf Tiny (Visual Wake Words / Person Detection) é uma
# MobileNetV1 com resolução 96x96x3 e fator de largura alpha=0.25:
#   - Convolução Inicial: Conv2D(8, 3x3, strides=2, padding='same') + BatchNorm + ReLU
#   - 13 Blocos Depthwise Separable (todos com BatchNorm e ReLU):
#       1. DW(3x3, s=1) -> PW(16)                  grupo "stem" (largura base 8)
#       2. DW(3x3, s=2) -> PW(32)                  grupo 2
#       3. DW(3x3, s=1) -> PW(32)                  grupo 2 (reps_2 = 1)
#       4. DW(3x3, s=2) -> PW(64)                  grupo 3
#       5. DW(3x3, s=1) -> PW(64)                  grupo 3 (reps_3 = 1)
#       6. DW(3x3, s=2) -> PW(128)                 grupo 4
#       7-11. 5 blocos DW(3x3, s=1) -> PW(128)     grupo 4 (middle_blocks = 5)
#       12. DW(3x3, s=2) -> PW(256)                grupo 5
#       13. DW(3x3, s=1) -> PW(256)                grupo 5 (reps_5 = 1)
#   - Cabeça: AveragePooling2D 3x3 + Flatten + Dense(2, softmax)
#
# Chaves de largura:
#   - alpha (legado/global): canais = max(8, int(base * alpha)), como no builder anterior.
#   - width_stem, width_2..width_5 (opcionais): número explícito de canais de cada
#     grupo; quando presentes, sobrescrevem o alpha para aquele grupo. O bloco 1
#     usa 2 * width_stem, como no MobileNetV1.
# input_size (opcional) troca a resolução de entrada (quadrada), mantendo os canais
# de model_specs.input_shape.
GRID_KEYS = (
    "alpha",
    "middle_blocks",
    "kernel_size",
)

OPTIONAL_GRID_KEYS = (
    "input_size",
    "width_stem",
    "width_2",
    "width_3",
    "width_4",
    "width_5",
    "reps_2",
    "reps_3",
    "reps_5",
) + ACTIVATION_GRID_KEYS

# Nomes legados aceitos para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "initial_channels",
    "channels_multiplier",
    "kernel",
)

CONTROL_KEYS = ("activation",)

DEFAULT_INPUT_SHAPE = (96, 96, 3)
DEFAULT_NUM_CLASSES = 2

# Valores que reproduzem o MobileNetV1 de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "alpha": 0.25,
    "middle_blocks": 5,
    "kernel_size": 3,
    "reps_2": 1,
    "reps_3": 1,
    "reps_5": 1,
}

# Largura base (alpha = 1) de cada grupo: stem, bloco 1, grupos 2..5.
_BASE_FILTERS = {"stem": 32, "block1": 64, 2: 128, 3: 256, 4: 512, 5: 1024}
_WIDTH_KEYS = ("width_stem", "width_2", "width_3", "width_4", "width_5")


def _get(config: dict, key: str, default):
    value = config.get(key)
    return default if value is None else value


def _resolve_alpha(config: dict) -> float:
    alpha = config.get("alpha")
    if alpha is None:
        init_ch = config.get("initial_channels")
        alpha = float(init_ch) / 32.0 if init_ch is not None else _DEFAULTS["alpha"]
    return float(alpha)


def _round_filters(filters: int, alpha: float, min_depth: int = 8) -> int:
    """Quantidade de filtros com base no multiplicador alpha (regra do builder anterior)."""
    return max(min_depth, int(filters * alpha))


def _resolve_widths(config: dict) -> dict:
    alpha = _resolve_alpha(config)
    widths = {
        "stem": _round_filters(_BASE_FILTERS["stem"], alpha),
        "block1": _round_filters(_BASE_FILTERS["block1"], alpha),
    }
    for group in (2, 3, 4, 5):
        widths[group] = _round_filters(_BASE_FILTERS[group], alpha)

    if config.get("width_stem") is not None:
        widths["stem"] = int(config["width_stem"])
        widths["block1"] = 2 * widths["stem"]
    for group in (2, 3, 4, 5):
        if config.get(f"width_{group}") is not None:
            widths[group] = int(config[f"width_{group}"])

    for name, value in widths.items():
        if value < 1:
            raise ValueError(f"largura do grupo {name} deve ser >= 1; recebido {value}.")
    return widths


def superseded_keys(grid: dict) -> set:
    """Chaves do GRID_KEYS que não têm efeito dado o grid (para o validate_grid)."""
    return {"alpha"} if all(k in grid for k in _WIDTH_KEYS) else set()


def canonicalize(config: dict) -> dict:
    """Anula chaves inativas para que modelos iguais tenham o mesmo hash."""
    config = canonicalize_activation(dict(config))
    # Se todas as larguras são explícitas, alpha não influencia o modelo.
    if "alpha" in config and all(config.get(k) is not None for k in _WIDTH_KEYS):
        config["alpha"] = None
    return config


def resolve_input_shape(config: dict, input_shape=None) -> tuple[int, ...]:
    shape = tuple(int(d) for d in (input_shape or DEFAULT_INPUT_SHAPE))
    size = config.get("input_size")
    if size is not None:
        size = int(size)
        if size < 8:
            raise ValueError(f"input_size deve ser >= 8; recebido {size}.")
        shape = (size, size, shape[2])
    return shape


def architecture(config: dict, input_shape=None, num_classes=None) -> GraphSpec:
    input_shape = resolve_input_shape(config, input_shape)
    num_classes = int(num_classes or DEFAULT_NUM_CLASSES)
    act = resolve_activation(config)
    widths = _resolve_widths(config)
    kernel = int(_get(config, "kernel_size", _get(config, "kernel", _DEFAULTS["kernel_size"])))
    middle = int(_get(config, "middle_blocks", _DEFAULTS["middle_blocks"]))
    reps = {g: int(_get(config, f"reps_{g}", _DEFAULTS[f"reps_{g}"])) for g in (2, 3, 5)}
    for name, value in [("middle_blocks", middle)] + [(f"reps_{g}", v) for g, v in reps.items()]:
        if value < 0:
            raise ValueError(f"{name} deve ser >= 0; recebido {value}.")

    g = GraphSpec(input_shape, name="mobilenet_v1_variant")

    # 1. Convolução inicial (32 * alpha canais, stride 2).
    x = g.conv("initial_conv", g.input, widths["stem"], 3, 2)
    x = g.bn("initial_conv_bn", x)
    x = g.act("initial_conv_relu", x, act)

    block_id = 0

    def depthwise_block(t, filters, stride):
        nonlocal block_id
        block_id += 1
        t = g.dwconv(f"block_{block_id}_dw", t, kernel, stride)
        t = g.bn(f"block_{block_id}_dw_bn", t)
        t = g.act(f"block_{block_id}_dw_relu", t, act)
        t = g.conv(f"block_{block_id}_pw", t, filters, 1, 1)
        t = g.bn(f"block_{block_id}_pw_bn", t)
        return g.act(f"block_{block_id}_pw_relu", t, act)

    # 2. Sequência de blocos MobileNetV1 (as repetições têm stride 1).
    x = depthwise_block(x, widths["block1"], 1)
    x = depthwise_block(x, widths[2], 2)
    for _ in range(reps[2]):
        x = depthwise_block(x, widths[2], 1)
    x = depthwise_block(x, widths[3], 2)
    for _ in range(reps[3]):
        x = depthwise_block(x, widths[3], 1)
    x = depthwise_block(x, widths[4], 2)
    for _ in range(middle):
        x = depthwise_block(x, widths[4], 1)
    x = depthwise_block(x, widths[5], 2)
    for _ in range(reps[5]):
        x = depthwise_block(x, widths[5], 1)

    # 3. Cabeça igual à referência oficial (AveragePooling2D + Flatten + Dense).
    x = g.avgpool("head_pool", x, g.shape(x)[:2])
    x = g.flatten("head_flatten", x)
    g.dense("logits", x, num_classes, activation="softmax", bias_initializer="random_normal")
    return g


def estimate_cost(config: dict, input_shape=None, num_classes=None) -> dict:
    """Custo analítico (params, MACs, pico de ativação, ops) sem TensorFlow."""
    return architecture(config, input_shape, num_classes).summary()


def build_keras_model(config: dict, input_shape=None, num_classes=None):
    import tensorflow as tf

    tf.keras.backend.clear_session()
    return build_keras(architecture(config, input_shape, num_classes), "mobilenet_v1_variant")


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = DEFAULT_INPUT_SHAPE,
    num_classes: int = DEFAULT_NUM_CLASSES,
) -> Path:
    """Constrói o MobileNetV1 configurável do MLPerf Tiny e quantiza para TFLite int8."""
    model = build_keras_model(config, input_shape, num_classes)
    return quantize_to_tflite(model, variant_name, tmp_dir)
