# Comparativo sanity FRDM-MCXN947 vs NUCLEO-H723ZG

Este documento registra a primeira comparacao operacional entre o alvo original
NXP e o novo alvo STM32 usando o fixture versionado em
`testdata/sanity-model`.

## Escopo

- Modelo: `testdata/sanity-model/model_quant.tflite`
- Dataset serial: `testdata/sanity-model/profiling_dataset`
- Amostras: 10 arquivos `.bin` com entrada `float32`
- Entrada por amostra: 12288 bytes
- MACs calculados pelo pipeline: 12501632

## Resultados

| Placa | MCU | Backend embarcado | Arena/ativacoes | Media MCU us | Desvio us | Fonte |
| --- | --- | --- | ---: | ---: | ---: | --- |
| FRDM-MCXN947 | Cortex-M33 | TFLM/NXP | 57344 | 234708.2 | 7.807688518377254 | `testdata/sanity-model/manifest.json` |
| NUCLEO-H723ZG | Cortex-M7 | ST Edge AI | 43424 | 23388.5 | 5.200961449578338 | `python_scripts/experiments/run_benchmark_suite.py` em 2026-05-18 |
| NUCLEO-H723ZG | Cortex-M7 | TFLM/STM32 CMSIS-NN parcial, `-O2` | 57344 | 878015.8 | 60.61814909744441 | `artifacts/stm32_tflm_suite.csv` em 2026-06-15 |
| NUCLEO-H723ZG | Cortex-M7 | TFLM/STM32 CMSIS-NN parcial, `-O3` | 57344 | 705410.6 | 65.5914628591252 | `artifacts/stm32_tflm_suite.csv` em 2026-06-15 |
| NUCLEO-H723ZG | Cortex-M7 | TFLM/STM32 CMSIS-NN + scratch Conv2D na arena | 81920 | 42720.8 | 4.166533331199931 | `artifacts/stm32_tflm_suite.csv` em 2026-06-15 |

A medicao STM32 foi executada com:

```bash
.venv/bin/python python_scripts/experiments/run_benchmark_suite.py \
  testdata/sanity-model/stm32-edgeai-suite.json \
  artifacts/stm32_edgeai_suite.csv \
  --workstation-repeats 1
```

A tentativa TFLM/STM32 foi executada com a biblioteca TFLM gerada localmente em
`external/tflm-stm32/package/lib/libtensorflow-microlite.a`, compilada para
`cortex-m7+fp`, `fpv5-d16`, ABI hard-float e kernels `cmsis_nn`.

Build e flash do firmware TFLM/STM32 passaram:

```bash
BALAS_TARGET=stm32 \
BALAS_STM32_ENABLE_MODEL=ON \
BALAS_STM32_MODEL_BACKEND=tflm \
./compile.sh

BALAS_TARGET=stm32 ./deploy.sh
```

Uso de memoria observado no link TFLM/STM32:

```text
RAM: 59536 B / 128 KB = 45.42%
ROM: 226860 B / 1 MB = 21.64%
```

A retomada de 2026-06-15 fez o TFLM/STM32 retornar resultado pela serial e pela
suite CSV. A primeira tentativa automatizada falhou porque o profiling começava
imediatamente apos o reset do `STM32_Programmer_CLI`; depois de adicionar espera
pos-deploy para STM32, a suite completou com 10 amostras.

O resultado STM32 com ST Edge AI ficou aproximadamente 10.0 vezes mais rapido
que a medicao historica do fixture na FRDM-MCXN947. O resultado STM32 com
TFLM/CMSIS-NN parcial inicialmente ficou aproximadamente 3.7 vezes mais lento
que a FRDM. A primeira rodada efetiva de otimizacao recompilou a
`libtensorflow-microlite.a` com `CORE_OPTIMIZATION_LEVEL=-O3`,
`KERNEL_OPTIMIZATION_LEVEL=-O3` e
`THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL=-O3`, reduzindo a media para
`705410.6 us`. Isso e uma melhora de cerca de `19.7%`, mas ainda deixa o
STM32/TFLM cerca de `3.0x` mais lento que a FRDM/TFLM historica.

A rodada seguinte instrumentou `cmsis_nn/conv.cc` e confirmou que as 7
convolucoes 3x3 caiam no fallback de referencia porque o caminho
`arm_convolve_s8` recebia `ctx.buf == NULL`. Primeiro isso foi validado com um
scratch global de 8 KB; depois o scratch foi movido para a arena persistente do
TFLM, com arena total de `81920` bytes. As 9 convolucoes passaram a retornar
sucesso via CMSIS-NN e a media da suite caiu para `42720.8 us`. Com essa
correcao, o
STM32/TFLM fica aproximadamente `5.5x` mais rapido que a FRDM/TFLM historica
neste sanity model.

Os numeros intermediarios de `878015.8 us` e `705410.6 us` nao devem ser lidos
como limite de desempenho do Cortex-M7; eles refletiam o estado incompleto do
port TFLM/STM32 com fallbacks Conv2D. A linha de `42720.8 us` e a melhor
comparacao TFLM/STM32 atual. O scratch ja nao fica mais em buffer global
estatico; ele e alocado pela arena persistente do TFLM. Ainda resta investigar
por que o overlay scratch nativo (`RequestScratchBufferInArena` +
`GetScratchBuffer`) registra indices validos, mas retorna ponteiro `NULL` neste
port.

Importante: essa comparacao mede o caminho completo de execucao disponivel hoje
em cada placa, nao uma diferenca isolada entre microcontroladores. Aqui,
`fluxo` significa o conjunto de firmware, runtime de inferencia, codigo gerado,
toolchain, flags e configuracao de placa usados para executar o mesmo modelo.

No estado atual do repositorio, os resultados validos dos dois lados nao usam a
mesma implementacao de inferencia:

- Na FRDM-MCXN947, o firmware original usa TensorFlow Lite Micro no caminho
  NXP, linkando a biblioteca versionada em
  `cpp-project/tflite-test/tensorflow/libtensorflow-microlite.a`.
- Na NUCLEO-H723ZG, o port STM32 usa ST Edge AI, com codigo C gerado a partir
  do `.tflite` e runtime `NetworkRuntime1020_CM7_GCC.a`.
- A biblioteca TFLM/STM32 ja foi gerada para Cortex-M7 hard-float e o firmware
  experimental agora retorna resultado pela serial e pela suite CSV, mas ainda
  nao esta otimizado o suficiente para uma conclusao final de desempenho.

Portanto, o numero de aproximadamente 10.0x deve ser lido como:

```text
FRDM-MCXN947 + Cortex-M33 + firmware NXP + TFLM/NXP
versus
NUCLEO-H723ZG + Cortex-M7 + firmware STM32 + ST Edge AI
```

Ele nao prova, sozinho, que o Cortex-M7 e 10.0x mais rapido que o Cortex-M33,
nem isola frequencia de clock, cache, FPU/DSP, runtime de inferencia ou flags de
compilacao. Para uma comparacao de arquitetura mais controlada, ainda e
necessario reduzir os fallbacks CMSIS-NN no STM32/TFLM, revisar posicionamento
de memoria e manter o mesmo criterio de runtime/toolchain nos dois alvos, ou
entao usar um microbenchmark separado do runtime de inferencia.

## Estado do pipeline

O `run_benchmark_suite.py` agora aceita entradas com:

```json
{
  "target": "stm32",
  "model_backend": "stedgeai"
}
```

Tambem existe um backend experimental:

```json
{
  "target": "stm32",
  "model_backend": "tflm"
}
```

Esse modo ja retorna o tempo pela serial, mas ainda deve ser tratado como
diagnostico enquanto as otimizacoes de CMSIS-NN/runtime/memoria estiverem
pendentes. O backend `stedgeai` continua sendo o baseline STM32 funcional e
otimizado.

Nesse modo, ele:

- usa o tamanho de ativacoes gerado pelo ST Edge AI;
- nao executa a geracao de `model_data.h` do fluxo TFLM/NXP;
- exporta `BALAS_TARGET=stm32`;
- exporta `BALAS_STM32_ENABLE_MODEL=ON`;
- exporta `BALAS_STM32_MODEL_BACKEND=stedgeai`;
- compila, grava e mede a placa STM32 pelo mesmo runner experimental.
