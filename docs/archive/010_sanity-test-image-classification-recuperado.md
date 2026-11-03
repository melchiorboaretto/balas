# Sanity Test Recuperado de `model_data.h`

## Objetivo

Este documento registra um caminho pratico e reproduzivel para usar o `automator.py` agora, mesmo sem o `.tflite` original ter sido versionado anteriormente.

O ponto de partida e o header [`cpp-project/tflite-test/model/model_data.h`](/home/christian/github/balas/cpp-project/tflite-test/model/model_data.h:3), que contem o modelo embutido no firmware.

## O que foi confirmado

Foi validado localmente em `2026-04-13` que:

- a placa aparece em `/dev/ttyACM0`
- o `LinkServer` detecta a `FRDM-MCXN947`
- o modelo do header pode ser recuperado como `.tflite`
- o modelo recuperado tem entrada `int8` com shape `1x32x32x3`
- o modelo recuperado tem saida `int8` com shape `1x10`
- o `automator.py` executa com sucesso contra a placa usando este modelo recuperado

Resultado observado no teste ponta a ponta:

- `arena_size`: `57344`
- `macs`: `12501632`
- inferencias observadas: `234722 us`, `234717 us`, `234726 us`

## Relacao com o PDF do TCC

Do PDF `../mestrado/TG2_BrunoSilveira/TG2_Bruno_Silveira.pdf`, os trechos relevantes indicam:

- o caso de `Image Classification` usa CIFAR-10
- as entradas de profiling sao salvas em `.bin` como `float32`
- o tamanho de entrada pre-processada e `12288` bytes
- o `stm32tflm` estimado para `Image Classification` foi `56832` bytes

O modelo recuperado bate com esse perfil:

- `1 x 32 x 32 x 3 x 4 bytes = 12288 bytes`
- o simbolo antigo do header apontava para `image_classification`
- o `results.csv` do repositorio registra `macs=12501632` e `arena_size=57344`, que batem com a validacao atual

## Arquivos adicionados para tornar isso reutilizavel

- [`python_scripts/recover_tflite_from_header.py`](/home/christian/github/balas/python_scripts/recover_tflite_from_header.py:1)
- [`python_scripts/generate_float32_dataset.py`](/home/christian/github/balas/python_scripts/generate_float32_dataset.py:1)
- [`testdata/sanity-model/manifest.json`](/home/christian/github/balas/testdata/sanity-model/manifest.json:1)

## Procedimento recomendado

Ative o ambiente virtual:

```bash
source .venv/bin/activate
```

Recupere o modelo a partir do header:

```bash
python python_scripts/recover_tflite_from_header.py \
  cpp-project/tflite-test/model/model_data.h \
  testdata/sanity-model/model_quant.tflite
```

Gere o dataset deterministico do sanity test:

```bash
python python_scripts/generate_float32_dataset.py \
  testdata/sanity-model/profiling_dataset \
  --model-path testdata/sanity-model/model_quant.tflite \
  --samples 10 \
  --mode uint8_as_float32 \
  --seed 42
```

Rode o sanity test reusando o firmware ja carregado na placa:

```bash
python automator.py \
  testdata/sanity-model/model_quant.tflite \
  testdata/sanity-model/profiling_dataset \
  ./results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0 \
  --skip-compile \
  --skip-deploy
```

Se quiser forcar recompilacao e reflash do firmware, rode o mesmo comando sem `--skip-compile` e sem `--skip-deploy`.

## Observacoes importantes

- o dataset versionado para sanity test e sintetico, nao o subconjunto real de CIFAR-10 usado no trabalho
- isso e suficiente para validar ambiente, build, deploy, comunicacao serial e geracao de relatorio
- para comparacoes de acuracia ou reproducao estrita do TCC, ainda sera necessario reconstruir o dataset real descrito no PDF
