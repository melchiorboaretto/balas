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

A medicao STM32 foi executada com:

```bash
.venv/bin/python python_scripts/experiments/run_benchmark_suite.py \
  testdata/sanity-model/stm32-edgeai-suite.json \
  artifacts/stm32_edgeai_suite.csv \
  --workstation-repeats 1
```

O resultado STM32 ficou aproximadamente 10.0 vezes mais rapido que a medicao
historica do fixture na FRDM-MCXN947. Essa comparacao mede o comportamento
pratico do firmware atual, nao isola arquitetura de CPU, frequencia, runtime de
inferencia ou flags de compilacao. O backend tambem mudou: FRDM usa o fluxo
TFLM/NXP original; NUCLEO usa codigo gerado pelo ST Edge AI e runtime
`NetworkRuntime1020_CM7_GCC.a`.

## Estado do pipeline

O `run_benchmark_suite.py` agora aceita entradas com:

```json
{
  "target": "stm32",
  "model_backend": "stedgeai"
}
```

Nesse modo, ele:

- usa o tamanho de ativacoes gerado pelo ST Edge AI;
- nao executa a geracao de `model_data.h` do fluxo TFLM/NXP;
- exporta `BALAS_TARGET=stm32`;
- exporta `BALAS_STM32_ENABLE_MODEL=ON`;
- exporta `BALAS_STM32_MODEL_BACKEND=stedgeai`;
- compila, grava e mede a placa STM32 pelo mesmo runner experimental.

