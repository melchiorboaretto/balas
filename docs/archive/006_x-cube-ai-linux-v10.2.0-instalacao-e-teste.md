# X-CUBE-AI Linux v10.2.0 - Instalacao e Teste Manual

## Objetivo

Este documento registra:

- o que foi verificado no arquivo `./assets/x-cube-ai-linux-v10.2.0.zip`
- como extrair o pacote manualmente
- como validar os binarios `stm32tflm` e `stedgeai`
- como encaixar essa instalacao no repositorio atual sem executar nada automaticamente

Importante:

- este documento nao instala nada por conta propria
- os comandos abaixo sao para voce executar manualmente
- o foco aqui e instalar e testar a ferramenta, nao alterar o repositorio

## Resultado da verificacao do ZIP em `./assets`

O arquivo verificado foi:

- `./assets/x-cube-ai-linux-v10.2.0.zip`

O pacote externo contem exatamente estes dois arquivos:

- `STMicroelectronics.X-CUBE-AI.10.2.0.pack`
- `stedgeai-linux-10.2.0.zip`

Dentro do ZIP interno `stedgeai-linux-10.2.0.zip`, foi confirmado que existem:

- `Utilities/linux/stm32tflm`
- `Utilities/linux/stedgeai`
- `Documentation/stm32_command_line_interface.html`
- `Documentation/command_line_interface.html`

Conclusao pratica:

- sim, o pacote em `./assets` contem o binario `stm32tflm` que o repositorio atual espera
- ele tambem contem a CLI nova `stedgeai`
- portanto, este pacote serve para recuperar a dependencia faltante do `python_scripts/arena_estimator/estimator.py`

## Contexto do repositorio atual

Hoje o repositorio usa um caminho hardcoded em:

- [estimator.py](/home/christian/github/balas/python_scripts/arena_estimator/estimator.py:3)

O caminho esperado pelo codigo atual e:

```bash
/home/bruno/X-Cube-AI/Utilities/linux/stm32tflm
```

Isso significa que, mesmo instalando o pacote corretamente no seu home, o repositorio nao vai encontra-lo automaticamente sem um ajuste posterior.

As duas formas mais simples de lidar com isso sao:

1. instalar em um caminho proprio e depois ajustar o codigo
2. instalar em um caminho proprio e criar um link simbolico compativel com o caminho hardcoded

Para primeiro teste, a opcao 1 e mais limpa. A opcao 2 e mais conveniente se voce quiser evitar editar o repositorio agora.

## Procedimento recomendado de instalacao

## Opcao recomendada de diretorio

Escolha um caminho controlado por voce, por exemplo:

```bash
mkdir -p "$HOME/opt/st/x-cube-ai/10.2.0"
```

Neste documento, vou assumir:

```bash
INSTALL_ROOT="$HOME/opt/st/x-cube-ai/10.2.0"
```

## Passo 1 - Extrair o pacote externo

Na raiz do repositorio:

```bash
cd /home/christian/github/balas
mkdir -p "$HOME/opt/st/x-cube-ai/10.2.0"
unzip ./assets/x-cube-ai-linux-v10.2.0.zip -d "$HOME/opt/st/x-cube-ai/10.2.0"
```

Depois disso, voce deve ver estes arquivos no diretorio de destino:

- `"$HOME/opt/st/x-cube-ai/10.2.0/STMicroelectronics.X-CUBE-AI.10.2.0.pack"`
- `"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0.zip"`

Importante:

- esses dois arquivos nao sao comandos
- nao tente executar `*.pack` nem `*.zip` diretamente no shell
- o proximo passo e extrair o ZIP interno `stedgeai-linux-10.2.0.zip`

Se quiser conferir por comando, use:

```bash
ls -l "$HOME/opt/st/x-cube-ai/10.2.0"
```

## Passo 2 - Extrair o ZIP interno com as ferramentas Linux

```bash
cd "$HOME/opt/st/x-cube-ai/10.2.0"
unzip stedgeai-linux-10.2.0.zip -d stedgeai-linux-10.2.0
```

Resultado esperado:

- `"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm"`
- `"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stedgeai"`

Essas duas linhas acima sao caminhos esperados, nao comandos.

## Passo 3 - Confirmar que os executaveis existem

```bash
ls -l \
  "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm" \
  "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stedgeai"
```

Resultado esperado:

- os dois arquivos devem existir
- os dois arquivos devem aparecer como executaveis

## Passo 4 - Testar a ajuda dos binarios

Importante:

- so execute os comandos abaixo depois de extrair o ZIP interno
- os binarios executaveis sao `stm32tflm` e `stedgeai`
- os arquivos `STMicroelectronics.X-CUBE-AI.10.2.0.pack` e `stedgeai-linux-10.2.0.zip` nao devem ser executados

Primeiro teste o binario legado que interessa ao repositorio:

```bash
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm" --help
```

Depois teste a CLI nova:

```bash
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stedgeai" --help
```

Se quiser evitar digitar caminhos longos durante os testes desta sessao:

```bash
export X_CUBE_AI_ROOT="$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0"
export PATH="$X_CUBE_AI_ROOT/Utilities/linux:$PATH"
hash -r
```

Entao valide:

```bash
stm32tflm --help
stedgeai --help
```

⚠️Observacao:

- esse `PATH` vale apenas para a shell atual, a menos que voce o persista manualmente

## Passo 5 - Conferir a documentacao incluida no pacote

Os documentos principais confirmados dentro do pacote sao:

- `Documentation/stm32_command_line_interface.html`
- `Documentation/command_line_interface.html`

Voce pode abrir assim:

```bash
xdg-open "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Documentation/stm32_command_line_interface.html"
xdg-open "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Documentation/command_line_interface.html"
```

## Teste funcional minimo do `stm32tflm`

Para um teste funcional de verdade, voce precisa de um modelo `.tflite`.

Se ja tiver um modelo quantizado:

```bash
stm32tflm /caminho/para/model_quant.tflite
```

O objetivo desse teste e confirmar que:

- o binario executa no seu host
- ele consegue abrir o `.tflite`
- ele emite uma linha com `Ram:`

No repositorio atual, essa linha e exatamente o que o `estimator.py` procura.

## Como encaixar isso no repositorio

## Opcao A - Ajustar o repositorio para o caminho real instalado

Esta e a opcao mais limpa.

Depois de validar o binario, voce alteraria o caminho em:

- [estimator.py](/home/christian/github/balas/python_scripts/arena_estimator/estimator.py:6)

Substituindo o caminho hardcoded antigo:

```bash
/home/bruno/X-Cube-AI/Utilities/linux/stm32tflm
```

por algo como:

```bash
$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm
```

Melhor ainda seria trocar isso por:

- variavel de ambiente
- argumento de configuracao
- fallback por busca no `PATH`

Mas isso ja seria uma mudanca de codigo no repositorio.

## Opcao B - Criar um link simbolico compativel com o caminho esperado hoje

Se voce quiser evitar editar o codigo agora, pode recriar um caminho compativel apenas no seu ambiente:

```bash
mkdir -p "$HOME/X-Cube-AI/Utilities/linux"
ln -s \
  "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm" \
  "$HOME/X-Cube-AI/Utilities/linux/stm32tflm"
```

Importante:

- isso ainda nao satisfaz o caminho `/home/bruno/...`
- apenas cria um caminho equivalente sob o seu usuario

Para o snapshot atual do repositorio, isso so resolveria totalmente se o codigo fosse atualizado para apontar para o seu home real.

## O que testar antes de tentar o `automator.py`

Antes de usar o `automator.py`, o minimo recomendado e:

1. confirmar `stm32tflm --help`
2. confirmar `stedgeai --help`
3. confirmar `stm32tflm /caminho/para/model_quant.tflite`
4. confirmar que o comando acima imprime uma linha `Ram:`

Depois disso, o proximo bloqueio do `automator.py` nao sera mais o X-CUBE-AI, e sim:

- `tensorflow` e `numpy` no Python
- caminho hardcoded em `compile.sh`
- serial `/dev/ttyACM0`
- disponibilidade de um modelo `.tflite`
- disponibilidade de um dataset `.bin`

## Comandos uteis de verificacao

Listar o que veio no ZIP externo:

```bash
unzip -l ./assets/x-cube-ai-linux-v10.2.0.zip
```

Listar os executaveis do ZIP interno:

```bash
unzip -l "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0.zip" | rg 'Utilities/linux/[^/]+$'
```

Validar a existencia dos binarios apos extracao:

```bash
find "$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux" -maxdepth 1 -type f | sort
```

Testar rapidamente as CLIs:

```bash
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stm32tflm" --help
"$HOME/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0/Utilities/linux/stedgeai" --help
```

## Resposta curta

Sim, o ZIP em `./assets` contem o que voce precisa para esta dependencia:

- `stm32tflm`
- `stedgeai`
- documentacao local da CLI

O procedimento recomendado e:

1. extrair o ZIP externo
2. extrair o ZIP interno
3. validar `stm32tflm --help`
4. validar `stm32tflm <modelo.tflite>`
5. so depois decidir se prefere ajustar o repositorio ou criar uma compatibilidade local de caminho
