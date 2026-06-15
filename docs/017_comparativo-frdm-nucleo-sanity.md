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
| NUCLEO-H723ZG | Cortex-M7 | TFLM/STM32 | 57344 | n/a | n/a | tentativa minima em 2026-05-18: build/link/flash OK, sem resposta serial |

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

O teste minimo de execucao, porem, ainda nao produziu uma medicao valida:

```text
sample_001.bin -> RuntimeError: Did not receive 4 bytes from device
```

Isso indica que o firmware TFLM/STM32 inicializa e foi gravado, mas ainda nao
conclui a inferencia ou nao retorna o `int32` de tempo pelo protocolo serial.
Portanto, ele ainda nao deve entrar na comparacao de desempenho como resultado
valido. Depois dessa tentativa, o firmware STM32 funcional com ST Edge AI foi
recompilado, regravado e validado novamente com `sample_001.bin`, retornando
`23404 us`.

O resultado STM32 ficou aproximadamente 10.0 vezes mais rapido que a medicao
historica do fixture na FRDM-MCXN947.

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
  experimental linka, mas a execucao ainda nao retornou resultado pela serial.

Portanto, o numero de aproximadamente 10.0x deve ser lido como:

```text
FRDM-MCXN947 + Cortex-M33 + firmware NXP + TFLM/NXP
versus
NUCLEO-H723ZG + Cortex-M7 + firmware STM32 + ST Edge AI
```

Ele nao prova, sozinho, que o Cortex-M7 e 10.0x mais rapido que o Cortex-M33,
nem isola frequencia de clock, cache, FPU/DSP, runtime de inferencia ou flags de
compilacao. Para uma comparacao de arquitetura mais controlada, seria
necessario rodar o mesmo runtime nos dois alvos, por exemplo TFLM recompilado
corretamente para Cortex-M7 no STM32 e validado ate completar a inferencia, ou
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

Esse modo deve ser tratado como diagnostico ate a inferencia TFLM/STM32 retornar
o tempo pela serial. O backend padrao e funcional continua sendo `stedgeai`.

Nesse modo, ele:

- usa o tamanho de ativacoes gerado pelo ST Edge AI;
- nao executa a geracao de `model_data.h` do fluxo TFLM/NXP;
- exporta `BALAS_TARGET=stm32`;
- exporta `BALAS_STM32_ENABLE_MODEL=ON`;
- exporta `BALAS_STM32_MODEL_BACKEND=stedgeai`;
- compila, grava e mede a placa STM32 pelo mesmo runner experimental.
