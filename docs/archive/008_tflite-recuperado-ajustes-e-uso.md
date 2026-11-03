# `.tflite` Recuperado: O Que Foi Preciso Fazer

## Objetivo

Este documento descreve especificamente o que foi necessario fazer com o modelo `.tflite` para que ele pudesse voltar a ser usado pelo fluxo do projeto.

O ponto central e este:

- o repositorio tinha o modelo embutido no firmware em C
- mas nao tinha o arquivo `.tflite` original versionado
- o `automator.py` precisa de um `.tflite` real como entrada

## O que existia no repositorio

O arquivo [`cpp-project/tflite-test/model/model_data.h`](/home/christian/github/balas/cpp-project/tflite-test/model/model_data.h:3) ja continha o binario do modelo convertido para array C.

Isso significa que o modelo nao estava perdido de fato. Ele estava apenas:

- serializado em hexadecimal dentro de um header C
- sem um `.tflite` pronto para ser entregue ao `automator.py`

## O que foi preciso fazer

## 1. Recuperar o binario `.tflite` a partir do header C

Foi criado o script:

- [`python_scripts/recover_tflite_from_header.py`](/home/christian/github/balas/python_scripts/recover_tflite_from_header.py:1)

Esse script:

- le os bytes `0x..` do `model_data.h`
- reconstroi o binario original
- valida o comprimento declarado no final do header
- grava um arquivo `.tflite`

Comando:

```bash
source .venv/bin/activate
python python_scripts/recover_tflite_from_header.py \
  cpp-project/tflite-test/model/model_data.h \
  testdata/sanity-model/model_quant.tflite
```

## 2. Validar se o modelo recuperado era um `.tflite` valido

O modelo recuperado foi validado com TensorFlow Lite.

O que foi confirmado:

- tamanho do arquivo: `94504` bytes
- tensor de entrada: shape `1x32x32x3`
- dtype de entrada do modelo: `int8`
- tensor de saida: shape `1x10`
- dtype de saida do modelo: `int8`

Isso bate com o caso de `Image Classification` descrito no PDF do TCC.

## 3. Entender o que precisava, e o que nao precisava, ser alterado no modelo

Importante:

- o conteudo interno do modelo nao foi alterado
- nao foi feita re-quantizacao
- nao foi feita conversao de operadores
- nao foi feita cirurgia no grafo do modelo

Ou seja:

- o `.tflite` foi recuperado
- validado
- e usado como ja estava

O que precisou de ajuste foi o entorno do fluxo, nao o binario interno do modelo.

## O que precisou ser ajustado ao redor do `.tflite`

## 1. Tensor arena

O modelo precisa de uma tensor arena coerente para o firmware.

No sanity test validado, foi usado:

- `arena_size = 57344`

Esse valor foi usado manualmente no `automator.py` para evitar dependencia obrigatoria do `stm32tflm` no caso de reaproveitar o firmware ja pronto.

## 2. Dataset compativel com a entrada esperada

O `automator.py` nao usa o `.tflite` sozinho. Ele tambem precisa de um dataset serializavel em `.bin`.

Para este modelo, o dataset precisava respeitar:

- shape efetivo `1x32x32x3`
- dados em `float32` no host
- serializacao crua em bytes

Foi criado um gerador generico para isso:

- [`python_scripts/generate_float32_dataset.py`](/home/christian/github/balas/python_scripts/generate_float32_dataset.py:1)

Comando usado para o fixture:

```bash
source .venv/bin/activate
python python_scripts/generate_float32_dataset.py \
  testdata/sanity-model/profiling_dataset \
  --shape 1,32,32,3 \
  --samples 10 \
  --mode uint8_as_float32 \
  --seed 42
```

## 3. Coerencia entre modelo no host e firmware na placa

Esse e o ponto mais importante de uso real:

- se o `.tflite` passado ao `automator.py` nao corresponder ao firmware ja gravado, o profiling pode falhar ou produzir resultados sem sentido

Por isso, quando usamos:

- `--skip-compile`
- `--skip-deploy`

precisamos garantir que o modelo usado no host seja exatamente o mesmo que originou o firmware da placa.

No sanity test atual, isso foi resolvido recuperando exatamente o modelo que ja estava embutido em `model_data.h`.

## 4. Estabilidade do header gerado

Ao regenerar `model_data.h` com `xxd -i`, o simbolo de comprimento no final do arquivo variava conforme o caminho do modelo usado.

Isso nao mudava o conteudo do `.tflite`, mas gerava instabilidade no header C.

Foi por isso que [`python_scripts/code_generator/generator.py`](/home/christian/github/balas/python_scripts/code_generator/generator.py:46) foi ajustado para normalizar o simbolo final para:

```c
unsigned int model_data_len = ...;
```

Esse ajuste nao altera o modelo. Ele apenas estabiliza o artefato C gerado a partir dele.

## Como usar esse `.tflite` com o `automator.py`

## Uso recomendado para sanity test

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

## Quando voce precisa recompilar e regravar

Se a placa ainda nao estiver com o firmware compativel, use o mesmo modelo sem os skips:

```bash
source .venv/bin/activate
python automator.py \
  testdata/sanity-model/model_quant.tflite \
  testdata/sanity-model/profiling_dataset \
  ./results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0
```

## Resumo objetivo

Do ponto de vista do `.tflite`, o que foi necessario foi:

- recuperar o arquivo que estava preso dentro de `model_data.h`
- validar que ele e um TFLite legitimo e compativel com o caso de Image Classification
- gerar um dataset compativel com sua entrada
- garantir coerencia entre o modelo do host e o firmware da placa
- estabilizar o header C gerado a partir dele

O que nao foi necessario foi:

- editar pesos
- editar camadas
- alterar quantizacao
- converter o modelo para outro formato
