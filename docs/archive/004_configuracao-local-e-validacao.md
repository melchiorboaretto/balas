# Configuracao Local e Validacao

## Objetivo

Este documento registra:

- como configurar o repositorio de forma portavel
- quais ajustes passaram a ficar fora do codigo
- o que foi validado na maquina atual
- como repetir o mesmo fluxo em outro computador com ajustes minimos

## Principio adotado

A configuracao especifica da maquina nao deve ficar hardcoded no codigo.

O repositorio agora segue esta ordem de resolucao:

1. variaveis de ambiente exportadas no shell
2. arquivo opcional `.balas.env` na raiz do repositorio
3. defaults genericos e previsiveis

Existe um arquivo de exemplo para isso:

- [.balas.env.example](/home/christian/github/balas/.balas.env.example)

Esse arquivo deve ser copiado manualmente para:

```bash
cp .balas.env.example .balas.env
```

Depois disso, ajuste apenas o que realmente for diferente na sua maquina.

## Variaveis de configuracao

As principais variaveis agora sao:

- `BALAS_SERIAL_PORT`
  Porta serial usada por `automator.py` e `profiler.py`

- `BALAS_STM32TFLM_BIN`
  Caminho absoluto para o binario `stm32tflm`

- `MCUXPRESSO_IDE_BIN`
  Caminho do executavel do `MCUXpresso IDE`

- `MCUX_WORKSPACE_DIR`
  Diretorio do workspace MCUXpresso

- `MCUX_IMPORT_PROJECT`
  Se `1`, `compile.sh` importa o projeto antes do build headless

- `BUILD_CONFIG`
  Configuracao de build, por exemplo `Debug`

- `LINKSERVER_ROOT`
  Diretorio raiz do `LinkServer`

- `PROBE_SERIAL`
  Serial do probe para `deploy.sh`

## Defaults genericos atuais

Se nenhuma configuracao local for fornecida, os scripts usam:

- serial: `/dev/ttyACM0`
- workspace: `<repo>/cpp-project`
- MCUXpresso: `/usr/local/mcuxpressoide/ide/mcuxpressoide`
- LinkServer: `/usr/local/LinkServer`
- `stm32tflm`: primeiro no `PATH`, depois em caminhos comuns sob `$HOME`

## O que mudou no codigo

## `compile.sh`

O script agora:

- usa `<repo>/cpp-project` como workspace padrao
- aceita `MCUX_WORKSPACE_DIR` e `MCUXPRESSO_IDE_BIN`
- carrega `.balas.env` automaticamente se o arquivo existir
- importa o projeto antes do build por padrao

Impacto:

- nao depende mais de `/home/bruno/...`
- o build pode ser repetido em outro host sem editar o script

## `deploy.sh`

O script agora:

- continua aceitando `LINKSERVER_ROOT` e `PROBE_SERIAL`
- passa a carregar `.balas.env` automaticamente

Impacto:

- o deploy continua generico
- a customizacao local pode ficar fora do codigo

## `python_scripts/arena_estimator/estimator.py`

O estimador agora:

- usa `BALAS_STM32TFLM_BIN` se definido
- tenta `stm32tflm` no `PATH`
- tenta caminhos comuns de instalacao da ST no `$HOME`

Impacto:

- nao depende mais de `/home/bruno/X-Cube-AI/...`

## `automator.py`

O `automator.py` agora aceita:

- `--serial-device`
- `--arena-size`
- `--skip-compile`
- `--skip-deploy`

Impacto:

- o sanity test pode ser mais incremental
- a serial nao fica presa a `/dev/ttyACM0`
- a estimativa via `stm32tflm` pode ser pulada com um valor manual de arena

## Validacao realizada na maquina atual

Os pontos abaixo foram validados nesta sessao:

### ST Edge AI / X-CUBE-AI

Pacote instalado em:

```text
/home/christian/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0
```

Binarios confirmados:

- `stm32tflm`
- `stedgeai`

Teste executado:

```bash
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm" --help
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stedgeai" --help
```

Resultado:

- ambos executaram corretamente
- o resolvedor automatico do repositorio encontrou `stm32tflm` nesse local

### Resolucao de configuracao

Teste executado:

```bash
python3 - <<'PY'
from python_scripts.config import default_serial_port, default_workspace_dir, default_mcuxpresso_bin, find_stm32tflm
print(default_serial_port())
print(default_workspace_dir())
print(default_mcuxpresso_bin())
print(find_stm32tflm())
PY
```

Resultado observado:

- serial padrao: `/dev/ttyACM0`
- workspace padrao: `/home/christian/github/balas/cpp-project`
- MCUXpresso padrao: `/usr/local/mcuxpressoide/ide/mcuxpressoide`
- `stm32tflm` encontrado corretamente no install local da ST

### Build headless

Teste executado:

```bash
./compile.sh
```

Resultado observado:

- o projeto foi importado e aberto em modo headless
- os caminhos do build foram regenerados para `/home/christian/github/balas/...`
- o firmware `Debug` foi recompilado com sucesso
- resultado final: `0 errors, 0 warnings`

Conclusao:

- o `compile.sh` agora funciona no host atual sem depender do caminho antigo `/home/bruno/...`

## O que ainda depende do ambiente

Mesmo com a configuracao generica, ainda existem dependencias externas naturais do projeto:

- `MCUXpresso IDE`
- `LinkServer`
- `stm32tflm` ou `stedgeai`
- `tensorflow` e `numpy` no ambiente Python
- modelo `.tflite`
- dataset `.bin`
- placa conectada e serial disponivel

Essas dependencias nao devem ser hardcoded; devem ser:

- instaladas no host
- apontadas por configuracao local quando necessario

## Fluxo recomendado em outro computador

1. Clonar o repositorio.
2. Instalar `MCUXpresso IDE` e `LinkServer`.
3. Instalar `X-CUBE-AI` ou `ST Edge AI` com `stm32tflm`.
4. Copiar `.balas.env.example` para `.balas.env`.
5. Ajustar apenas os campos que diferirem no host.
6. Validar `stm32tflm --help`.
7. Rodar `./compile.sh`.
8. Rodar `./deploy.sh` com `PROBE_SERIAL` se necessario.
9. Rodar o `automator.py` com os argumentos adequados.

## Exemplo de sanity test com menos atrito

Se o firmware ja estiver compilado e gravado, um teste incremental pode ser:

```bash
python3 automator.py \
  /caminho/model_quant.tflite \
  /caminho/profiling_dataset \
  /caminho/results.csv \
  --arena-size 200000 \
  --skip-compile \
  --skip-deploy
```

Esse formato reduz as dependencias do teste para:

- Python
- modelo `.tflite`
- dataset `.bin`
- porta serial correta
- firmware ja presente na placa

## Observacao importante

Esta validacao melhora bastante a portabilidade dos scripts do host.

Ela nao corrige, por si so, problemas funcionais ja conhecidos do firmware, como:

- bug de tamanho em `input.h`
- bug de tamanho em `output.h`

Ou seja:

- a infraestrutura de host ficou mais portavel
- a confianca no protocolo completo de inferencia ainda depende da revisao desses pontos do firmware
