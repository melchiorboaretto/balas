# Port para Nordic nRF52840-DK

Data do registro: 2026-08-19

## Objetivo

Este documento registra o inicio da terceira implementacao embarcada do BALAS,
agora para a placa Nordic `nRF52840-DK` (`PCA10056`).

O port foi criado em um diretorio proprio:

```text
cpp-project/nrf52840-tflite-test/
```

Os projetos das placas NXP e STM32 permanecem separados e nao compartilham
startup, drivers, configuracoes de memoria ou artefatos de build com a Nordic.

Este registro cobre:

- identificacao da placa e das portas USB;
- ferramentas necessarias e opcionais;
- instalacao do nRF Connect SDK e do modulo TFLM;
- estrutura do novo firmware;
- protocolo serial usado pelo BALAS;
- integracao com os scripts existentes;
- comandos de build, gravacao e diagnostico;
- recuperacao da protecao AP-Protect encontrada no chip;
- validacoes reais de build, gravacao, UART e inferencia.

## Resumo executivo

Foi criado um alvo `BALAS_TARGET=nordic` baseado no nRF Connect SDK e no
Zephyr. O projeto possui dois modos de build:

1. `bring-up`, para validar LED, UART, gravacao e comunicacao com o host;
2. `TFLM`, para executar o modelo quantizado com TensorFlow Lite Micro e
   kernels CMSIS-NN.

O hardware foi detectado corretamente pelo `nrfutil`, incluindo o J-Link
onboard e as duas portas seriais virtuais. Nenhuma alteracao de jumper foi
necessaria para essa deteccao.

O nRF Connect SDK v3.4.0 e seu toolchain foram instalados e registrados
localmente pelo `sdk-manager`. Esse registro nao exige conta, licenca, e-mail
ou cadastro em um servico da Nordic.

O AP-Protect que bloqueava o SWD foi removido com `device recover`, apos a
autorizacao para gravar e validar a placa. A operacao apagou a Flash e a UICR
anteriores. Em seguida, os firmwares de bring-up e TFLM foram compilados,
gravados e verificados. O bring-up respondeu `52840` pela VCOM0 e o sanity
benchmark TFLM concluiu as 10 amostras na placa.

## Hardware de destino

### Placa

- placa: Nordic `nRF52840-DK`;
- identificador da placa: `PCA10056`;
- debugger/programmer onboard: SEGGER J-Link;
- alvo Zephyr: `nrf52840dk/nrf52840`;
- serial do probe detectado: `1050275396`.

### Microcontrolador

- MCU: Nordic `nRF52840`;
- arquitetura: Arm Cortex-M4F;
- Flash interna: 1 MiB;
- RAM: 256 KiB;
- possui FPU de precisao simples;
- pode usar kernels CMSIS-NN otimizados para Cortex-M.

### Estado fisico observado

A placa foi reconhecida sem modificacoes fisicas e sem instalar jumpers
adicionais. Para o fluxo atual, basta:

1. manter a placa na configuracao padrao de fabrica;
2. liga-la pela porta USB associada ao J-Link;
3. manter a chave de alimentacao ligada;
4. usar o VCOM0 para o protocolo serial da aplicacao.

Se a placa deixa de aparecer no sistema, a primeira verificacao deve ser cabo,
porta USB, chave de alimentacao e enumeracao USB. A ausencia de jumpers extras,
por si so, nao impediu a deteccao desta unidade.

### Documentacao de hardware e localizacao fisica

O repositorio ja possui uma copia do esquema e das camadas de PCB da PCA10056:

```text
docs/hardware-pdfs/nordic-nrf52840-dk-pca10056-schematic-and-pcb.pdf
```

O PDF possui 12 paginas e identifica conectores, alimentacao, interface J-Link,
UART/VCOM, chaves, LEDs, headers e ligacoes entre o interface MCU e o nRF52840.

Para fotografias e desenhos com a localizacao fisica dos elementos, consultar
o guia oficial da nRF52840-DK. Para especificacoes eletricas e registradores do
SoC, consultar a Product Specification do nRF52840. A pagina de downloads da
placa tambem oferece o pacote oficial com schematic, layout, BOM e Gerbers.

## Identificacao no Ubuntu

Comando usado:

```bash
nrfutil device list
```

Resultado observado:

```text
1050275396
Product         J-Link
Board version   PCA10056
Ports           /dev/ttyACM0, vcom: 0
                /dev/ttyACM1, vcom: 1
Traits          devkit, jlink, seggerUsb, serialPorts, usb

Found 1 supported device
```

Para este port:

- `/dev/ttyACM0`, VCOM0, e a porta da UART0 da aplicacao;
- `/dev/ttyACM1`, VCOM1, e enumerada, mas nao possui ligacao ao nRF52840;
- configuracao serial: `115200 8N1`, com RTS/CTS;
- o host deve ativar DTR para o interface MCU conectar fisicamente a UART.

Os nomes `/dev/ttyACM0` e `/dev/ttyACM1` podem mudar depois de desconectar a
placa ou reiniciar o computador. Sempre confirme com `nrfutil device list`.

## Ferramentas necessarias

Nao e obrigatorio instalar uma IDE grafica proprietaria da Nordic.

O fluxo versionado usa linha de comando:

- `nRF Util`, para detectar, recuperar, programar e reiniciar a placa;
- comando `device` do nRF Util;
- comando `sdk-manager` do nRF Util;
- nRF Connect SDK `v3.4.0`;
- toolchain correspondente ao NCS;
- Zephyr, `west`, CMake e Ninja, fornecidos pelo ambiente do SDK;
- SEGGER J-Link, usado pelo debugger onboard.

Ferramentas opcionais:

- nRF Connect for Desktop;
- nRF Connect for Visual Studio Code;
- uma instalacao separada do SEGGER J-Link para uso manual de `JLinkExe` ou
  ferramentas graficas.

Essas interfaces podem facilitar depuracao, mas nao fazem parte do build
reproduzivel adotado no repositorio.

## Versoes instaladas nesta maquina

```text
nrfutil       8.2.1
device        2.20.0
sdk-manager   1.16.1
```

O executavel esta em:

```text
/home/christian/bin/nrfutil
```

O toolchain de identificador `fbf7391cab` foi baixado e extraido. O arquivo
compactado possui aproximadamente 1,26 GB e a instalacao extraida ocupa cerca
de 4,1 GB.

Estado confirmado pelo SDK Manager:

```text
SDK Type  SDK Version  SDK Status  Toolchain Status
nrf       v3.4.0       Installed   Installed
```

O workspace do SDK esta em `/home/christian/ncs/v3.4.0` e ocupa cerca de
4,8 GB nesta maquina.

## Instalacao oficial por linha de comando

No Ubuntu x86-64:

```bash
mkdir -p "$HOME/bin"
curl -fL \
  https://files.nordicsemi.com/artifactory/swtools/external/nrfutil/executables/x86_64-unknown-linux-gnu/nrfutil \
  -o "$HOME/bin/nrfutil"
chmod 755 "$HOME/bin/nrfutil"
export PATH="$HOME/bin:$PATH"

nrfutil install device sdk-manager
nrfutil sdk-manager install v3.4.0
```

O `sdk-manager` usa `$HOME/ncs` como diretorio padrao no Linux. A instalacao
nao deve ser executada com `sudo`, para evitar arquivos pertencentes a `root`.

O pacote de fontes do NCS v3.4.0 possui aproximadamente 3,09 GB. O download do
`sdk-manager` e retomavel. Se ele for interrompido, retome com:

```bash
nrfutil sdk-manager install v3.4.0
```

Confirme a instalacao com:

```bash
nrfutil sdk-manager list
```

Se o SDK estiver ausente, o `compile.sh` encerra com uma mensagem explicita:

```text
nRF Connect SDK v3.4.0 is not installed.
Install it with: nrfutil sdk-manager install v3.4.0
```

### Modulo opcional TensorFlow Lite Micro

O manifesto do NCS importa apenas uma lista restrita de modulos do Zephyr e
nao inclui o projeto opcional `tflite-micro`. O build de bring-up nao precisa
dele. Para o modo TFLM, instale a revisao fixada pelo Zephyr 4.4:

```bash
mkdir -p "$HOME/ncs/v3.4.0/optional/modules/lib"
git clone https://github.com/zephyrproject-rtos/tflite-micro.git \
  "$HOME/ncs/v3.4.0/optional/modules/lib/tflite-micro"
git -C "$HOME/ncs/v3.4.0/optional/modules/lib/tflite-micro" \
  checkout --detach fcc760af130f3a595b5802cdebcc77461e54f382
```

O `compile.sh` passa esse diretorio por `ZEPHYR_EXTRA_MODULES` somente quando
`BALAS_NORDIC_ENABLE_MODEL=ON`. Outro local pode ser informado por
`NORDIC_TFLM_MODULE_DIR`.

## Por que usar o NCS v3.4.0

O nRF Connect SDK v3.4.0 e uma versao LTS baseada no Zephyr 4.4. A Nordic
tambem registra essa linha como a ultima do NCS que inclui suporte a dispositivos
da serie nRF52.

Fixar a versao evita que mudancas futuras no Zephyr, Kconfig ou nos modulos
opcionais do TFLM alterem silenciosamente o build.

O valor pode ser sobrescrito por `NORDIC_NCS_VERSION`, mas qualquer mudanca de
versao deve ser validada nos dois modos do firmware.

## Estrutura isolada do projeto

```text
cpp-project/nrf52840-tflite-test/
  CMakeLists.txt
  prj.conf
  model.conf
  README.md
  boards/
    nrf52840dk_nrf52840.overlay
  include/
    serial_io.h
    timer.h
  src/
    main_bringup.cpp
    main_model.cpp
    serial_io.cpp
    timer.cpp
  Model/
    input.h
    output.h
    model.h
    model.cpp
    model_data.h
    quantization.h
    quantization.cpp
```

O diretorio de build e criado em:

```text
cpp-project/nrf52840-tflite-test/build/
```

Esse diretorio esta ignorado pelo Git.

## Modo 1: bring-up

O bring-up e o modo padrao e nao carrega o TensorFlow Lite Micro.

Comportamento:

1. configura o LED1;
2. pisca o LED durante o boot;
3. inicializa a UART0;
4. aguarda exatamente quatro bytes;
5. alterna o LED;
6. devolve o inteiro assinado `52840` em little-endian.

Esse protocolo permite validar separadamente:

- build do Zephyr;
- gravacao pelo J-Link;
- boot do nRF52840;
- GPIO/LED;
- UART0/VCOM0;
- leitura e escrita binaria pelo host.

Build:

```bash
BALAS_TARGET=nordic ./compile.sh
```

Artefato esperado:

```text
cpp-project/nrf52840-tflite-test/build/zephyr/zephyr.hex
```

Gravacao:

```bash
BALAS_TARGET=nordic \
NORDIC_PROBE_SERIAL=1050275396 \
./deploy.sh
```

Diagnostico serial:

```bash
.venv/bin/python python_scripts/diag_nordic_bringup.py /dev/ttyACM0
```

O script envia `BLAS` e espera quatro bytes que representem `52840`.
Ele ativa DTR e RTS/CTS, como exigido pelo VCOM da DK.

Resultado real do build de bring-up:

```text
Flash: 19.904 B / 1 MiB (1,90%)
RAM:    9.152 B / 256 KiB (3,49%)
```

## Modo 2: TFLM com CMSIS-NN

O modo de modelo e habilitado por:

```bash
BALAS_TARGET=nordic \
BALAS_NORDIC_ENABLE_MODEL=ON \
./compile.sh
```

Configuracoes principais:

```text
CONFIG_CPP=y
CONFIG_STD_CPP17=y
CONFIG_TENSORFLOW_LITE_MICRO=y
CONFIG_TENSORFLOW_LITE_MICRO_CMSIS_NN_KERNELS=y
CONFIG_HEAP_MEM_POOL_SIZE=24576
CONFIG_MAIN_STACK_SIZE=8192
```

O modelo sanity atual usa:

- tensor arena: `81920` bytes;
- modelo quantizado `int8` embutido em `Model/model_data.h`;
- entrada recebida do host em `float32`;
- conversao `float32 -> int8` antes da inferencia;
- conversao `int8 -> float32` para a saida local;
- medicao ao redor de `run_inference()`, incluindo quantizacao da entrada,
  `interpreter.Invoke()` e desquantizacao da saida.

O resolvedor gerado para o modelo sanity possui nove operacoes:

```text
Conv2D
Add
AveragePool2D
Shape
StridedSlice
Pack
Reshape
FullyConnected
Softmax
```

O timer usa `k_cycle_get_32()` e converte a diferenca de ciclos para
microssegundos com `k_cyc_to_us_floor32()`.

Resultado real do build TFLM/CMSIS-NN:

```text
Flash: 219.632 B / 1 MiB (20,95%)
RAM:   119.948 B / 256 KiB (45,76%)
```

## Protocolo binario do benchmark

O protocolo preserva o comportamento usado nos alvos anteriores:

1. o host envia uma entrada completa em `float32`;
2. o firmware bloqueia ate receber todos os bytes;
3. a entrada e quantizada para o tensor `int8`;
4. o TFLM executa a inferencia;
5. o firmware devolve um `int32` little-endian com o tempo em microssegundos;
6. se a inferencia falhar, o firmware devolve `-1`.

Como cada entrada sanity possui 12.288 bytes, RTS/CTS foi mantido ativo no
firmware e no PySerial. Sem HWFC, a deteccao dinamica do interface MCU permitia
o pacote curto do bring-up, mas interrompia o payload longo do modelo.

UART0 pertence exclusivamente a esse protocolo. Para impedir que mensagens de
boot contaminem o valor binario, foram desabilitados:

```text
CONFIG_CONSOLE
CONFIG_UART_CONSOLE
CONFIG_PRINTK
CONFIG_LOG
```

Portanto, nao devem ser adicionados logs textuais na mesma UART sem alterar o
protocolo do host.

## Geracao do modelo

O gerador Python ganhou um destino Nordic proprio:

```text
cpp-project/nrf52840-tflite-test/Model/
```

A funcao `generate_nordic_tflm_code()` atualiza:

- `model_data.h` com o binario `.tflite`;
- `TENSOR_ARENA_SIZE` em `model.h`;
- quantidade de operacoes do resolvedor;
- chamadas `resolver.Add...()` em `model.cpp`.

O gerador nao copia os templates NXP sobre os arquivos Nordic. Ele altera
somente os pontos gerados dentro do diretorio do novo alvo.

## Integracao com o repositorio

Arquivos integrados ou adicionados:

- `compile.sh`: reconhece `BALAS_TARGET=nordic` e chama `west build` dentro do
  toolchain do NCS;
- `deploy.sh`: programa `zephyr.hex` com `nrfutil device program`;
- `.balas.env.example`: documenta variaveis Nordic;
- `.gitignore`: ignora builds do novo alvo;
- `automator.py`: gera o modelo Nordic e habilita o modo TFLM;
- `python_scripts/code_generator/generator.py`: adiciona o gerador Nordic;
- `python_scripts/experiments/run_benchmark_suite.py`: aceita o alvo Nordic e
  restringe o backend a `tflm`;
- `python_scripts/diag_nordic_bringup.py`: valida o firmware minimo;
- `testdata/sanity-model/nordic-tflm-suite.json`: define o sanity benchmark.

## Variaveis de configuracao

As variaveis disponiveis sao:

```bash
BALAS_TARGET=nordic
BALAS_SERIAL_PORT=/dev/ttyACM0
NORDIC_PROJECT_DIR=$PWD/cpp-project/nrf52840-tflite-test
NORDIC_BUILD_DIR=$PWD/cpp-project/nrf52840-tflite-test/build
NORDIC_BOARD=nrf52840dk/nrf52840
NORDIC_NCS_VERSION=v3.4.0
NORDIC_NCS_DIR=$HOME/ncs/v3.4.0
NORDIC_TFLM_MODULE_DIR=$HOME/ncs/v3.4.0/optional/modules/lib/tflite-micro
BALAS_NORDIC_ENABLE_MODEL=OFF
NORDIC_FIRMWARE_FILE=$PWD/cpp-project/nrf52840-tflite-test/build/zephyr/zephyr.hex
NORDIC_PROBE_SERIAL=1050275396
NRFUTIL_BIN=nrfutil
```

Elas podem ser exportadas no shell ou colocadas em `.balas.env`, que nao deve
ser versionado.

## Execucao do sanity benchmark

Depois de instalar o SDK, recuperar a placa, validar o bring-up e gerar o
firmware TFLM:

```bash
source .venv/bin/activate
python python_scripts/experiments/run_benchmark_suite.py \
  testdata/sanity-model/nordic-tflm-suite.json \
  artifacts/nordic_tflm_suite.csv
```

O manifesto usa:

```text
target: nordic
model_backend: tflm
serial_device: /dev/ttyACM0
arena_size: 81920
```

O backend Nordic atualmente aceita somente `tflm`. Outro valor produz erro
explicito, evitando gerar codigo para o alvo errado.

Resultado real salvo em `artifacts/nordic_tflm_suite.csv`:

```text
status: ok
amostras: 10
tentativas: 1
tensor arena: 81.920 B
MACs: 12.501.632
nRF52840 media: 704.854,8 us
nRF52840 desvio padrao: 168,8 us
workstation media: 268,4 us
```

## Recuperacao do AP-Protect

Comando executado:

```bash
nrfutil device protection-get --serial-number 1050275396
```

Resultado:

```text
serial_number: 001050275396
    core: Application
    access status: Debug access is currently disabled (status value: All)
```

Isso significa que o probe e as portas seriais estao acessiveis, mas o acesso
SWD ao processador esta bloqueado.

Para liberar o chip foi executado:

```bash
nrfutil device recover \
  --serial-number 1050275396 \
  --family nrf52
```

Atencao: a recuperacao apagou toda a Flash e a UICR anteriores. Esses dados
nao podem ser recuperados pelo fluxo atual.

Depois da operacao, `protection-get` confirmou:

```text
access status: Debug access is enabled (status value: None)
```

Depois da recuperacao, o fluxo executado foi:

```bash
BALAS_TARGET=nordic ./compile.sh
BALAS_TARGET=nordic NORDIC_PROBE_SERIAL=1050275396 ./deploy.sh
.venv/bin/python python_scripts/diag_nordic_bringup.py /dev/ttyACM0
```

## Comportamento do deploy

O `deploy.sh` usa:

```text
nrfutil device program
family: nrf52
erase: somente intervalos tocados pelo firmware
verify: leitura apos gravacao
reset: reset de sistema
```

A imagem TFLM final possui SHA-256
`bac24d0346e052ecfb96e08bdc5ad336b7d0fbfddb32e9c9914d5b8589788577` e
passou tambem por uma chamada independente de `nrfutil device fw-verify`.

O erase normal do deploy nao substitui `device recover` quando AP-Protect esta
ativo. A recuperacao e necessaria somente para restabelecer o acesso de debug.

## Validacoes realizadas

### Confirmado nesta maquina

- placa detectada como `PCA10056`;
- J-Link onboard detectado;
- serial do probe confirmado;
- `/dev/ttyACM0` e `/dev/ttyACM1` enumeradas;
- nRF Util e comandos `device`/`sdk-manager` instalados;
- NCS v3.4.0 e toolchain registrados como `Installed`;
- modulo TFLM na revisao `fcc760af130f3a595b5802cdebcc77461e54f382`;
- firmware da interface J-Link reconhecido;
- AP-Protect removido por `device recover` e acesso confirmado como `None`;
- bring-up e TFLM compilados com sucesso;
- firmware gravado, reiniciado e confirmado por `fw-verify`;
- resposta `52840` recebida pela VCOM0;
- DTR e RTS/CTS validados para o protocolo serial;
- inferencia TFLM/CMSIS-NN executada fisicamente;
- 10 de 10 amostras concluidas na primeira tentativa;
- CSV salvo em `artifacts/nordic_tflm_suite.csv`;
- geracao do header do modelo sanity executada;
- scripts Bash validados com `bash -n`;
- arquivos Python validados com `py_compile`;
- erro de SDK e modulo TFLM ausentes tratado explicitamente por `compile.sh`.

### Limitacoes atuais

- apenas o modelo sanity foi executado; a suite ampla de modelos ainda deve ser
  validada separadamente;
- a medicao inclui quantizacao, `Invoke()` e desquantizacao, conforme o escopo
  atual do firmware;
- o caminho serial validado e a VCOM0 da unidade `1050275396`.

## Diagnostico de problemas comuns

### `No SDKs installed`

Retome a instalacao:

```bash
nrfutil sdk-manager install v3.4.0
```

Depois confirme:

```bash
nrfutil sdk-manager list
```

### `west: unknown command build`

Esse erro ocorre quando o toolchain foi instalado, mas o workspace do SDK nao
esta registrado. Conclua a instalacao do NCS. O `compile.sh` atual ja detecta
essa situacao antes de chamar o `west`.

### Placa aparece, mas nao grava

Verifique a protecao:

```bash
nrfutil device protection-get --serial-number 1050275396
```

Se o status continuar `All`, sera necessario `device recover`, lembrando que a
operacao apaga a memoria do chip.

### Porta serial sem permissao

Confirme os grupos e permissoes:

```bash
groups
ls -l /dev/ttyACM0 /dev/ttyACM1
```

Em distribuicoes que usam o grupo `dialout`, adicione o usuario e abra uma nova
sessao:

```bash
sudo usermod -aG dialout "$USER"
```

### Diagnostico aponta a porta errada

Use `nrfutil device list` para relacionar `vcom: 0` ao dispositivo correto e
informe o caminho explicitamente ao script.

### VCOM0 abre, mas nao responde

Confirme que o terminal ativa DTR. O interface MCU mantem TX/RX em alta
impedancia enquanto DTR nao estiver ativo. Para payloads grandes, confirme
tambem RTS/CTS no firmware e no host. A VCOM1 nao e uma alternativa: ela nao
esta conectada ao nRF52840 nesta placa.

### Resposta binaria possui bytes extras

Confirme que console, `printk` e logs continuam desabilitados. Texto escrito na
UART0 quebra o protocolo de quatro bytes usado pelo host.

### Falha em `AllocateTensors`

Revise:

- `TENSOR_ARENA_SIZE` gerado em `Model/model.h`;
- tamanho da heap do Zephyr;
- tamanho da stack principal;
- uso total de RAM informado pelo linker;
- operacoes presentes no `MicroMutableOpResolver`.

## Ordem para reproduzir a validacao

1. instalar `nrfutil`, `device`, `sdk-manager` e o NCS v3.4.0;
2. instalar a revisao TFLM documentada acima;
3. confirmar o SDK com `nrfutil sdk-manager list`;
4. verificar o AP-Protect e executar `device recover` somente se necessario;
5. compilar, gravar e diagnosticar o bring-up;
6. compilar o modo TFLM;
7. gravar e confirmar a imagem com `device fw-verify`;
8. executar `run_benchmark_suite.py` com o manifesto Nordic;
9. conferir a linha `status=ok` no CSV.

## Referencias oficiais

- nRF Util:
  `https://www.nordicsemi.com/Products/Development-tools/nRF-Util`
- instalacao do nRF Util:
  `https://docs.nordicsemi.com/r/bundle/nrfutil/page/guides/installing.html/installing-nrf-util-from-the-web-default`
- SDK Manager:
  `https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-sdk-manager/nrfutil-sdk-manager.html`
- instalacao de SDK pelo SDK Manager:
  `https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-sdk-manager/guides/sdk_manager_installing.html/basic-usage`
- suporte Zephyr para a nRF52840-DK:
  `https://docs.zephyrproject.org/latest/boards/nordic/nrf52840dk/doc/index.html`
- guia da nRF52840-DK, incluindo imagens e descricao do hardware:
  `https://docs.nordicsemi.com/r/bundle/ug_nrf52840_dk/`
- porta serial virtual, incluindo DTR, VCOM0 e VCOM1:
  `https://docs.nordicsemi.com/r/bundle/ug_nrf52840_dk/page/ug/dk/vir_com_port.html`
- Product Specification do nRF52840:
  `https://docs.nordicsemi.com/r/bundle/ps_nrf52840/`
- downloads e arquivos de hardware da nRF52840-DK:
  `https://www.nordicsemi.com/Products/Development-hardware/nRF52840-DK/Download`
- exemplo TFLM oficial do Zephyr:
  `https://docs.zephyrproject.org/latest/samples/modules/tflite-micro/hello_world/README.html`
- projetos opcionais do Zephyr, incluindo `tflite-micro`:
  `https://docs.zephyrproject.org/latest/develop/manifest/index.html`
- recuperacao de dispositivos nRF52:
  `https://docs.nordicsemi.com/r/bundle/nrfutil/page/nrfutil-device/guides/programming_recovery.html/recovering-nrf52-nrf54l-and-nrf91-series-devices`
- release notes do nRF Connect SDK v3.4.0:
  `https://github.com/nrfconnect/sdk-nrf/blob/main/doc/nrf/releases_and_maturity/releases/release-notes-3.4.0.rst`

## Estado final deste registro

O port Nordic esta implementado, isolado e integrado ao repositorio. O SDK e o
modulo TFLM foram instalados, o AP-Protect foi recuperado, a imagem foi gravada
e verificada, o protocolo serial foi validado e o modelo sanity executou as 10
amostras na nRF52840-DK. A placa terminou a validacao com o firmware TFLM
gravado e acesso de debug habilitado.
