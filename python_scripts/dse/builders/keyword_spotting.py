import os
from pathlib import Path
import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


def _parse_first_kernel(first_kernel_param) -> tuple[int, int]:
    """Converte parâmetros de filtro como '10x4' ou [10, 4] para tupla (10, 4)."""
    if isinstance(first_kernel_param, (list, tuple)):
        return int(first_kernel_param[0]), int(first_kernel_param[1])
    if isinstance(first_kernel_param, str) and "x" in first_kernel_param:
        parts = first_kernel_param.split("x")
        return int(parts[0]), int(parts[1])
    k = int(first_kernel_param)
    return k, k


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (49, 10, 1),
    num_classes: int = 12,
) -> Path:
    """Constrói o modelo Keras de Keyword Spotting (DS-CNN Áudio) e quantiza para .tflite int8."""
    tf.keras.backend.clear_session()

    channels = int(config.get("channels", 64))
    kernel_size = int(config.get("kernel", 3))
    first_k_h, first_k_w = _parse_first_kernel(config.get("first_kernel", "10x4"))

    inputs = tf.keras.Input(shape=input_shape, name="input")

    # Primeira Convolução Retangular para Áudio
    x = tf.keras.layers.Conv2D(
        channels, (first_k_h, first_k_w), strides=(2, 1), padding="same", activation="relu"
    )(inputs)

    # Bloco DS-CNN 1
    x = tf.keras.layers.DepthwiseConv2D(
        (kernel_size, kernel_size), padding="same", activation="relu"
    )(x)
    x = tf.keras.layers.Conv2D(channels, (1, 1), padding="same", activation="relu")(x)

    # Bloco DS-CNN 2
    x = tf.keras.layers.DepthwiseConv2D(
        (kernel_size, kernel_size), padding="same", activation="relu"
    )(x)
    x = tf.keras.layers.Conv2D(channels, (1, 1), padding="same", activation="relu")(x)

    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Dense(num_classes, name="logits")(x)
    model = tf.keras.Model(inputs=inputs, outputs=outputs, name=variant_name)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset_gen():
        rng = np.random.default_rng(72)

        for _ in range(100):
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

    tflite_bytes = converter.convert()
    tflite_path = tmp_dir / f"{variant_name}.tflite"
    tflite_path.write_bytes(tflite_bytes)

    return tflite_path
