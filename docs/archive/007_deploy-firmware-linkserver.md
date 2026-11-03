# Deploy de Firmware com `deploy.sh` e `LinkServer`

## Objetivo

Este documento explica como gravar o firmware do projeto na placa NXP `FRDM-MCXN947` usando o script `deploy.sh` da raiz do repositorio.

O foco aqui e o deploy do firmware ja compilado, usando `LinkServer` no Linux.

Este guia foi escrito para que uma pessoa consiga executar o processo sozinha, mesmo sem conhecer o historico do projeto.

## Quando usar este guia

Use este guia quando:

- o ambiente NXP no host ja foi instalado
- a placa `FRDM-MCXN947` ja esta conectada ao computador
- voce quer gravar um arquivo `.axf` na MCU
- voce quer usar o fluxo de linha de comando do projeto, sem depender do IDE para o flash

Este guia nao cobre a geracao do modelo `.tflite` nem a compilacao completa do firmware.

## Pre-requisitos

## Hardware

Voce precisa de:

- 1 placa `FRDM-MCXN947`
- 1 cabo USB de dados conectado na porta `J17 (MCU-Link USB)` da placa
- permissao de acesso ao probe USB no Linux

## Software NXP que precisa estar instalado e configurado

Antes do deploy, o host precisa ter estes componentes da NXP instalados e funcionando:

- `MCUXpresso IDE`
- `LinkServer`

No ambiente Linux validado para este projeto, os caminhos padrao esperados sao:

```bash
/usr/local/mcuxpressoide/ide/mcuxpressoide
/usr/local/LinkServer
```

O `deploy.sh` usa diretamente a ferramenta de flash do `LinkServer`, normalmente localizada em:

```bash
/usr/local/LinkServer/binaries/crt_emu_cm_redlink
```

Tambem e esperado que o script de pre-connect da familia MCX N exista em:

```bash
/usr/local/LinkServer/binaries/ToolScripts/LS_preconnect_MCXN9XX.scp
```

Observacao:

- o script atual tenta usar esses caminhos por padrao
- se sua instalacao estiver em outro lugar, e possivel sobrescrever os caminhos por variaveis de ambiente

## O que deve estar funcionando antes do deploy

Antes de tentar gravar firmware, valide estes pontos:

### 1. O `LinkServer` precisa responder

```bash
LinkServer -v
```

Se o comando falhar por `PATH`, tente:

```bash
/usr/local/LinkServer/LinkServer -v
```

### 2. O probe precisa ser detectado

```bash
LinkServer probes
```

Exemplo de saida real:

```text
#  Description                                    Serial         Device    Board         Capabilities
---  ---------------------------------------------  -------------  --------  ------------  ----------------
1  MCU-LINK FRDM-MCXN947 (r0E7) CMSIS-DAP V3.128  EB04LLNGMJHMR  MCXN947   FRDM-MCXN947  DEBUG, VCOM, SIO
```

Nesse caso:

- o serial do probe e `EB04LLNGMJHMR`
- o device e `MCXN947`
- a board e `FRDM-MCXN947`

Se `LinkServer probes` so funcionar com `sudo`, por exemplo:

```bash
sudo /usr/local/LinkServer/LinkServer probes
```

entao o problema restante nao e de instalacao do `LinkServer`; e de permissao de acesso ao probe no usuario normal.

### 3. O firmware compilado precisa existir

O `deploy.sh` procura por padrao o arquivo:

```bash
cpp-project/tflite-test/Debug/tflite-test.axf
```

Valide:

```bash
ls -l cpp-project/tflite-test/Debug/tflite-test.axf
```

Sem esse arquivo, nao ha o que gravar na placa.

## O que o `deploy.sh` faz

O script `deploy.sh`:

- descobre a raiz do repositorio automaticamente
- monta os caminhos principais a partir da raiz do projeto
- procura o binario `crt_emu_cm_redlink`
- usa o arquivo `.axf` do firmware
- seleciona o device `MCXN947`
- usa `bootrom stall` apropriado para o target
- inclui diretorios de `Flash` quando eles existirem
- inclui o script `LS_preconnect_MCXN9XX.scp` quando ele existir
- aceita informar o serial do probe para fixar exatamente qual probe deve ser usado

O script foi escrito para funcionar bem em dois cenarios:

- uso simples com a estrutura padrao deste repositorio
- uso customizado por variaveis de ambiente

## Caminhos padrao usados pelo script

Se nenhuma variavel for sobrescrita, o script assume:

```bash
REPO_ROOT=<raiz do repositorio>
PROJECT_NAME=tflite-test
WORKSPACE_DIR=$REPO_ROOT/cpp-project
PROJECT_DIR=$WORKSPACE_DIR/$PROJECT_NAME
BUILD_DIR=$PROJECT_DIR/Debug
AXF_FILE=$BUILD_DIR/$PROJECT_NAME.axf
TARGET_DEVICE=MCXN947
CORE_INDEX=0
BOOTROM_STALL=0x50000040
LINKSERVER_ROOT=/usr/local/LinkServer
REDLINK_BIN=$LINKSERVER_ROOT/binaries/crt_emu_cm_redlink
LINKSERVER_FLASH_DIR=$LINKSERVER_ROOT/binaries/Flash
PACKAGE_SUPPORT_DIR=$WORKSPACE_DIR/.mcuxpressoide_packages_support/MCXN947_support
PACKAGE_FLASH_DIR=$PACKAGE_SUPPORT_DIR/Flash
PRECONNECT_SCRIPT=$LINKSERVER_ROOT/binaries/ToolScripts/LS_preconnect_MCXN9XX.scp
```

## Formas de usar o `deploy.sh`

Todos os exemplos abaixo assumem que voce esta na raiz do repositorio:

```bash
cd /caminho/para/o/repositorio
```

## Forma 1: deploy mais simples

Se:

- ha apenas um probe conectado
- o firmware esta no caminho padrao
- o `LinkServer` esta no caminho padrao

entao rode:

```bash
./deploy.sh
```

Esse e o uso mais simples.

## Forma 2: deploy informando o serial do probe como argumento

Se quiser fixar explicitamente qual probe usar:

```bash
./deploy.sh EB04LLNGMJHMR
```

Esse e o uso recomendado quando:

- ha mais de um probe conectado
- voce quer evitar ambiguidade
- voce quer tornar o comando reproduzivel em anotacoes ou scripts

## Forma 3: deploy informando o serial por variavel de ambiente

Tambem e possivel informar o serial assim:

```bash
PROBE_SERIAL=EB04LLNGMJHMR ./deploy.sh
```

Essa forma e util quando o deploy faz parte de outro script.

## Forma 4: usar outro arquivo `.axf`

Se o firmware compilado nao estiver no caminho padrao:

```bash
AXF_FILE=/caminho/completo/para/outro-firmware.axf ./deploy.sh
```

Exemplo:

```bash
AXF_FILE=$PWD/cpp-project/tflite-test/Release/tflite-test.axf ./deploy.sh
```

## Forma 5: usar outro diretorio de build

Se a configuracao nao for `Debug`:

```bash
BUILD_DIR=$PWD/cpp-project/tflite-test/Release ./deploy.sh
```

ou:

```bash
PROJECT_NAME=tflite-test BUILD_DIR=$PWD/cpp-project/tflite-test/Release ./deploy.sh
```

## Forma 6: usar outro nome de projeto

Se outro colega clonar este modelo de script para outro projeto MCUXpresso:

```bash
PROJECT_NAME=meu-projeto ./deploy.sh
```

Nesse caso, o script passa a procurar:

```bash
cpp-project/meu-projeto/Debug/meu-projeto.axf
```

## Forma 7: usar instalacao NXP fora do caminho padrao

Se o `LinkServer` estiver em outro diretorio:

```bash
LINKSERVER_ROOT=/opt/nxp/LinkServer ./deploy.sh
```

Se for necessario informar diretamente o binario de flash:

```bash
REDLINK_BIN=/opt/nxp/LinkServer/binaries/crt_emu_cm_redlink ./deploy.sh
```

## Forma 8: usar outro workspace

Se o projeto MCUXpresso estiver em outro lugar:

```bash
WORKSPACE_DIR=/algum/outro/workspace ./deploy.sh
```

Exemplo:

```bash
WORKSPACE_DIR=$HOME/work/mcx/cpp-project ./deploy.sh EB04LLNGMJHMR
```

## Forma 9: sobrescrever varios parametros juntos

Exemplo completo:

```bash
PROBE_SERIAL=EB04LLNGMJHMR \
LINKSERVER_ROOT=/usr/local/LinkServer \
WORKSPACE_DIR=$PWD/cpp-project \
PROJECT_NAME=tflite-test \
./deploy.sh
```

## Procedimento recomendado passo a passo

Este e o procedimento mais seguro para uso manual.

### Passo 1: entrar na raiz do repositorio

```bash
cd /home/christian/github/balas
```

### Passo 2: validar o probe

```bash
LinkServer probes
```

Se o retorno mostrar sua placa, anote o serial.

### Passo 3: validar o firmware

```bash
ls -l cpp-project/tflite-test/Debug/tflite-test.axf
```

### Passo 4: executar o deploy com serial explicito

```bash
./deploy.sh EB04LLNGMJHMR
```

Esse e o fluxo mais claro para o primeiro uso.

## Exemplos prontos de uso

## Exemplo A: caso padrao do projeto

```bash
cd /home/christian/github/balas
./deploy.sh EB04LLNGMJHMR
```

## Exemplo B: caso padrao sem informar serial

```bash
cd /home/christian/github/balas
./deploy.sh
```

Use este formato apenas se houver certeza de que so existe um probe elegivel conectado.

## Exemplo C: build em `Release`

```bash
cd /home/christian/github/balas
BUILD_DIR=$PWD/cpp-project/tflite-test/Release ./deploy.sh EB04LLNGMJHMR
```

## Exemplo D: `LinkServer` fora do padrao

```bash
cd /home/christian/github/balas
LINKSERVER_ROOT=/opt/nxp/LinkServer ./deploy.sh EB04LLNGMJHMR
```

## Exemplo E: firmware em arquivo customizado

```bash
cd /home/christian/github/balas
AXF_FILE=/tmp/teste.axf ./deploy.sh EB04LLNGMJHMR
```

## Variaveis aceitas pelo script

As variaveis abaixo podem ser usadas para adaptar o deploy:

- `REPO_ROOT`
- `PROJECT_NAME`
- `WORKSPACE_DIR`
- `PROJECT_DIR`
- `BUILD_DIR`
- `AXF_FILE`
- `TARGET_DEVICE`
- `CORE_INDEX`
- `BOOTROM_STALL`
- `LINKSERVER_ROOT`
- `REDLINK_BIN`
- `LINKSERVER_FLASH_DIR`
- `PACKAGE_SUPPORT_DIR`
- `PACKAGE_FLASH_DIR`
- `PRECONNECT_SCRIPT`
- `PROBE_SERIAL`

## Como o serial do probe funciona

O serial pode ser informado de duas formas:

### Como argumento posicional

```bash
./deploy.sh EB04LLNGMJHMR
```

### Como variavel de ambiente

```bash
PROBE_SERIAL=EB04LLNGMJHMR ./deploy.sh
```

Se os dois forem fornecidos, a variavel `PROBE_SERIAL` tem prioridade porque ela ja chega preenchida antes do argumento ser usado como fallback.

## O que fazer se der erro

## Caso 1: `crt_emu_cm_redlink not found`

Significa que o script nao encontrou a ferramenta de flash do `LinkServer`.

O que fazer:

```bash
find -L /usr/local/LinkServer -maxdepth 4 -type f -name crt_emu_cm_redlink
```

Se ela estiver em outro lugar:

```bash
REDLINK_BIN=/caminho/real/para/crt_emu_cm_redlink ./deploy.sh
```

## Caso 2: `Firmware image not found`

Significa que o `.axf` esperado nao existe.

O que fazer:

- confirmar se o projeto foi compilado
- confirmar se o nome do projeto e `tflite-test`
- confirmar se a configuracao usada foi `Debug`
- sobrescrever `AXF_FILE` ou `BUILD_DIR` se necessario

Exemplo:

```bash
AXF_FILE=$PWD/cpp-project/tflite-test/Debug/tflite-test.axf ./deploy.sh
```

## Caso 3: o probe nao aparece em `LinkServer probes`

O que fazer:

- confirmar que a placa esta conectada na porta correta `J17`
- testar outro cabo USB de dados
- testar outra porta USB do host
- validar `lsusb`
- validar se o problema so desaparece com `sudo`

Comandos uteis:

```bash
lsusb
LinkServer probes
sudo /usr/local/LinkServer/LinkServer probes
```

## Caso 4: `LinkServer probes` so funciona com `sudo`

Isso indica problema de permissao de acesso ao probe no usuario normal.

Nesse estado:

- a instalacao do `LinkServer` provavelmente esta correta
- o proximo ajuste e permissao USB, `udev` ou `hidraw`

Enquanto isso nao for corrigido, pode ser necessario rodar o deploy com privilegio e caminho absoluto das ferramentas, mas isso deve ser tratado como contingencia, nao como estado final desejado.

## Caso 5: ha mais de um probe conectado

Sempre informe o serial:

```bash
./deploy.sh EB04LLNGMJHMR
```

Sem isso, a ferramenta pode escolher outro probe elegivel.

## Boas praticas

- prefira usar `./deploy.sh <serial>` no primeiro teste
- so omita o serial quando tiver certeza de que ha um unico probe conectado
- valide sempre `LinkServer probes` antes do deploy
- valide sempre a existencia do `.axf`
- use variaveis de ambiente em vez de editar o script para ajustes locais
- mantenha o script generico e os ajustes especificos no comando de execucao

## Comando recomendado para este ambiente

No ambiente atualmente validado, o comando recomendado e:

```bash
cd /home/christian/github/balas
./deploy.sh EB04LLNGMJHMR
```

## Proximo passo depois do deploy

Depois de gravar o firmware, o passo seguinte normalmente e validar a comunicacao serial da placa.

Exemplo:

```bash
picocom -b 115200 /dev/ttyACM0
```

Se o firmware nao escrever texto na serial, isso nao significa necessariamente que o flash falhou. Depende do comportamento implementado no firmware gravado.
