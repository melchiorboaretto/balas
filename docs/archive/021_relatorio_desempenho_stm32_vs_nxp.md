# Relatorio de desempenho STM32 vs NXP para o experimento BALAS

Data: 2026-06-15

## Resumo executivo

O port para a `NUCLEO-H723ZG` ja executa o mesmo modelo de sanity usado na
`FRDM-MCXN947` e tambem gera CSV pela suite de benchmark do repositorio. Nesta
rodada, a principal causa do desempenho inicialmente inferior ao NXP foi
identificada e corrigida de forma experimental: as convolucoes 3x3 estavam
caindo no fallback de referencia porque o caminho `arm_convolve_s8` recebia
`ctx.buf == NULL`.

Resultado medido pela suite em 2026-06-15:

| Placa | Backend | Media MCU |
| --- | --- | ---: |
| FRDM-MCXN947 | TFLM/NXP | `234708.2 us` |
| NUCLEO-H723ZG | TFLM/STM32 CMSIS-NN parcial, `-O2` | `878015.8 us` |
| NUCLEO-H723ZG | TFLM/STM32 CMSIS-NN parcial, `-O3` | `705410.6 us` |
| NUCLEO-H723ZG | TFLM/STM32 CMSIS-NN + scratch Conv2D na arena | `42720.8 us` |
| NUCLEO-H723ZG | ST Edge AI historico | `~23388 us` |

O STM32/TFLM corrigido ficou cerca de `5.5x` mais rapido que o NXP/TFLM
historico neste modelo de sanity. Antes da correcao, ele era cerca de `3.0x`
mais lento mesmo com `-O3`; portanto o resultado inferior anterior era efeito
do port/runtime, nao uma limitacao conclusiva da placa.

## Principais causas tecnicas identificadas

1. **Causa principal encontrada: fallback nas convolucoes 3x3.**
   A instrumentacao mostrou `9` chamadas de `Conv2D`: as `2` convolucoes 1x1
   usavam CMSIS-NN, mas as `7` convolucoes 3x3 caiam em
   `reference_integer_ops::ConvPerChannel`. Isso explicava a media ruim de
   `705410.6 us`.

2. **Razao do fallback: scratch buffer ausente em `arm_convolve_s8`.**
   O wrapper CMSIS-NN encaminha as 3x3 para `arm_convolve_s8`, que retorna erro
   se `ctx->buf == NULL`. No port STM32/TFLM, esse buffer nao estava chegando ao
   kernel. Um scratch buffer estatico de 8 KB fez as 9 convolucoes retornarem
   sucesso via CMSIS-NN. A primeira validacao usou scratch global; a versao
   atual aloca esse scratch pela arena persistente do TFLM, com arena total de
   `81920` bytes, e reduziu a media para `42720.8 us`.

3. **A biblioteca TFLM/CMSIS-NN precisava de otimizacao de compilacao.**
   A primeira build estava efetivamente na configuracao padrao `-O2` do
   Makefile TFLM. Recompilar core, kernels e kernels de terceiros com `-O3`
   reduziu a media de `878015.8 us` para `705410.6 us`. Isso mostra que ainda
   havia ganho de toolchain disponivel.

4. **O runtime TFLM nao e o mesmo do NXP.**
   A FRDM usa a biblioteca TFLM do fluxo NXP/eIQ ja presente no projeto
   original. O STM32 usa uma biblioteca TFLM upstream gerada localmente e
   corrigida com patches. Portanto a comparacao ainda mistura placa, runtime,
   versao de TFLM, wrappers CMSIS-NN, toolchain e flags.

5. **Foi necessario contornar uma corrupcao de metadata do tensor.**
   No STM32/TFLM, apos uma inferencia, a metadata persistente do tensor de
   entrada ficava corrompida e a segunda amostra podia causar HardFault em
   `float32_to_int8`. O workaround atual reconstrui o interpretador a cada
   inferencia. Isso estabiliza a medicao porque fica fora da janela cronometrada,
   mas mostra que a integracao TFLM ainda nao esta madura.

6. **A alocacao e o mapa de memoria ainda nao foram otimizados.**
   O link atual mostra `ITCMRAM: 0 B`; codigo e dados criticos ainda nao foram
   posicionados de forma dirigida em ITCM/DTCM/AXI SRAM. Para Cortex-M7, esse
   tipo de posicionamento pode alterar desempenho de forma significativa.

7. **O fluxo automatizado precisava de estabilizacao pos-deploy.**
   A primeira execucao da suite falhou com `Did not receive 4 bytes from device`
   porque o profiling iniciava imediatamente apos o reset do
   `STM32_Programmer_CLI`. Foi adicionada uma espera pos-deploy para STM32, e a
   suite passou em seguida.

## Isso impede comparar com os resultados do BALAS?

Nao impede uma **comparacao de reproducao do fluxo BALAS**. Existe CSV da suite
usando o mesmo modelo, dataset, protocolo serial e contagem de MACs
(`12501632`), e o backend TFLM/STM32 ja executa as 10 amostras com estabilidade.

Para uma **conclusao final e justa de desempenho de hardware STM32 vs NXP**,
ainda e preciso deixar claro que o STM32 usa patches locais e uma alocacao
persistente de scratch no kernel Conv2D, porque o overlay scratch nativo do TFLM
registrou indices validos mas retornou ponteiro `NULL` neste port. A forma
correta de apresentar ao professor e:

> A placa STM32 ja executa o experimento e produz CSV comparavel pelo pipeline
> BALAS. O desempenho inferior inicial em relacao a NXP foi causado por
> fallbacks Conv2D no port TFLM/STM32; apos corrigir o scratch buffer, o STM32
> ficou mais rapido neste sanity model. O scratch ja foi movido para a arena do
> TFLM, mas ainda existem ressalvas de engenharia: entender por que o overlay
> scratch nativo retorna `NULL`, revisar memoria/runtime e remover workarounds
> antes de tratar o resultado como comparacao final de hardware.

## Proximas otimizacoes necessarias

- Investigar por que `RequestScratchBufferInArena` gera indices validos, mas
  `GetScratchBuffer` devolve `NULL` para esses indices neste port.
- Avaliar se o scratch Conv2D pode voltar a usar overlay reutilizavel, reduzindo
  a arena de `81920` bytes.
- Avaliar posicionamento de codigo/dados em ITCM/DTCM/AXI SRAM.
- Reduzir ou eliminar o workaround de reconstruir o interpretador por
  inferencia, se a causa no TFLM upstream for isolada.
- Repetir a suite apos cada otimizacao e comparar novamente com a linha NXP.

## Evidencia gerada

CSV:

- `artifacts/stm32_tflm_suite.csv`

Linha valida mais recente:

- status: `ok`
- backend: `stm32/tflm`
- amostras: `10`
- arena: `81920`
- MACs: `12501632`
- media MCU: `42720.8 us`
- desvio MCU: `4.166533331199931 us`
