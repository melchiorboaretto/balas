import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


# Builder DSE do CIFAR-10 baseado no ResNet8 do MLPerf Tiny.
#
# A topologia é sempre um DAG com três estágios residuais: o tensor se divide
# em ramo principal e atalho, os dois caminhos se encontram em um Add e o
# resultado recebe ReLU. O grid controla apenas largura, kernel, profundidade,
# stride e tipo de bloco. BatchNorm, ReLU, atalho automático, GAP e softmax
# ficam fixos para manter o espaço próximo do grid anterior.
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

# Constantes fixas do modelo. Não entram no grid para não inflar a busca com
# combinações que não mudam a topologia mensurada.
_L2_STRENGTH = 1e-4
_KERNEL_INITIALIZER = "he_normal"
_REPRESENTATIVE_SAMPLES = 100
_REPRESENTATIVE_SEED = 72


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
    return config.get(key, _DEFAULTS[key])


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
            raise ValueError(
                f"bottleneck_N exige N >= 2; recebido {value!r}."
            )
        return "bottleneck", ratio

    raise ValueError(
        f"block_type inválido: {value!r}. Use 'basic' ou 'bottleneck_N'."
    )


def _parse_stage(config: dict, index: int) -> StageConfig:
    """Lê e valida os parâmetros de um estágio."""
    block_type, bottleneck_ratio = _parse_block_type(
        _setting(config, f"block_type_{index}")
    )

    stage = StageConfig(
        channels=int(_setting(config, f"channels_{index}")),
        kernel=int(_setting(config, f"kernel_{index}")),
        blocks=int(_setting(config, f"blocks_{index}")),
        stride=int(_setting(config, f"stride_{index}")),
        block_type=block_type,
        bottleneck_ratio=bottleneck_ratio,
    )

    if stage.channels < 1:
        raise ValueError(f"channels_{index} deve ser >= 1; recebido {stage.channels}.")
    if stage.kernel < 1:
        raise ValueError(f"kernel_{index} deve ser >= 1; recebido {stage.kernel}.")
    if stage.blocks < 1:
        raise ValueError(f"blocks_{index} deve ser >= 1; recebido {stage.blocks}.")
    if stage.stride < 1:
        raise ValueError(f"stride_{index} deve ser >= 1; recebido {stage.stride}.")

    return stage


def _conv_bn(
    x: tf.Tensor,
    filters: int,
    kernel_size: int,
    strides: int,
    *,
    relu: bool,
    name: str,
) -> tf.Tensor:
    """Conv2D + BatchNorm + ReLU opcional.

    O último conv de um bloco residual usa relu=False para chegar sem ativação
    até a soma com o atalho.
    """
    # Convolução: extrai features e, com strides > 1, faz o downsampling.
    x = tf.keras.layers.Conv2D(
        filters=filters,
        kernel_size=kernel_size,
        strides=strides,
        padding="same",
        use_bias=True,
        kernel_initializer=_KERNEL_INITIALIZER,
        kernel_regularizer=tf.keras.regularizers.l2(_L2_STRENGTH),
        name=f"{name}_conv",
    )(x)

    # BatchNorm: normaliza por canal; em inferência usa médias/variâncias móveis.
    x = tf.keras.layers.BatchNormalization(name=f"{name}_bn")(x)

    # ReLU: não-linearidade padrão do ResNet8.
    if relu:
        x = tf.keras.layers.ReLU(name=f"{name}_relu")(x)

    return x


def _projection_shortcut(
    x: tf.Tensor,
    filters: int,
    strides: int,
    *,
    name: str,
) -> tf.Tensor:
    """Atalho 1x1 para igualar canais e/ou resolução antes do Add."""
    return tf.keras.layers.Conv2D(
        filters=filters,
        kernel_size=1,
        strides=strides,
        padding="same",
        use_bias=True,
        kernel_initializer=_KERNEL_INITIALIZER,
        kernel_regularizer=tf.keras.regularizers.l2(_L2_STRENGTH),
        name=f"{name}_conv",
    )(x)


def _build_shortcut(
    x: tf.Tensor,
    filters: int,
    strides: int,
    *,
    name: str,
) -> tf.Tensor:
    """Atalho automático: identity se o formato bate, projeção caso contrário."""
    if strides == 1 and int(x.shape[-1]) == filters:
        return x

    return _projection_shortcut(x, filters, strides, name=name)


def _residual_block(
    x: tf.Tensor,
    stage: StageConfig,
    *,
    strides: int,
    name: str,
) -> tf.Tensor:
    """Bloco residual: ramo principal + atalho + Add + ReLU."""
    if stage.block_type == "basic":
        # Basic block: dois convs espaciais. O segundo não tem ReLU antes do Add.
        y = _conv_bn(
            x,
            stage.channels,
            stage.kernel,
            strides,
            relu=True,
            name=f"{name}_conv1",
        )
        y = _conv_bn(
            y,
            stage.channels,
            stage.kernel,
            1,
            relu=False,
            name=f"{name}_conv2",
        )
    else:
        # Bottleneck: 1x1 reduz, conv espacial processa, 1x1 expande.
        inner_channels = max(1, stage.channels // stage.bottleneck_ratio)
        y = _conv_bn(
            x,
            inner_channels,
            1,
            strides,
            relu=True,
            name=f"{name}_reduce",
        )
        y = _conv_bn(
            y,
            inner_channels,
            stage.kernel,
            1,
            relu=True,
            name=f"{name}_spatial",
        )
        y = _conv_bn(
            y,
            stage.channels,
            1,
            1,
            relu=False,
            name=f"{name}_expand",
        )

    # Atalho: identity ou Conv1x1 com o mesmo stride do ramo principal.
    shortcut = _build_shortcut(
        x,
        stage.channels,
        strides,
        name=f"{name}_shortcut",
    )

    # Fan-in dos dois caminhos. As formas já foram equalizadas pelo atalho.
    x = tf.keras.layers.Add(name=f"{name}_add")([shortcut, y])

    # Ativação após a soma residual.
    return tf.keras.layers.ReLU(name=f"{name}_relu")(x)


def _build_stage(
    x: tf.Tensor,
    stage: StageConfig,
    *,
    stage_index: int,
) -> tf.Tensor:
    """Constrói os blocos de um estágio.

    Só o primeiro bloco usa o stride do estágio; os seguintes usam stride 1.
    """
    for block_index in range(stage.blocks):
        block_strides = stage.stride if block_index == 0 else 1
        x = _residual_block(
            x,
            stage,
            strides=block_strides,
            name=f"stage{stage_index}_block{block_index + 1}",
        )

    return x


def _safe_tflite_filename(variant_name: str) -> str:
    """Gera um nome seguro para o .tflite, mesmo com muitas chaves no grid."""
    sanitized = "".join(
        char if char.isalnum() or char in "-_." else "_"
        for char in variant_name
    )
    if not sanitized:
        sanitized = "model"

    # O nome completo pode passar do limite de 255 bytes do filesystem.
    if len(sanitized) > 180:
        digest = hashlib.sha1(variant_name.encode("utf-8")).hexdigest()[:16]
        sanitized = f"model_{digest}"

    return f"{sanitized}.tflite"


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (32, 32, 3),
    num_classes: int = 10,
) -> Path:
    """Constrói o ResNet8 configurável e quantiza para TFLite int8."""
    tf.keras.backend.clear_session()

    input_shape = tuple(int(dim) for dim in input_shape)
    num_classes = int(num_classes or 10)

    # O stem usa a largura e o kernel do estágio 1. No ResNet8 de referência
    # ambos têm 16 canais e kernel 3x3, então isso preserva o ponto padrão sem
    # adicionar uma chave extra ao grid.
    stage_1 = _parse_stage(config, 1)
    # batch_size=1 deixa todas as formas estáticas, como nos .tflite oficiais;
    # sem isso o Flatten vira SHAPE/STRIDED_SLICE/PACK/RESHAPE no grafo.
    inputs = tf.keras.Input(shape=input_shape, batch_size=1, name="input")
    x = _conv_bn(
        inputs,
        stage_1.channels,
        stage_1.kernel,
        1,
        relu=True,
        name="stem",
    )

    # Três estágios residuais. Cada um adiciona um ou mais blocos com Add.
    for stage_index in (1, 2, 3):
        stage = _parse_stage(config, stage_index)
        x = _build_stage(x, stage, stage_index=stage_index)

    # Cabeça fixa do ResNet8: pooling global, Flatten, Dense e softmax.
    pool_size = int(np.amin(x.shape[1:3]))
    x = tf.keras.layers.AveragePooling2D(pool_size=pool_size, name="head_pool")(x)
    x = tf.keras.layers.Flatten(name="head_flatten")(x)
    outputs = tf.keras.layers.Dense(
        num_classes,
        activation="softmax",
        use_bias=True,
        kernel_initializer=_KERNEL_INITIALIZER,
        # Bias aleatório: com bias zero (inicialização padrão) o conversor o
        # descarta, e o modelo treinado oficial tem bias.
        bias_initializer="random_normal",
        kernel_regularizer=tf.keras.regularizers.l2(_L2_STRENGTH),
        name="predictions",
    )(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="resnet8_variant")

    # Quantização int8 com o mesmo esquema de calibração sintética do builder
    # anterior. Pesos e amostras aleatórios servem para medir MACs/latência/
    # arena; a acurácia resultante não é representativa.
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
