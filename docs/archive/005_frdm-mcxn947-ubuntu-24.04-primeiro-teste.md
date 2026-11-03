# FRDM-MCXN947 no Ubuntu 24.04 - Primeiro Teste

## Objetivo

Preparar o host Ubuntu 24.04 para fazer o primeiro teste com a placa `FRDM-MCXN947`, usando o fluxo mais direto:

1. instalar dependencias basicas do host
2. instalar compatibilidade para o `MCUXpresso IDE` no Ubuntu 24.04
3. instalar `MCUXpresso IDE`
4. baixar o `MCUXpresso SDK` da placa
5. validar que o `MCU-Link` aparece no Linux
6. partir para o primeiro exemplo `hello_world`

## Observacao importante sobre Ubuntu 24.04

Em uma resposta publica de um funcionario da NXP em `11 Jun 2024`, a NXP informou que `Ubuntu 24.04` nao estava oficialmente suportado e recomendou instalar `libncurses5` e `libncursesw5` antes de rodar o instalador do `MCUXpresso IDE`.

Como referencia pratica para hoje:

- siga os passos abaixo exatamente nesta ordem
- se a NXP mudar o suporte oficial em uma versao mais nova do IDE, este passo de compatibilidade pode deixar de ser necessario

## Links oficiais

- Placa FRDM-MCXN947:
  `https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947`
- Getting Started da placa:
  `https://www.nxp.com/document/guide/getting-started-with-frdm-mcxn947%3AGS-FRDM-MCXNXX`
- Quick Start Guide da placa:
  `https://www.nxp.com/docs/en/quick-reference-guide/FRDM-MCXN947-QSG.pdf`
- MCUXpresso IDE:
  `https://www.nxp.com/mcuxpresso/ide`
- LinkServer:
`https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/linkserver-for-microcontrollers%3ALINKERSERVER`
- SDK da FRDM-MCXN947:
  `https://mcuxpresso.nxp.com/mcuxsdk/latest/html/boards/MCX/frdmmcxn947/index.html`
- SDK Builder:
  `https://mcuxpresso.nxp.com/`
- Pagina Ubuntu do pacote `libtinfo5`:
  `https://packages.ubuntu.com/jammy/amd64/libtinfo5`
- Pagina Ubuntu do pacote `libncurses5`:
  `https://packages.ubuntu.com/libncurses5`
- Pagina Ubuntu do pacote `libncursesw5`:
  `https://packages.ubuntu.com/jammy/libncursesw5`

## Referencias oficiais pertinentes

### Placa FRDM-MCXN947

- Pagina principal da placa:
  `https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947`
- Getting Started:
  `https://www.nxp.com/document/guide/getting-started-with-frdm-mcxn947%3AGS-FRDM-MCXNXX`
- Quick Start Guide:
  `https://www.nxp.com/docs/en/quick-reference-guide/FRDM-MCXN947-QSG.pdf`
- Board User Manual `UM12018`:
  `https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947`
- Board User Manual `UM12018` PDF espelhado na comunidade:
  `https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/MCX/4254/1/UM12018%20%283%29.pdf`
- Esquematico da placa:
  `https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947`
- Design files da placa:
  `https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947`
- Block diagram da placa:
  `https://www.nxp.com/assets/block-diagram/en/FRDM-MCXN947.pdf`

### MCU MCXN947 e familia MCX N

- Pagina da familia `MCX N94/N54/N53/N52/N24`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Data sheet `MCXN947/946/547/546/537/536/527/526/247`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Reference Manual `MCX N Reference Manual`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Security Reference Manual:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Errata `MCXN_1P02G`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Hardware Design Guide `UG10092`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Power Management User Guide `UG10101`:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Factsheet da familia:
  `https://www.nxp.com/products/MCX-N94-N54-N53-N52-N24`
- Block diagram da familia:
  `https://www.nxp.com/assets/block-diagram/en/MCX-N94-N54-N53-N52-N24.pdf`

### SDK e documentacao de exemplos

- Portal do SDK Builder:
  `https://mcuxpresso.nxp.com/`
- Pagina da board no SDK:
  `https://mcuxpresso.nxp.com/mcuxsdk/latest/html/boards/MCX/frdmmcxn947/index.html`
- API Reference do device `MCXN947`:
  `https://mcuxpresso.nxp.com/mcuxsdk/latest/html/drivers/MCX/MCXN/MCXN947/index.html`
- Board docs em snapshot do SDK:
  `https://docs.mcuxpresso.nxp.com/mcuxsdk/25.03.00-pvw2/html/boards/MCX/frdmmcxn947/index.html`

### MCUXpresso IDE

- Pagina principal do IDE:
  `https://www.nxp.com/mcuxpresso/ide`
- Download do IDE:
  `https://www.nxp.com/mcuxpresso/ide/download`
- Release notes do IDE:
  `https://www.nxp.com/mcuxpresso/ide`
- Release notes addendum:
  `https://www.nxp.com/webapp/sps/download/license.jsp?colCode=MCUXPRESS-IDE-RN-ADDENDUM`
- Installation Guide do IDE:
  `https://www.nxp.com/mcuxpresso/ide`
- User Guide do IDE:
  `https://www.nxp.com/mcuxpresso/ide`
- Command Line User Guide:
  `https://www.nxp.com/mcuxpresso/ide`
- Knowledge base de releases:
  `https://community.nxp.com/t5/MCUXpresso-IDE-Knowledge-Base/tkb-p/mcuxpresso-ide%40tkb`
- Installation Guide PDF espelhado na comunidade:
  `https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/mcuxpresso/4530/1/MCUXpresso_IDE_Installation_Guide.pdf`

### LinkServer e debug

- Pagina principal do LinkServer:
  `https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/linkserver-for-microcontrollers%3ALINKERSERVER`
- Pagina alternativa do LinkServer:
  `https://www.nxp.com/design/design-center/software/development-software/mcuxpresso-software-and-tools-/linkserver-for-microcontrollers%3ALINKERSERVER`
- User guide `LinkServer Integration with MCUXpresso IDE`:
  `https://www.nxp.com/docs/en/user-guide/UG10219.pdf`
- Curriculum e material de treinamento LinkServer:
  `https://community.nxp.com/t5/MCUXpresso-Training-Hub/LinkServer-Curriculum/ta-p/2120354`

### MCU-Link onboard e bridge USB

- Getting Started with MCU-Link:
  `https://www.nxp.com/document/guide/getting-started-with-the-mcu-link%3AGS-MCU-LINK`
- Pagina do MCU-Link:
  `https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/mcu-link-debug-probe%3AMCU-LINK`
- User Manual do MCU-Link `UM11931`:
  `https://www.nxp.com/docs/en/user-manual/UM11931.pdf`
- Quick reference do MCU-Link:
  `https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/mcu-link-debug-probe%3AMCU-LINK`
- LIBUSBSIO:
  `https://www.nxp.com/design/design-center/software/development-software/libusbsio-host-library-for-usb-enabled-mcus%3ALIBUSBSIO`
- USBSIO Library User's Guide:
  `https://www.nxp.com/docs/en/user-guide/LIBUSBSIOUG.pdf`

## O que instalar agora

Neste primeiro momento, instale apenas:

- ferramentas basicas de terminal e serial
- bibliotecas de compatibilidade para o instalador NXP
- `MCUXpresso IDE`
- `MCUXpresso SDK` da `FRDM-MCXN947`

`MCUXpresso Config Tools` pode ficar para a proxima etapa.

## Passo 1 - Pacotes basicos do Ubuntu

```bash
sudo apt update
sudo apt install -y \
  git curl wget unzip xz-utils tar \
  build-essential cmake ninja-build \
  libusb-1.0-0 udev \
  picocom minicom
```

Adicionar seu usuario ao grupo serial:

```bash
sudo usermod -aG dialout "$USER"
```

Depois disso, faca logout/login antes de tentar abrir a porta serial da placa.

### Teste de permissao serial

Este teste serve para confirmar que sua sessao passou a ter permissao para acessar a serial da `FRDM-MCXN947`.

1. Conecte a placa na porta `J17 (MCU-Link USB)`.
2. Abra um novo terminal depois do `logout/login`.
3. Rode os comandos abaixo.

Verificar se a porta serial apareceu:

```bash
ls /dev/ttyACM*
```

Resultado esperado:

- deve aparecer algo como `/dev/ttyACM0`

Verificar se seu usuario esta mesmo no grupo `dialout`:

```bash
groups
```

Resultado esperado:

- a lista deve conter `dialout`

Testar abertura da serial:

```bash
picocom -b 115200 /dev/ttyACM0
```

Para sair do `picocom`:

```text
Ctrl+A
Ctrl+X
```

O que significa cada caso:

- se abrir normalmente, a permissao serial esta correta
- se aparecer `Permission denied`, sua sessao ainda nao aplicou o grupo `dialout`
- se `/dev/ttyACM0` nao existir, a placa nao foi enumerada ainda ou apareceu em outro indice como `/dev/ttyACM1`

## Passo 2 - Instalar bibliotecas de compatibilidade do MCUXpresso

Este passo e importante no `Ubuntu 24.04` por causa da dependencia legado do toolchain embarcado pela NXP.

Antes de baixar qualquer `.deb`, confirme a arquitetura real do sistema:

```bash
uname -m
dpkg --print-architecture
```

Resultado esperado para este guia:

- `uname -m` = `x86_64`
- `dpkg --print-architecture` = `amd64`

Importante:

- no Ubuntu/Debian, `amd64` significa arquitetura `x86_64`
- isso vale tanto para processadores `Intel` quanto para processadores `AMD`
- `amd64` neste contexto nao quer dizer "somente AMD"

### Procesador Arquitetura Intel

Se seu processador for `Intel` e os comandos acima retornarem `x86_64` e `amd64`, siga exatamente os pacotes `amd64` abaixo.

O que deve ser feito:

- usar os arquivos `.deb` com sufixo `_amd64.deb`
- instalar `libtinfo5`, `libncurses5` e `libncursesw5` antes do instalador do `MCUXpresso IDE`
- manter o instalador Linux do IDE na variante `x86_64`

O que nao deve ser feito:

- nao baixar pacote `arm64`, `armhf` ou `i386`
- nao trocar `amd64` por outro nome por achar que `Intel` exige pacote diferente
- nao pular este passo se o instalador do IDE reclamar de `libncurses5` ou `libncursesw5`

Comandos para host `Intel x86_64`:

```bash
mkdir -p ~/Downloads/nxp-compat
cd ~/Downloads/nxp-compat

wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_6.3-2ubuntu0.1_amd64.deb
wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncurses5_6.3-2ubuntu0.1_amd64.deb
wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncursesw5_6.3-2ubuntu0.1_amd64.deb

sudo apt install -y \
  ./libtinfo5_6.3-2ubuntu0.1_amd64.deb \
  ./libncurses5_6.3-2ubuntu0.1_amd64.deb \
  ./libncursesw5_6.3-2ubuntu0.1_amd64.deb
```

### Como confirmar que deu certo

Se a instalacao terminar com linhas como estas, considere o passo concluido:

- `Configurando libtinfo5:amd64 (...)`
- `Configurando libncurses5:amd64 (...)`
- `Configurando libncursesw5:amd64 (...)`

Validacao objetiva:

```bash
dpkg -l | grep -E 'libtinfo5|libncurses5|libncursesw5'
```

Resultado esperado:

- as tres linhas devem aparecer com status `ii`

### Aviso do `apt` que parece erro mas nao e

Durante a instalacao via arquivos locais `.deb`, pode aparecer uma mensagem como:

- `N: O download e executado sem isolamento e como root ... usuario '_apt' ... Permissao negada`

Se os pacotes tiverem sido configurados e o `dpkg -l` mostrar status `ii`, esse aviso final nao representa falha da instalacao.

### Processador Arquitetura AMD

Se seu processador for `AMD` e os comandos acima retornarem `x86_64` e `amd64`, siga exatamente os mesmos pacotes `amd64`.

O que deve ser feito:

- usar os arquivos `.deb` com sufixo `_amd64.deb`
- tratar `amd64` como o nome da arquitetura `x86_64` suportada pelo Ubuntu
- instalar estas bibliotecas antes de rodar o instalador da NXP

O que nao deve ser feito:

- nao procurar um pacote especial "para Ryzen" ou "para AMD"
- nao baixar `arm64` por engano so porque a maquina e nova
- nao misturar pacotes de arquiteturas diferentes no mesmo sistema

Comandos para host `AMD x86_64`:

```bash
mkdir -p ~/Downloads/nxp-compat
cd ~/Downloads/nxp-compat

wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_6.3-2ubuntu0.1_amd64.deb
wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncurses5_6.3-2ubuntu0.1_amd64.deb
wget https://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libncursesw5_6.3-2ubuntu0.1_amd64.deb

sudo apt install -y \
  ./libtinfo5_6.3-2ubuntu0.1_amd64.deb \
  ./libncurses5_6.3-2ubuntu0.1_amd64.deb \
  ./libncursesw5_6.3-2ubuntu0.1_amd64.deb
```

### Quando nao seguir este passo do jeito acima

Pare aqui e nao use os links `_amd64.deb` se:

- `uname -m` retornar `aarch64`
- `dpkg --print-architecture` retornar `arm64`
- seu Ubuntu estiver rodando em `ARM`
- voce estiver em container ou VM com arquitetura diferente da maquina fisica

Nesses casos, primeiro precisamos revisar a compatibilidade do `MCUXpresso IDE` com a arquitetura real do host.

## Passo 3 - Baixar e instalar o MCUXpresso IDE

Baixe o instalador Linux no link oficial:

- `https://www.nxp.com/mcuxpresso/ide`

O arquivo normalmente vem com nome parecido com:

- `mcuxpressoide-<versao>.x86_64.deb.bin`

Depois de baixar:

```bash
cd ~/Downloads
chmod +x mcuxpressoide-*.x86_64.deb.bin
sudo ./mcuxpressoide-*.x86_64.deb.bin
```

Ao final, confirme se o binario do IDE existe:

```bash
ls -l /usr/local/mcuxpressoide/ide/mcuxpressoide
```

Resultado esperado:

- o arquivo `/usr/local/mcuxpressoide/ide/mcuxpressoide` deve existir

Importante:

- a instalacao do `MCUXpresso IDE` nao garante, na pratica, que o executavel `LinkServer` sera instalado junto
- se o IDE existir mas o `LinkServer` nao existir, isso nao significa falha do passo 3
- nesse caso, siga para o passo 4 e instale o `LinkServer` separadamente

Verificacao opcional para detectar esse caso:

```bash
ls -l /usr/local/LinkServer/LinkServer
```

Se aparecer `Arquivo ou diretorio inexistente`, apenas continue para o passo seguinte.

## Passo 4 - Baixar e instalar o LinkServer

Baixe o instalador oficial do `LinkServer` na pagina da NXP:

- `https://www.nxp.com/design/software/development-software/mcuxpresso-software-and-tools-/linkserver-for-microcontrollers%3ALINKERSERVER`

Observacao importante:

- nessa pagina, a NXP lista um download separado chamado `Linkserver installer Linux`
- o download exige conta NXP autenticada
- a versao muda com o tempo, entao use sempre o instalador Linux mais recente exibido na pagina

Referencia verificada neste roteiro:

- em `22 Mar 2026`, a pagina oficial listava `Linkserver installer Linux` no formato `DEB.BIN`

O nome do arquivo baixado tende a seguir este padrao, mudando apenas a versao:

- `LinkServer_<versao>.x86_64.deb.bin`

Exemplo pratico:

- `LinkServer_25.12.83.x86_64.deb.bin`

Depois de baixar o arquivo do `LinkServer`, rode:

```bash
cd ~/Downloads
chmod +x ./LinkServer_*.x86_64.deb.bin
sudo ./LinkServer_*.x86_64.deb.bin
```

Durante a instalacao, pode aparecer um aviso de licenca e confirmacao para continuar:

```text
Do you want to continue? [Y/n]
```

Nesse caso, responda:

```text
y
```

Depois disso, o instalador pode mostrar uma etapa adicional para associar o `LinkServer` a uma instalacao existente do `MCUXpresso IDE`, por exemplo:

```text
Detected MCUXpresso IDE installations:
1) mcuxpressoide-25.6.136
2) Custom installation path
q) Quit
```

Se o instalador detectar corretamente o seu IDE ja instalado, escolha o numero correspondente.

Exemplo:

```text
1
```

Depois de associar uma instalacao, o instalador pode voltar para o mesmo menu novamente.

Isso nao significa erro, travamento ou loop infinito.

Esse comportamento indica apenas que o instalador permite associar outras instalacoes do IDE antes de sair.

Se voce ja associou o IDE correto, o proximo passo e sair manualmente do menu com:

```text
q
```

Fluxo esperado nessa etapa:

1. digitar `1`
2. ler a mensagem informando que o `LinkServer` foi associado ao IDE detectado
3. perceber que o menu apareceu novamente
4. digitar `q` para encerrar o instalador

Se voce instalou o IDE em um caminho nao padrao e ele nao apareceu na lista, escolha:

```text
2
```

e informe manualmente o caminho da instalacao.

Importante:

- essa tela de associacao nao indica erro
- a instalacao principal do `LinkServer` ja pode ter sido concluida antes desse prompt
- o objetivo aqui e integrar essa versao do `LinkServer` ao `MCUXpresso IDE` ja instalado

Ao final, confirme se o binario existe:

```bash
ls -l /usr/local/LinkServer
ls -l /usr/local/LinkServer/LinkServer
```

Resultado esperado:

- o diretorio simbolico `/usr/local/LinkServer` deve existir
- o executavel `/usr/local/LinkServer/LinkServer` deve existir

Importante:

- nesta versao validada do instalador, o executavel principal ficou em `/usr/local/LinkServer/LinkServer`
- o nome do comando e `LinkServer`, com `L` e `S` maiusculos
- em Linux, `LinkServer` e `linkserver` sao comandos diferentes
- se voce rodar `linkserver` em minusculas, o shell pode responder `comando nao encontrado`
- nao assuma que o binario estara em `/usr/local/LinkServer/binaries/linkserver`

## Passo 5 - Colocar MCUXpresso e LinkServer no PATH

```bash
echo 'export PATH="/usr/local/mcuxpressoide/ide:/usr/local/LinkServer:$PATH"' >> ~/.bashrc
source ~/.bashrc
hash -r
```

Validar:

```bash
mcuxpressoide --help >/dev/null
LinkServer -v
```

Validacao alternativa sem depender do `PATH`:

```bash
/usr/local/LinkServer/LinkServer -v
```

Importante sobre `sudo`:

- o `PATH` configurado no `~/.bashrc` normalmente vale para o seu usuario
- esse mesmo `PATH` pode nao ser herdado automaticamente quando voce usa `sudo`
- por isso, `LinkServer -v` pode funcionar no seu shell e `sudo LinkServer -v` pode responder `comando nao encontrado`

Quando precisar testar com privilegios, use o caminho absoluto:

```bash
sudo /usr/local/LinkServer/LinkServer -v
sudo /usr/local/LinkServer/LinkServer probes
```

## Passo 6 - Baixar o SDK da FRDM-MCXN947

Voce tem dois caminhos validos:

### Opcao recomendada

Baixar o SDK da placa no portal da NXP e importar no IDE:

- `https://mcuxpresso.nxp.com/`

Buscar por:

- `FRDM-MCXN947`

Baixe o pacote zip da board e guarde, por exemplo, em:

```bash
mkdir -p ~/nxp/sdk
mv ~/Downloads/SDK_*.zip ~/nxp/sdk/
```

### Alternativa

Consultar os exemplos e a documentacao da placa primeiro:

- `https://mcuxpresso.nxp.com/mcuxsdk/latest/html/boards/MCX/frdmmcxn947/index.html`

## Passo 7 - Conectar a placa e validar o MCU-Link

Conecte a placa pela porta `J17 (MCU-Link USB)`.

Comandos de verificacao:

```bash
lsusb
LinkServer probes
ls /dev/ttyACM* 2>/dev/null
```

Interpretacao dos resultados:

- se `lsusb` mostrar `MCU-LINK FRDM-MCXN947` e `/dev/ttyACM0` existir, a placa esta conectada corretamente
- se `LinkServer probes` listar a placa, o probe de debug tambem esta acessivel no usuario atual
- se `LinkServer probes` vier vazio, mas `sudo /usr/local/LinkServer/LinkServer probes` listar a placa, a instalacao do `LinkServer` esta correta e o problema restante e permissao de acesso ao probe no usuario normal
- se `sudo /usr/local/LinkServer/LinkServer probes` tambem vier vazio, entao o problema nao e `PATH`; e preciso investigar deteccao do probe ou regras do sistema

Se a porta serial aparecer, um teste rapido e:

```bash
picocom -b 115200 /dev/ttyACM0
```

## Passo 8 - O que ainda nao instalar

Ainda nao e necessario instalar:

- `MCUXpresso Config Tools`
- `VS Code` com extensoes NXP
- stacks de middleware como `FreeRTOS`, `lwIP` ou `USB`

Primeiro vamos validar:

1. deteccao da placa
2. instalacao do IDE
3. instalacao do `LinkServer`
4. importacao do SDK
5. build e flash do `hello_world`

## Checklist do primeiro momento

Quando terminar esta etapa, estes comandos precisam funcionar:

```bash
mcuxpressoide --help >/dev/null
LinkServer -v
LinkServer probes
ls /dev/ttyACM* 2>/dev/null
```

Diagnostico complementar, se `LinkServer probes` vier vazio:

```bash
sudo /usr/local/LinkServer/LinkServer probes
```

Se esse comando listar a placa, considere a instalacao do `LinkServer` correta e trate o proximo problema como permissao USB/udev no usuario normal.

## Proximo passo

Depois que voce concluir esta instalacao, a proxima etapa do documento sera:

1. importar o SDK no `MCUXpresso IDE`
2. importar o exemplo `hello_world`
3. compilar
4. gravar na `FRDM-MCXN947`
5. validar a saida serial em `115200 8N1`
