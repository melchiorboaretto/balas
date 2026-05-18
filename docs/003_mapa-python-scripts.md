# Mapa de `python_scripts`

## Objetivo

Este documento resume os scripts em `python_scripts/` e explica:

- o que cada um faz
- em que parte do fluxo ele entra
- quando faz sentido usa-lo diretamente

## Visao geral

O diretorio `python_scripts/` hoje esta organizado, na pratica, em cinco grupos:

1. configuracao local
2. pipeline principal do `automator.py`
3. utilitarios de fixture e sanity test
4. experimentos para reproducao do artigo
5. utilitarios auxiliares internos

## Tabela resumida

| Script | Funcao principal | Quando usar |
| --- | --- | --- |
| `python_scripts/config.py` | Le configuracao local e descobre caminhos padrao | Sempre que o fluxo depende de serial, MCUXpresso ou `stm32tflm` |
| `python_scripts/arena_estimator/estimator.py` | Estima tensor arena com `stm32tflm` | Quando voce nao quer informar `--arena-size` manualmente |
| `python_scripts/code_generator/generator.py` | Gera codigo C++ embarcado a partir do `.tflite` | Quando o modelo muda e o firmware precisa ser atualizado |
| `python_scripts/deployer/deployer.py` | Aciona `compile.sh` e `deploy.sh` | Quando o fluxo precisa compilar e gravar a placa |
| `python_scripts/mac_calculator/mac_calculator.py` | Conta MACs do modelo | Quando voce quer usar MACs como proxy de latencia |
| `python_scripts/profiler/profiler.py` | Envia `.bin` por serial e le tempos da placa | Quando voce quer medir inferencia real na MCU |
| `python_scripts/report_writer/report.py` | Escreve o CSV simples do fluxo atual | Quando usa o `automator.py` normal |
| `python_scripts/recover_tflite_from_header.py` | Recupera um `.tflite` de `model_data.h` | Quando o modelo esta embutido no firmware, mas nao existe como arquivo |
| `python_scripts/generate_float32_dataset.py` | Gera datasets `.bin` em `float32` | Quando voce precisa montar ou congelar datasets de profiling |
| `python_scripts/experiments/run_benchmark_suite.py` | Roda uma suite de benchmark e coleta CSV rico | Quando voce quer reproduzir a logica experimental do artigo |
| `python_scripts/experiments/analyze_benchmark_suite.py` | Analisa o CSV experimental e gera relatorio | Quando voce quer correlacoes e resumo estatistico |
| `python_scripts/experiments/common.py` | Funcoes comuns dos experimentos | Nao costuma ser usado diretamente |
| `python_scripts/file_utils.py` | Operacoes simples de arquivo | Nao costuma ser usado diretamente |
| `python_scripts/code_generator/resolver_map.py` | Mapa entre operadores TFLite e resolver do firmware | Suporte interno ao gerador |
| `python_scripts/code_generator/gen_resolver_map.py` | Script auxiliar de geracao do mapa de resolvers | Uso raro, mais interno |

## 1. Configuracao local

## `python_scripts/config.py`

Esse arquivo centraliza a configuracao local do projeto.

Ele faz:

- leitura de `.balas.env` ou `balas.env`
- definicao da porta serial padrao
- descoberta do workspace do MCUXpresso
- descoberta do binario do IDE
- descoberta do `stm32tflm`

Na pratica, ele evita hardcode de caminhos no restante do fluxo.

Se voce quer entender como o projeto decide:

- qual serial usar
- onde esta o `stm32tflm`
- onde esta o `MCUXpresso`

este e o primeiro arquivo para ler.

## 2. Pipeline principal do `automator.py`

Esses scripts formam o fluxo central usado pelo `automator.py`.

## `python_scripts/arena_estimator/estimator.py`

Responsavel por chamar o `stm32tflm` e extrair do output o valor de RAM estimado para a tensor arena.

Use quando:

- voce quer estimar arena automaticamente
- nao quer fixar `--arena-size` manualmente

## `python_scripts/code_generator/generator.py`

Responsavel por gerar partes do firmware que dependem do modelo:

- numero de operadores no resolver
- chamadas do resolver
- valor da tensor arena
- `model_data.h` a partir do `.tflite`

Ele tambem foi ajustado para estabilizar o simbolo final do comprimento do modelo em:

```c
unsigned int model_data_len = ...;
```

Use quando:

- o modelo `.tflite` mudou
- o firmware precisa refletir esse modelo novo

## `python_scripts/deployer/deployer.py`

Arquivo pequeno que apenas encapsula:

- `compile.sh`
- `deploy.sh`

Use quando:

- voce quer que o fluxo Python compile e grave a placa

## `python_scripts/mac_calculator/mac_calculator.py`

Calcula o numero de MACs do modelo a partir dos operadores TFLite.

Use quando:

- voce quer usar MACs como proxy de custo computacional
- voce quer reproduzir a comparacao `MACs vs MCU latency`

## `python_scripts/profiler/profiler.py`

Esse e o script que faz o trabalho real de profiling na placa.

Ele:

- le arquivos `.bin` em `float32`
- envia os bytes crus pela serial
- espera o inteiro de 4 bytes retornado pela MCU
- agrega os tempos de inferencia

Tambem tem uma funcao auxiliar para enviar dado aleatorio com base no shape do modelo.

Use quando:

- voce quer medir latencia real na MCU
- voce quer testar a serial
- voce quer validar se o firmware responde corretamente

## `python_scripts/report_writer/report.py`

Escreve o CSV simples do fluxo atual.

Campos gravados hoje:

- `arena_size`
- `macs`
- `avg_inference_us`
- `std_inference_us`

Use quando:

- o fluxo simples do `automator.py` ja e suficiente

Se voce quer reproduzir o artigo com mais detalhes, esse CSV e simples demais. Nesse caso, prefira os scripts de `experiments/`.

## 3. Utilitarios de fixture e sanity test

## `python_scripts/recover_tflite_from_header.py`

Foi criado para recuperar um `.tflite` a partir de um `model_data.h` gerado com `xxd -i`.

Ele:

- le os bytes hexadecimais do header
- reconstroi o binario
- valida o comprimento declarado
- escreve o arquivo `.tflite`

Use quando:

- o modelo esta embutido no firmware
- mas nao existe o `.tflite` como arquivo no repositorio

## `python_scripts/generate_float32_dataset.py`

Gera datasets `.bin` em `float32`.

Ele pode:

- usar um shape informado manualmente
- inferir o shape a partir de um `.tflite`

Modos suportados:

- `zeros`
- `uniform`
- `uint8_as_float32`

Use quando:

- voce precisa montar um dataset minimo para sanity test
- voce quer gerar dados deterministcos para reproduzir experimentos

## 4. Scripts de experimento para reproducao do artigo

Esses scripts sao os mais adequados quando o objetivo nao e apenas rodar um modelo, mas reproduzir a logica experimental do trabalho do Bruno Silveira.

## `python_scripts/experiments/run_benchmark_suite.py`

Esse e o runner principal da reproducao reduzida.

Ele recebe um manifesto JSON com modelos e datasets e coleta, para cada entrada:

- arena estimada
- arena final usada
- numero de tentativas
- MACs
- latencia media e desvio no workstation
- latencia media e desvio na MCU
- tempos das etapas do pipeline
- status de sucesso ou falha

Use quando:

- voce quer construir um CSV experimental mais rico
- voce quer comparar estimadores com latencia real da MCU
- voce quer rodar o mesmo fixture no alvo STM32 usando `target=stm32` e
  `model_backend=stedgeai`
- voce quer se aproximar do experimento do artigo

## `python_scripts/experiments/analyze_benchmark_suite.py`

Esse script le o CSV gerado pelo runner e produz um relatorio em Markdown.

Ele calcula:

- correlacao `MACs vs MCU avg us`
- correlacao `workstation avg us vs MCU avg us`
- correlacao `arena_estimated vs arena_final`
- resumo por familia
- tabela das amostras coletadas

Use quando:

- voce ja tem um CSV experimental e quer transformar isso em leitura analitica

## `python_scripts/experiments/common.py`

Contem utilitarios compartilhados dos experimentos:

- leitura de manifesto
- resolucao de caminhos
- append de CSV
- correlacao de Pearson

Nao costuma ser chamado diretamente.

## 5. Utilitarios auxiliares internos

## `python_scripts/file_utils.py`

Conjunto de funcoes utilitarias para:

- copiar arquivos
- copiar diretorios
- substituir texto em arquivos
- criar diretorios

E usado principalmente pelo gerador de codigo.

## `python_scripts/code_generator/resolver_map.py`

Mapa entre nomes de operadores TFLite e chamadas do `MicroMutableOpResolver`.

E um arquivo de suporte interno ao `generator.py`.

## `python_scripts/code_generator/gen_resolver_map.py`

Script auxiliar relacionado a geracao do mapa de resolvers.

Normalmente nao e um ponto de entrada de uso diario.

## Ordem recomendada para entender o sistema

Se voce quiser entender o projeto com o menor custo de leitura, a ordem recomendada e:

1. `automator.py`
2. `python_scripts/config.py`
3. `python_scripts/profiler/profiler.py`
4. `python_scripts/code_generator/generator.py`
5. `python_scripts/arena_estimator/estimator.py`
6. `python_scripts/mac_calculator/mac_calculator.py`
7. `python_scripts/recover_tflite_from_header.py`
8. `python_scripts/generate_float32_dataset.py`
9. `python_scripts/experiments/run_benchmark_suite.py`
10. `python_scripts/experiments/analyze_benchmark_suite.py`

## Resumo pratico

Se a pergunta for "quais scripts eu realmente vou usar?", a resposta curta e:

- para o fluxo normal: `config.py`, `generator.py`, `estimator.py`, `profiler.py`, `report.py`
- para sanity test e fixtures: `recover_tflite_from_header.py`, `generate_float32_dataset.py`
- para repetir o artigo: `experiments/run_benchmark_suite.py` e `experiments/analyze_benchmark_suite.py`
