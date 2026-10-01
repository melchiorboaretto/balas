import os
from pathlib import Path
import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (96, 96, 3),
    num_classes: int = 2,
) -> Path:
    """Constrói o modelo Keras de Visual Wake Words (MobileNetV1 / Depthwise Separable) e quantiza para .tflite int8."""
    tf.keras.backend.clear_session()

    initial_channels = int(config.get("initial_channels", 8))
    multiplier = float(config.get("channels_multiplier", 1.5))
    kernel_size = int(config.get("kernel", 3))

    inputs = tf.keras.Input(shape=input_shape, name="input")

    # Camada Convolucional Inicial
    x = tf.keras.layers.Conv2D(
        initial_channels, kernel_size=3, strides=2, padding="same", activation="relu"
    )(inputs)

    # Bloco Depthwise Separable 1
    ch1 = int(initial_channels * multiplier)
    x = tf.keras.layers.DepthwiseConv2D(
        kernel_size=kernel_size, padding="same", activation="relu"
    )(x)
    x = tf.keras.layers.Conv2D(ch1, kernel_size=1, padding="same", activation="relu")(x)

    # Bloco Depthwise Separable 2 (Stride 2)
    ch2 = int(ch1 * multiplier)
    x = tf.keras.layers.DepthwiseConv2D(
        kernel_size=kernel_size, strides=2, padding="same", activation="relu"
    )(x)
    x = tf.keras.layers.Conv2D(ch2, kernel_size=1, padding="same", activation="relu")(x)

    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Dense(num_classes, name="logits")(x)
    model = tf.keras.Model(inputs=inputs, outputs=outputs, name=variant_name)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset_gen():
        for _ in range(20):
            data = np.random.uniform(0.0, 1.0, size=(1,) + input_shape).astype(np.float32)
            yield [data]

    converter.representative_dataset = representative_dataset_gen
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_bytes = converter.convert()
    tflite_path = tmp_dir / f"{variant_name}.tflite"
    tflite_path.write_bytes(tflite_bytes)

    return tflite_path
