import struct
import argparse
import os
import time
import numpy as np
import serial

from python_scripts.config import default_serial_port

DEFAULT_SERIAL_TIMEOUT_SEC = float(os.environ.get("BALAS_SERIAL_TIMEOUT_SEC", "60"))


def configure_nordic_vcom(ser: serial.Serial) -> None:
    """Assert DTR so the nRF52840-DK interface MCU drives its VCOM pins."""
    if os.environ.get("BALAS_TARGET") != "nordic":
        return
    ser.dtr = False
    time.sleep(0.1)
    ser.dtr = True
    time.sleep(0.5)
    ser.reset_input_buffer()

def load_bin_dir_as_f32_list(dir_path):
    """
    Loads all .bin files in a directory as float32 numpy arrays.

    Parameters:
        dir_path (str): Path to the directory containing .bin files.

    Returns:
        List[np.ndarray]: List of numpy arrays, each loaded from a .bin file.
    """
    arrays = []
    for fname in os.listdir(dir_path):
        if fname.endswith(".bin"):
            file_path = os.path.join(dir_path, fname)
            arr = np.fromfile(file_path, dtype=np.float32)
            arrays.append(arr)
    return arrays

def send_array_and_get_int(port_name, array: np.ndarray) -> int:
    """
    Sends a float32 numpy array via serial and reads a signed int32 response.

    Parameters:
        port_name (str): Serial port device name (e.g., "/dev/ttyUSB0").
        array (np.ndarray): Numpy array of dtype float32.

    Returns:
        int: The signed int32 received from the device.
    """
    if array.dtype != np.float32:
        raise ValueError("Array must be of dtype float32")

    # Open serial port
    with serial.Serial(
        port=port_name,
        baudrate=115200,
        timeout=DEFAULT_SERIAL_TIMEOUT_SEC,
        rtscts=os.environ.get("BALAS_TARGET") == "nordic",
    ) as ser:
        configure_nordic_vcom(ser)
        # Send the array as raw bytes
        ser.write(array.tobytes())
        ser.flush()

        # Read 4 bytes for signed int32
        resp_bytes = ser.read(4)
        if len(resp_bytes) != 4:
            raise RuntimeError("Did not receive 4 bytes from device")

        # Convert bytes to int32
        resp_int = int.from_bytes(resp_bytes, byteorder='little', signed=True)
        return resp_int

def send_profiling_inputs(serial_port, profiling_dir):
    f32_inputs = load_bin_dir_as_f32_list(profiling_dir)
    inference_times = []
    count = 1
    for f32_input in f32_inputs:
        inference_time_us = send_array_and_get_int(serial_port, f32_input)
        inference_times.append(inference_time_us)
        print(f"Inference {count}/{len(f32_inputs)}: {inference_time_us} us")
        count += 1
    return inference_times


def send_random_input_and_get_result(model_path: str, serial_port: str) -> int:
    import tensorflow as tf

    # Load model
    interpreter = tf.lite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    input_shape = input_details[0]['shape']

    # Get input size (#elements)
    input_size = np.prod(input_shape)

    # Generate random float32 data
    data = np.random.rand(input_size).astype(np.float32)

    # Serialize to bytes
    payload = struct.pack('<' + 'f' * input_size, *data)

    print(f"Sending {input_shape} float values. {len(payload)} bytes")
    # Open serial
    with serial.Serial(
        serial_port,
        baudrate=115200,
        timeout=DEFAULT_SERIAL_TIMEOUT_SEC,
        rtscts=os.environ.get("BALAS_TARGET") == "nordic",
    ) as ser:
        configure_nordic_vcom(ser)
        # Send payload
        ser.write(payload)
        ser.flush()

        # Wait for 1 integer (4 bytes, little-endian)
        resp = ser.read(4)
        if len(resp) < 4:
            raise TimeoutError("Did not receive full response from MCU")

        result = struct.unpack('<i', resp)[0]  # signed int32

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_quant", help="Path to the quantized model file")
    parser.add_argument("profiling_dataset", help="Path to the dataset with .bin float32 inputs")
    parser.add_argument(
        "--serial-device",
        default=default_serial_port(),
        help="Path to the serial device (default: BALAS_SERIAL_PORT or /dev/ttyACM0)",
    )
    args = parser.parse_args()
    inference_time_us = send_random_input_and_get_result(args.model_quant, args.serial_device)
    print(f"Inference Time with random data: {inference_time_us} us")
