# Relatório Detalhado das Alterações: Alinhamento dos Modelos ao MLPerf Tiny

**Data:** Outubro de 2026  
**Projeto:** B.A.L.A.S (Benchmarking and Automated Latency Assessment Suite)  
**Assunto:** Correção dos geradores de modelos (DSE Builders), alinhamento topológico ao MLPerf Tiny v1.0/v1.1 e definição do espaço de exploração.

---

## 1. Diagnóstico Inicial e Motivação

### 1.1. O Problema Identificado
Uma análise comparativa direta entre os modelos gerados pelo BALAS e o repositório oficial do MLPerf Tiny (`/home/cami/Documentos/tiny`) revelou que 3 dos 4 benchmarks estavam **excessivamente simplificados (modelos toy)**:

1. **Anomaly Detection (AD / ToyADMOS):**
   * *MLPerf Tiny Oficial:* Deep Autoencoder de **10 camadas Dense**, todas com `BatchNormalization` e `ReLU`, afunilamento central estrito (gargalo de 8 neurônios) e saída linear.
   * *BALAS Anterior:* Apenas **6 camadas Dense**, sem nenhuma camada de Batch Normalization, com ativação ReLU na saída (truncando valores negativos de reconstrução) e dimensões não padronizadas.
2. **Keyword Spotting (KWS / Speech Commands):**
   * *MLPerf Tiny Oficial:* Rede convolucional separável **DS-CNN** com 1 Convolução 2D inicial retangular `(10, 4)` com stride `(2, 2)` + **4 blocos Depthwise Separable** completos, todos com `BatchNormalization` (total de 9 convoluções com BatchNorm).
   * *BALAS Anterior:* Apenas **2 blocos Depthwise Separable** (5 convoluções ao todo), stride temporal incorreto `(2, 1)` e sem Batch Normalization.
3. **Visual Wake Words (VWW / Person Detection):**
   * *MLPerf Tiny Oficial:* Rede **MobileNetV1 ($\alpha = 0.25$)** completa de 96x96x3, contendo **13 blocos Depthwise Separable** (27 camadas convolucionais com Batch Normalization).
   * *BALAS Anterior:* Modelo de brinquedo com apenas **2 blocos convolucionais** (5 convoluções), representando menos de 18% da profundidade do modelo original.

### 1.2. Por que a Simplificação Anterior era Danosa?
Mesmo quando o objetivo do trabalho não é medir acurácia de treino (foco em métricas de hardware: latência, SRAM/Tensor Arena e Flash), modelos excessivamente pequenos:
* **Não estressam a memória:** Cabem inteiramente nos caches e buffers rápidos do microcontrolador, mascarando os gargalos reais de transferência de dados e de escalonamento da Tensor Arena.
* **Ignoram operadores essenciais:** A ausência de `BatchNormalization` muda a etapa de quantização (*quantization folding*), gerando tensores com escalas e offsets diferentes da literatura.
* **Perdem relevância científica:** Os resultados obtidos em placas como NXP MCXN947 ou STM32 não poderiam ser comparados com as métricas publicadas do MLPerf Tiny.

---

## 2. Relação Exata das Alterações Feitas

### 2.1. Builder de Anomaly Detection
* **Arquivo modificado:** [`python_scripts/dse/builders/anomaly_detection.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/anomaly_detection.py)
* **O que foi feito:**
  1. A arquitetura foi reescrita para instanciar o Deep Autoencoder completo:
     * **Encoder:** 4 camadas `Dense(128)` com `BatchNormalization` e `Activation('relu')`.
     * **Bottleneck:** 1 camada `Dense(8)` com `BatchNormalization` e `Activation('relu')`.
     * **Decoder:** 4 camadas `Dense(128)` com `BatchNormalization` e `Activation('relu')`.
     * **Saída:** 1 camada `Dense(640)` com ativação linear `None` (restaura a formulação correta de autoencoder acústico).
  2. Implementado dicionário `_DEFAULTS` com os valores exatos de referência (`hidden_units: 128`, `bottleneck_units: 8`, `num_hidden_layers: 4`).
  3. Adicionado suporte ao grid DSE configurável e compatibilidade retroativa para nomes legados (`large_fc`, `medium_fc`, `small_fc`).
  4. Mantida quantização para `int8` via dataset sintético representativo (100 amostras, seed 72).
* **Por que foi feito:** Para que a referência produza rigorosamente os **264.192 MACs** do MLPerf Tiny e permita explorar a profundidade e largura das camadas densas sem deformar a natureza do autoencoder.

---

### 2.2. Builder de Keyword Spotting
* **Arquivo modificado:** [`python_scripts/dse/builders/keyword_spotting.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/keyword_spotting.py)
* **O que foi feito:**
  1. Convolução inicial corrigida para strides `(2, 2)` (tempo e frequência) com `BatchNormalization`.
  2. O número de blocos Depthwise Separable foi expandido para **4 blocos padrão** (cada um com `DepthwiseConv2D 3x3` + `BN` + `ReLU` seguido de `Conv2D 1x1` + `BN` + `ReLU`).
  3. A cabeça de pooling e classificação foi ajustada com `GlobalAveragePooling2D` e `Dense(12, softmax)`. *(Corrigido na revisão da seção 5: o oficial usa `AveragePooling2D(25x5)` + `Flatten`.)*
  4. Dicionário `_DEFAULTS` definido com os valores canônicos (`first_conv_channels: 64`, `first_kernel_row: 10`, `first_kernel_col: 4`, `ds_blocks: 4`, `ds_channels: 64`, `ds_kernel_size: 3`).
* **Por que foi feito:** Para reproduzir exatamente a arquitetura DS-CNN do Speech Commands, atingindo exatamente os **2.656.768 MACs** oficiais do MLPerf Tiny.

---

### 2.3. Builder de Visual Wake Words
* **Arquivo modificado:** [`python_scripts/dse/builders/visual_wake_words.py`](file:///home/cami/Documentos/balas/python_scripts/dse/builders/visual_wake_words.py)
* **O que foi feito:**
  1. A rede foi reestruturada para seguir fielmente a **MobileNetV1 ($\alpha = 0.25$)** com todos os seus **13 blocos Depthwise Separable**:
     * Convolução inicial de 8 canais ($32 \times 0.25$) com stride 2.
     * Blocos 1 a 6 com progressão de canais 16, 32, 32, 64, 64, 128 e strides correspondentes.
     * Estágio central de 5 blocos repetidos com 128 canais.
     * Blocos finais 12 e 13 com 256 canais.
     * Todas as convoluções com `BatchNormalization` e `Activation('relu')`.
  2. Dicionário `_DEFAULTS` definido com `alpha: 0.25`, `middle_blocks: 5`, `kernel_size: 3`.
  3. Parametrização elegante via `alpha` (controlando a largura de toda a rede) e `middle_blocks` (permitindo podar ou expandir a profundidade central).
* **Por que foi feito:** O modelo anterior com 2 blocos não representava uma MobileNet. A nova implementação atinge exatamente os **7.489.664 MACs** oficiais do MLPerf Tiny v1.0/v1.1.

---

### 2.4. Criação dos Arquivos de Configuração de Referência
Foram criados três novos arquivos TOML de ponto único (grid com 1 combinação fixa) que servem como ponto âncora para caracterizar o hardware nas condições exatas do benchmark:
* [`configs/ad_reference.toml`](file:///home/cami/Documentos/balas/configs/ad_reference.toml)
* [`configs/kws_reference.toml`](file:///home/cami/Documentos/balas/configs/kws_reference.toml)
* [`configs/vww_reference.toml`](file:///home/cami/Documentos/balas/configs/vww_reference.toml)
*(O arquivo [`configs/cifar_10_reference.toml`](file:///home/cami/Documentos/balas/configs/cifar_10_reference.toml) para ResNet-8 já existia no repositório).*

---

### 2.5. Atualização dos Arquivos de Busca DSE
Os arquivos de exploração contínua foram atualizados para conter grids com variações plausíveis centradas na referência oficial:
* [`configs/ad.toml`](file:///home/cami/Documentos/balas/configs/ad.toml): Varia largura oculta (32 a 256), bottleneck (4 a 64) e profundidade (2 a 5 camadas).
* [`configs/kws.toml`](file:///home/cami/Documentos/balas/configs/kws.toml): Varia canais da 1ª conv (16 a 96), kernel inicial (6 a 12 linhas, 2 a 6 colunas), blocos DS (2 a 5), canais DS (16 a 128) e tamanho do kernel (3 ou 5).
* [`configs/vww.toml`](file:///home/cami/Documentos/balas/configs/vww.toml): Varia multiplicador `alpha` (0.125 a 0.5), profundidade central `middle_blocks` (1 a 5) e tamanho do kernel (3 ou 5).

---

### 2.6. Criação da Suíte de Testes Automatizada
* **Arquivo criado:** [`python_scripts/tests/test_dse_builders_exhaustive.py`](file:///home/cami/Documentos/balas/python_scripts/tests/test_dse_builders_exhaustive.py)
* **Cobertura dos testes:**
  1. Validação de chaves TOML de todos os arquivos de configuração (nenhuma chave desconhecida).
  2. Validação matemática exata de MACs contra o MLPerf Tiny oficial (0 diferença em todos os 4 modelos).
  3. Teste dinâmico de amostragem multi-seed de dezenas de modelos com compilação e quantização real para `.tflite` `int8`.
  4. Teste de compatibilidade regressiva para chaves legadas.

---

## 3. Validação Comparativa (Gabarito de MACs)

A execução dos testes unitários contra os binários `.tflite` clonados do MLPerf Tiny comprovou a equivalência:

```
Benchmark               MACs MLPerf Tiny Oficial      MACs BALAS Gerado      Diferença
--------------------------------------------------------------------------------------
Anomaly Detection                        264.192                264.192              0
Keyword Spotting                       2.656.768              2.656.768              0
Visual Wake Words                      7.489.664              7.489.664              0
Image Classification (ResNet8)        12.501.632             12.501.632              0
```

---

## 4. Por que Todos os Modelos Estão em `int8`?
Todos os modelos gerados são estritamente quantizados em **`int8` (Full Integer Quantization)** porque:
1. É a exigência normativa do MLPerf Tiny para sistemas embarcados.
2. Permite que o microcontrolador execute instruções SIMD do **CMSIS-NN**, processando 4 operações por ciclo de clock.
3. Reduz a pegada de Flash e SRAM em 75% em comparação com `float32`.
4. O host envia tensores em float32 pela UART, e o firmware C++ embarcado quantiza para int8 antes de executar no interpretador TensorFlow Lite Micro.

---

## 5. Revisão de Fidelidade Operador por Operador (27/10/2026)

### 5.1. Por que revisar
As seções anteriores validaram a fidelidade **só pela contagem de MACs**. MACs iguais não garantem modelos iguais: dois operadores diferentes podem fazer a mesma conta, e a CPU e a NPU tratam cada operador de um jeito. Para comparar CPU × NPU, o `.tflite` gerado pelo BALAS precisa ter **os mesmos operadores** dos `.tflite` oficiais do MLPerf Tiny.

### 5.2. Como foi verificado
Os quatro modelos de referência (`configs/*_reference.toml`) foram gerados com os builders e comparados camada por camada com os modelos oficiais do repositório `tiny`:

| Benchmark | Modelo oficial comparado |
|---|---|
| AD | `benchmark/training/anomaly_detection/trained_models/ad01_int8.tflite` |
| KWS | `benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite` |
| VWW | `benchmark/training/visual_wake_words/trained_models/vww_96_int8.tflite` |
| IC | `benchmark/training/image_classification/trained_models/pretrainedResnet_quant.tflite` |

Foram comparados: sequência de operadores, formato dos pesos e das saídas, ativação embutida (fused), padding, stride, tipo de quantização dos pesos (por canal / por tensor), presença de bias, tipo de entrada/saída e MACs.

### 5.3. O que já estava correto
* Arquitetura: mesmas camadas, formatos e número de pesos nos quatro modelos.
* MACs: idênticos (264.192 / 2.656.768 / 7.489.664 / 12.501.632), como afirmado na seção 3.
* Convoluções: mesma ativação (ReLU embutida), padding, stride e quantização por canal.
* Entrada e saída em `int8`.
* Nenhuma ReLU aparece como operador separado: BatchNorm e ReLU são absorvidos pela convolução/densa anterior na conversão.

### 5.4. Diferenças encontradas e corrigidas

| # | Diferença | Onde | Causa | Correção |
|---|---|---|---|---|
| 1 | `MEAN` no lugar de `AVERAGE_POOL_2D` + `RESHAPE` | KWS, VWW | O builder usava `GlobalAveragePooling2D`; o oficial (`keras_model.py`/`vww_model.py`) usa `AveragePooling2D(pool_size=mapa final)` + `Flatten` | Cabeça trocada para `AveragePooling2D` + `Flatten` |
| 2 | Operadores extras `SHAPE`, `STRIDED_SLICE`, `PACK`, `RESHAPE` | IC (e KWS/VWW após a correção 1) | Com lote variável (`batch=None`) o `Flatten` vira cálculo dinâmico de formato | `tf.keras.Input(..., batch_size=1)` em todos os builders; os oficiais também são de lote 1 |
| 3 | `FULLY_CONNECTED` sem bias | AD (10 camadas) e última camada de KWS/VWW/IC | Pesos aleatórios com bias inicializado em zero: o conversor descarta bias nulo. Nos modelos treinados o bias é diferente de zero | `bias_initializer="random_normal"` nas camadas `Dense` |
| 4 | `FULLY_CONNECTED` quantizada por canal (oficial: por tensor) | Mesmas camadas do item 3 | O TensorFlow atual (2.21) quantiza camadas densas por canal por padrão; os oficiais foram gerados com versões antigas | `converter._experimental_disable_per_channel_quantization_for_dense_layers = True` |

Após as correções, a comparação dá **0 camadas com atributos diferentes** nos quatro modelos.

**Desvio remanescente (aceito):** os oficiais têm um `RESHAPE` entre o pooling e a `FULLY_CONNECTED`. Ele não faz cálculo (só muda o formato de `[1,1,1,C]` para `[1,C]`), e o conversor atual o remove automaticamente.

**Por que os itens 3 e 4 importam para a NPU:** a documentação da NXP indica suporte da Neutron a `FULLY_CONNECTED` com quantização **por canal**. Com quantização por tensor, como no modelo oficial, essas camadas podem ficar na CPU. O BALAS passa a reproduzir o comportamento do modelo oficial, e a confirmação de onde cada camada roda vem do Neutron Converter (seção 5.7).

### 5.5. Arquivos alterados
* `python_scripts/dse/builders/keyword_spotting.py`: itens 1, 2, 3, 4.
* `python_scripts/dse/builders/visual_wake_words.py`: itens 1, 2, 3, 4.
* `python_scripts/dse/builders/cifar_ten.py`: itens 2, 3, 4.
* `python_scripts/dse/builders/anomaly_detection.py`: itens 2, 3, 4.
* `python_scripts/tests/test_dse_builders_exhaustive.py`: novo `test_06b_reference_operator_sequence`, que verifica a sequência de operadores e o bias/quantização das `FULLY_CONNECTED`. Os 12 testes passam.

As correções valem também para as variações do DSE, já que a cabeça e a conversão são as mesmas para todas.

### 5.6. Limitações que permanecem
* **Pesos aleatórios:** a latência é representativa (mesmos operadores e MACs), mas a **acurácia não pode ser medida**. Na NPU, a descompressão de pesos pode se comportar de forma ligeiramente diferente com pesos aleatórios do que com pesos treinados.
* **Correções do documento `026_tutorial-npu-mcxn947.md`:** a lista de operadores dele está incompleta (não cita `SOFTMAX`, `ADD`, `AVERAGE_POOL_2D`) e diz que o ResNet-8 usa `MAX_POOL_2D`, mas ele usa `AVERAGE_POOL_2D`. A tabela "Dados Oficiais NXP" de desempenho não teve fonte encontrada; não usar esses números como referência.

### 5.7. O que falta para a comparação CPU × NPU
Hoje o fluxo do BALAS na NXP (`cpp-project/tflite-test`) mede **só CPU**: usa uma `libtensorflow-microlite.a` própria, sem driver da NPU, e não tem etapa de conversão para a Neutron. Para gerar o dataset CPU × NPU:

1. **Baixar o eIQ Neutron SDK 3.2.2 (Linux)**, que contém o `neutron-converter`. A versão precisa ser a mesma das bibliotecas `libNeutronDriver.a`/`libNeutronFirmware.a` do MCUXpresso SDK 26.09; com versões diferentes o firmware recusa o modelo ("Microcode version mismatch").
2. **Converter cada `.tflite` gerado:** `neutron-converter --input modelo.tflite --output modelo_npu.tflite --target mcxn94x --dump-header-file-output`. O relatório do conversor mostra o que virou `NEUTRON_GRAPH` (NPU) e o que ficou na CPU.
3. **Criar um projeto NXP com o TFLite Micro do SDK e as bibliotecas Neutron**, usando como base o exemplo `eiq_examples/tflm_kws` do SDK 26.09 (validado na placa: ~4 ms por inferência na NPU). Importante: ao importar exemplos do SDK 26.09 na IDE 25.6, ajustar *TrustZone Project Type* para **None** no compilador C e no linker C++, ou o link falha.
4. **Gerar o resolver com `NEUTRON_GRAPH`** (`AddCustom(tflite::GetString_NEUTRON_GRAPH(), tflite::Register_NEUTRON_GRAPH())`) mais os operadores que ficaram na CPU.
5. **Medir a CPU no mesmo projeto**, com o `.tflite` sem conversão, para que a única diferença entre as colunas seja a NPU (e não a versão do TFLite Micro).
6. **Acrescentar uma coluna `backend` (cpu/npu)** nos CSVs.
