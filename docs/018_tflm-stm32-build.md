# Build TFLM para STM32

Este documento registra o projeto separado usado para gerar uma biblioteca
TensorFlow Lite Micro para o alvo STM32/Cortex-M7 sem alterar o projeto
`cpp-project/stm32-tflite-test`.

## Objetivo

Gerar uma `libtensorflow-microlite.a` especifica para Cortex-M7, para permitir
um backend futuro `TFLM/STM32` comparavel ao backend `TFLM/NXP` historico.

O checkout, objetos e biblioteca gerada ficam em:

```text
external/tflm-stm32/
```

Essa pasta e ignorada pelo Git.

## Script

O script versionado e:

```bash
scripts/build_tflm_stm32.sh
```

Por padrao ele usa:

```text
TFLM_REPO_URL=https://github.com/tensorflow/tflite-micro.git
TFLM_COMMIT=9f5ac257ee7f6a07f1f3c28aa1c86411c05f11e3
TFLM_TARGET=cortex_m_generic
TFLM_TARGET_ARCH=cortex-m7+fp
TFLM_FPU=fpv5-d16
TFLM_OPTIMIZED_KERNEL_DIR=cmsis_nn
```

O commit fica fixado para que a biblioteca possa ser reproduzida.

## Uso

```bash
scripts/build_tflm_stm32.sh
```

O script usa o `arm-none-eabi-gcc` local encontrado no `PATH` e passa esse
diretorio ao Makefile da TFLM via `TARGET_TOOLCHAIN_ROOT`, evitando depender do
toolchain baixado automaticamente pelo Makefile.

O Makefile da TFLM chama `python3` diretamente em alguns pontos. Para manter o
ambiente reprodutivel, o script cria um shim local que aponta `python3` para a
`.venv` do repositorio quando ela existe. Essa `.venv` precisa conter `numpy` e
`Pillow`.

O artefato esperado e:

```text
external/tflm-stm32/package/lib/libtensorflow-microlite.a
```

O script tambem gera:

```text
external/tflm-stm32/package/build-info.env
```

Esse arquivo registra commit, alvo, arquitetura e versao do `arm-none-eabi-gcc`
usados na build.

## Validacao local

Em 2026-05-18, o script gerou:

```text
external/tflm-stm32/package/lib/libtensorflow-microlite.a
```

Tamanho observado:

```text
1.7M
```

Metadados registrados em `build-info.env`:

```text
TFLM_COMMIT=9f5ac257ee7f6a07f1f3c28aa1c86411c05f11e3
TFLM_TARGET=cortex_m_generic
TFLM_TARGET_ARCH=cortex-m7+fp
TFLM_FPU=fpv5-d16
TFLM_OPTIMIZED_KERNEL_DIR=cmsis_nn
TARGET_TOOLCHAIN_ROOT=/home/christian/bin/
ARM_NONE_EABI_GCC=arm-none-eabi-gcc (Arm GNU Toolchain 14.2.Rel1 (Build arm-14.52)) 14.2.1 20241119
```

Uma checagem com `arm-none-eabi-readelf -A` em um objeto da build confirmou:

```text
Tag_CPU_arch: v7E-M
Tag_FP_arch: FPv5/FP-D16 for ARMv8
Tag_ABI_VFP_args: VFP registers
```

Isso indica que a biblioteca foi gerada para Cortex-M7 com ABI hard-float
compativel com o alvo STM32H723ZG usado neste port.

## Proximo passo

Depois que a biblioteca for gerada e validada, o backend
`BALAS_STM32_MODEL_BACKEND=tflm` pode ser alterado para linkar essa lib em vez
da lib TFLM do projeto NXP.
