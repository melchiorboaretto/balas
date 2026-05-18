# STM32 NUCLEO-H723ZG bring-up target

This is the first STM32 port target for the `NUCLEO-H723ZG`.

It currently builds a minimal firmware that:

- configures the STM32H723ZG clock from the official ST template;
- configures USART3 on PD8/PD9 for the ST-LINK Virtual COM Port;
- sends `BALAS STM32H723ZG echo ready` at boot;
- echoes received bytes at 115200 8N1;
- toggles PB0 while waiting on serial input.

The STM32-specific `MyModel` port lives in `Core/Model`. It removes the NXP
`fsl_common.h` dependency and uses a local GCC alignment macro for the tensor
arena. It is not enabled in the default firmware yet because the current
`libtensorflow-microlite.a` in the NXP project was built for Cortex-M33, while
this board is Cortex-M7.

The NXP/MCUXpresso target remains the default. Build this target with:

```bash
BALAS_TARGET=stm32 ./compile.sh
```

To compile the STM32 `MyModel` port into the target build:

```bash
BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=ON ./compile.sh
```

The current `main.c` still runs the echo firmware, so the linker can garbage
collect unused model code. Instantiating `MyModel` in the STM32 main loop is the
next integration step.

Flash it with:

```bash
BALAS_TARGET=stm32 ./deploy.sh
```

The default firmware passed to `STM32_Programmer_CLI` is:

```text
cpp-project/stm32-tflite-test/build/stm32-tflite-echo.elf
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
