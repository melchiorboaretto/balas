# Reproducao Reduzida do Experimento de Bruno Silveira

## Objetivo

Este fluxo adiciona ao repositorio uma forma pratica de repetir, em versao reduzida, a experiencia central do artigo:

- medir latencia real na MCU
- comparar com proxies de estimacao
- gerar um CSV experimental
- gerar um relatorio em Markdown com correlacoes

## Scripts adicionados

- `python_scripts/experiments/run_benchmark_suite.py`
- `python_scripts/experiments/analyze_benchmark_suite.py`
- `python_scripts/experiments/common.py`

## O que o runner coleta

Para cada entrada do manifesto, o runner registra:

- familia e nome do modelo
- caminho do modelo e do dataset
- arena estimada e arena final usada
- numero de tentativas
- MACs
- latencia media e desvio no workstation
- latencia media e desvio na MCU
- tempos de cada etapa do pipeline
- status e mensagem de erro

## Formato do manifesto

Exemplo versionado:

- `testdata/experiments/image-classification-reduced-suite.json`

Esse manifesto define:

- nome da suite
- defaults de serial e skip de build/deploy
- lista de entradas com modelo, dataset e arena

## Como rodar a coleta

```bash
source .venv/bin/activate
python python_scripts/experiments/run_benchmark_suite.py \
  testdata/experiments/image-classification-reduced-suite.json \
  ./results/reduced-suite.csv
```

Se voce quiser deixar o runner recompilar e regravar por padrao, remova os `skip_*` do manifesto ou rode um manifesto diferente.

## Como gerar o relatorio

```bash
source .venv/bin/activate
python python_scripts/experiments/analyze_benchmark_suite.py \
  ./results/reduced-suite.csv \
  ./results/reduced-suite-report.md
```

## O que o relatorio responde

O analisador calcula:

- correlacao de Pearson entre `MACs` e latencia real na MCU
- correlacao de Pearson entre latencia no workstation e latencia real na MCU
- correlacao entre arena estimada e arena final

## Limitacao importante

Com apenas uma linha no CSV, a correlacao fica como `n/a`.

Isso nao e erro. Correlacao so faz sentido com pelo menos dois pontos e variacao real entre eles.

Portanto:

- o manifesto versionado serve para validar o pipeline
- para repetir a analise do artigo, voce precisa adicionar varias variacoes de modelos da mesma familia

## Caminho recomendado

1. validar o pipeline com o manifesto reduzido
2. adicionar mais modelos `.tflite` e datasets ao manifesto
3. rerodar a coleta
4. rerodar a analise
5. comparar os `r` obtidos com os valores discutidos no PDF
