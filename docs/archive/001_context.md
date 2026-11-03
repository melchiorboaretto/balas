# Contexto Atual

## Objetivo geral

Este repositorio implementa um fluxo para:

1. receber um modelo `.tflite` quantizado
2. gerar partes do codigo C++ embarcado para TensorFlow Lite Micro
3. compilar firmware para a placa NXP `FRDM-MCXN947` / MCU `MCXN947`
4. gravar o firmware na placa
5. enviar entradas por serial
6. medir o tempo de inferencia
7. registrar resultados em CSV

O host de desenvolvimento e Linux. O firmware roda na MCU.

## Estado atual do ambiente

Ambiente do usuario validado nesta sessao:

- sistema: Ubuntu 24.04
- usuario: `christian`
- repositorio: `/home/christian/github/balas`
- Python virtualenv: `.venv`
- IDE: `MCUXpresso IDE`
- flash/debug: `LinkServer`
- serial da placa: `/dev/ttyACM0`
- placa detectada: `FRDM-MCXN947`

Ferramentas e caminhos relevantes confirmados:

- `MCUXpresso IDE`: `/usr/local/mcuxpressoide/ide/mcuxpressoide`
- `LinkServer`: `/usr/local/LinkServer/LinkServer`
- `stm32tflm`: encontrado na instalacao local do X-CUBE-AI em
  `/home/christian/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm`

## O que foi lido e usado como referencia

Documentos do repositorio lidos ou atualizados para montar o contexto:

- `docs/projeto-visao-geral.md`
- `docs/frdm-mcxn947-ubuntu-24.04-primeiro-teste.md`
- `docs/deploy-firmware-linkserver.md`
- `docs/deploy-terminal-output.txt`
- `docs/sanity-test-expectativas-tcc-vs-repositorio.md`
- `docs/configuracao-local-e-validacao.md`
- `docs/x-cube-ai-linux-v10.2.0-instalacao-e-teste.md`

Documento externo usado para reconstruir o caso de teste:

- `../mestrado/TG2_BrunoSilveira/TG2_Bruno_Silveira.pdf`

## O que foi entendido do projeto

- O repositorio automatiza o fluxo host + firmware para benchmarking de modelos TFLite quantizados em MCU.
- O firmware principal esta em `cpp-project/tflite-test/`.
- O fluxo principal de uso e o `automator.py`.
- O `automator.py` espera sempre:
  - um modelo `.tflite`
  - um diretorio de dataset com arquivos `.bin` em `float32`
  - um arquivo CSV de saida
- O dataset e enviado pela serial para a placa, e a placa retorna tempos de inferencia em microssegundos.

## Problemas que existiam no inicio da sessao

No inicio desta sessao, o projeto ainda tinha problemas de portabilidade e reproducao:

- caminhos hardcoded para ambiente local em partes do fluxo
- dependencia do `stm32tflm` sem descoberta automatica
- dependencia pratica de `/dev/ttyACM0` hardcoded
- falta de fixture versionado para sanity test
- ausencia de um `.tflite` diretamente utilizavel pelo `automator.py`
- ausencia de dataset `.bin` versionado para teste fim a fim
- documentacao insuficiente sobre como usar o `automator.py`
- rastreamento indevido de artefatos gerados do MCUXpresso

Esses pontos foram tratados ao longo da sessao.

## Ajustes de codigo e configuracao realizados

## 1. Configuracao local externalizada

Foi criado um mecanismo de configuracao local em:

- `python_scripts/config.py`
- `.balas.env.example`

Esse mecanismo permite configurar, sem editar codigo:

- `BALAS_SERIAL_PORT`
- `BALAS_STM32TFLM_BIN`
- `MCUXPRESSO_IDE_BIN`
- `MCUX_WORKSPACE_DIR`
- `MCUX_IMPORT_PROJECT`
- `BUILD_CONFIG`
- `LINKSERVER_ROOT`
- `PROBE_SERIAL`

## 2. Build e deploy tornados portaveis

Os scripts abaixo foram ajustados para usar configuracao local e defaults razoaveis:

- `compile.sh`
- `deploy.sh`

O objetivo foi remover dependencia de caminhos fixos da maquina original.

## 3. Descoberta automatica do `stm32tflm`

O estimador de tensor arena em `python_scripts/arena_estimator/estimator.py` agora procura o `stm32tflm` em:

- `BALAS_STM32TFLM_BIN`
- `PATH`
- locais comuns da instalacao do X-CUBE-AI no `$HOME`

## 4. Porta serial configuravel

O `automator.py` e o profiler passaram a aceitar `--serial-device`, com default vindo de:

- `BALAS_SERIAL_PORT`
- ou `/dev/ttyACM0`

## 5. Parametros operacionais adicionados ao `automator.py`

O `automator.py` hoje aceita:

- `--serial-device`
- `--arena-size`
- `--skip-compile`
- `--skip-deploy`

Isso viabiliza tanto:

- o fluxo completo com build e flash
- quanto o fluxo rapido reaproveitando o firmware ja gravado

## 6. Estabilidade do header do modelo gerado

O gerador em `python_scripts/code_generator/generator.py` foi ajustado para normalizar o simbolo de comprimento do modelo em `model_data.h` para:

```c
unsigned int model_data_len = ...;
```

Antes disso, o nome do simbolo dependia do caminho local do arquivo `.tflite` usado na execucao.

## 7. Scripts genericos adicionados

Foram adicionados dois scripts utilitarios reutilizaveis:

- `python_scripts/recover_tflite_from_header.py`
- `python_scripts/generate_float32_dataset.py`

Eles servem para:

- recuperar um `.tflite` a partir de `model_data.h`
- gerar datasets `.bin` em `float32` de forma deterministica

## Ambiente Python e dependencias

Foi criada a `.venv` do projeto e instaladas as dependencias Python necessarias.

Validacoes realizadas na `.venv`:

- `numpy`: OK
- `pyserial`: OK
- `tensorflow`: OK

Foi gerado:

- `docs/requirements.txt`

Esse arquivo registra o `pip freeze` do virtualenv para replicacao.

Observacao:

- `docs/requirements.txt` cobre dependencias Python
- nao cobre instalacao de `MCUXpresso`, `LinkServer` e `stm32tflm`

## X-CUBE-AI / ST Edge AI

Foi validado o conteudo do zip Linux baixado em `./assets`:

- o zip principal contem o `.pack` do CubeMX e o zip `stedgeai-linux`
- o zip `stedgeai-linux` contem `stm32tflm` e `stedgeai`

Foi criada documentacao especifica para isso:

- `docs/x-cube-ai-linux-v10.2.0-instalacao-e-teste.md`

Essa documentacao tambem corrige um erro operacional observado:

- o `.pack` e o `.zip` extraidos nao devem ser executados como comandos
- eles precisam ser extraidos e usados como artefatos, nao executados diretamente

## Estado atual da placa, serial e probe

Validacoes de hardware feitas nesta sessao:

- `/dev/ttyACM0` apareceu corretamente
- `LinkServer probes` encontrou a FRDM-MCXN947
- foi possivel enviar dados pela serial e receber tempos de inferencia da placa

Saida validada de probe:

```text
#  Description                                    Serial         Device    Board         Capabilities
---  ---------------------------------------------  -------------  --------  ------------  ----------------
1  MCU-LINK FRDM-MCXN947 (r0E7) CMSIS-DAP V3.128  EB04LLNGMJHMR  MCXN947   FRDM-MCXN947  DEBUG, VCOM, SIO
```

Conclusao atual:

- a placa esta conectada corretamente
- a serial esta funcional
- o `LinkServer` esta funcional no ambiente atual

## Descoberta importante sobre modelo e dataset

No inicio da sessao, nao existia no repositorio:

- um `.tflite` pronto para ser passado ao `automator.py`
- um dataset `.bin` versionado para sanity test

Foi encontrado apenas:

- `cpp-project/tflite-test/model/model_data.h`

Esse arquivo continha o modelo embutido em C.

Foi entao feita a recuperacao do `.tflite` a partir desse header e a validacao do modelo com TensorFlow Lite.

O que foi confirmado no modelo recuperado:

- tamanho: `94504` bytes
- entrada: `int8`
- shape de entrada: `1x32x32x3`
- saida: `int8`
- shape de saida: `1x10`
- `ops_count`: `21`

Esses dados batem com o caso de `Image Classification` descrito no PDF do TCC, associado ao uso de CIFAR-10.

## Fixture de sanity test criado e validado

Foi criado e versionado um fixture em:

- `testdata/sanity-model/`

Conteudo atual do fixture:

- `testdata/sanity-model/model_quant.tflite`
- `testdata/sanity-model/profiling_dataset/sample_001.bin` ate `sample_010.bin`
- `testdata/sanity-model/manifest.json`
- `testdata/sanity-model/README.md`

Esse fixture representa um caso pequeno e reproduzivel de sanity test.

Observacoes:

## Estrutura nova para a Fase 1 do artigo

Foi iniciada a organizacao especifica para reproduzir a familia `image_classification` do PDF de Bruno Silveira.

Arquivos novos principais:

- `configs/phase1_image_classification.json`
- `python_scripts/phase1/fetch_mlcommons_ic.py`
- `python_scripts/phase1/fetch_cifar10.py`
- `python_scripts/phase1/build_ic_variants.py`
- `python_scripts/phase1/quantize_ic_variants.py`
- `python_scripts/phase1/build_ic_profiling_dataset.py`
- `python_scripts/phase1/make_ic_suite_manifest.py`
- `docs/fase1-image-classification.md`

Estrutura local criada para esse fluxo:

- `external/`
- `datasets/`
- `artifacts/phase1_image_classification/`

Decisoes de portabilidade:

- fontes externas e datasets ficam fora do versionamento
- artefatos gerados da Fase 1 ficam em `artifacts/phase1_image_classification/generated/`
- a grade de 96 variantes fica congelada em `configs/phase1_image_classification.json`
- qualquer ajuste local deve ocorrer por argumentos dos scripts ou pela edicao pontual do `config`, sem hardcode de caminhos pessoais no codigo

Scripts hoje disponiveis na Fase 1:

- `python_scripts/phase1/fetch_mlcommons_ic.py`
- `python_scripts/phase1/fetch_cifar10.py`
- `python_scripts/phase1/build_ic_variants.py`
- `python_scripts/phase1/quantize_ic_variants.py`
- `python_scripts/phase1/build_ic_profiling_dataset.py`
- `python_scripts/phase1/make_ic_suite_manifest.py`
- `python_scripts/phase1/common.py`
- `python_scripts/phase1/cifar10_utils.py`

## Fase 1 ja executada nesta maquina

Nao ficou apenas na organizacao. O fluxo piloto da Fase 1 foi efetivamente executado no ambiente atual.

O que ja foi feito:

- clone raso da referencia oficial `MLCommons Tiny` em `external/mlcommons-tiny/`
- download e extracao do `CIFAR-10` oficial em `datasets/cifar-10-batches-py/`
- geracao de 1 variante piloto da grade de `image_classification`
- quantizacao da variante piloto para `.tflite` `int8`
- geracao de dataset de profiling com 10 amostras, uma por classe
- geracao de manifesto para o runner experimental existente
- execucao real do runner com compilacao, deploy e profiling na placa

Modelo piloto validado:

- `ic_c1-16_k1-3_c2-32_k2-3_c3-64_k3-2`

Arquivos gerados no piloto:

- `artifacts/phase1_image_classification/generated/float_models/`
- `artifacts/phase1_image_classification/generated/quantized_models/`
- `artifacts/phase1_image_classification/generated/profiling_dataset/default/`
- `artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json`

Correcao importante feita durante a validacao:

- `python_scripts/phase1/make_ic_suite_manifest.py` foi ajustado para gravar caminhos relativos ao diretorio do manifesto, e nao ao diretorio raiz do repositorio

Melhorias de robustez aplicadas:

- os scripts da Fase 1 nao carregam mais TensorFlow desnecessariamente em `--help`
- o loader do `CIFAR-10` em `python_scripts/phase1/cifar10_utils.py` foi ajustado para evitar warning desnecessario durante a leitura do dataset oficial

- o modelo veio da recuperacao de `model_data.h`
- o dataset versionado e sintetico e deterministico
- ele serve para sanity test de ambiente, serial, build e relatorio
- ele nao substitui um dataset real para avaliacao de acuracia

## Validacao ponta a ponta do `automator.py`

O `automator.py` foi validado com sucesso usando o fixture versionado e a placa conectada.

Comando validado:

```bash
source .venv/bin/activate
python automator.py \
  testdata/sanity-model/model_quant.tflite \
  testdata/sanity-model/profiling_dataset \
  /tmp/balas-sanity-results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0 \
  --skip-compile \
  --skip-deploy
```

Resultado observado:

- `arena_size = 57344`
- `macs = 12501632`
- `avg_inference_us = 234708.2`
- `std_inference_us = 7.807688518377254`

Tambem foi validado um envio serial direto de um tensor aleatorio compativel com o modelo, com resposta da placa.

Conclusao:

- o fluxo minimo do `automator.py` esta funcional nesta maquina
- a placa responde pela serial
- o fixture atual e suficiente para sanity test reproduzivel

## Validacao do piloto da Fase 1 na placa

Foi validado um piloto real da Fase 1 usando o runner:

```bash
source .venv/bin/activate
python python_scripts/experiments/run_benchmark_suite.py \
  artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json \
  /tmp/phase1-image-classification-pilot.csv
```

O primeiro disparo falhou por causa do bug de caminho no manifesto. Depois da correcao, o piloto passou com sucesso.

Resultado valido observado:

- `family = image_classification`
- `name = ic_c1-16_k1-3_c2-32_k2-3_c3-64_k3-2`
- `arena_final = 24576`
- `macs = 2187264`
- `workstation_avg_us = 52.9821`
- `mcu_avg_us = 46547.7`
- `sample_count = 10`
- `attempts = 1`

Artefatos temporarios usados para validacao:

- CSV bruto: `/tmp/phase1-image-classification-pilot.csv`
- CSV limpo com apenas a execucao valida: `/tmp/phase1-image-classification-pilot-clean.csv`
- relatorio: `/tmp/phase1-image-classification-pilot-clean.md`

Observacao importante:

- durante o teste, o gerador substituiu temporariamente os arquivos de modelo em `cpp-project/tflite-test/model/`
- ao final, esses arquivos foram restaurados para o fixture versionado de sanity test
- portanto o estado rastreado do firmware voltou a apontar para `testdata/sanity-model/model_quant.tflite`


## Escalonamento da Fase 1 para 8 variantes

Depois do piloto unitario, a Fase 1 foi escalada para um lote real com `8` variantes da familia `image_classification`.

Fluxo executado:

- `python python_scripts/phase1/build_ic_variants.py --limit 8`
- `python python_scripts/phase1/quantize_ic_variants.py --limit 8`
- `python python_scripts/phase1/build_ic_profiling_dataset.py`
- `python python_scripts/phase1/make_ic_suite_manifest.py --limit 8`
- `python python_scripts/experiments/run_benchmark_suite.py artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv`
- `python python_scripts/experiments/analyze_benchmark_suite.py artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.md`

Artefatos produzidos nesse lote:

- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.md`

Status final do lote:

- `8/8` entradas com `status = ok`
- nenhuma falha registrada

Metricas resumidas do relatorio:

- `MACs vs MCU avg us = 0.9977`
- `Workstation avg us vs MCU avg us = 0.4086`
- `Arena estimada vs arena final = 1.0000`

Faixas observadas:

- `MACs`: `2187264` ate `4063232`
- `mcu_avg_us`: `46549.8` ate `74051.0`
- `arena_final`: `24576` ou `25088`

Leitura pratica desse resultado:

- para esse subconjunto de `8` modelos, `MACs` ja se mostrou um proxy muito forte para a latencia real na MCU
- o tempo no workstation nao acompanhou a MCU tao bem quanto `MACs`
- o estimador de arena foi coerente com a arena final usada durante a coleta

Ao final desse lote, os arquivos de firmware do `cpp-project` foram restaurados novamente para o fixture versionado de sanity test.

## Documentacao produzida ou atualizada hoje

Documentos existentes ou produzidos nesta sessao que agora fazem parte do contexto:

- `docs/configuracao-local-e-validacao.md`
- `docs/x-cube-ai-linux-v10.2.0-instalacao-e-teste.md`
- `docs/sanity-test-image-classification-recuperado.md`
- `docs/relatorio-ajustes-automator.md`
- `docs/tflite-recuperado-ajustes-e-uso.md`
- `docs/requirements.txt`
- `docs/fase1-image-classification.md`

Esses arquivos cobrem:

- instalacao e validacao do ambiente
- X-CUBE-AI / ST Edge AI no Linux
- sanity test recuperado de `model_data.h`
- relatorio dos ajustes para o `automator.py`
- explicacao especifica sobre o `.tflite` recuperado
- snapshot das dependencias Python
- organizacao da Fase 1 para reproducao de `image_classification`

## Higiene de repositorio realizada

Foram removidos do versionamento artefatos gerados do workspace do MCUXpresso e adicionadas regras de ignore para:

- `.venv`
- `__pycache__`
- `*.pyc`
- `cpp-project/.metadata/`
- `cpp-project/.mcuxpressoide_packages_support/`
- `cpp-project/tflite-test/.settings/`
- `cpp-project/tflite-test/Debug/`
- `cpp-project/tflite-test/Release/`

Isso evita poluir o repositorio com build local e metadados de IDE.

## Commits relevantes criados hoje

Commits produzidos nesta sessao:

- `b0f3b5d` `Make host tooling configurable and document setup`
- `fb2723b` `Stop tracking generated MCUXpresso artifacts`
- `92c0fa3` `Add sanity test fixture structure`
- `a21b97a` `Add reusable tooling for recovered TFLite sanity fixtures`
- `e556d05` `Add recovered image-classification sanity fixture`
- `4c9ec14` `Document automator setup and recovered TFLite usage`

## Estado atual do git

No ponto atual de parada, o repositorio esta limpo do ponto de vista dos arquivos rastreados.

Estado observado:

- nenhum arquivo rastreado pendente de commit
- `assets/` continua fora do versionamento
- os artefatos gerados em `artifacts/phase1_image_classification/generated/` continuam locais e ignorados

Importante:

- o commit da estrutura reutilizavel da Fase 1 ja foi criado
- o firmware em `cpp-project/tflite-test/model/` foi restaurado para o fixture base de sanity ao fim das medicoes
- o estado atual do workspace e adequado para retomar novos benchmarks sem carregar a ultima variante executada

## Como retomar rapidamente em uma proxima sessao

Se a proxima sessao precisar apenas validar o ambiente e usar o `automator.py`, o caminho mais curto e:

1. confirmar que a placa aparece em `/dev/ttyACM0`
2. ativar a `.venv`
3. usar o fixture em `testdata/sanity-model`
4. rodar o comando validado do sanity test

Comandos uteis:

```bash
ls -l /dev/ttyACM*
/usr/local/LinkServer/LinkServer probes
source .venv/bin/activate
python automator.py \
  testdata/sanity-model/model_quant.tflite \
  testdata/sanity-model/profiling_dataset \
  /tmp/balas-sanity-results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0 \
  --skip-compile \
  --skip-deploy
```

Se a proxima sessao for continuar a reproducao do artigo pela Fase 1, o caminho mais curto e:

```bash
source .venv/bin/activate
python python_scripts/phase1/build_ic_variants.py --dry-run
python python_scripts/phase1/build_ic_variants.py --limit 32
python python_scripts/phase1/quantize_ic_variants.py --limit 32
python python_scripts/phase1/build_ic_profiling_dataset.py
python python_scripts/phase1/make_ic_suite_manifest.py --limit 32
python python_scripts/experiments/run_benchmark_suite.py \
  artifacts/phase1_image_classification/generated/manifests/image-classification-suite.json \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification-32.csv
python python_scripts/experiments/analyze_benchmark_suite.py \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification-32.csv \
  artifacts/phase1_image_classification/generated/results/phase1-image-classification-32.md
```

## Atualizacao da Fase 1

Desde o estado anterior deste contexto, a Fase 1 de `image_classification` avancou para um fluxo reutilizavel e ja validado em lotes maiores.

Commit novo relevante:

- `ecdc22f` `Add phase 1 image-classification reproduction workflow`

Esse commit consolidou:

- `configs/phase1_image_classification.json`
- `python_scripts/phase1/` com scripts para fetch, geracao, quantizacao, dataset de profiling e manifesto
- `docs/fase1-image-classification.md`
- `external/README.md`
- `datasets/README.md`
- `artifacts/README.md`
- `artifacts/phase1_image_classification/README.md`

Execucoes ja realizadas localmente:

- lote de `8` variantes concluido e analisado
- lote de `16` variantes concluido com `16/16` sucessos
- lote de `32` variantes concluido com `32/32` sucessos

Arquivos de resultado hoje:

- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.csv`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-8.md`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-16.csv`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-32.csv`
- `artifacts/phase1_image_classification/generated/results/phase1-image-classification-32.md`

Observacao critica sobre o lote de `32`:

- a execucao fechou com `32/32` sucessos operacionais
- o CSV de `32` contem dois outliers de latencia da MCU claramente invalidos para analise estatistica
- isso distorceu as correlacoes do relatorio de `32`

Outliers detectados:

- `ic_c1-16_k1-3_c2-48_k2-4_c3-128_k3-2` com `mcu_avg_us = 163803498.6`
- `ic_c1-16_k1-4_c2-32_k2-3_c3-96_k3-2` com `mcu_avg_us = -161010189.8`

Interpretacao pratica:

- o pipeline de compilacao, deploy e coleta serial esta funcional
- o conjunto de `32` modelos foi de fato executado na placa
- antes de usar o lote de `32` para conclusoes de correlacao, o correto e rerodar apenas essas `2` variantes e substituir as linhas invalidas

## Resumo curto para retomada

O contexto essencial para a proxima sessao e:

- o fluxo host + serial + CSV esta funcional
- o `automator.py` foi tornado configuravel e documentado
- o `stm32tflm` local foi encontrado e validado
- existe um `.tflite` recuperado e versionado para sanity test
- existe um dataset `.bin` versionado e deterministico
- a FRDM-MCXN947 foi detectada e respondeu ao profiling
- a Fase 1 de `image_classification` ja foi estruturada e executada em piloto
- o piloto da Fase 1 compilou, gravou e mediu na placa com sucesso
- um lote de `8` variantes ja foi medido com `8/8` sucessos
- um lote de `16` variantes ja foi medido com `16/16` sucessos
- um lote de `32` variantes ja foi medido com `32/32` sucessos operacionais
- o relatorio de `32` esta contaminado por `2` outliers de `mcu_avg_us` e precisa de rerun pontual
- o proximo passo natural e rerodar essas `2` variantes, corrigir o CSV e so entao recalcular as correlacoes
- os commits principais desta sessao ja foram criados, incluindo `ecdc22f`
- `assets/` continua fora do versionamento
