# Fase 1: Estrutura para Reproduzir `Image Classification`

## Objetivo

Esta Fase 1 organiza o trabalho para reproduzir a familia `image_classification` do PDF de Bruno Silveira com o minimo de ajustes locais:

- obter a referencia oficial do MLCommons Tiny
- baixar o dataset oficial CIFAR-10
- gerar as 96 variantes descritas no PDF
- quantizar essas variantes para `.tflite` int8
- gerar o dataset de profiling em `.bin`
- montar um manifesto para reaproveitar o runner de benchmark ja existente

## Arquivos adicionados

Configuracao versionada:

- `configs/phase1_image_classification.json`

Scripts da Fase 1:

- `python_scripts/phase1/fetch_mlcommons_ic.py`
- `python_scripts/phase1/fetch_cifar10.py`
- `python_scripts/phase1/build_ic_variants.py`
- `python_scripts/phase1/quantize_ic_variants.py`
- `python_scripts/phase1/build_ic_profiling_dataset.py`
- `python_scripts/phase1/make_ic_suite_manifest.py`
- `python_scripts/phase1/common.py`
- `python_scripts/phase1/cifar10_utils.py`

Estrutura local esperada:

- `external/mlcommons-tiny/`
- `datasets/cifar-10-batches-py/`
- `artifacts/phase1_image_classification/generated/`

Esses diretorios gerados estao ignorados no Git.

## O que vem do PDF

A grade de variantes usada no `config` segue a familia descrita no PDF:

- `CHANNELS_1`: `16`, `24`
- `KERNEL_1`: `3`, `4`
- `CHANNELS_2`: `32`, `48`
- `KERNEL_2`: `3`, `4`
- `CHANNELS_3`: `64`, `96`, `128`
- `KERNEL_3`: `2`, `3`

Isso produz `96` combinacoes.

## O que vem das fontes oficiais

Fonte do baseline:

- repositorio oficial do MLCommons Tiny:
  `https://github.com/mlcommons/tiny`

Dataset:

- arquivo oficial do CIFAR-10:
  `https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz`

## Fluxo recomendado

Ative o virtualenv:

```bash
source .venv/bin/activate
```

Baixe a referencia do MLCommons:

```bash
python python_scripts/phase1/fetch_mlcommons_ic.py
```

Baixe o CIFAR-10 oficial:

```bash
python python_scripts/phase1/fetch_cifar10.py
```

Confirme quantas variantes serao geradas:

```bash
python python_scripts/phase1/build_ic_variants.py --dry-run
```

Gere um piloto com 2 variantes:

```bash
python python_scripts/phase1/build_ic_variants.py --limit 2
```

Quantize esse piloto:

```bash
python python_scripts/phase1/quantize_ic_variants.py --limit 2
```

Gere o dataset de profiling:

```bash
python python_scripts/phase1/build_ic_profiling_dataset.py
```

Monte um manifesto para o runner:

```bash
python python_scripts/phase1/make_ic_suite_manifest.py --limit 2
```

Rode o benchmark usando o runner ja existente:

```bash
python python_scripts/experiments/run_benchmark_suite.py \
  artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification.csv
```

Gere o relatorio:

```bash
python python_scripts/experiments/analyze_benchmark_suite.py \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification.csv \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification.md
```


## Lote validado nesta maquina

Depois do piloto inicial, foi executado um lote de `8` variantes na placa conectada.

Fluxo executado:

```bash
source .venv/bin/activate
python python_scripts/phase1/build_ic_variants.py --limit 8
python python_scripts/phase1/quantize_ic_variants.py --limit 8
python python_scripts/phase1/build_ic_profiling_dataset.py
python python_scripts/phase1/make_ic_suite_manifest.py --limit 8
python python_scripts/experiments/run_benchmark_suite.py   artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json   artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv
python python_scripts/experiments/analyze_benchmark_suite.py   artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv   artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.md
```

Artefatos produzidos:

- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.md`

Resultado consolidado do lote:

- `8/8` entradas com status `ok`
- correlacao `MACs vs MCU avg us = 0.9977`
- correlacao `Workstation avg us vs MCU avg us = 0.4086`
- correlacao `Arena estimada vs arena final = 1.0000`

Faixas observadas nesse lote:

- `MACs`: de `2187264` ate `4063232`
- `mcu_avg_us`: de `46549.8` ate `74051.0`
- `arena_final`: `24576` ou `25088`

Interpretacao pratica:

- mesmo com apenas `8` variantes, o proxy por `MACs` ja mostrou correlacao muito forte com a latencia real na MCU
- o tempo de inferencia no workstation variou menos e correlacionou pior com a MCU nesse subconjunto
- o estimador de arena foi consistente com a arena final usada nesse lote parcial

## Observacao importante sobre exatidao da reproducao

Esta Fase 1 resolve a organizacao operacional de:

- fonte de referencia
- dataset oficial
- geracao da grade de arquiteturas
- quantizacao
- dataset de profiling
- manifesto de coleta

Ela ainda nao prova igualdade numerica com o artigo em termos de acuracia final, pesos treinados ou sementes historicas do experimento original.

Em termos praticos:

- para latencia e profiling estrutural, esta base ja e utilizavel
- para reproduzir os numeros finais do artigo com mais fidelidade, o proximo passo e explicitar treino, seeds, checkpoints e politica de quantizacao final usada por Bruno
