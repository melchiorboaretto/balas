
import os
from pathlib import Path
import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (32, 32, 3),
    num_classes: int = 10,
) -> Path:
    """Constrói o modelo Keras com os hiperparâmetros e quantiza para .tflite int8."""
    tf.keras.backend.clear_session()

    inputs = tf.keras.Input(shape=input_shape, name="input")
    x = tf.keras.layers.Conv2D(
        config["channels_1"], config["kernel_1"], padding="same", activation="relu"
    )(inputs)
    x = tf.keras.layers.MaxPooling2D(pool_size=2)(x)
    x = tf.keras.layers.Conv2D(
        config["channels_2"], config["kernel_2"], padding="same", activation="relu"
    )(x)
    x = tf.keras.layers.MaxPooling2D(pool_size=2)(x)
    x = tf.keras.layers.Conv2D(
        config["channels_3"], config["kernel_3"], padding="same", activation="relu"
    )(x)
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
