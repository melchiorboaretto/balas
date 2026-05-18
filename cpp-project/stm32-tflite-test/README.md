# STM32 NUCLEO-H723ZG bring-up target

This is the first STM32 port target for the `NUCLEO-H723ZG`.

With `BALAS_STM32_ENABLE_MODEL=OFF`, it builds a minimal firmware that:

- configures the STM32H723ZG clock from the official ST template;
- configures USART3 on PD8/PD9 for the ST-LINK Virtual COM Port;
- sends `BALAS STM32H723ZG echo ready` at boot;
- echoes received bytes at 115200 8N1;
- toggles PB0 while waiting on serial input.

The STM32-specific `MyModel` port lives in `Core/Model`. It removes the NXP
`fsl_common.h` dependency and uses a local GCC alignment macro for the tensor
arena.

The NXP/MCUXpresso target remains the default. Build this target with:

```bash
BALAS_TARGET=stm32 ./compile.sh
```

To compile the STM32 `MyModel` port into the target build:

```bash
BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=ON ./compile.sh
```

With `BALAS_STM32_ENABLE_MODEL=ON`, the build uses `Core/Src/main_model.cpp`,
`Core/Platform/serial_io.cpp`, and `Core/Platform/timer.cpp`. This matches the
NXP protocol: receive one float32 input tensor, run inference, and return one
little-endian signed `int` with elapsed microseconds.

Current validation status: the firmware builds, flashes, constructs `MyModel`,
and receives the full 12288-byte input tensor. It then blocks inside
`interpreter.Invoke()`. The current `libtensorflow-microlite.a` still comes from
the NXP project and was built for Cortex-M33; the next required step is a
Cortex-M7 TFLM library.

For local diagnosis, this emits boot/progress bytes without changing normal
builds:

```bash
BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=ON BALAS_STM32_MODEL_BOOT_MARKER=ON ./compile.sh
```

Flash it with:

```bash
BALAS_TARGET=stm32 ./deploy.sh
```

The default firmware passed to `STM32_Programmer_CLI` is:

```text
cpp-project/stm32-tflite-test/build/stm32-tflite-test.elf
```

The project expects the official `STM32CubeH7` package at:

```text
external/STM32CubeH7
```

That directory is intentionally ignored by Git. It was created with:

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/STMicroelectronics/STM32CubeH7.git external/STM32CubeH7
git -C external/STM32CubeH7 sparse-checkout set Drivers Projects/NUCLEO-H723ZG/Templates
git -C external/STM32CubeH7 submodule update --init --depth 1 \
  Drivers/STM32H7xx_HAL_Driver \
  Drivers/CMSIS/Device/ST/STM32H7xx \
  Drivers/CMSIS/Core \
  Drivers/BSP/STM32H7xx_Nucleo
```

On this machine the ST-LINK VCP appeared as `/dev/ttyACM0`. Flashing requires
the ST-LINK udev rules so `STM32_Programmer_CLI` can open the raw USB device.
After those rules were installed and reloaded, `BALAS_TARGET=stm32 ./deploy.sh`
programmed and verified the firmware successfully.
