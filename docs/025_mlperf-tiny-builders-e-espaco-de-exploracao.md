# Reestruturação dos Builders DSE: Alinhamento com MLPerf Tiny e Espaço de Exploração

## 1. Contexto e Motivação

O projeto BALAS visa realizar **Design Space Exploration (DSE)** e medição precisa de métricas físicas em hardware (latência de inferência, ocupação da Tensor Arena em SRAM, código de Flash e energia) em microcontroladores (NXP MCXN947, STM32 NUCLEO-H723ZG, Nordic nRF52840-DK).

Anteriormente, os geradores de modelos (`python_scripts/dse/builders/`) apresentavam uma simplificação excessiva em relação aos benchmarks oficiais do **MLPerf Tiny v1.0/v1.1**:
- **Anomaly Detection (AD):** Implementava um autoencoder raso de 6 camadas sem Batch Normalization e com saída ReLU.
- **Keyword Spotting (KWS):** Implementava um modelo com apenas 2 blocos Depthwise Separable (5 convoluções), sem Batch Normalization e com stride temporal diferente `(2, 1)`.
- **Visual Wake Words (VWW):** Implementava uma rede toy com apenas 2 blocos convolucionais (5 convoluções) em vez dos 13 blocos da MobileNetV1.

Essa disparidade impedia que as medições de hardware refletissem o comportamento de cargas de trabalho reais de TinyML. Os builders foram reformulados para que:
1. **Ponto de Partida (Baseline):** A configuração padrão reproduza **com exatidão matemática de 100% a topologia, tipos de camada e contagem de MACs do MLPerf Tiny oficial**.
2. **Espaço de Exploração Plausível:** O grid de hiperparâmetros varie largura e profundidade **ao redor da arquitetura de referência oficial**.

---

## 2. Topologia de Referência vs. Implementação BALAS

A tabela abaixo resume a correspondência exata obtida entre os builders do BALAS e o MLPerf Tiny oficial:

| Benchmark | Modelo Oficial MLPerf Tiny | Resolução Entrada | Saída | MACs Oficiais | MACs BALAS Ref | Diferença MACs |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **AD** | Deep Autoencoder (10 Dense + BN) | `[1, 640]` | `[1, 640]` | **264.192** | **264.192** | **0** |
| **KWS** | DS-CNN (1 Conv + 4 blocos DS + BN) | `[1, 49, 10, 1]` | `[1, 12]` | **2.656.768** | **2.656.768** | **0** |
| **VWW** | MobileNetV1 $\alpha=0.25$ (13 blocos DS + BN) | `[1, 96, 96, 3]` | `[1, 2]` | **7.489.664** | **7.489.664** | **0** |
| **IC** | ResNet-8 (3 estágios residuais + BN) | `[1, 32, 32, 3]` | `[1, 10]` | **12.501.632** | **12.501.632** | **0** |

---

## 3. Detalhamento por Benchmark

### 3.1. Anomaly Detection (ToyADMOS)
* **Arquivo do Builder:** [`python_scripts/dse/builders/anomaly_detection.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/anomaly_detection.py)
* **Configs:**
  * Referência exata: [`configs/ad_reference.toml`](file:///home/cami/Documentos/balas/configs/ad_reference.toml)
  * Busca DSE: [`configs/ad.toml`](file:///home/cami/Documentos/balas/configs/ad.toml)
* **Arquitetura Oficial:**
  * Entrada: 640 floats (5 frames $\times$ 128 mel-bins) quantizados em int8.
  * Encoder: 4 camadas de `Dense(128)` com `BatchNormalization` e `Activation('relu')`.
  * Bottleneck: 1 camada `Dense(8)` com `BatchNormalization` e `Activation('relu')`.
  * Decoder: 4 camadas de `Dense(128)` com `BatchNormalization` e `Activation('relu')`.
  * Saída: `Dense(640)` com ativação linear (reconstrução do sinal espectral).
* **Espaço de Exploração (`configs/ad.toml`):**
  * `hidden_units`: `[32, 64, 96, 128, 160, 192, 256]` (ref = 128)
  * `bottleneck_units`: `[4, 8, 12, 16, 24, 32, 48, 64]` (ref = 8)
  * `num_hidden_layers`: `[2, 3, 4, 5]` (camadas no encoder e decoder; ref = 4)
  * Espaço combinatório bruto: $7 \times 8 \times 4 = 224$ variações plausíveis.

---

### 3.2. Keyword Spotting (Speech Commands)
* **Arquivo do Builder:** [`python_scripts/dse/builders/keyword_spotting.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/keyword_spotting.py)
* **Configs:**
  * Referência exata: [`configs/kws_reference.toml`](file:///home/cami/Documentos/balas/configs/kws_reference.toml)
  * Busca DSE: [`configs/kws.toml`](file:///home/cami/Documentos/balas/configs/kws.toml)
* **Arquitetura Oficial:**
  * Entrada: `[1, 49, 10, 1]` (49 passos temporais, 10 coeficientes MFCC).
  * Convolução Inicial: `Conv2D(64, (10, 4), strides=(2, 2))` + `BatchNormalization` + `ReLU`.
  * 4 Blocos Depthwise Separable:
    * `DepthwiseConv2D((3, 3), padding='same')` + `BN` + `ReLU`
    * `Conv2D(64, (1, 1), padding='same')` + `BN` + `ReLU`
  * Cabeça: `AveragePooling2D(25x5)` $\rightarrow$ `Flatten` $\rightarrow$ `Dense(12, softmax)` (ver seção 5 do `RELATORIO_ALTERACOES_MLPERF_TINY.md`).
* **Espaço de Exploração (`configs/kws.toml`):**
  * `first_conv_channels`: `[16, 24, 32, 48, 64, 80, 96]` (ref = 64)
  * `first_kernel_row`: `[6, 8, 10, 12]` (ref = 10)
  * `first_kernel_col`: `[2, 4, 6]` (ref = 4)
  * `ds_blocks`: `[2, 3, 4, 5]` (ref = 4)
  * `ds_channels`: `[16, 24, 32, 48, 64, 80, 96, 128]` (ref = 64)
  * `ds_kernel_size`: `[3, 5]` (ref = 3)
  * Espaço combinatório bruto: $7 \times 4 \times 3 \times 4 \times 8 \times 2 = 5.376$ variações.

---

### 3.3. Visual Wake Words (Person Detection)
* **Arquivo do Builder:** [`python_scripts/dse/builders/visual_wake_words.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/visual_wake_words.py)
* **Configs:**
  * Referência exata: [`configs/vww_reference.toml`](file:///home/cami/Documentos/balas/configs/vww_reference.toml)
  * Busca DSE: [`configs/vww.toml`](file:///home/cami/Documentos/balas/configs/vww.toml)
* **Arquitetura Oficial:**
  * Entrada: `[1, 96, 96, 3]`.
  * Convolução Inicial: `Conv2D(8, (3, 3), strides=2)` + `BatchNorm` + `ReLU` ($8 = 32 \times \alpha$).
  * 13 Blocos Depthwise Separable com canais escalados por $\alpha=0.25$:
    * Bloco 1: DW(s=1) $\rightarrow$ PW(16)
    * Bloco 2: DW(s=2) $\rightarrow$ PW(32)
    * Bloco 3: DW(s=1) $\rightarrow$ PW(32)
    * Bloco 4: DW(s=2) $\rightarrow$ PW(64)
    * Bloco 5: DW(s=1) $\rightarrow$ PW(64)
    * Bloco 6: DW(s=2) $\rightarrow$ PW(128)
    * Blocos 7 a 11 (5 blocos repetidos centrais): DW(s=1) $\rightarrow$ PW(128)
    * Bloco 12: DW(s=2) $\rightarrow$ PW(256)
    * Bloco 13: DW(s=1) $\rightarrow$ PW(256)
  * Cabeça: `AveragePooling2D(3x3)` $\rightarrow$ `Flatten` $\rightarrow$ `Dense(2, softmax)` (ver seção 5 do `RELATORIO_ALTERACOES_MLPERF_TINY.md`).
* **Espaço de Exploração (`configs/vww.toml`):**
  * `alpha`: `[0.125, 0.1875, 0.25, 0.3125, 0.375, 0.5]` (multiplicador de largura MobileNet; ref = 0.25)
  * `middle_blocks`: `[1, 2, 3, 4, 5]` (profundidade de repetição no estágio central; ref = 5, correspondendo a 9 a 13 blocos)
  * `kernel_size`: `[3, 5]` (ref = 3)
  * Espaço combinatório bruto: $6 \times 5 \times 2 = 60$ variações.

---

### 3.4. Image Classification (CIFAR-10)
* **Arquivo do Builder:** [`python_scripts/dse/builders/cifar_ten.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/cifar_ten.py)
* **Configs:**
  * Referência exata: [`configs/cifar_10_reference.toml`](file:///home/cami/Documentos/balas/configs/cifar_10_reference.toml)
  * Busca DSE: [`configs/cifar_10.toml`](file:///home/cami/Documentos/balas/configs/cifar_10.toml)
* **Arquitetura Oficial:**
  * ResNet-8 com Stem de 16 canais e 3 estágios residuais (16, 32 e 64 canais).
  * 12.501.632 MACs.

---

## 4. Como Executar os Experimentos

### 4.1. Execução do Ponto de Referência Oficial
Para rodar a referência exata de cada tarefa na placa:

```bash
# Anomaly Detection (264.192 MACs)
uv run python_scripts/run_continuous_experiment.py --config-toml configs/ad_reference.toml --max-iterations 1

# Keyword Spotting (2.656.768 MACs)
uv run python_scripts/run_continuous_experiment.py --config-toml configs/kws_reference.toml --max-iterations 1

# Visual Wake Words (7.489.664 MACs)
uv run python_scripts/run_continuous_experiment.py --config-toml configs/vww_reference.toml --max-iterations 1

# Image Classification (12.501.632 MACs)
uv run python_scripts/run_continuous_experiment.py --config-toml configs/cifar_10_reference.toml --max-iterations 1
```

### 4.2. Execução da Busca DSE Multi-seed
Para rodar a exploração paramétrica automatizada:

```bash
# Roda 50 iterações de busca em KWS
uv run python_scripts/run_continuous_experiment.py --config-toml configs/kws.toml --max-iterations 50

# Ou roda a suite completa de benchmarks
uv run run_all_benchmarks.py --max-iterations-per-config 20
```

### 4.3. Execução dos Testes Automatizados da Suíte
Para validar a integridade dos modelos e builders sem necessidade de hardware conectado:

```bash
python python_scripts/tests/test_dse_builders_exhaustive.py
```
