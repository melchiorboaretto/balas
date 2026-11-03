# Relatorio de Ajustes Para o `automator.py`

## Objetivo

Este documento registra o que precisou ser ajustado no repositorio para que o `automator.py` pudesse ser usado de forma pratica, reproduzivel e com o minimo possivel de configuracao local.

O foco aqui e:

- explicar o que estava impedindo o uso direto do fluxo
- registrar os ajustes feitos no codigo e na configuracao
- documentar como usar o `automator.py` corretamente

## Problemas encontrados antes dos ajustes

Antes dos ajustes, o fluxo nao era portavel nem imediatamente executavel em outra maquina.

Os principais problemas eram:

- caminhos hardcoded para ambiente local em partes do fluxo
- dependencia do `stm32tflm` sem descoberta automatica do binario
- dependencia da porta serial fixa
- ausencia, no repositorio, de um `.tflite` utilizavel diretamente pelo `automator.py`
- ausencia de um dataset `.bin` versionado para sanity test
- documentacao insuficiente sobre os parametros obrigatorios do `automator.py`

Na pratica, isso significava que nao bastava rodar `python3 automator.py`. Era necessario conhecer:

- qual modelo `.tflite` usar
- qual dataset `.bin` usar
- qual porta serial usar
- como estimar ou informar a tensor arena
- quando compilar e quando reaproveitar firmware ja gravado

## Ajustes feitos para o fluxo funcionar

## 1. Configuracao local externalizada

Foi criado um mecanismo de configuracao local via [`python_scripts/config.py`](/home/christian/github/balas/python_scripts/config.py:1) e [`.balas.env.example`](/home/christian/github/balas/.balas.env.example:1).

Com isso, o repositorio passou a aceitar configuracao local sem hardcode no codigo:

- `BALAS_SERIAL_PORT`
- `BALAS_STM32TFLM_BIN`
- `MCUXPRESSO_IDE_BIN`
- `MCUX_WORKSPACE_DIR`
- `MCUX_IMPORT_PROJECT`
- `BUILD_CONFIG`
- `LINKSERVER_ROOT`
- `PROBE_SERIAL`

Isso reduz os ajustes por maquina a um arquivo de configuracao local pequeno e claro.

## 2. `compile.sh` e `deploy.sh` tornados portaveis

Os scripts de build e deploy foram ajustados para:

- usar `.balas.env` quando presente
- usar defaults razoaveis para Linux
- falhar com mensagem clara quando faltar ferramenta local

Arquivos relevantes:

- [`compile.sh`](/home/christian/github/balas/compile.sh:1)
- [`deploy.sh`](/home/christian/github/balas/deploy.sh:1)

## 3. Descoberta automatica do `stm32tflm`

O estimador de tensor arena passou a procurar o `stm32tflm` em tres lugares:

- `BALAS_STM32TFLM_BIN`
- `PATH`
- caminhos tipicos de instalacao do X-CUBE-AI no `$HOME`

Arquivo relevante:

- [`python_scripts/arena_estimator/estimator.py`](/home/christian/github/balas/python_scripts/arena_estimator/estimator.py:1)

Isso elimina a necessidade de editar codigo so para apontar para o executavel da ST.

## 4. Porta serial configuravel

O `automator.py` e o profiler passaram a aceitar `--serial-device`, com default vindo de `BALAS_SERIAL_PORT` ou `/dev/ttyACM0`.

Arquivos relevantes:

- [`automator.py`](/home/christian/github/balas/automator.py:17)
- [`python_scripts/profiler/profiler.py`](/home/christian/github/balas/python_scripts/profiler/profiler.py:100)

## 5. Parametros operacionais adicionados ao `automator.py`

O `automator.py` hoje aceita opcoes que tornam o fluxo bem mais controlavel:

- `--serial-device`
- `--arena-size`
- `--skip-compile`
- `--skip-deploy`

Isso e importante porque, em muitos cenarios, o firmware correto ja esta compilado e gravado na placa. Nesses casos, recompilar e regravar so aumenta tempo e risco de introduzir diferencas desnecessarias.

## 6. Correcao do gerador de `model_data.h`

O gerador de binario C do modelo foi ajustado para usar um nome fixo para o simbolo de comprimento:

- antes, o nome do simbolo `_len` dependia do caminho do arquivo de modelo usado na execucao
- agora, ele e normalizado para `model_data_len`

Arquivo relevante:

- [`python_scripts/code_generator/generator.py`](/home/christian/github/balas/python_scripts/code_generator/generator.py:46)

Sem isso, usar um `.tflite` temporario podia poluir o header gerado com um simbolo instavel, dependente do caminho local.

## 7. Criacao de um sanity fixture versionado

Como o repositorio nao tinha um `.tflite` utilizavel nem dataset `.bin` prontos, foi criado um fixture versionado em:

- [`testdata/sanity-model`](/home/christian/github/balas/testdata/sanity-model)

Esse fixture inclui:

- `model_quant.tflite`
- `profiling_dataset/` com 10 arquivos `.bin`
- `manifest.json`

O fixture permite validar:

- ambiente Python
- parsing do modelo
- protocolo serial
- leitura de tempos de inferencia
- geracao de CSV

## Como o `automator.py` funciona

O `automator.py` executa este fluxo:

1. recebe um modelo `.tflite`
2. determina a tensor arena, por estimativa ou valor manual
3. calcula o numero de MACs
4. gera os arquivos C++ do firmware para esse modelo
5. opcionalmente compila o projeto
6. opcionalmente grava o firmware na placa
7. envia os tensores `.bin` pela serial
8. recebe os tempos de inferencia
9. escreve o relatorio CSV

Importante:

- mesmo com `--skip-compile` e `--skip-deploy`, o `automator.py` ainda executa a etapa de geracao de codigo C++
- portanto, ele ainda reescreve arquivos gerados em `cpp-project/tflite-test/model/`

## Como usar o `automator.py`

## Sintaxe

```bash
python automator.py <model_quant> <profiling_dataset> <report_file> [opcoes]
```

## Parametros obrigatorios

- `model_quant`
  Caminho para o modelo quantizado `.tflite`.

- `profiling_dataset`
  Caminho para um diretorio contendo arquivos `.bin` em `float32`.

- `report_file`
  Caminho para o CSV onde o resultado sera salvo ou appendado.

## Opcoes disponiveis

- `--serial-device <porta>`
  Porta serial da placa. Exemplo: `/dev/ttyACM0`.

- `--arena-size <bytes>`
  Informa manualmente a tensor arena. Quando presente, o `stm32tflm` nao e chamado.

- `--skip-compile`
  Reaproveita o build existente e nao executa `compile.sh`.

- `--skip-deploy`
  Reaproveita o firmware ja gravado e nao executa `deploy.sh`.

## Pre-requisitos por modo de uso

## Modo completo

Se voce for deixar o `automator.py` compilar e gravar a placa, precisa de:

- `.venv` com dependencias Python instaladas
- MCUXpresso instalado
- LinkServer instalado
- placa detectada
- `stm32tflm` instalado, a menos que use `--arena-size`

## Modo reaproveitando firmware ja gravado

Se voce usar `--skip-compile --skip-deploy`, precisa de:

- `.venv` com dependencias Python instaladas
- placa conectada e acessivel na serial
- modelo `.tflite` compativel com o firmware que ja esta na placa
- dataset `.bin` compativel com o tensor de entrada esperado por esse firmware

## Comandos de exemplo

## Exemplo 1. Sanity test com o fixture versionado

Esse e o comando validado no repositorio:

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

Esse modo assume que:

- a placa ja esta com firmware compativel gravado
- o modelo usado no comando e o mesmo que originou o firmware atual

## Exemplo 2. Fluxo completo com compilacao e deploy

```bash
source .venv/bin/activate
python automator.py \
  /caminho/model_quant.tflite \
  /caminho/profiling_dataset \
  ./results.csv \
  --serial-device /dev/ttyACM0
```

Nesse caso:

- o `automator.py` tentara estimar a arena via `stm32tflm`
- depois vai gerar o codigo C++
- depois vai compilar
- depois vai gravar a placa
- e so entao vai rodar o profiling serial

## Exemplo 3. Fluxo com arena manual, mas ainda compilando e gravando

```bash
source .venv/bin/activate
python automator.py \
  /caminho/model_quant.tflite \
  /caminho/profiling_dataset \
  ./results.csv \
  --arena-size 57344 \
  --serial-device /dev/ttyACM0
```

Esse modo e util quando:

- o `stm32tflm` nao esta instalado
- ou voce ja sabe qual arena quer usar

## Erros comuns de uso

- passar apenas o modelo e esquecer `profiling_dataset` e `report_file`
- usar dataset com shape diferente do esperado pelo modelo
- usar `.bin` que nao estejam em `float32`
- usar `--skip-deploy` com firmware antigo que nao corresponde ao modelo enviado ao host
- esquecer `--arena-size` quando o `stm32tflm` nao esta instalado
- assumir que `--skip-compile` impede toda geracao de arquivos, o que nao e verdade

## Recomendacao pratica

Para sanity test inicial de ambiente, a forma recomendada hoje e:

1. ativar a `.venv`
2. confirmar a placa em `/dev/ttyACM0`
3. usar o fixture de `testdata/sanity-model`
4. rodar o `automator.py` com `--arena-size 57344 --skip-compile --skip-deploy`

Esse e o caminho mais curto para validar se:

- Python esta pronto
- serial esta funcional
- o fluxo host para MCU esta coerente
- o CSV esta sendo gerado corretamente
