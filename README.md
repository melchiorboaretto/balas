# Como ter um ambiente funcional

O projeto inclui um arquivo ```distrobox.ini``` contendo os pacotes necessários (e alguns a mais)
para que tudo funcione.


## Inicializar o distrobox

Tendo o distrobox e o git baixados na máquina host e na raiz do repositório:

```bash
distrobox assemble create --file distrobox.ini
distrobox enter balas
```


## Ajustando o ambiente

Baseado em ```.balas.env.example```, cria um ```.balas.env``` e ajusta os
parâmetros, os absolutamente necessários são os seguintes:
- BALAS_SERIAL_PORT   (geralmente /dev/ttyACM0)
- BALAS_TARGET   (nxp, stm32 ou nordic)
- BALAS_STM32TFLM_BIN   (local do binário do stm32tflm, cuja instalação é abordada adiante. O caminho deve ser absoluto)

## Baixando as ferramentas

### stm32tflm

#### Baixando o zip da ferramenta
- Entra [nesse link](https://www.st.com/en/embedded-software/x-cube-ai.html) e clica em ```Get software```
- Dentre as 4 versões, seleciona ```Linux``` e a versão ```10.2.0```
- Aceita os termos e rola até o final, clica, após, em ```Download as a guest```
- Preenche o formulário e clica em ```Get link to download```
- Abre a caixa de entrada do email (o mesmo preenchido no formulário, obviamente)
- Acessa o email da STM
- Clica em ```Download now``` e ele vai começar a baixar

#### Colocando o binário no lugar
- Certifica-te de estar no terminal e no distrobox do balas na raíz do projeto
- Executa:
```bash
mkdir -p external/tflm-stm32
unzip ~/Downloads/x-cube-ai-linux-v10.2.0.zip -d /tmp/stm-extract
unzip /tmp/stm-extract/stedgeai-linux-10.2.0.zip -d /tmp/stm-extract-dois
mv /tmp/stm-extract-dois/Utilities/linux/stm32tflm external/tflm-stm32/stm32tflm
```
- Ajusta a variável de ambiente BALAS_STM32TFLM_BIN para apontar para o binário recém movido


### IDE da NXP (a da nordic será adicionada posteriormente)

#### Baixando o instalador da ferramenta
- Entra [nesse link](https://www.nxp.com/design/design-center/software/development-software/mcuxpresso-software-and-tools-/mcuxpresso-integrated-development-environment-ide:MCUXpresso-IDE) e clica em ```DOWNLOADS```
- Clica em ```DOWNLOAD``` no item MCUXpresso Integrated Development Environment (IDE)
- Se não tiver uma conta clica em ```Create an account```, se tiver, pula pro passo "*"
- Preenche o email e continua
- Abre a caixa de entrada do email (o mesmo preenchido no passo anterior)
- Acessa o email da NXP
- Procura o código de 6 dígitos, coloca no site da NXP e clica em ```VERIFY CODE```
- Preenche o resto do formulário e clica em ```CREATE ACCOUNT```
- "*" Preenche o email e clica em ```CONTINUE```
- Coloca a senha e clica em ```SIGN IN``` (deixa marcado pra manter logado)
- Abre outra guia do navegador e repete os passos 1 e 2
- A versão em uso é a 26.06, se for a atual, clica no link ```MCUXpresso IDE```. Do contrário,
clica em ```Previous``` e clica no mesmo botão, mas da versão correspondente (obviamente)
- Se tiver paciência lê os termos de uso e clica no botão preto ```I Agree```
- Clica em ```mcuxpressoide-25.6.136.x86_64.deb.bin``` e ele começa a baixar

#### Instalando a IDE
- Certifica-te de estar no terminal e no distrobox
- Executa:
```bash
chmod +x ~/Downloads/mcuxpressoide-25.6.136.x86_64.deb.bin
sudo ~/Downloads/mcuxpressoide-25.6.136.x86_64.deb.bin
```
- O instalador pede pra aceitar alguns termos, usa TAB e ENTER pra selecionar e confirmar, respectivamente
- Depois da janela de interação ele ainda vai abrir um diálogo pedindo pra apertar ```y``` e enter
- Quando terminar ele vai ter instalado a IDE no lugar que a ferramenta espera que esteja

#### Instalando o SDK (FRDM-MCXN947)
- Executa ```/usr/local/mcuxpressoide/ide/mcuxpressoide``` no mesmo terminal e no distrobox
- Deverá ser aberta a interface gráfica da IDE e ele vai pedir pra dar um diretório como workspace. Escolha a pasta cpp-project da pasta do balas
- Clica no botão amarelo (Download and Install SDKs)
- Vai abrir um menu que permite pesquisar pela placa
- Filtra por frdmmcxn947, clica na placa (vai ficar azul e clica em install)
- Espera terminar

# Atenção
Se não quiser mexer nas permissões em udev e afins, pode usar simplesmente (com cuidado) o comando abaixo
mas, não é NEM UM POUCO recomendado:
```
sudo chmod -R 777 /dev/bus/usb/
```
O mais correto é ajustar as permissões por dispositivo.


## Exemplo de uso da ferramenta de benchmark
```bash
uv run python_scripts/run_continuous_experiment.py \
    --config-toml configs/kws.toml \
    --serial-device /dev/ttyACM2 \
    --target nxp \
    --max-iterations 1000
```

# Observação importante
Vale ressaltar que a ferramenta é "burra", se uma configuração randomizada der algum erro por causa
do ambiente ou porque, por exemplo, a placa estava desconectada, será emitido um erro de deploy e essa variante apenas
será pulada. Por isso, convém rodar o comando antes do teste oficial pra ver se tudo ocorre corretamente, arrumar o que
não funciona, e a partir do momento que tudo estiver de acordo, apagar os .csvs gerados e começar de novo.

Isso será "corrigido" em um futuro próximo.


## Execução de todos os benchmarks (`run_all_benchmarks.py`)

O script `run_all_benchmarks.py` funciona como um wrapper para o `run_continuous_experiment.py`, executando sequencialmente todos os arquivos `.toml` presentes na raiz do diretório `configs/`.

Caso ocorra um erro crítico em qualquer um dos benchmarks durante uma iteração (como falha no `deploy.sh` ou erro na leitura na porta serial), todas as linhas dos `.csv` e entradas dos `_map.json` referentes àquela iteração são apagadas e a mesma iteração é tentada novamente. Erros de `compile.sh` são mantidos normalmente, pois indicam que a arena/modelo excedeu a memória FLASH/RAM da placa.

```bash
uv run run_all_benchmarks.py \
    --batch-size 10 \
    --configs-dir configs \
    --results-dir results \
    --target nxp \
    --serial-device /dev/ttyACM0 \
    --profiling-samples 10 \
    --max-iterations 1000 \
    --retry-delay 5.0
```

### Flags e valores padrão

- `--batch-size`: Quantidade de iterações completas antes de copiar os arquivos `.csv` e `.json` gerados em `artifacts/` para o diretório oficial de resultados (padrão: `10`).
- `--configs-dir`: Diretório onde o script busca os arquivos `.toml` apenas no primeiro nível, ignorando subpastas (padrão: `configs`).
- `--results-dir`: Diretório na raiz do repositório para onde os arquivos de resultados oficiais são copiados a cada lote de `--batch-size` iterações (padrão: `results`).
- `--target`: Placa alvo (`nxp`, `stm32`, `nordic`). Se omitido, utiliza o valor de `BALAS_TARGET` configurado no ambiente/ `.balas.env` (padrão: `None` -> `BALAS_TARGET` ou `nxp`).
- `--serial-device`: Porta serial do microcontrolador. Se omitido, utiliza a porta configurada no `.toml` ou em `BALAS_SERIAL_PORT` (padrão: `None` -> `BALAS_SERIAL_PORT` ou `/dev/ttyACM0`).
- `--profiling-samples`: Quantidade de amostras enviadas via serial por modelo testado. Se omitido, utiliza o `profiling_samples` definido em cada `.toml` (padrão: `None` -> `10` nos arquivos `.toml`).
- `--max-iterations`: Limite máximo de iterações a serem executadas. Se omitido, roda continuamente até ser interrompido com `Ctrl+C` (padrão: `None`).
- `--retry-delay`: Tempo de espera em segundos antes de tentar novamente a iteração atual após um erro crítico e rollback (padrão: `5.0`).


## Execução de Benchmarks CPU x NPU na NXP (FRDM-MCXN947)

Para avaliar o coprocessador neural (**eIQ Neutron N1-16**) em comparação direta com o núcleo **Cortex-M33 (CMSIS-NN)**, o repositório conta com um módulo dedicado em `python_scripts/npu/`.

### 1. Diagnóstico do Ambiente
Verifica se todas as ferramentas NXP e permissões de hardware estão prontas:
```bash
python python_scripts/npu/run_nxp.py check
```

### 2. Modos de Teste
O launcher unificado `run_nxp.py` facilita os diferentes formatos de execução:

```bash
# Modo Teste / Dry-Run (valida 1 modelo de cada no PC sem precisar da placa conectada)
python python_scripts/npu/run_nxp.py dry-run

# Modo Referência (mede os 4 modelos oficiais do MLPerf Tiny na placa)
python python_scripts/npu/run_nxp.py referencia

# Modo Aleatório (busca DSE com sorteio baseado em seeds - formato clássico do BALAS)
python python_scripts/npu/run_nxp.py aleatorio --modelos kws --max-variantes 50

# Modo Bateria Completa (executa sistematicamente todas as combinações dos grids novos)
python python_scripts/npu/run_nxp.py completo --modelos kws
```

Os resultados comparativos pareados e o cálculo de speedup (`CPU_us / NPU_us`) são salvos em `artifacts/cpu_vs_npu/`. Para mais detalhes de configuração e arquitetura, consulte [`docs/026_tutorial-npu-mcxn947.md`](docs/026_tutorial-npu-mcxn947.md).
