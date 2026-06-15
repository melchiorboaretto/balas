# Status STM32/TFLM apos correcao de scratch Conv2D

Data: 2026-06-15

## Resumo

O port TFLM para a `NUCLEO-H723ZG` saiu do estado de desempenho inferior ao
NXP. A causa principal era que as 7 convolucoes 3x3 do sanity model caiam no
fallback de referencia porque `arm_convolve_s8` recebia `ctx.buf == NULL`.

A instrumentacao confirmou:

```text
Antes:  calls=9  cmsis_success=2  fallback_int8=7
Depois: calls=9  cmsis_success=9  fallback_int8=0
```

Primeiro a causa foi validada com um scratch buffer global de 8 KB. Em seguida,
o scratch foi movido para alocacao dentro da arena do TFLM via
`context->AllocatePersistentBuffer(...)`, removendo o buffer global fixo. A arena
do backend STM32/TFLM foi ajustada para `81920` bytes.

## Resultado atual

Linha valida mais recente em `artifacts/stm32_tflm_suite.csv`:

| Campo | Valor |
| --- | ---: |
| status | `ok` |
| alvo | `stm32/tflm` |
| amostras | `10` |
| arena | `81920` |
| MACs | `12501632` |
| media MCU | `42720.8 us` |
| desvio MCU | `4.166533331199931 us` |

Comparacao no sanity model:

| Placa / backend | Media |
| --- | ---: |
| FRDM-MCXN947 / TFLM NXP | `234708.2 us` |
| NUCLEO-H723ZG / TFLM STM32 corrigido | `42720.8 us` |
| NUCLEO-H723ZG / ST Edge AI historico | `~23388 us` |

O STM32/TFLM corrigido ficou cerca de `5.5x` mais rapido que o NXP/TFLM
historico neste fixture, e cerca de `1.8x` mais lento que o ST Edge AI.

## Estado tecnico

- O port STM32/TFLM esta funcional no pipeline BALAS.
- A suite oficial executa as 10 amostras e grava CSV comparavel.
- O desempenho inferior inicial foi explicado por fallback de `Conv2D`.
- O scratch Conv2D ja nao depende de buffer global estatico; agora e alocado
  pela arena persistente do TFLM.
- Ainda existe uma pendencia: o overlay scratch nativo do TFLM registra indices
  validos (`buffer_idx_valid=7`), mas `GetScratchBuffer()` retorna `NULL`
  (`arena_scratch=0`) neste port. Investigar isso pode reduzir a arena e deixar
  a integracao mais limpa.
- Ainda existe o workaround de reconstruir o interpretador por inferencia para
  evitar corrupcao da metadata persistente do tensor de entrada apos `Invoke()`.

## Arquivos principais

- `scripts/patches/tflm-stm32-cmsis-nn-conv.patch`
- `cpp-project/stm32-tflite-test/Core/Model/model.h`
- `testdata/sanity-model/stm32-tflm-suite.json`
- `python_scripts/diag_markers.py`
- `docs/020_tflm-stm32-cmsis-nn-reentrada-e-fallbacks.md`
- `docs/021_relatorio_desempenho_stm32_vs_nxp.md`

