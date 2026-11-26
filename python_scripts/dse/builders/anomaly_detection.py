import math
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


# Builder DSE de Anomaly Detection baseado no Deep Autoencoder do MLPerf Tiny.
#
# A topologia oficial do MLPerf Tiny (ToyADMOS) é um Deep Autoencoder com:
#   - Entrada: 640 (5 frames de 128 mel-bins)
#   - Encoder: 4 camadas Dense de 128 neurônios, cada uma com BatchNorm e ReLU
#   - Bottleneck: 1 camada Dense de 8 neurônios com BatchNorm e ReLU
#   - Decoder: 4 camadas Dense de 128 neurônios, cada uma com BatchNorm e ReLU
#   - Saída: 1 camada Dense de 640 neurônios com ativação linear (sem ReLU)
#
# Chaves:
#   - hidden_units / num_hidden_layers (legado): largura e profundidade simétricas.
#   - enc_layers / dec_layers (opcionais): profundidade separada do encoder e do decoder.
#   - enc_units_i / dec_units_i (opcionais): largura de cada camada (i = 1 é a mais
#     próxima da entrada no encoder e a mais próxima do bottleneck no decoder).
#   - activation / leaky_slope (opcionais): ativação das camadas ocultas; a saída
#     continua linear.
# Quando os defaults são mantidos, reproduz EXATAMENTE a topologia de referência.
MAX_LAYERS = 8

GRID_KEYS = (
    "hidden_units",
    "bottleneck_units",
    "num_hidden_layers",
)

OPTIONAL_GRID_KEYS = (
    ("enc_layers", "dec_layers")
    + tuple(f"enc_units_{i}" for i in range(1, MAX_LAYERS + 1))
    + tuple(f"dec_units_{i}" for i in range(1, MAX_LAYERS + 1))
    + ACTIVATION_GRID_KEYS
)

# Nomes legados aceitos como fallback para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "large_fc",
    "medium_fc",
    "small_fc",
)

CONTROL_KEYS = ("activation", "enc_layers", "dec_layers", "num_hidden_layers")

DEFAULT_INPUT_SHAPE = (1, 640)
DEFAULT_NUM_CLASSES = 640

# Valores que reproduzem o Deep Autoencoder de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "hidden_units": 128,
    "bottleneck_units": 8,
    "num_hidden_layers": 4,
}

# Com bias zero (inicialização padrão) o conversor descarta o bias das camadas
# densas; o modelo treinado oficial tem bias em todas elas.
_DENSE_KERAS = dict(bias_initializer="random_normal")


def _get(config: dict, key: str, default):
    value = config.get(key)
    return default if value is None else value


def _resolve_params(config: dict) -> dict:
    """Resolve os hiperparâmetros suportando chaves canônicas, novas e legadas."""
    hidden_units = config.get("hidden_units")
    if hidden_units is None:
        hidden_units = _get(config, "medium_fc", _get(config, "large_fc", _DEFAULTS["hidden_units"]))
    hidden_units = int(hidden_units)

    bottleneck_units = int(
        _get(config, "bottleneck_units", _get(config, "small_fc", _DEFAULTS["bottleneck_units"]))
    )
    num_hidden_layers = int(_get(config, "num_hidden_layers", _DEFAULTS["num_hidden_layers"]))
    enc_layers = int(_get(config, "enc_layers", num_hidden_layers))
    dec_layers = int(_get(config, "dec_layers", num_hidden_layers))

    for name, value in (("enc_layers", enc_layers), ("dec_layers", dec_layers)):
        if not 0 <= value <= MAX_LAYERS:
            raise ValueError(f"{name} deve estar entre 0 e {MAX_LAYERS}; recebido {value}.")

    enc = [int(_get(config, f"enc_units_{i}", hidden_units)) for i in range(1, enc_layers + 1)]
    dec = [int(_get(config, f"dec_units_{i}", hidden_units)) for i in range(1, dec_layers + 1)]
    return {"enc": enc, "dec": dec, "bottleneck": bottleneck_units}


def superseded_keys(grid: dict) -> set:
    """Chaves do GRID_KEYS que não têm efeito dado o grid (para o validate_grid)."""
    superseded = set()
    if "enc_layers" in grid and "dec_layers" in grid:
        superseded.add("num_hidden_layers")
        max_enc = max(int(v) for v in grid["enc_layers"])
        max_dec = max(int(v) for v in grid["dec_layers"])
        needed = [f"enc_units_{i}" for i in range(1, max_enc + 1)]
        needed += [f"dec_units_{i}" for i in range(1, max_dec + 1)]
        if all(k in grid for k in needed):
            superseded.add("hidden_units")
    return superseded


def canonicalize(config: dict) -> dict:
    """Anula chaves inativas para que modelos iguais tenham o mesmo hash."""
    config = canonicalize_activation(dict(config))
    num_hidden = int(_get(config, "num_hidden_layers", _DEFAULTS["num_hidden_layers"]))
    enc_layers = int(_get(config, "enc_layers", num_hidden))
    dec_layers = int(_get(config, "dec_layers", num_hidden))

    for prefix, layers in (("enc", enc_layers), ("dec", dec_layers)):
        for i in range(layers + 1, MAX_LAYERS + 1):
            if f"{prefix}_units_{i}" in config:
                config[f"{prefix}_units_{i}"] = None

    # num_hidden_layers só importa se enc_layers ou dec_layers estiverem ausentes.
    if "num_hidden_layers" in config and config.get("enc_layers") is not None \
            and config.get("dec_layers") is not None:
        config["num_hidden_layers"] = None

    # hidden_units só importa se alguma camada ativa não tiver largura explícita.
    if "hidden_units" in config:
        active = [f"enc_units_{i}" for i in range(1, enc_layers + 1)]
        active += [f"dec_units_{i}" for i in range(1, dec_layers + 1)]
        if all(config.get(k) is not None for k in active):
            config["hidden_units"] = None
    return config


def resolve_input_shape(config: dict, input_shape=None) -> tuple[int, ...]:
    shape = tuple(int(d) for d in (input_shape or DEFAULT_INPUT_SHAPE))
    # Autoencoder: entrada sempre achatada.
    return (int(math.prod(shape)),)


def architecture(config: dict, input_shape=None, num_classes=None) -> GraphSpec:
    p = _resolve_params(config)
    input_shape = resolve_input_shape(config, input_shape)
    output_dim = int(num_classes or input_shape[0])
    act = resolve_activation(config)
    g = GraphSpec(input_shape, name="deep_autoencoder_variant")

    x = g.input
    for i, units in enumerate(p["enc"], start=1):
        x = g.dense(f"enc_dense_{i}", x, units, **_DENSE_KERAS)
        x = g.bn(f"enc_bn_{i}", x)
        x = g.act(f"enc_relu_{i}", x, act)

    x = g.dense("bottleneck_dense", x, p["bottleneck"], **_DENSE_KERAS)
    x = g.bn("bottleneck_bn", x)
    x = g.act("bottleneck_relu", x, act)

    for i, units in enumerate(p["dec"], start=1):
        x = g.dense(f"dec_dense_{i}", x, units, **_DENSE_KERAS)
        x = g.bn(f"dec_bn_{i}", x)
        x = g.act(f"dec_relu_{i}", x, act)

    # Reconstrução linear, sem ativação, como no MLPerf Tiny oficial.
    g.dense("reconstruction", x, output_dim, activation=None, **_DENSE_KERAS)
    return g


def estimate_cost(config: dict, input_shape=None, num_classes=None) -> dict:
    """Custo analítico (params, MACs, pico de ativação, ops) sem TensorFlow."""
    return architecture(config, input_shape, num_classes).summary()


def build_keras_model(config: dict, input_shape=None, num_classes=None):
    import tensorflow as tf

    tf.keras.backend.clear_session()
    return build_keras(architecture(config, input_shape, num_classes), "deep_autoencoder_variant")


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = DEFAULT_INPUT_SHAPE,
    num_classes: int = DEFAULT_NUM_CLASSES,
) -> Path:
    """Constrói o Deep Autoencoder configurável do MLPerf Tiny e quantiza para TFLite int8."""
    model = build_keras_model(config, input_shape, num_classes)
    return quantize_to_tflite(model, variant_name, tmp_dir)
