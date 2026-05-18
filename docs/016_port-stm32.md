# Port para STM32 NUCLEO-H723ZG

Data da analise: 2026-05-12

## Objetivo

Registrar o que precisa ser alterado no projeto, que hoje funciona na placa NXP `FRDM-MCXN947`, para passar a funcionar na placa ST `NUCLEO-H723ZG` / `NUH723ZG$AT2`, baseada no MCU `STM32H723ZG`.

Este documento e uma analise de portabilidade. Ele nao aplica o port ainda.

## Resumo executivo

O codigo de aplicacao de inferencia e relativamente portavel, mas o firmware atual esta fortemente acoplado ao ecossistema NXP:

- projeto Eclipse/MCUXpresso em `cpp-project/tflite-test`
- startup, linker script, CMSIS device headers e drivers da NXP
- inicializacao gerada pelo MCUXpresso Config Tools
- UART por `LPUART` / `LP_FLEXCOMM4`
- timer por `CTIMER0`
- build por `MCUXpresso IDE`
- flash por `LinkServer` / `crt_emu_cm_redlink`

Para a `NUCLEO-H723ZG`, nao basta trocar nomes de placa. O caminho correto e criar um novo alvo STM32 e reutilizar somente a camada de aplicacao:

- `source/MCXN947_Project.cpp`, com ajustes de inicializacao
- `model/`, com pequena remocao do include NXP
- TensorFlow Lite Micro, recompilado ou substituido por biblioteca compatvel com Cortex-M7
- scripts Python do host, mantendo o protocolo serial

## Hardware de destino

Placa:

- `NUCLEO-H723ZG`
- variante informada: `NUH723ZG$AT2`
- familia: STM32H7 Nucleo-144
- debugger/programmer onboard: ST-LINK integrado

MCU:

- `STM32H723ZG`
- nucleo Arm Cortex-M7
- frequencia maxima anunciada pela ST: ate 550 MHz
- FPU double/single precision
- cache L1 de instrucao e dados
- ate 1 MB de Flash
- ate 564 KB de RAM

Observacao importante:

- A `FRDM-MCXN947` usa Cortex-M33.
- A `STM32H723ZG` usa Cortex-M7.
- Por isso, flags de compilacao, biblioteca TFLM/CMSIS-NN e objetos precompilados precisam ser revistos.

## Arquivos do projeto atual que prendem o firmware na NXP

### Entrada principal

Arquivo atual:

- `cpp-project/tflite-test/source/MCXN947_Project.cpp`

Acoplamentos:

- inclui `peripherals.h`, `pin_mux.h` e `clock_config.h`
- chama `BOARD_InitBootPins()`
- chama `BOARD_InitBootClocks()`
- chama `BOARD_InitBootPeripherals()`

No STM32 isso deve virar:

- `HAL_Init()`
- `SystemClock_Config()`
- inicializacao gerada pelo CubeMX, por exemplo `MX_GPIO_Init()`, `MX_USART3_UART_Init()` ou UART equivalente, `MX_TIMx_Init()`
- manter o loop principal de `serial_read()`, `start_timing()`, `model.run_inference()`, `stop_timing()` e `serial_write()`

### Serial

Arquivo atual:

- `cpp-project/tflite-test/model/serial_io.cpp`

Acoplamentos:

- inclui `peripherals.h`
- usa `LPUART_ReadBlocking(LP_FLEXCOMM4_PERIPHERAL, ...)`
- usa `LPUART_WriteBlocking(LP_FLEXCOMM4_PERIPHERAL, ...)`

No STM32 isso deve virar uma implementacao usando HAL ou LL, por exemplo:

```c
HAL_UART_Receive(&huart3, dst, n_bytes, HAL_MAX_DELAY);
HAL_UART_Transmit(&huart3, src, n_bytes, HAL_MAX_DELAY);
```

A UART exata precisa ser confirmada no CubeMX conforme a VCP do ST-LINK da `NUCLEO-H723ZG`. Em Nucleo-144, normalmente ha uma UART conectada ao Virtual COM Port do ST-LINK, mas a instancia/pinos devem ser confirmados no `UM2407` e no `.ioc` gerado.

### Timer

Arquivo atual:

- `cpp-project/tflite-test/model/timer.cpp`

Acoplamentos:

- inclui `peripherals.h`
- usa `CTIMER_StartTimer(CTIMER0_PERIPHERAL)`
- usa `CTIMER_StopTimer(CTIMER0_PERIPHERAL)`
- usa `CTIMER_GetTimerCountValue(CTIMER0_PERIPHERAL)`
- usa `CTIMER_Reset(CTIMER0_PERIPHERAL)`

No STM32 ha duas opcoes praticas:

1. Usar um timer de hardware, por exemplo `TIM2` ou `TIM5`, configurado para tick de 1 MHz. Essa opcao preserva a semantica atual de retornar microssegundos.
2. Usar o contador de ciclos `DWT->CYCCNT` do Cortex-M7 e converter ciclos para microssegundos usando `SystemCoreClock`. Essa opcao tende a ter menor overhead, mas exige habilitar DWT.

Recomendacao inicial:

- usar `DWT->CYCCNT` para profiling fino
- validar contra um timer HAL a 1 MHz em um teste simples
- documentar se o retorno de `stop_timing()` e microssegundos reais ou ciclos convertidos

### Modelo e TensorFlow Lite Micro

Arquivos principais:

- `cpp-project/tflite-test/model/model.cpp`
- `cpp-project/tflite-test/model/model.h`
- `cpp-project/tflite-test/model/model_data.h`
- `cpp-project/tflite-test/model/quantization.cpp`
- `cpp-project/tflite-test/model/input.h`
- `cpp-project/tflite-test/model/output.h`

Acoplamento encontrado:

- `model.cpp` inclui `fsl_common.h`
- `model.cpp` usa `__ALIGNED(16)` vindo do ambiente NXP/CMSIS

No STM32:

- remover `#include "fsl_common.h"`
- trocar `__ALIGNED(16)` por uma macro portavel, por exemplo:

```c
#if defined(__GNUC__)
#define BALAS_ALIGNED(x) __attribute__((aligned(x)))
#else
#define BALAS_ALIGNED(x)
#endif

static uint8_t tensor_arena[TENSOR_ARENA_SIZE] BALAS_ALIGNED(16);
```

Tambem e necessario recompilar ou substituir `tensorflow/libtensorflow-microlite.a`, porque a biblioteca atual foi ligada para Cortex-M33:

- `-mcpu=cortex-m33`
- `-mfpu=fpv5-sp-d16`
- `-mfloat-abi=hard`

Para STM32H723ZG, o alvo deve ser Cortex-M7, normalmente com flags do tipo:

- `-mcpu=cortex-m7`
- `-mthumb`
- `-mfpu=fpv5-d16` ou configuracao equivalente gerada pela IDE
- `-mfloat-abi=hard`

Nao reutilizar a `libtensorflow-microlite.a` atual sem validar a arquitetura do objeto.

### Build atual

Arquivo atual:

- `compile.sh`

Acoplamentos:

- chama `MCUXpresso IDE`
- usa `org.eclipse.cdt.managedbuilder.core.headlessbuild`
- assume workspace em `cpp-project`
- assume projeto `tflite-test`

No STM32:

- criar novo projeto STM32CubeIDE ou CMake separado
- ajustar `compile.sh` para escolher alvo por variavel, por exemplo `BALAS_TARGET=nxp|stm32`
- para STM32CubeIDE, usar o headless build do Eclipse/CDT da instalacao STM32CubeIDE
- para fluxo CMake, usar `cmake` + `ninja` + `arm-none-eabi-gcc`

Recomendacao:

- iniciar com STM32CubeIDE/CubeMX para gerar startup, linker, HAL e `.ioc`
- depois, se necessario, extrair para CMake para automacao mais limpa

### Flash/deploy atual

Arquivo atual:

- `deploy.sh`

Acoplamentos:

- usa `LinkServer`
- usa `crt_emu_cm_redlink`
- target default `MCXN947`
- preconnect script `LS_preconnect_MCXN9XX.scp`
- pacote de flash `MCXN947_support`

No STM32:

- substituir por `STM32_Programmer_CLI`
- gravar `.elf`, `.hex` ou `.bin` via ST-LINK/SWD
- exemplo de comando esperado:

```bash
STM32_Programmer_CLI -c port=SWD -w build/tflite-test.elf -v -rst
```

O caminho real do binario depende da instalacao do `STM32CubeProgrammer`.

### Linker, startup e memoria

Arquivos atuais NXP:

- `cpp-project/tflite-test/startup/startup_mcxn947_cm33_core0.cpp`
- `cpp-project/tflite-test/device/*`
- `cpp-project/tflite-test/Debug/tflite-test_Debug.ld`
- `cpp-project/tflite-test/Debug/tflite-test_Debug_memory.ld`

No STM32 esses arquivos devem ser substituidos por arquivos gerados para `STM32H723ZG`, por exemplo:

- `startup_stm32h723xx.s`
- `system_stm32h7xx.c`
- `STM32H723ZGTX_FLASH.ld` ou equivalente
- headers CMSIS device `stm32h723xx.h`
- HAL/LL drivers `stm32h7xx_hal_*.c`

Ponto de atencao:

- O STM32H723ZG tem memoria em bancos diferentes: ITCM, DTCM, AXI SRAM, AHB SRAM e backup SRAM.
- A `tensor_arena` deve ficar em RAM acessivel de forma previsivel.
- Em Cortex-M7 com cache, buffers usados por DMA precisam de cuidado. Para o protocolo atual com UART bloqueante sem DMA, a complexidade de cache e menor.

## Estrategia recomendada de port

### Fase 1 - Criar firmware STM32 minimo

Criar um projeto novo no STM32CubeIDE para:

- board `NUCLEO-H723ZG`, ou MCU `STM32H723ZGTx`
- UART VCP do ST-LINK em `115200 8N1`
- timer/profiling
- sem RTOS
- toolchain GNU Arm Embedded

Validar:

- build limpo
- flash via ST-LINK
- eco serial simples pelo `/dev/ttyACM*`

### Fase 2 - Levar a camada de aplicacao

Copiar ou compartilhar estes arquivos:

- `model/model.h`
- `model/model.cpp`, com ajuste de alinhamento
- `model/model_data.h`
- `model/quantization.*`
- `model/input.h`
- `model/output.h`
- `model/serial_io.h`
- `model/timer.h`

Criar implementacoes STM32 para:

- `serial_io.cpp`
- `timer.cpp`

Manter o protocolo binario igual:

- host envia `input.size` bytes
- placa executa inferencia
- placa devolve `sizeof(int)` bytes com tempo de inferencia

### Fase 3 - Resolver TensorFlow Lite Micro

Opcoes:

1. Recompilar TensorFlow Lite Micro para Cortex-M7 com os mesmos headers usados hoje.
2. Usar X-CUBE-AI/ST Edge AI para gerar codigo de inferencia para STM32.
3. Usar projeto/exemplo STM32Cube.AI/TFLM como base e adaptar o modelo.

Para menor impacto no host Python atual, a opcao 1 preserva melhor a API `MyModel`.

Para melhor encaixe no ecossistema STM32, a opcao 2 pode ser mais natural, mas muda mais a camada de inferencia.

### Fase 4 - Atualizar scripts

Atualizar:

- `compile.sh`
- `deploy.sh`
- `.balas.env.example`, se existir no ambiente
- documentacao de uso

Variaveis sugeridas:

```bash
BALAS_TARGET=stm32
STM32CUBEIDE_BIN=/opt/st/stm32cubeide/stm32cubeide
STM32_PROGRAMMER_CLI=/opt/st/stm32cubeprogrammer/bin/STM32_Programmer_CLI
STM32_PROJECT_DIR=/home/christian/github/balas/cpp-project/stm32-tflite-test
BUILD_CONFIG=Debug
BALAS_SERIAL_PORT=/dev/ttyACM0
```

### Fase 5 - Validacao

Validar em ordem:

1. `STM32_Programmer_CLI -l` detecta ST-LINK.
2. O firmware grava e reseta.
3. A porta serial VCP aparece como `/dev/ttyACM*`.
4. Um teste de eco serial funciona.
5. O firmware retorna um `int` de tempo para uma entrada sintetica.
6. `automator.py --skip-compile --skip-deploy` funciona com a placa STM32.
7. Os tempos medidos sao plausiveis e consistentes.

## Softwares necessarios

### Obrigatorios

#### STM32CubeIDE

Uso:

- criar/importar projeto STM32
- compilar firmware
- depurar via ST-LINK
- usar configurador integrado derivado do CubeMX

Download oficial:

- `https://www.st.com/en/development-tools/stm32cubeide.html`
- pagina alternativa usada pela ST: `https://www.st.com/content/st_com/en/stm32cubeide.html`

Observacao:

- Pode exigir login/aceite de licenca no site da ST.
- No Linux, conferir se o executavel foi instalado e se pode ser chamado em modo headless.

#### STM32CubeProgrammer

Uso:

- gravar firmware via ST-LINK/SWD
- validar deteccao do probe
- automatizar `deploy.sh` no futuro

Download oficial:

- `https://www.st.com/en/development-tools/stm32cubeprog.html`
- pagina de produto tambem aparece como `https://www.st.com/en/product/stm32cubeprog`

Comando esperado apos instalacao:

```bash
STM32_Programmer_CLI --version
STM32_Programmer_CLI -l
```

#### STM32CubeH7 MCU Package

Uso:

- HAL/LL drivers
- CMSIS device headers
- startup/linker/templates
- exemplos da `NUCLEO-H723ZG`

Como obter:

- pelo gerenciador de pacotes do STM32CubeIDE/STM32CubeMX
- ou pelo repositorio oficial:
  `https://github.com/STMicroelectronics/STM32CubeH7`

#### GNU Arm Embedded Toolchain

Uso:

- compilador `arm-none-eabi-gcc/g++`
- assembler, linker, objcopy, size

Como obter:

- normalmente ja vem integrado ao STM32CubeIDE
- alternativamente pelo pacote oficial Arm GNU Toolchain:
  `https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads`

Recomendacao:

- inicialmente usar o toolchain empacotado com o STM32CubeIDE para evitar incompatibilidade com o projeto gerado.

### Recomendados

#### STM32CubeMX

Uso:

- gerar `.ioc`
- configurar clock tree
- configurar UART VCP
- configurar timers
- configurar pinos

Download oficial:

- `https://www.st.com/en/development-tools/stm32cubemx.html`

Observacao:

- O STM32CubeIDE ja inclui funcionalidades do CubeMX, mas instalar o CubeMX separado pode ajudar na configuracao e revisao.

#### X-CUBE-AI / ST Edge AI Core

Uso:

- validar/gerar codigo de IA para STM32
- obter utilitarios `stedgeai` e `stm32tflm`
- estimar memoria e comparar com o fluxo atual

Download oficial:

- `https://www.st.com/en/embedded-software/x-cube-ai.html`
- tambem pode ser instalado pelo gerenciador de pacotes do STM32CubeMX

Observacao:

- O repositorio ja possui `assets/x-cube-ai-linux-v10.2.0.zip` e documentacao em `docs/x-cube-ai-linux-v10.2.0-instalacao-e-teste.md`.
- Para o port STM32, vale manter a versao registrada, mas conferir no site da ST se ha versao mais nova antes de iniciar uma entrega final.

#### ST-LINK udev rules / permissao USB

Uso:

- permitir acesso ao ST-LINK sem `sudo`

Onde obter:

- instaladores do STM32CubeIDE/STM32CubeProgrammer normalmente incluem ou orientam a instalacao
- em Linux, conferir tambem documentacao da ST incluida no pacote instalado

Validacao:

```bash
STM32_Programmer_CLI -l
lsusb
ls /dev/ttyACM*
```

#### Ferramentas basicas Linux

Pacotes recomendados no Ubuntu:

```bash
sudo apt update
sudo apt install -y \
  git curl wget unzip xz-utils tar \
  build-essential cmake ninja-build \
  libusb-1.0-0 udev \
  picocom minicom
```

Adicionar usuario ao grupo serial:

```bash
sudo usermod -aG dialout "$USER"
```

Depois fazer logout/login.

## Referencias oficiais

Placa `NUCLEO-H723ZG`:

- `https://www.st.com/en/evaluation-tools/nucleo-h723zg.html`
- user manual `UM2407`: `https://www.st.com/resource/en/user_manual/um2407-stm32h7-nucleo144-boards-mb1364-stmicroelectronics.pdf`

MCU `STM32H723ZG`:

- `https://www.st.com/en/microcontrollers-microprocessors/stm32h723zg.html`
- datasheet: `https://www.st.com/resource/en/datasheet/stm32h723zg.pdf`

STM32CubeIDE:

- `https://www.st.com/en/development-tools/stm32cubeide.html`

STM32CubeMX:

- `https://www.st.com/en/development-tools/stm32cubemx.html`

STM32CubeProgrammer:

- `https://www.st.com/en/development-tools/stm32cubeprog.html`

STM32CubeH7:

- `https://github.com/STMicroelectronics/STM32CubeH7`

X-CUBE-AI:

- `https://www.st.com/en/embedded-software/x-cube-ai.html`

## Status inicial do port

Inicio do port: 2026-05-18

Foi criado o alvo `cpp-project/stm32-tflite-test` como projeto CMake separado do
alvo NXP. O primeiro firmware e apenas de bring-up: configura clock, USART3
PD8/PD9 para a VCP do ST-LINK, emite uma mensagem de boot e ecoa bytes em
`115200 8N1`.

Validacoes feitas:

- `STM32_Programmer_CLI --version`: v2.22.0.
- `lsusb`: placa detectada como `0483:374e STMicroelectronics STLINK-V3`.
- VCP detectada em `/dev/ttyACM0`.
- `BALAS_TARGET=stm32 ./compile.sh`: build CMake/Ninja concluido.
- Artefatos gerados em `cpp-project/stm32-tflite-test/build/`.
- Apos instalacao/reload das regras udev do ST-LINK, `STM32_Programmer_CLI`
  detectou a placa como `NUCLEO-H723ZG`, ST-LINK `V3J6M2`, MCU
  `STM32H72x/STM32H73x`, Cortex-M7.
- `BALAS_TARGET=stm32 ./deploy.sh`: grava o ELF em `0x08000000`, verifica o
  download com sucesso e executa reset por software.

Correcao aplicada:

- O primeiro `deploy.sh` apontava para `build/stm32-tflite-echo`, um ELF sem
  extensao. O `STM32_Programmer_CLI -w` rejeita esse caminho porque exige uma
  extensao conhecida (`.elf`, `.hex`, `.bin`, etc.).
- O alvo CMake agora gera `stm32-tflite-test.elf`, e `deploy.sh` usa esse
  arquivo por padrao.
- `Core/Model/model.cpp` foi portado para o alvo STM32 sem alterar o
  `cpp-project/tflite-test/model/model.cpp` original da NXP. O port remove
  `fsl_common.h`, troca `__ALIGNED(16)` por uma macro local e mantem `size`
  como bytes para o protocolo serial, convertendo para quantidade de `float`
  apenas na etapa de quantizacao.
- O port de `MyModel` fica atras da opcao CMake `BALAS_STM32_ENABLE_MODEL`,
  desligada por padrao ate existir uma `libtensorflow-microlite.a` recompilada
  para Cortex-M7.
- `BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=ON ./compile.sh` compila o
  loop STM32 de inferencia em `Core/Src/main_model.cpp`.
- `Core/Platform/serial_io.cpp` implementa o protocolo serial com
  `HAL_UART_Receive`/`HAL_UART_Transmit` em `USART3`.
- `Core/Platform/timer.cpp` mede tempo com `DWT->CYCCNT` e converte ciclos para
  microssegundos via `SystemCoreClock`.
- Validacao com marcadores UART (`BALAS_STM32_MODEL_BOOT_MARKER=ON`) mostrou:
  o firmware inicializa UART, constroi `MyModel`, recebe os 12288 bytes do
  tensor float32 enviado pelo host, entra em `run_inference`, conclui a etapa de
  quantizacao e bloqueia dentro de `interpreter.Invoke()`.
- Hipotese tecnica atual: a `libtensorflow-microlite.a` usada no link ainda e a
  biblioteca do projeto NXP, compilada para Cortex-M33 (`ARMv8-M.mainline`).
  Para concluir o port funcional, e necessario recompilar TFLM para
  Cortex-M7/STM32H723ZG ou trocar para o fluxo X-CUBE-AI/ST Edge AI.
- O proximo passo escolhido foi trocar o backend STM32 para ST Edge AI. O
  `stedgeai generate` gerou a rede a partir de
  `testdata/sanity-model/model_quant.tflite`, e os arquivos versionados ficam em
  `cpp-project/stm32-tflite-test/Core/Generated/EdgeAI`.
- `BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=ON ./compile.sh` agora usa
  `BALAS_STM32_MODEL_BACKEND=stedgeai` por padrao, inclui os headers de
  `$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Middlewares/ST/AI/Inc`
  e linka `NetworkRuntime1020_CM7_GCC.a` para `STM32H7`/Cortex-M7.
- Validacao na placa com `BALAS_STM32_MODEL_BOOT_MARKER=ON`:
  boot `IIII...MMMM...`, tamanho de entrada `12288`, resposta serial
  `RQGDV + int32 + W`, com `sample_001.bin` retornando `23748 us`.
- O backend TFLM anterior continua selecionavel para diagnostico com
  `BALAS_STM32_MODEL_BACKEND=tflm`, mas nao e o caminho recomendado enquanto a
  biblioteca TFLM vier do projeto NXP.

## Checklist de alteracoes no repositorio

- [x] Criar novo projeto STM32, preferencialmente `cpp-project/stm32-tflite-test`.
- [ ] Gerar `.ioc` para `NUCLEO-H723ZG` ou `STM32H723ZGTx`.
- [x] Configurar clock do STM32H723ZG no CubeMX/CubeIDE.
- [x] Configurar UART conectada ao Virtual COM Port do ST-LINK em 115200 8N1.
- [ ] Configurar mecanismo de medicao de tempo.
- [x] Substituir startup/linker/device headers NXP por STM32.
- [x] Remover dependencia de `fsl_common.h` em `model.cpp`.
- [x] Trocar `__ALIGNED(16)` por macro portavel ou macro CMSIS compativel.
- [x] Recompilar `libtensorflow-microlite.a` para Cortex-M7 ou trocar por fluxo STM32/X-CUBE-AI.
- [x] Reimplementar `serial_io.cpp` para STM32 HAL/LL.
- [x] Reimplementar `timer.cpp` para STM32 HAL/LL ou DWT.
- [x] Atualizar `compile.sh` para selecionar alvo STM32.
- [x] Atualizar `deploy.sh` para usar `STM32_Programmer_CLI`.
- [ ] Validar `automator.py` com `BALAS_SERIAL_PORT=/dev/ttyACM*`.
- [x] Registrar resultado de sanity test inicial na NUCLEO-H723ZG.
- [ ] Registrar resultados de sanity test comparando FRDM-MCXN947 e NUCLEO-H723ZG.

## Riscos tecnicos

### Biblioteca TFLM precompilada

O maior risco e assumir que `cpp-project/tflite-test/tensorflow/libtensorflow-microlite.a` pode ser reutilizada. Ela deve ser tratada como especifica do alvo atual ate prova em contrario. O port deve recompilar essa biblioteca para Cortex-M7.

### Memoria e linker

O modelo atual tem `model_data.h` com cerca de 94 KB e `TENSOR_ARENA_SIZE` de 57344 bytes. Isso cabe no STM32H723ZG, mas a colocacao exata entre Flash, DTCM, AXI SRAM e outras regioes deve ser definida pelo linker STM32.

### Cache do Cortex-M7

O Cortex-M7 tem cache. Para o protocolo serial bloqueante sem DMA, o risco inicial e baixo. Se futuramente UART com DMA for usada, sera necessario tratar alinhamento, regioes nao cacheadas ou limpeza/invalidation de cache.

### Unidade de tempo

O firmware atual retorna um `int` chamado `inference_time_us`, mas o valor vem diretamente do contador `CTIMER0`. No port, garantir explicitamente que o timer gere microsegundos ou documentar a conversao.

### Equivalencia de desempenho

Comparar tempos entre FRDM-MCXN947 e NUCLEO-H723ZG exige cuidado:

- Cortex-M33 vs Cortex-M7
- clock diferente
- cache no M7
- biblioteca TFLM/CMSIS-NN diferente
- possivel uso de FPU/DSP diferente

## Decisao recomendada

Nao modificar diretamente o projeto MCUXpresso atual para tentar transforma-lo em STM32. Criar um novo alvo STM32 ao lado do alvo NXP e compartilhar a camada de aplicacao/modelo.

Estrutura sugerida:

```text
cpp-project/
  tflite-test/          # alvo NXP atual
  stm32-tflite-test/    # novo alvo STM32
```

Depois que o alvo STM32 estiver funcional, os arquivos comuns podem ser movidos para uma pasta compartilhada, por exemplo:

```text
embedded-common/
  model/
  platform/
```

Essa separacao reduz risco de quebrar a FRDM-MCXN947 enquanto o port STM32 ainda esta em andamento.
