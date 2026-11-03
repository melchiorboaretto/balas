# Visao Geral do Projeto

## Objetivo

Este repositorio implementa um fluxo para:

1. analisar um modelo quantizado em formato `.tflite`
2. gerar partes do codigo C++ embarcado para TensorFlow Lite Micro
3. compilar o firmware para a MCU NXP `MCXN947`
4. gravar o firmware na placa
5. enviar entradas pela serial
6. medir o tempo de inferencia e registrar resultados

O projeto foi preparado para ser operado a partir de Linux, mas o firmware principal nao roda no Linux. O firmware roda na MCU. No Linux rodam os scripts Python, o processo de build e o deploy.

## Estrutura Principal

### Diretorios relevantes

- `cpp-project/tflite-test/`
  Projeto embarcado do MCUXpresso para a MCU `MCXN947`.

- `cpp-project/tflite-test/source/`
  Contem o `main` da aplicacao embarcada.

- `cpp-project/tflite-test/model/`
  Contem a integracao com TensorFlow Lite Micro, quantizacao, serial e medicao de tempo.

- `cpp-project/tflite-test/tensorflow/`
  Contem headers e a biblioteca estatica `libtensorflow-microlite.a` versionada no repositorio.

- `python_scripts/`
  Scripts auxiliares para geracao de codigo, profiling, deploy e relatorios.

- `templates/`
  Templates usados pelo gerador para recriar `model.h` e `model.cpp`.

- `compile.sh`
  Script de compilacao headless com MCUXpresso IDE.

- `deploy.sh`
  Script de gravacao da imagem na placa via LinkServer.

- `automator.py`
  Script de orquestracao do fluxo principal.

### Arquivos importantes

- `cpp-project/tflite-test/source/MCXN947_Project.cpp`
  Ponto de entrada do firmware.

- `cpp-project/tflite-test/model/model.cpp`
  Implementacao da classe `MyModel`, configuracao do resolver TFLM, alocacao de arena e execucao da inferencia.

- `cpp-project/tflite-test/model/model.h`
  Define `TENSOR_ARENA_SIZE`, `N_OPS` e a interface da classe `MyModel`.

- `python_scripts/code_generator/generator.py`
  Analisa o modelo `.tflite`, identifica operadores e gera parte do codigo C++.

- `python_scripts/profiler/profiler.py`
  Envia entradas pela serial e recebe o tempo de inferencia retornado pela MCU.

- `python_scripts/arena_estimator/estimator.py`
  Estima o uso de RAM da tensor arena usando uma ferramenta externa.

- `python_scripts/mac_calculator/mac_calculator.py`
  Conta operacoes MAC do modelo.

- `python_scripts/report_writer/report.py`
  Salva resultados em CSV.

## Como o Projeto Funciona

## Fluxo de alto nivel

O fluxo pretendido do projeto e este:

1. o usuario fornece um modelo `.tflite` quantizado
2. o script estima o tamanho da tensor arena
3. o script calcula o numero de MACs
4. o gerador recria `model.h` e `model.cpp` a partir dos templates
5. o modelo binario `.tflite` e convertido em um header C (`model_data.h`)
6. o firmware e compilado
7. o firmware e gravado na placa
8. entradas de profiling sao enviadas pela serial
9. o firmware devolve o tempo de inferencia em microssegundos
10. os resultados sao agregados em CSV

## Papel de cada componente

### 1. Script orquestrador

O arquivo `automator.py` e o ponto de entrada mais proximo de um fluxo completo. Ele faz:

1. estimativa da arena
2. contagem de MACs
3. geracao do codigo C++
4. compilacao
5. deploy
6. envio de dataset de profiling
7. escrita do relatorio CSV

### 2. Geracao de codigo

O arquivo `python_scripts/code_generator/generator.py` faz tres coisas principais:

- abre o modelo `.tflite` usando `tf.lite.Interpreter`
- descobre quais operadores o modelo usa
- preenche os templates de `model.h` e `model.cpp`

Ele tambem usa `xxd -i` para transformar o modelo `.tflite` em `cpp-project/tflite-test/model/model_data.h`, que sera linkado dentro do firmware.

### 3. Firmware embarcado

O `main` em `cpp-project/tflite-test/source/MCXN947_Project.cpp` inicializa board, clocks e perifericos, instancia `MyModel` e entra em loop infinito:

1. le dados da serial
2. mede o tempo
3. executa inferencia
4. devolve um `int` com o tempo de inferencia

Importante: o firmware atual devolve apenas o tempo de inferencia. Ele nao devolve a saida do modelo pela serial.

### 4. TensorFlow Lite Micro

O arquivo `cpp-project/tflite-test/model/model.cpp`:

- carrega o modelo de `model_data.h`
- monta o `MicroMutableOpResolver`
- aloca a `tensor_arena`
- quantiza entrada `float32 -> int8`
- chama `interpreter.Invoke()`
- dequantiza a saida `int8 -> float32`

### 5. Comunicacao serial

O arquivo `cpp-project/tflite-test/model/serial_io.cpp` usa `LPUART_ReadBlocking` e `LPUART_WriteBlocking`.

Do lado host, `python_scripts/profiler/profiler.py` abre a serial em `115200` baud, escreve bytes das entradas e le 4 bytes de resposta.

### 6. Profiling e relatorio

O profiler envia:

- um input aleatorio gerado em memoria
- ou varios arquivos `.bin` contendo `float32`

O retorno esperado da MCU e um inteiro de 32 bits little-endian representando o tempo de inferencia.

Depois disso, `python_scripts/report_writer/report.py` grava media e desvio padrao em CSV.

## Dependencias Externas

## Hardware necessario

Obrigatorio para o fluxo completo:

- placa NXP baseada em `MCXN947`
- probe de debug compativel com o fluxo do LinkServer
- conexao USB para programacao e serial

Observacao importante:

O `deploy.sh` esta travado para um probe especifico:

- `--probeserial IRFAZHJCVDLI1`

Isso precisa ser ajustado para a sua placa e o seu ambiente.

## Software externo necessario

### Necessario para compilar e gravar

- `MCUXpresso IDE`
  Usado pelo `compile.sh` em modo headless.

- `LinkServer`
  Usado pelo `deploy.sh` para gravar o firmware.

- toolchain ARM `arm-none-eabi`
  O projeto gerado usa `arm-none-eabi-gcc`, `arm-none-eabi-c++` e `arm-none-eabi-size`.

### Necessario para os scripts Python

- Python 3
- `venv`
- `pip`
- `numpy`
- `pyserial`
- `tensorflow`

### Necessario para gerar o header do modelo

- `xxd`

## Dependencias que ja estao no repositorio

Pelo menos uma parte importante do TFLM ja esta versionada no projeto:

- `cpp-project/tflite-test/tensorflow/libtensorflow-microlite.a`
- headers de TensorFlow Lite Micro e dependencias em `cpp-project/tflite-test/tensorflow/`

Ou seja, nao parece necessario baixar separadamente a biblioteca TFLM para este repositorio funcionar.

## Dependencias opcionais ou situacionais

- `stm32tflm`
  Usado por `python_scripts/arena_estimator/estimator.py` para estimar RAM.

Observacao:

Essa ferramenta vem de um pacote da ST e o caminho atual aponta para:

- `/home/bruno/X-Cube-AI/Utilities/linux/stm32tflm`

Ela nao e parte deste repositorio. Sem ela, a estimativa automatica da arena falha. Ainda assim, o projeto pode ser adaptado para usar um valor manual da arena.

## Instalacao via APT

Esta secao cobre apenas o que e plausivel instalar via `apt` em Debian ou Ubuntu. Alguns componentes importantes nao costumam estar disponiveis por `apt` e sao listados na secao seguinte.

### Pacotes basicos

```bash
sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-serial \
  python3-numpy \
  xxd \
  make \
  git \
  gcc-arm-none-eabi \
  binutils-arm-none-eabi
```

Observacoes:

- `python3-serial` e a versao empacotada de `pyserial`
- `python3-numpy` pode ser instalado via apt, mas em alguns ambientes pode ser preferivel usar `pip` dentro de uma venv
- `xxd` costuma vir pelo pacote `xxd` ou por variantes do pacote do Vim, dependendo da distribuicao

### Ferramentas uteis para diagnostico serial

```bash
sudo apt install -y minicom screen
```

### Permissao para acessar serial USB

Em muitas distribuicoes Linux, o usuario precisa estar no grupo `dialout`:

```bash
sudo usermod -aG dialout "$USER"
```

Depois disso, normalmente e necessario sair e entrar novamente na sessao.

## Instalacao que provavelmente nao sera via APT

Estas dependencias sao externas ao repositorio, mas normalmente exigem instalacao manual:

- `MCUXpresso IDE`
- `LinkServer`
- `tensorflow` para Python
- `stm32tflm` do X-Cube-AI

### Exemplo de ambiente Python com venv

O `README.md` atual apenas menciona ativacao de venv. Um fluxo tipico seria:

```bash
python3 -m venv myenv
source myenv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install numpy pyserial tensorflow
```

## Pontos de Atencao que Precisam ser Revisados

## 1. Caminhos absolutos hardcoded

Existem varios caminhos absolutos presos ao ambiente original do autor, por exemplo:

- `/home/bruno/ufrgs/tcc/automator/cpp-project`
- `/usr/local/mcuxpressoide/ide/mcuxpressoide`
- `/usr/local/LinkServer/binaries`
- `/home/bruno/X-Cube-AI/Utilities/linux/stm32tflm`

Esses caminhos aparecem em:

- `compile.sh`
- `deploy.sh`
- `cpp-project/tflite-test/Debug/makefile`
- `cpp-project/tflite-test/Debug/*/subdir.mk`
- `python_scripts/arena_estimator/estimator.py`

Impacto:

- o projeto nao e portavel sem ajustes
- o build gerado em `Debug/` tambem carrega caminhos absolutos

## 2. Bug no tamanho de entrada e saida

Em `cpp-project/tflite-test/model/input.h` e `output.h`, o campo `size` esta sendo definido assim:

- `this->size = sizeof(data);`

Isso esta errado. `sizeof(data)` devolve o tamanho do ponteiro, nao o tamanho real do buffer alocado.

Impacto pratico:

- a quantidade de bytes lida da serial fica errada
- a quantizacao usa tamanho incorreto
- a dequantizacao usa tamanho incorreto
- o comportamento esperado da inferencia fica comprometido

Esse e um dos pontos mais criticos a revisar antes de confiar na execucao.

## 3. Ambiguidade de unidade em input e output

O `main` instancia:

- `ModelInput input(model.get_input_size())`
- `ModelOutput output(model.get_output_size())`

Mas `get_input_size()` e `get_output_size()` retornam `bytes`, enquanto `new float[size]` interpreta `size` como numero de elementos do vetor.

Impacto:

- o buffer alocado nao representa claramente a quantidade correta de elementos
- ha mistura entre contagem de bytes e contagem de floats

## 4. Geracao de IO esta incompleta

Em `python_scripts/code_generator/generator.py` existe a funcao `generate_io_code(inputs, outputs)`, mas ela nao e chamada por `generate_cpp_code`.

Alem disso, os arquivos atuais `input.h` e `output.h` nao parecem mais conter placeholders ativos sendo preenchidos pelo gerador.

Impacto:

- a geracao de codigo nao esta completamente coerente com a estrutura atual dos headers

## 5. O profiler ignora parte dos argumentos

No `main` de `python_scripts/profiler/profiler.py`:

- o argumento `profiling_dataset` e aceito
- mas o codigo executado usa `send_random_input_and_get_result(...)`
- a porta serial esta fixa em `/dev/ttyACM0`

Impacto:

- o modo CLI do profiler nao executa o fluxo de dataset que a assinatura sugere
- o script fica preso a uma porta serial especifica

## 6. O firmware retorna apenas tempo, nao retorna a predicao

O loop principal escreve apenas:

- `serial_write((uint8_t*)&inference_time_us, sizeof(int));`

Impacto:

- este firmware serve para benchmarking/profiling
- nao serve, no estado atual, como interface de inferencia completa para consumir a saida do modelo pelo host

## 7. Dependencia de uma ferramenta STM32 em um projeto NXP

A estimativa de arena usa `stm32tflm`, uma ferramenta ligada ao ecossistema STM32, enquanto o target aqui e NXP `MCXN947`.

Impacto:

- a dependencia e externa
- o nome da ferramenta e o caminho causam estranheza arquitetural
- este ponto merece validacao tecnica para garantir que a estimativa realmente faz sentido neste contexto

## 8. O build versionado em `Debug/` pode ficar obsoleto

O diretorio `cpp-project/tflite-test/Debug/` contem makefiles e artefatos gerados, todos com referencias ao ambiente original.

Impacto:

- se o projeto for movido de maquina, os arquivos gerados podem nao refletir o ambiente novo
- pode ser necessario regenerar o projeto no MCUXpresso ou corrigir os arquivos gerados

## 9. Documentacao ainda e insuficiente

O `README.md` atual so contem instrucoes de ativacao e desativacao de venv.

Impacto:

- nao ha guia oficial de build
- nao ha lista de dependencias
- nao ha passo a passo de deploy

## Checklist Minimo para Colocar o Projeto em Funcionamento

1. corrigir os caminhos hardcoded
2. revisar o bug de `size` em `input.h` e `output.h`
3. revisar a distincao entre numero de bytes e numero de elementos `float`
4. instalar `MCUXpresso IDE`, `LinkServer` e toolchain ARM
5. instalar dependencias Python
6. validar o acesso a `/dev/ttyACM0` ou trocar para a porta correta
7. ajustar o serial do probe em `deploy.sh`
8. validar se a estimativa de arena via `stm32tflm` sera mantida ou substituida
9. testar o fluxo completo com `automator.py`

## Resumo Executivo

Este projeto foi desenhado para ser usado em Linux como ambiente host, mas para executar em hardware embarcado NXP.

Ele depende de software de terceiros, inclusive:

- MCUXpresso IDE
- LinkServer
- toolchain ARM
- Python com bibliotecas especificas
- `xxd`
- opcionalmente `stm32tflm`

O repositorio contem boa parte do codigo e da biblioteca embarcada, mas ainda nao esta pronto para uso direto sem ajustes. Os principais pontos de revisao sao os caminhos hardcoded, o bug de tamanho em `input.h` e `output.h`, e a dependencia de ferramentas externas nao documentadas adequadamente.
