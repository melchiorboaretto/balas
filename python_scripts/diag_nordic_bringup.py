import argparse
import time

import serial


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the BALAS Nordic bring-up protocol")
    parser.add_argument("serial_device", nargs="?", default="/dev/ttyACM0")
    args = parser.parse_args()

    with serial.Serial(args.serial_device, baudrate=115200, timeout=5, rtscts=True) as port:
        # The nRF52840-DK interface MCU keeps the VCOM UART pins tri-stated
        # until the host terminal asserts DTR.
        port.dtr = False
        time.sleep(0.1)
        port.dtr = True
        time.sleep(0.5)
        port.reset_input_buffer()
        port.write(b"BLAS")
        port.flush()
        response = port.read(4)

    if len(response) != 4:
        raise RuntimeError(f"Expected 4 response bytes, received {len(response)}")
    value = int.from_bytes(response, byteorder="little", signed=True)
    if value != 52840:
        raise RuntimeError(f"Unexpected Nordic bring-up response: {value}")
    print(f"Nordic bring-up OK on {args.serial_device}: {value}")


if __name__ == "__main__":
    main()
