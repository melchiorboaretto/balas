import hashlib
import os
from pathlib import Path

import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


# Builder DSE de Anomaly Detection baseado no Deep Autoencoder do MLPerf Tiny.
#
# A topologia oficial do MLPerf Tiny (ToyADMOS) é um Deep Autoencoder com:
#   - Entrada: 640 (5 frames de 128 mel-bins)
#   - Encoder: 4 camadas Dense de 128 neurônios, cada uma com BatchNorm e ReLU
#   - Bottleneck: 1 camada Dense de 8 neurônios com BatchNorm e ReLU
#   - Decoder: 4 camadas Dense de 128 neurônios, cada uma com BatchNorm e ReLU
#   - Saída: 1 camada Dense de 640 neurônios com ativação linear (sem ReLU)
#
# O grid controla a largura das camadas ocultas, o afunilamento do gargalo e a profundidade.
# Quando os defaults são mantidos, reproduz EXATAMENTE a topologia de referência.
GRID_KEYS = (
    "hidden_units",
    "bottleneck_units",
    "num_hidden_layers",
)

# Nomes legados aceitos como fallback para compatibilidade regressiva.
LEGACY_GRID_KEYS = (
    "large_fc",
    "medium_fc",
    "small_fc",
)

# Valores que reproduzem o Deep Autoencoder de referência do MLPerf Tiny v1.0/v1.1.
_DEFAULTS = {
    "hidden_units": 128,
    "bottleneck_units": 8,
    "num_hidden_layers": 4,
}

_REPRESENTATIVE_SAMPLES = 100
_REPRESENTATIVE_SEED = 72
# Com bias zero (inicialização padrão) o conversor descarta o bias das camadas
# densas; o modelo treinado oficial tem bias em todas elas.
_BIAS_INITIALIZER = "random_normal"


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


def _resolve_params(config: dict) -> tuple[int, int, int]:
    """Resolve os hiperparâmetros suportando chaves canônicas e legadas."""
    hidden_units = config.get("hidden_units")
    if hidden_units is None:
        # Fallback para legados
        hidden_units = config.get("medium_fc", config.get("large_fc", _DEFAULTS["hidden_units"]))
    hidden_units = int(hidden_units)

    bottleneck_units = config.get("bottleneck_units")
    if bottleneck_units is None:
        bottleneck_units = config.get("small_fc", _DEFAULTS["bottleneck_units"])
    bottleneck_units = int(bottleneck_units)

    num_hidden_layers = int(config.get("num_hidden_layers", _DEFAULTS["num_hidden_layers"]))
    return hidden_units, bottleneck_units, num_hidden_layers


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (1, 640),
    num_classes: int = 640,
) -> Path:
    """Constrói o Deep Autoencoder configurável do MLPerf Tiny e quantiza para TFLite int8."""
    tf.keras.backend.clear_session()

    hidden_units, bottleneck_units, num_hidden_layers = _resolve_params(config)

    # Garante dimensionalidade plana para o Autoencoder
    input_dim = int(np.prod(input_shape))
    output_dim = int(num_classes or input_dim)

    inputs = tf.keras.Input(shape=(input_dim,), batch_size=1, name="input")
    x = inputs

    # --- ENCODER ---
    for i in range(num_hidden_layers):
        x = tf.keras.layers.Dense(hidden_units, bias_initializer=_BIAS_INITIALIZER, name=f"enc_dense_{i+1}")(x)
        x = tf.keras.layers.BatchNormalization(name=f"enc_bn_{i+1}")(x)
        x = tf.keras.layers.Activation("relu", name=f"enc_relu_{i+1}")(x)

    # --- BOTTLENECK ---
    x = tf.keras.layers.Dense(bottleneck_units, bias_initializer=_BIAS_INITIALIZER, name="bottleneck_dense")(x)
    x = tf.keras.layers.BatchNormalization(name="bottleneck_bn")(x)
    x = tf.keras.layers.Activation("relu", name="bottleneck_relu")(x)

    # --- DECODER ---
    for i in range(num_hidden_layers):
        x = tf.keras.layers.Dense(hidden_units, bias_initializer=_BIAS_INITIALIZER, name=f"dec_dense_{i+1}")(x)
        x = tf.keras.layers.BatchNormalization(name=f"dec_bn_{i+1}")(x)
        x = tf.keras.layers.Activation("relu", name=f"dec_relu_{i+1}")(x)

    # --- OUTPUT RECONSTRUCTION (Linear, sem ReLU como no MLPerf Tiny oficial) ---
    outputs = tf.keras.layers.Dense(
        output_dim, activation=None, bias_initializer=_BIAS_INITIALIZER, name="reconstruction"
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
                size=(1, input_dim),
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
