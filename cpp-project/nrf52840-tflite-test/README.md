# nRF52840-DK port

This directory is the isolated BALAS target for the Nordic nRF52840-DK
(`PCA10056`). It uses the nRF Connect SDK/Zephyr board target
`nrf52840dk/nrf52840` and keeps all Nordic-specific platform code separate from
the NXP and STM32 projects.

Two build modes are available:

- bring-up (default): blinks LED1 at boot, receives four bytes on VCOM0 and
  returns the signed little-endian value `52840`;
- TFLM profiling: receives one float32 input tensor, invokes TensorFlow Lite
  Micro with CMSIS-NN kernels and returns inference time as signed little-endian
  microseconds.

Build and flash the bring-up firmware:

```bash
BALAS_TARGET=nordic ./compile.sh
BALAS_TARGET=nordic ./deploy.sh
python python_scripts/diag_nordic_bringup.py /dev/ttyACM0
```

Build the TFLM profiling firmware:

```bash
BALAS_TARGET=nordic BALAS_NORDIC_ENABLE_MODEL=ON ./compile.sh
BALAS_TARGET=nordic ./deploy.sh
```

The default SDK is nRF Connect SDK `v3.4.0`. Override it with
`NORDIC_NCS_VERSION`. TFLM is an optional Zephyr module and is expected at
`$HOME/ncs/v3.4.0/optional/modules/lib/tflite-micro`; override that location
with `NORDIC_TFLM_MODULE_DIR`.

VCOM0 must be opened with DTR asserted and RTS/CTS enabled. VCOM1 is exposed by
the J-Link USB device but is not wired to the nRF52840 on this DK. Build output
is written to `build/` and ignored by Git.
