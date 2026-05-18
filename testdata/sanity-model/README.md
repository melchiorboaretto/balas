# Sanity Model Fixture

## Objetivo

Este diretorio contem um fixture pequeno e controlado para sanity tests reproduziveis do projeto.

O fixture atual foi recuperado do proprio firmware ja versionado no repositorio e validado contra uma FRDM-MCXN947 conectada por USB serial.

## Estrutura

```text
testdata/sanity-model/
  README.md
  manifest.json
  model_quant.tflite
  stm32-edgeai-suite.json
  profiling_dataset/
    sample_001.bin
    ...
    sample_010.bin
```

## O que existe aqui

- `model_quant.tflite`
  Modelo quantizado recuperado de `cpp-project/tflite-test/model/model_data.h`.

- `profiling_dataset/`
  Dez tensores deterministicos em `float32`, no shape `1x32x32x3`, gerados com seed fixa.

- `manifest.json`
  Metadados do fixture e dos valores observados na validacao.

- `stm32-edgeai-suite.json`
  Manifesto minimo para rodar o mesmo fixture na `NUCLEO-H723ZG` com
  `BALAS_TARGET=stm32` e backend `stedgeai`.

## O que este fixture representa

Pelos metadados do modelo recuperado e pelo PDF do TCC, este fixture corresponde ao caso de `Image Classification`:

- entrada em host: `float32` com shape `1x32x32x3`
- entrada no modelo: `int8`
- saida do modelo: `int8` com shape `1x10`
- conjunto de referencia do trabalho: CIFAR-10 convertido para `float32`

Para evitar dependencia de download externo, o dataset versionado aqui e sintetico, mas respeita o mesmo shape e o mesmo contrato de serializacao em `float32`. Ele serve para sanity test de ambiente, protocolo serial, build e relatorio. Nao serve para avaliar acuracia.

## Como reconstruir localmente

Recuperar o `.tflite` diretamente do header:

```bash
source .venv/bin/activate
python python_scripts/recover_tflite_from_header.py \
  cpp-project/tflite-test/model/model_data.h \
  testdata/sanity-model/model_quant.tflite
```

Gerar novamente o dataset deterministico:

```bash
source .venv/bin/activate
python python_scripts/generate_float32_dataset.py \
  testdata/sanity-model/profiling_dataset \
  --model-path testdata/sanity-model/model_quant.tflite \
  --samples 10 \
  --mode uint8_as_float32 \
  --seed 42
```

## Fluxo validado

O fluxo abaixo foi validado com sucesso nesta maquina:

```bash
source .venv/bin/activate
python automator.py \
  testdata/sanity-model/model_quant.tflite \
  testdata/sanity-model/profiling_dataset \
  ./results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0 \
  --skip-compile \
  --skip-deploy
```

Se voce precisar recompilar ou regravar o firmware, remova os flags `--skip-compile` e `--skip-deploy`.
