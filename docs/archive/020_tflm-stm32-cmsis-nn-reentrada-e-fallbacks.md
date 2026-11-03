# TFLM/STM32 CMSIS-NN: reentrada consecutiva e fallbacks

Data: 2026-06-14

## Objetivo

Deixar o backend TFLM/STM32 funcional de forma equivalente ao alvo de
referência NXP `FRDM-MCXN947`, para que o benchmark consiga rodar o dataset
inteiro sem reset entre amostras e produzir uma comparação válida.

Dois problemas herdados de `docs/019` precisavam ser resolvidos:

1. **Reentrada consecutiva**: a primeira inferência CMSIS-NN funciona
   (`~877978 us` para `sample_001.bin`), mas a segunda inferência na mesma
   sessão serial trava (>60s, timeout do profiler). Com reset do MCU entre
   amostras, ambas funcionam.
2. **Ganho marginal**: o CMSIS-NN parcial é apenas `~1.38x` mais rápido que os
   kernels de referência, enquanto a expectativa para Conv2D acelerado por DSP
   é de várias vezes. O NXP/TFLM histórico (`234708 us`) é mais rápido que o
   STM32/CMSIS-NN atual, o que é anômalo para um Cortex-M7 a 260 MHz.

## Investigação estática (continuação de docs/019)

A análise anterior já havia descartado várias hipóteses. Esta retomada fechou
mais alguns pontos:

### Buffer do `arm_convolve_1x1_s8_fast` é irrelevante no GCC

O caminho bufferizado de `arm_convolve_1x1_s8_fast` é compilado apenas sob:

```c
#if defined(ARM_MATH_DSP) && !defined(ARM_MATH_MVEI) && \
    defined(__ARMCC_VERSION) && (__ARMCC_VERSION >= 6010050)
```

Como a build usa `arm-none-eabi-gcc`, `__ARMCC_VERSION` nunca está definido.
Logo, o 1x1 cai direto em `arm_nn_mat_mult_nt_t_s8`, sem usar `ctx->buf`. Isso
é coerente com `arm_convolve_1x1_s8_fast_get_buffer_size` retornando `0` no
GCC. Hipótese de mismatch de buffer no 1x1 está descartada.

### A biblioteca CMSIS-NN ESTÁ com DSP habilitado

Confirmado que `arm-none-eabi-gcc -mcpu=cortex-m7` define automaticamente:

```text
__ARM_FEATURE_DSP 1
```

E `arm_nn_math_types.h` deriva `ARM_MATH_DSP 1` a partir disso. Portanto a
lentidão **não** vem de a CMSIS-NN ter sido compilada em modo escalar. O
caminho DSP SIMD está ativo na biblioteca.

### Conclusão da análise: a lentidão vem dos fallbacks para referência

Se a CMSIS-NN tem DSP ativo mas o ganho total é só `1.38x`, a explicação mais
provável é que a maioria dos `Conv2D` está caindo no fallback de referência
introduzido pelo patch `tflm-stm32-cmsis-nn-conv.patch` (o `convolve_wrapper`
rejeita o shape e o kernel usa `reference_integer_ops::ConvPerChannel`). Isso
precisa ser confirmado instrumentando o port por operador.

## Correções aplicadas nesta sessão

### 1. Tornar falha de `Invoke()` visível ao host

`Core/Model/model.cpp` tinha:

```cpp
if (interpreter.Invoke() != kTfLiteOk) {
    while (1) { }
}
```

Esse `while(1)` faz uma falha de `Invoke()` (retorno `kTfLiteError`) parecer
idêntica a uma computação infinita do ponto de vista do host: nos dois casos o
host só vê timeout. Foi trocado por um sentinela de erro + soft reset:

```cpp
if (interpreter.Invoke() != kTfLiteOk) {
    int32_t error_sentinel = -1;
    serial_write(reinterpret_cast<uint8_t *>(&error_sentinel), sizeof(error_sentinel));
    HAL_Delay(10);
    NVIC_SystemReset();
}
```

Efeito diagnóstico:

- se a segunda inferência retornar `-1` rapidamente, o `Invoke()` falhou com
  `kTfLiteError` (algum operador sem soft fallback, p. ex. FullyConnected);
- se ainda houver timeout, é um laço infinito real dentro do `Invoke()` ou do
  `serial_read`.

Os `#include "main.h"` e `#include "serial_io.h"` passaram a ser
incondicionais em `model.cpp` (antes só entravam com `BOOT_MARKER`).

### 2. Limpar flags de erro da UART antes de receber

`Core/Platform/serial_io.cpp`:

```cpp
void serial_read(uint8_t *dst, unsigned long n_bytes)
{
    __HAL_UART_CLEAR_FLAG(&huart3, UART_CLEAR_OREF | UART_CLEAR_NEF |
                                   UART_CLEAR_FEF | UART_CLEAR_PEF);
    HAL_UART_Receive(&huart3, dst, static_cast<uint16_t>(n_bytes), HAL_MAX_DELAY);
}
```

Hipótese: durante a primeira inferência (longa) ou na reabertura da VCP entre
amostras, a USART3 pode acumular Overrun/Framing/Parity Error. Com a flag de
erro setada, o `HAL_UART_Receive` bloqueante pode falhar ou nunca completar na
segunda amostra. Limpar as flags antes de cada recepção remove esse estado
residual.

### 3. Script de diagnóstico de duas amostras consecutivas

Novo `python_scripts/diag_two_samples.py`: abre `/dev/ttyACM0` uma única vez e
envia duas amostras seguidas, sem reset entre elas, reportando para cada uma se
recebeu um tempo válido, o sentinela `-1` ou timeout. Isso reproduz exatamente
o cenário que trava, de forma controlada.

## Diagnóstico em hardware (NUCLEO-H723ZG conectada)

Com a placa conectada, o diagnóstico com marcadores
(`python_scripts/diag_markers.py`) trocou a especulação por medições diretas.

### A segunda inferência NÃO trava no Invoke

Resultado de duas amostras consecutivas na mesma sessão serial:

```text
Sample 1: R Q G D V <878327 us> W      (saudável)
Sample 2: R Q  ...  TIMEOUT
```

A segunda inferência imprime `R` (recebeu) e `Q` (entrou em `run_inference`),
mas nunca chega ao `G`. Ou seja, o travamento está **entre `Q` e `G`**, dentro
de `float32_to_int8` — e não no `Invoke()`, como toda a análise anterior
(docs/019) assumia.

### HardFault confirmado por SWD

Halt via `STM32_Programmer_CLI ... -coreReg`:

```text
XPSR = 0x010F0003   -> exceção 3 = HardFault
LR   = 0xFFFFFFE9   -> EXC_RETURN (dentro de handler)
PC   = 0x08000992   -> HardFault_Handler (stm32h7xx_it.c:10, while(1))
CFSR = 0x00000400   -> bit 10 = IMPRECISERR (escrita de barramento imprecisa)
```

`addr2line` do PC empilhado aponta para `quantization.cpp:9`, dentro de
`float32_to_int8`.

### Causa raiz: metadata do tensor de entrada corrompida no Invoke

Dump diagnóstico enviado pela serial antes de `float32_to_int8`
(ponteiro do tensor, ponteiro de dados, contagem, arena usada):

```text
Sample 1: in_t=0x2000cbd0 data.int8=0x2000cbc4 count=3072 arena_used=54708/57344
Sample 2: in_t=0x00000000 data.int8=0x00000000 count=3072 arena_used=54708/57344
```

`interpreter.input_tensor(0)` retorna **NULL** na segunda inferência. Leitura da
memória da arena via SWD mostra a `TfLiteTensor` persistente do input
(em `0x2000cbd0`) **zerada** após o primeiro `Invoke()`. Como
`input_tensors_[0]` aponta para essa struct na cauda persistente da arena, o
primeiro `Invoke()` corrompe essa região. Na segunda inferência,
`float32_to_int8` escreve em `data.int8 = NULL` (região `0x0`/ITCM) → escrita de
barramento inválida → HardFault → `while(1)` → host vê timeout.

### O bug NÃO é do CMSIS-NN nem do tamanho da arena

- Recompilando a TFLM com kernels de **referência** (sem CMSIS-NN), a corrupção
  é **idêntica**: `in_t` vira NULL na segunda inferência.
- Aumentando a arena de 57344 para 81920 bytes, `arena_used` continua 54708 e a
  struct persistente continua sendo zerada (o layout do planner é o mesmo, só
  deslocado). Não é overflow absorvível por folga.
- O alvo de referência NXP usa o **mesmo modelo, a mesma arena (57344) e os
  mesmos 9 operadores**, porém com uma versão diferente do TFLM (eIQ/NXP,
  `TFLITE_SCHEMA_VERSION=3`). O `Invoke()` consecutivo é o padrão normal do TFLM
  e funciona no NXP; nesta versão upstream (`9f5ac257`) com este modelo (que tem
  flatten dinâmico `Shape→StridedSlice→Pack→Reshape`) ele corrompe a metadata
  persistente.

> O projeto NXP é a referência e **não foi alterado** — apenas inspecionado.

## Correção adotada: reconstruir o interpretador por inferência

Como a primeira inferência após uma inicialização limpa sempre produz uma
latência válida (o `Invoke()` usa o `EvalTensor`, com ponteiro separado da
`TfLiteTensor` corrompida), a solução é fazer cada inferência ser uma "primeira
inferência":

Em `Core/Src/main_model.cpp`, o loop passou a **reconstruir `MyModel`** (e com
isso re-executar `AllocateTensors()`, que re-planeja a arena do zero) a cada
amostra. A reconstrução fica **fora** de `start_timing()/stop_timing()`, então
não afeta a latência medida. Isso equivale ao "reset entre amostras" que já era
sabido funcionar, mas sem resetar o MCU.

Resultado (kernels de referência, 3 amostras consecutivas, porta persistente):

```text
Sample 1: R Q G D V <1215584 us> W
Sample 2: R Q G D V <1215453 us> W
Sample 3: R Q G D V <1215562 us> W
```

`in_t` permanece em `0x2000cbd0` (restaurado a cada reconstrução) e a sequência
de marcadores fica completa nas três. O port TFLM/STM32 passou a rodar
inferências consecutivas de forma estável.

## Validação final em produção

Com CMSIS-NN (patches aplicados) e a reconstrução por inferência, o firmware de
produção (sem marcadores) foi gravado e o profiler padrão
(`send_profiling_inputs`, que reabre a porta serial por amostra) rodou o dataset
completo **sem reset entre amostras**:

```text
Inference 1/10: 877983 us
...
Inference 10/10: 877966 us
N = 10  media = 877972.9 us  min = 877964  max = 877994
```

As 10 amostras consecutivas completaram de forma estável e repetível
(variação < 30 us). O port TFLM/STM32 está funcional como o alvo de referência
NXP para fins de comparação.

## Comparativo (sanity model 1x32x32x3, ~12.5M MACs)

| Alvo | Backend | Tempo (µs) | Observação |
| --- | --- | ---: | --- |
| NUCLEO-H723ZG | ST Edge AI | ~23388 | histórico |
| FRDM-MCXN947 | TFLM/NXP (CMSIS-NN) | ~234708 | referência, histórico |
| NUCLEO-H723ZG | TFLM CMSIS-NN | ~877973 | **funcional, este doc** |
| NUCLEO-H723ZG | TFLM referência | ~1215500 | funcional |

O STM32/TFLM-CMSIS-NN ainda é ~3.7x mais lento que o NXP/TFLM, apesar do
Cortex-M7 a 260 MHz. A explicação provável é a quantidade de `Conv2D` caindo no
fallback de referência (o ganho de só ~1.38x sobre a referência pura sugere que
o caminho CMSIS-NN otimizado está sendo pouco usado). A `libtensorflow-microlite`
foi confirmada com DSP habilitado (`__ARM_FEATURE_DSP=1` em `cortex-m7`), então a
otimização existe na lib; falta entender por que o wrapper rejeita as camadas.

## Estado / próximos passos

- [x] Causa raiz do travamento consecutivo identificada (HardFault em
      `float32_to_int8` por metadata de tensor corrompida no `Invoke()`)
- [x] Correção: reconstrução do interpretador por inferência
- [x] Verificado estável com kernels de referência (3x consecutivas)
- [x] Revalidado consecutivas com CMSIS-NN (3x + dataset completo de 10)
- [x] Dataset completo rodado sem reset com o profiler padrão
- [x] Registrada comparação STM32/TFLM em CSV via suite de benchmark
- [x] Instrumentados contadores de Conv2D CMSIS-NN/fallback
- [x] Causa principal do desempenho inferior isolada: `ctx.buf == NULL` no
      caminho `arm_convolve_s8` das convolucoes 3x3
- [x] Correção experimental: scratch estático de 8 KB para `arm_convolve_s8`
- [x] Scratch movido para alocação na arena persistente do TFLM
- [ ] Investigar por que o overlay scratch nativo do TFLM registra indices
      validos, mas `GetScratchBuffer` retorna `NULL`
- [ ] Avaliar posicionamento de memoria/codigo para reduzir o gap contra ST
      Edge AI

## Registro via suite de benchmark

Em 2026-06-15 foi adicionado o manifesto
`testdata/sanity-model/stm32-tflm-suite.json` e a suite foi executada contra a
`NUCLEO-H723ZG`:

```bash
.venv/bin/python python_scripts/experiments/run_benchmark_suite.py \
  testdata/sanity-model/stm32-tflm-suite.json \
  artifacts/stm32_tflm_suite.csv \
  --workstation-repeats 1
```

A primeira tentativa automatizada falhou com `Did not receive 4 bytes from
device`, porque o profiling começava imediatamente apos o reset do
`STM32_Programmer_CLI`. Foi adicionada uma espera pos-deploy para STM32 no
`run_benchmark_suite.py` e no `automator.py`, controlada por
`BALAS_STM32_POST_DEPLOY_DELAY_SEC` (padrao: `3` segundos).

Resultado valido gravado no CSV:

| Campo | Valor |
| --- | ---: |
| status | `ok` |
| amostras | `10` |
| arena | `57344` |
| MACs | `12501632` |
| media MCU | `878015.8 us` |
| desvio MCU | `60.61814909744441 us` |

Esse registro confirma que o port STM32/TFLM ja participa do pipeline BALAS,
mas a comparacao continua marcada como preliminar ate resolver os fallbacks
CMSIS-NN e as otimizacoes de memoria/runtime documentadas em `docs/021`.

## Rodada de otimizacao: TFLM/CMSIS-NN com `-O3`

Em 2026-06-15 foi testada uma primeira rodada de otimizacao de baixo risco:
recompilar a `libtensorflow-microlite.a` do STM32 com niveis `-O3` no Makefile
TFLM:

```bash
TFLM_OPTIMIZED_KERNEL_DIR=cmsis_nn \
TFLM_CORE_OPTIMIZATION_LEVEL=-O3 \
TFLM_KERNEL_OPTIMIZATION_LEVEL=-O3 \
TFLM_THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL=-O3 \
./scripts/build_tflm_stm32.sh
```

Depois disso o firmware foi compilado em `Release`, gravado e medido no mesmo
fixture. Medicao manual das 10 amostras:

```text
avg 705431.5 us  min 705382  max 705611
```

Medicao registrada pelo runner oficial:

| Campo | Valor |
| --- | ---: |
| status | `ok` |
| amostras | `10` |
| arena | `57344` |
| media MCU | `705410.6 us` |
| desvio MCU | `65.5914628591252 us` |

Comparado com a linha anterior (`878015.8 us`), a melhora foi de cerca de
`19.7%`. O script `scripts/build_tflm_stm32.sh` passou a usar `-O3` como padrao
para `CORE_OPTIMIZATION_LEVEL`, `KERNEL_OPTIMIZATION_LEVEL` e
`THIRD_PARTY_KERNEL_OPTIMIZATION_LEVEL`, mantendo as variaveis de ambiente como
override para futuras comparacoes.

## Rodada de otimizacao: Conv2D CMSIS-NN com scratch buffer

Em seguida foi instrumentado o kernel
`tensorflow/lite/micro/kernels/cmsis_nn/conv.cc` para contar, por inferencia:

- chamadas totais de `Conv2D`;
- sucessos no wrapper CMSIS-NN;
- fallbacks INT8 para `reference_integer_ops::ConvPerChannel`;
- chamadas/sucessos/fallbacks separados para filtros 1x1 e 3x3;
- uso de scratch persistente e caso de scratch insuficiente.

Diagnostico antes da correcao, em `sample_001.bin`:

```text
calls=9
cmsis_success=2
fallback_int8=7
calls_1x1=2 success_1x1=2 fallback_1x1=0
calls_3x3=7 success_3x3=0 fallback_3x3=7
scratch_missing=9
inference time: 731261 us
```

Isso confirmou a suspeita: as duas convolucoes 1x1 ja usavam CMSIS-NN, mas as
sete convolucoes 3x3 caiam no fallback de referencia.

A leitura do CMSIS-NN mostrou que `arm_convolve_wrapper_s8` encaminha as 3x3
para `arm_convolve_s8`, e `arm_convolve_s8` retorna
`ARM_CMSIS_NN_ARG_ERROR` imediatamente quando recebe `ctx->buf == NULL`. O
scratch deveria ter vindo da arena do TFLM, mas nesta integracao o contexto
chegava sem buffer.

Foi aplicada uma primeira correcao experimental no patch
`scripts/patches/tflm-stm32-cmsis-nn-conv.patch`: quando o caminho INT8 nao
1x1 chega com `ctx.buf == NULL`, o kernel calcula
`arm_convolve_s8_get_buffer_size(...)` e usa um scratch buffer alinhado se o
tamanho requerido couber. Inicialmente esse buffer era global/estatico de 8 KB,
apenas para validar a causa.

Diagnostico depois da correcao, na mesma amostra:

```text
calls=9
cmsis_success=9
fallback_int8=0
calls_1x1=2 success_1x1=2 fallback_1x1=0
calls_3x3=7 success_3x3=7 fallback_3x3=0
scratch_missing=9
persistent_scratch=7
scratch_too_small=0
inference time: 47778 us
```

Resultado registrado pelo runner oficial, sem marcadores:

| Campo | Valor |
| --- | ---: |
| status | `ok` |
| amostras | `10` |
| arena | `57344` |
| MACs | `12501632` |
| media MCU | `42728.4 us` |
| desvio MCU | `10.753604047016053 us` |

Comparado com a linha `-O3` anterior (`705410.6 us`), a melhora foi de cerca de
`16.5x`. Comparado com a referencia historica NXP/TFLM (`234708.2 us`), o
STM32/TFLM corrigido ficou cerca de `5.5x` mais rapido neste sanity model.

### Troca do scratch estatico por alocacao na arena

Em seguida foi testado se o problema era apenas arena insuficiente: aumentar
temporariamente `TENSOR_ARENA_SIZE` de `57344` para `81920` nao mudou o
diagnostico. Os pedidos de scratch eram registrados e os indices chegavam
validos no `Eval()`:

```text
buffer_idx_valid=7
last_buffer_idx=6
max_required_scratch=2304
arena_scratch=0
```

Ou seja, `RequestScratchBufferInArena()` atribuia indices para as 7 convolucoes
3x3, mas `GetScratchBuffer()` retornava `NULL` para esses indices. Isso indica
um problema no planejamento/commit dos handles de scratch do TFLM neste port,
nao falta de bytes brutos na arena.

Para remover o buffer global estatico, o patch passou a alocar o scratch via
`context->AllocatePersistentBuffer(context, buf_size)` dentro do `Prepare()` de
cada `Conv2D` que precisa de scratch. O `Eval()` ainda tenta o overlay nativo do
TFLM primeiro; se ele vier `NULL`, usa o scratch persistente da arena. Com isso:

```text
calls=9
cmsis_success=9
fallback_int8=0
calls_3x3=7 success_3x3=7 fallback_3x3=0
persistent_scratch=7
scratch_too_small=0
arena_scratch=0
max_required_scratch=2304
```

Resultado registrado pelo runner oficial, sem marcadores:

| Campo | Valor |
| --- | ---: |
| status | `ok` |
| amostras | `10` |
| arena | `81920` |
| MACs | `12501632` |
| media MCU | `42720.8 us` |
| desvio MCU | `4.166533331199931 us` |

Comparado com a versao com scratch global (`42728.4 us`), a latencia ficou
equivalente. A melhoria agora e de engenharia: o scratch sai de um buffer global
fixo e passa a ser propriedade da arena TFLM. A proxima etapa, mais limpa, e
corrigir o overlay scratch para permitir reutilizacao da memoria e reduzir a
arena novamente.
