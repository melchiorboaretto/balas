import os
from pathlib import Path
import numpy as np

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf


def build_and_quantize_model(
    config: dict,
    variant_name: str,
    tmp_dir: Path,
    input_shape: tuple = (1, 640),
    num_classes: int = 640,
) -> Path:
    """Constrói o modelo Keras de Anomaly Detection (Deep Autoencoder FC) e quantiza para .tflite int8."""
    tf.keras.backend.clear_session()

    large_fc = int(config.get("large_fc", 256))
    medium_fc = int(config.get("medium_fc", 128))
    small_fc = int(config.get("small_fc", 32))

    inputs = tf.keras.Input(shape=input_shape, name="input")
    x = tf.keras.layers.Flatten()(inputs)

    # Encoder
    x = tf.keras.layers.Dense(large_fc, activation="relu")(x)
    x = tf.keras.layers.Dense(medium_fc, activation="relu")(x)
    x = tf.keras.layers.Dense(small_fc, activation="relu", name="bottleneck")(x)

    # Decoder
    x = tf.keras.layers.Dense(medium_fc, activation="relu")(x)
    x = tf.keras.layers.Dense(large_fc, activation="relu")(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="relu", name="reconstruction")(x)

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
