import os
from dataclasses import dataclass
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


# Builder DSE do CIFAR-10 baseado no ResNet8 do MLPerf Tiny.
#
# A topologia é sempre um DAG com três estágios residuais: o tensor se divide
# em ramo principal e atalho, os dois caminhos se encontram em um Add e o
# resultado recebe a ativação. O grid controla largura, kernel, profundidade,
# stride, tipo de bloco e a função de ativação (global, para a rede inteira).
# BatchNorm, atalho automático, GAP e softmax ficam fixos.
GRID_KEYS = (
    "channels_1",
    "kernel_1",
    "blocks_1",
    "stride_1",
    "block_type_1",
    "channels_2",
    "kernel_2",
    "blocks_2",
    "stride_2",
    "block_type_2",
    "channels_3",
    "kernel_3",
    "blocks_3",
    "stride_3",
    "block_type_3",
)

# Chaves aceitas, mas que podem faltar no grid sem aviso: o default reproduz a
# referência (ativação relu).
OPTIONAL_GRID_KEYS = ACTIVATION_GRID_KEYS

# Chaves cujo valor decide se outras chaves estão ativas (usado no space_report).
CONTROL_KEYS = ("activation",)

DEFAULT_INPUT_SHAPE = (32, 32, 3)
DEFAULT_NUM_CLASSES = 10

# Valores que reproduzem o ResNet8 de referência do MLPerf Tiny v1.1.
_DEFAULTS = {
    "channels_1": 16,
    "kernel_1": 3,
    "blocks_1": 1,
    "stride_1": 1,
    "block_type_1": "basic",
    "channels_2": 32,
    "kernel_2": 3,
    "blocks_2": 1,
    "stride_2": 2,
    "block_type_2": "basic",
    "channels_3": 64,
    "kernel_3": 3,
    "blocks_3": 1,
    "stride_3": 2,
    "block_type_3": "basic",
}

# Constantes fixas do modelo. Não entram no grid porque não mudam o custo no
# dispositivo (regularização e inicialização não existem no .tflite).
_L2_STRENGTH = 1e-4
_KERNEL_INITIALIZER = "he_normal"
_CONV_KERAS = dict(kernel_initializer=_KERNEL_INITIALIZER, l2=_L2_STRENGTH)


@dataclass(frozen=True)
class StageConfig:
    """Parâmetros estruturais de um estágio residual."""

    channels: int
    kernel: int
    blocks: int
    stride: int
    block_type: str
    bottleneck_ratio: int


def _setting(config: dict, key: str):
    """Lê uma chave do grid ou devolve o valor de referência."""
    value = config.get(key)
    return _DEFAULTS[key] if value is None else value


def _parse_block_type(value: str) -> tuple[str, int]:
    """Converte 'basic' ou 'bottleneck_N' em (tipo, razão do gargalo)."""
    value = str(value).strip().lower()

    if value == "basic":
        return "basic", 1

    if value.startswith("bottleneck_"):
        try:
            ratio = int(value.removeprefix("bottleneck_"))
        except ValueError as exc:
            raise ValueError(
                f"block_type inválido: {value!r}. Use 'basic' ou 'bottleneck_N'."
            ) from exc

        if ratio < 2:
            raise ValueError(f"bottleneck_N exige N >= 2; recebido {value!r}.")
        return "bottleneck", ratio

    raise ValueError(f"block_type inválido: {value!r}. Use 'basic' ou 'bottleneck_N'.")


def _parse_stage(config: dict, index: int) -> StageConfig:
    """Lê e valida os parâmetros de um estágio."""
    block_type, bottleneck_ratio = _parse_block_type(_setting(config, f"block_type_{index}"))

    stage = StageConfig(
        channels=int(_setting(config, f"channels_{index}")),
        kernel=int(_setting(config, f"kernel_{index}")),
        blocks=int(_setting(config, f"blocks_{index}")),
        stride=int(_setting(config, f"stride_{index}")),
        block_type=block_type,
        bottleneck_ratio=bottleneck_ratio,
    )

    for field_name in ("channels", "kernel", "blocks", "stride"):
        value = getattr(stage, field_name)
        if value < 1:
            raise ValueError(f"{field_name}_{index} deve ser >= 1; recebido {value}.")

    return stage


def canonicalize(config: dict) -> dict:
    """Anula chaves inativas para que modelos iguais tenham o mesmo hash."""
    return canonicalize_activation(dict(config))


def _conv_bn(g, x, filters, kernel, strides, *, act, name):
    """Conv2D + BatchNorm + ativação opcional (act=None no fim do bloco)."""
    x = g.conv(f"{name}_conv", x, filters, kernel, strides, **_CONV_KERAS)
    x = g.bn(f"{name}_bn", x)
    if act is not None:
        x = g.act(f"{name}_relu", x, act)
    return x


def _residual_block(g, x, stage: StageConfig, *, strides, act, name):
    """Bloco residual: ramo principal + atalho + Add + ativação."""
    if stage.block_type == "basic":
        y = _conv_bn(g, x, stage.channels, stage.kernel, strides, act=act, name=f"{name}_conv1")
        y = _conv_bn(g, y, stage.channels, stage.kernel, 1, act=None, name=f"{name}_conv2")
    else:
        inner = max(1, stage.channels // stage.bottleneck_ratio)
        y = _conv_bn(g, x, inner, 1, strides, act=act, name=f"{name}_reduce")
        y = _conv_bn(g, y, inner, stage.kernel, 1, act=act, name=f"{name}_spatial")
        y = _conv_bn(g, y, stage.channels, 1, 1, act=None, name=f"{name}_expand")

    # Atalho automático: identity se a forma bate, Conv1x1 caso contrário.
    if strides == 1 and g.shape(x)[-1] == stage.channels:
        shortcut = x
    else:
        shortcut = g.conv(
            f"{name}_shortcut_conv", x, stage.channels, 1, strides, **_CONV_KERAS
        )

    x = g.add(f"{name}_add", shortcut, y)
    return g.act(f"{name}_relu", x, act)


def resolve_input_shape(config: dict, input_shape=None) -> tuple[int, ...]:
    return tuple(int(d) for d in (input_shape or DEFAULT_INPUT_SHAPE))


def architecture(config: dict, input_shape=None, num_classes=None) -> GraphSpec:
    """Descreve o ResNet8 configurável (mesma topologia do builder anterior)."""
    input_shape = resolve_input_shape(config, input_shape)
    num_classes = int(num_classes or DEFAULT_NUM_CLASSES)
    act = resolve_activation(config)
    g = GraphSpec(input_shape, name="resnet8_variant")

    # O stem usa a largura e o kernel do estágio 1, como no ResNet8 de referência.
    stage_1 = _parse_stage(config, 1)
    x = _conv_bn(g, g.input, stage_1.channels, stage_1.kernel, 1, act=act, name="stem")

    for index in (1, 2, 3):
        stage = _parse_stage(config, index)
        for block in range(stage.blocks):
            x = _residual_block(
                g, x, stage,
                strides=stage.stride if block == 0 else 1,
                act=act,
                name=f"stage{index}_block{block + 1}",
            )

    pool = min(g.shape(x)[:2])
    x = g.avgpool("head_pool", x, pool)
    x = g.flatten("head_flatten", x)
    # Bias aleatório: com bias zero o conversor o descarta, e o oficial tem bias.
    g.dense(
        "predictions", x, num_classes, activation="softmax",
        kernel_initializer=_KERNEL_INITIALIZER, bias_initializer="random_normal",
        l2=_L2_STRENGTH,
    )
    return g


def estimate_cost(config: dict, input_shape=None, num_classes=None) -> dict:
    """Custo analítico (params, MACs, pico de ativação, ops) sem TensorFlow."""
    return architecture(config, input_shape, num_classes).summary()


def build_keras_model(config: dict, input_shape=None, num_classes=None):
    import tensorflow as tf

    tf.keras.backend.clear_session()
    return build_keras(architecture(config, input_shape, num_classes), "resnet8_variant")


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = DEFAULT_INPUT_SHAPE,
    num_classes: int = DEFAULT_NUM_CLASSES,
) -> Path:
    """Constrói o ResNet8 configurável e quantiza para TFLite int8."""
    model = build_keras_model(config, input_shape, num_classes)
    return quantize_to_tflite(model, variant_name, tmp_dir)
