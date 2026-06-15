# Retomada do TFLM/STM32 - diagnostico de execucao

Data da retomada: 2026-06-14

## Objetivo

Continuar o port STM32 usando TensorFlow Lite Micro, para que a
`NUCLEO-H723ZG` rode o mesmo tipo de runtime usado no alvo NXP
`FRDM-MCXN947`.

O objetivo tecnico nao e manter a medicao STM32 em ST Edge AI. O backend
`stedgeai` continua util como baseline funcional, mas a comparacao controlada
entre placas precisa do backend `tflm` no STM32.

## Contexto lido antes da retomada

Documentos consultados:

- `docs/016_port-stm32.md`
- `docs/017_comparativo-frdm-nucleo-sanity.md`
- `docs/018_tflm-stm32-build.md`
- `docs/002_projeto-visao-geral.md`
- `docs/010_sanity-test-image-classification-recuperado.md`
- `docs/012_relatorio-ajustes-automator.md`
- `docs/013_fase1-image-classification.md`

Pontos importantes recuperados do historico:

- O firmware NXP original usa TFLM e retorna apenas um `int32` com o tempo de
  inferencia pela serial.
- O host envia entradas `float32` cruas pela serial.
- O modelo de sanity tem entrada `1x32x32x3`, portanto cada amostra enviada
  pelo host tem `12288` bytes.
- O port STM32 com ST Edge AI ja havia sido validado em 2026-05-18 com media
  de `23388.5 us`.
- A primeira tentativa TFLM/STM32 antiga travava dentro de
  `interpreter.Invoke()` quando ainda havia suspeita de uso da biblioteca TFLM
  do projeto NXP.
- O trabalho pausado ja tinha uma biblioteca TFLM separada em
  `external/tflm-stm32/package/lib/libtensorflow-microlite.a`, gerada para
  Cortex-M7 hard-float com kernels `cmsis_nn`.

## Estado inicial encontrado

O repositorio ja tinha alteracoes nao commitadas:

- `.gitignore` ignorando `external/tflm-stm32/`
- `scripts/build_tflm_stm32.sh`
- `docs/018_tflm-stm32-build.md`
- `cpp-project/stm32-tflite-test/CMakeLists.txt` com backend `tflm` apontando
  para a biblioteca TFLM STM32 propria
- `docs/017_comparativo-frdm-nucleo-sanity.md` documentando a tentativa
  TFLM/STM32 sem resposta serial

Essas alteracoes foram tratadas como trabalho pausado e nao foram revertidas.

## Validacoes feitas

### Build do backend TFLM/STM32

Comando:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=ON \
BALAS_STM32_MODEL_BACKEND=tflm \
./compile.sh
```

Resultado:

- build CMake/Ninja concluido
- link contra `external/tflm-stm32/package/lib/libtensorflow-microlite.a`
- uso de memoria observado:

```text
RAM: 59536 B / 128 KB = 45.42%
ROM: 226860 B / 1 MB = 21.64%
```

Interpretacao:

- O problema atual nao e build nem link.
- A biblioteca STM32 propria esta sendo usada pelo CMake.

### Build TFLM/STM32 com marcadores UART

Comando:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=ON \
BALAS_STM32_MODEL_BACKEND=tflm \
BALAS_STM32_MODEL_BOOT_MARKER=ON \
./compile.sh
```

Resultado:

- build concluido
- o ELF contem `BALAS_STM32_MODEL_BOOT_MARKER=1`
- o disassembly mostra o `main` escrevendo marcador `'I'` pela serial antes de
  construir `MyModel`

Interpretacao:

- Se a aplicacao chegar ao `main` depois de inicializar a UART, deveria haver
  pelo menos bytes `'I'` na VCP antes de qualquer chamada TFLM.

### Flash via STM32_Programmer_CLI

O comando padrao:

```bash
BALAS_TARGET=stm32 ./deploy.sh
```

falhou em uma tentativa com:

```text
Error: Unable to get core ID
Error: ST-LINK error (DEV_TARGET_NOT_HALTED)
```

Validacao alternativa:

```bash
STM32_Programmer_CLI \
  -c port=SWD mode=UR \
  -w cpp-project/stm32-tflite-test/build/stm32-tflite-test.elf \
  -v \
  -rst
```

Resultado:

- ST-LINK detectado
- placa detectada como `NUCLEO-H723ZG`
- MCU detectado como `STM32H72x/STM32H73x`
- gravação e verificacao concluidas com sucesso

Interpretacao:

- Quando o firmware em flash impede conexao normal, `mode=UR` permite recuperar
  e gravar.
- O `deploy.sh` ainda deve ser ajustado para aceitar ou usar esse modo em
  cenarios de diagnostico.

### Teste serial com marcadores

Foi aberto `/dev/ttyACM0` em `115200 8N1` e enviada a amostra:

```text
testdata/sanity-model/profiling_dataset/sample_001.bin
```

Resultado observado:

```text
boot_total 0 b''
run_total 0 b''
```

O mesmo ocorreu tentando resetar via `STM32_Programmer_CLI` com a serial ja
aberta.

Interpretacao:

- Nao houve nem marcador `'I'`.
- Portanto, o sintoma observado nesta retomada ficou anterior ao
  `interpreter.Invoke()`.
- Isso e diferente do diagnostico anterior registrado em `docs/016`, onde o
  firmware chegava em `run_inference` e travava no `Invoke`.

### Comparacao com backend ST Edge AI

Tambem foi recompilado e gravado o backend funcional esperado:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=ON \
BALAS_STM32_MODEL_BACKEND=stedgeai \
BALAS_STM32_MODEL_BOOT_MARKER=ON \
./compile.sh
```

Depois disso, foi enviado `sample_001.bin` pela serial.

Resultado observado nesta retomada:

```text
total 0 b''
```

Interpretacao:

- Como o backend ST Edge AI tambem ficou sem resposta, o problema imediato nao
  pode ser atribuido somente ao TFLM.
- O diagnostico passou a focar em inicio do firmware, reset/debug, clock e UART.

### Comparacao com firmware minimo de eco

Foi compilado o firmware minimo sem modelo:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=OFF \
./compile.sh
```

Ele foi gravado com `mode=UR` e testado com leitura de banner e eco de um byte.

Resultado:

```text
banner b''
echo b''
```

Interpretacao:

- O silencio tambem ocorre sem TFLM e sem ST Edge AI.
- Isso descarta, para este sintoma especifico, falha exclusiva no runtime de
  inferencia.

### Estado do core via STM32_Programmer_CLI

Comando:

```bash
STM32_Programmer_CLI \
  -c port=SWD mode=UR \
  -halt \
  -score \
  -coreReg PC LR MSP PSP XPSR
```

Exemplo observado no firmware TFLM:

```text
PC  = 0x080100C0
LR  = 0xFFFFFFFF
MSP = 0x20020000
XPSR = 0x01000000
```

`addr2line` mostrou que esse PC corresponde ao `Reset_Handler`.

Exemplo observado no firmware minimo:

```text
PC  = 0x0800038C
LR  = 0xFFFFFFFF
MSP = 0x20020000
XPSR = 0x01000000
```

Tambem corresponde ao `Reset_Handler`.

Interpretacao:

- Ao conectar em `mode=UR`, o core fica parado no reset handler, o que e
  coerente com o modo "under reset".
- As tentativas com `-run`, `-rst -run`, `-g <Reset_Handler>` e escrita manual
  de `MSP`/`PC` nao produziram atividade serial.
- Ainda falta confirmar com um debugger mais preciso se o firmware sai do
  `Reset_Handler`, entra em `SystemClock_Config()` e onde para.

## Correcao em andamento: clock por HSI

Hipotese levantada:

- O firmware STM32 estava configurado para usar `HSE_BYPASS`.
- Se o clock externo/bypass vindo da placa/ST-LINK nao estiver presente ou nao
  estiver estavel no momento do teste, `SystemClock_Config()` pode travar antes
  da inicializacao efetiva da UART.
- Esse sintoma explicaria o silencio tanto do firmware TFLM quanto do ST Edge
  AI e do firmware minimo.

Alteracao aplicada para testar a hipotese:

- em `Core/Src/main.c`
- em `Core/Src/main_model.cpp`

Troca:

```text
PLL source: HSE bypass
PLLM=4
PLLN=260
```

por:

```text
PLL source: HSI
PLLM=4
PLLN=65
```

Com HSI de 64 MHz, isso preserva o PLL em aproximadamente 520 MHz:

```text
64 MHz / 4 * 65 = 1040 MHz VCO
PLLP = 1 -> SYSCLK 520 MHz
HCLK divisor 2 -> HCLK 260 MHz
```

Estado:

- a alteracao foi aplicada
- ainda precisa ser recompilada, gravada e validada na placa
- se a UART voltar a responder, atualizar este documento com o resultado e
  entao retomar a validacao TFLM/STM32

## Problemas abertos

1. O `deploy.sh` usa conexao SWD normal por padrao. Em uma situacao de firmware
   travando o debug, isso pode falhar com `DEV_TARGET_NOT_HALTED`. Deve ser
   considerado suporte a uma variavel como `STM32_CONNECT_MODE=UR`.

2. A serial `/dev/ttyACM0` esta visivel e listada pelo `STM32_Programmer_CLI`,
   mas nao recebeu bytes em nenhum dos tres firmwares testados nesta retomada.

3. O sintoma atual impede concluir se a biblioteca TFLM STM32 ja resolve o
   antigo travamento em `interpreter.Invoke()`.

4. A mudanca para HSI e diagnostica. Se for mantida, o `.ioc` e a documentacao
   do clock devem ser atualizados para nao divergir do firmware CMake.

## Proxima sequencia recomendada

1. Recompilar o firmware minimo com clock HSI:

```bash
BALAS_TARGET=stm32 BALAS_STM32_ENABLE_MODEL=OFF ./compile.sh
```

2. Gravar com modo under-reset:

```bash
STM32_Programmer_CLI \
  -c port=SWD mode=UR \
  -w cpp-project/stm32-tflite-test/build/stm32-tflite-test.elf \
  -v \
  -rst
```

3. Validar banner e eco serial em `/dev/ttyACM0`.

4. Se o eco funcionar, recompilar ST Edge AI com marcadores e confirmar retorno
   `RQGDV + int32 + W`.

5. Se ST Edge AI voltar a funcionar, recompilar TFLM/STM32 com marcadores e
   verificar se o fluxo chega ate:

```text
R Q G D V <int32> W
```

6. Somente depois disso rodar o benchmark sem marcadores:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=ON \
BALAS_STM32_MODEL_BACKEND=tflm \
./compile.sh
```

e então:

```bash
.venv/bin/python python_scripts/experiments/run_benchmark_suite.py \
  testdata/sanity-model/stm32-edgeai-suite.json \
  artifacts/stm32_tflm_suite.csv \
  --workstation-repeats 1
```

ajustando o manifesto para `model_backend=tflm` antes de usar o resultado como
comparacao valida.

## Retomada em 2026-06-14 - validacao funcional

Depois da limpeza da worktree em commits separados, a investigacao continuou a
partir do firmware minimo.

### UART e boot

O firmware minimo foi reduzido para nao configurar MPU, cache nem PLL antes do
teste de serial. Ele passou a emitir periodicamente:

```text
BALAS STM32H723ZG echo ready
```

Resultado:

- a VCP `/dev/ttyACM0` voltou a responder;
- a board foi validada como viva sem depender do instante exato do boot;
- o problema anterior de "sem nenhum byte serial" ficou isolado no bring-up de
  clock/cache/MPU, nao no ST-LINK nem no cabo.

### TFLM com CMSIS-NN

Com o firmware de modelo usando TFLM e `BALAS_STM32_MODEL_BOOT_MARKER=ON`, a
placa retornou:

```text
RQG
```

Interpretacao dos marcadores:

- `R`: recebeu os `12288` bytes da amostra;
- `Q`: entrou/concluiu a quantizacao `float32 -> int8`;
- `G`: entrou em `interpreter.Invoke()`;
- ausencia de `D`: nao saiu normalmente do `Invoke()`.

O core foi parado via hotplug e o PC apontou para:

```text
AbortImpl()
```

A pilha mostrou o abort vindo do caminho:

```text
tflite::(anonymous namespace)::EvalQuantizedPerChannel(...)
tflite::(anonymous namespace)::Eval(...)
tensorflow/lite/micro/kernels/cmsis_nn/conv.cc
```

Conclusao:

- a integracao TFLM ja inicializava e recebia dados corretamente;
- o problema especifico era o kernel Conv2D otimizado por CMSIS-NN abortando
  durante a inferencia.

### TFLM sem CMSIS-NN

Foi compilada uma biblioteca TFLM alternativa sem `OPTIMIZED_KERNEL_DIR`, usando
os kernels de referencia:

```bash
make -C external/tflm-stm32/src/tflite-micro \
  -j8 \
  -f tensorflow/lite/micro/tools/make/Makefile \
  TARGET=cortex_m_generic \
  TARGET_ARCH=cortex-m7+fp \
  FPU=fpv5-d16 \
  OPTIMIZED_KERNEL_DIR= \
  TARGET_TOOLCHAIN_ROOT=/home/christian/bin/ \
  microlite
```

Essa biblioteca foi copiada para:

```text
external/tflm-stm32/package/lib/libtensorflow-microlite.a
```

Com essa variante, o firmware com marcadores retornou:

```text
RQGDV + int32 + W
```

Tempo observado em `sample_001.bin`:

```text
26333142 us
```

Depois, o firmware sem marcadores foi regravado e o protocolo normal do profiler
tambem funcionou:

```text
25165567 us
```

Conclusao:

- o port TFLM/STM32 esta funcional com kernels de referencia;
- ainda nao e uma comparacao de desempenho justa, porque o firmware esta
  rodando sem a configuracao de clock/cache final;
- o proximo trabalho e reintroduzir clock/cache de forma controlada e depois
  investigar por que o caminho CMSIS-NN aborta no Conv2D.

### Ajuste no profiler

O timeout serial fixo de `10s` em `python_scripts/profiler/profiler.py` era
insuficiente para o TFLM de referencia no clock atual. Foi adicionado:

```text
BALAS_SERIAL_TIMEOUT_SEC
```

Default atual:

```text
60s
```

Isso permite que o runner consiga medir firmwares mais lentos sem alterar o
protocolo serial.
