# Medicao de energia em placas de desenvolvimento

Documento criado em 2026-04-27 para registrar se as placas avaliadas possuem ponto de medicao de corrente/energia diretamente na placa e onde consultar os esquematicos.

## Resumo

| Placa | Medicao direta na placa | Ponto de medicao | Observacao |
| --- | --- | --- | --- |
| NXP FRDM-MCXN947 | Sim | J24 / IDD_MCU | Mede a corrente que entra em `P3V3_MCU`, rail usado para alimentar os dominios do MCU na configuracao padrao. |
| ST Nucleo-H723ZG | Sim | JP4 / IDD | Mede a corrente IDD do STM32H723 no VDD_MCU. |
| Nordic nRF5340 DK | Sim | P22 / VDD e P23 / VDDH | Requer abrir SB40/SB41 ou inserir instrumento em serie conforme a configuracao. |
| Nordic nRF52840 DK | Sim | P22 / VDD e P23 / VDDH | Requer abrir SB40/SB41 ou inserir instrumento em serie conforme a configuracao. |
| Nordic nRF53840-DK | Nao identificada | - | Nao foi localizada uma placa oficial com esse nome. Provavel confusao com nRF5340 DK ou nRF52840 DK. |

Essas placas normalmente fornecem um ponto de medicao de corrente, nao um medidor de energia completo. A potencia instantanea pode ser estimada por:

```text
P = V * I
```

Para energia em um intervalo:

```text
E = integral(P(t) dt)
```

Na pratica, use um amperimetro de precisao, osciloscopio com shunt, Joulescope, Nordic Power Profiler Kit II, Otii Arc ou instrumento equivalente para registrar a corrente ao longo do tempo.

## Valores eletricos dos microcontroladores

Valores de referencia extraidos dos datasheets/product specifications dos MCUs. Eles nao substituem a medicao real na placa: corrente depende de clock, codigo executado, memoria usada, perifericos, radio, temperatura e regulador ativo.

| Placa | Microcontrolador | Tensao de trabalho do MCU | Corrente de trabalho / referencia | Baixo consumo / referencia |
| --- | --- | --- | --- | --- |
| FRDM-MCXN947 | NXP MCXN947 | `1.71 V` a `3.6 V` | Ate `57 uA/MHz` em modo ativo, conforme condicao de menor consumo do datasheet. Em `150 MHz`, isso equivale a aproximadamente `8.55 mA` como ordem de grandeza minima do nucleo em ativo. | `6 uA` em Power-down com RTC e `512 KB` de SRAM retida; `2 uA` em Deep Power-down com RTC e `32 KB` de SRAM retida. |
| Nucleo-H723ZG | ST STM32H723ZG | `1.62 V` a `3.6 V` em `VDD`/`VDDLDO`/`VDDA` | `145 mA` tipico em Run a `550 MHz`, codigo com processamento e perifericos desabilitados, conforme tabela de consumo em Run do datasheet. | Stop: `0.52 mA` tipico no melhor caso listado. Standby: `2.8 uA` tipico a `3.3 V` com backup SRAM/RTC desligados; `4.75 uA` tipico a `3.3 V` com backup SRAM e RTC/LSE ligados. |
| nRF5340 DK | Nordic nRF5340 | Modo normal `VDD`: `1.7 V` a `3.6 V`; modo alta tensao `VDDH`: `2.5 V` a `5.5 V` | Application CPU rodando CoreMark: `8.0 mA` tipico a `128 MHz` com HFXO e execucao em flash; `3.6 mA` tipico a `64 MHz`. Radio BLE: TX `0 dBm` `4.1 mA` tipico; RX 1 Mbps `3.7 mA` tipico. | System OFF: `1.0 uA` tipico com `0 KB` de RAM de aplicacao retida e wake por reset; `0.9 uA` tipico com wake por LPCOMP/reset em algumas condicoes do datasheet. |

Nota sobre a Nordic: como `nRF53840-DK` nao foi identificada como placa oficial, a tabela acima assume `nRF5340 DK`. Se a placa em uso for `nRF52840 DK`, use os valores do SoC `nRF52840`, nao os do `nRF5340`.

## PDFs salvos localmente

Os PDFs de esquematico/layout disponiveis foram salvos em:

| Placa | Arquivo local | Fonte |
| --- | --- | --- |
| NXP FRDM-MCXN947 | [nxp-frdm-mcxn947-90818-mcxn947sh-schematic.pdf](hardware-pdfs/nxp-frdm-mcxn947-90818-mcxn947sh-schematic.pdf) | NXP: `90818-MCXN947SH`, tambem disponivel como anexo em dominio `community.nxp.com`. |
| ST Nucleo-H723ZG | [st-nucleo-h723zg-mb1364-h723zg-e01-schematic.pdf](hardware-pdfs/st-nucleo-h723zg-mb1364-h723zg-e01-schematic.pdf) | ST: `MB1364-H723ZG-E01 Schematics`. |
| Nordic nRF5340 DK | [nordic-nrf5340-dk-pca10095-schematic-and-pcb.pdf](hardware-pdfs/nordic-nrf5340-dk-pca10095-schematic-and-pcb.pdf) | Pacote oficial Nordic `nRF5340 Development Kit - Hardware files 2_0_0`. |
| Nordic nRF52840 DK | [nordic-nrf52840-dk-pca10056-schematic-and-pcb.pdf](hardware-pdfs/nordic-nrf52840-dk-pca10056-schematic-and-pcb.pdf) | Pacote oficial Nordic `nRF52840 Development Kit - Hardware files 3_0_3`. |

Links de consulta:

- NXP FRDM-MCXN947: https://www.nxp.com/design/design-center/development-boards-and-designs/FRDM-MCXN947
- ST Nucleo-H723ZG: https://www.st.com/en/evaluation-tools/nucleo-h723zg.html
- ST esquematico direto: https://www.st.com/resource/en/schematic_pack/mb1364-h723zg-e01_schematic.pdf
- Nordic nRF5340 DK downloads: https://www.nordicsemi.com/Products/Development-hardware/nRF5340-DK/Download
- Nordic nRF52840 DK downloads: https://www.nordicsemi.com/Products/Development-hardware/nRF52840-DK/Download

## NXP FRDM-MCXN947

A FRDM-MCXN947 possui medicao direta do consumo do MCU pelo ponto `J24 / IDD_MCU`, associado ao rail `P3V3_MCU`. Na documentacao do MCUXpresso SDK para o exemplo `power_manager_test`, a NXP indica duas formas de medir a potencia/corrente do MCU: conectar um amperimetro ao conector `J24` ou conectar o `J24` ao MCU-Link Debug Probe e usar a funcao de medicao de energia do MCUXpresso IDE.

Mapeamento do ponto de medicao:

| Sinal | Ponto na FRDM-MCXN947 | Observacao |
| --- | --- | --- |
| `IDD_IN` | `J24-1` | Entrada da corrente para o rail do MCU. |
| `IDD_OUT` | `J24-2` | Saida da corrente apos o instrumento de medicao. |
| `VSS` | `J10-4` | Referencia de terra usada pelo MCU-Link Debug Probe. |

Procedimento tipico:

1. Remover o jumper/short de `J24`.
2. Inserir o amperimetro em serie entre `J24-1` (`IDD_IN`) e `J24-2` (`IDD_OUT`).
3. Medir a corrente do rail do MCU.
4. Calcular potencia usando a tensao do rail, tipicamente `3.3 V` para `P3V3_MCU`.

Essa medicao nao deve ser feita no USB, em `P5V0` ou em `P3V3` geral se o objetivo for isolar apenas o consumo do microcontrolador, pois esses pontos tambem incluem outros circuitos da placa, como reguladores, LEDs, interfaces, sensores e o MCU-Link. Se a placa tiver sido modificada para alimentar separadamente `VDD_ANA`, `VDD_BAT`, `VDD_USB` ou `VDD_CORE_SYS`, confirme no esquematico se todos os dominios relevantes ainda passam por `J24`; caso contrario, a corrente total do MCU precisa ser reconstruida pela soma das medicoes dos ramos separados.

Observacao: o site da NXP lista o arquivo `FRDM-MCXN947 Schematics`, codigo `90818-MCXN947SH`, como "Account Required". O PDF local foi baixado de um anexo publico no dominio da NXP Community.

## ST Nucleo-H723ZG

A Nucleo-H723ZG possui medicao direta de corrente do MCU pelo jumper `JP4 / IDD`.

Procedimento tipico:

1. Remover o jumper `JP4`.
2. Conectar o amperimetro em serie nos pinos de `JP4`.
3. Medir a corrente `IDD` do MCU.
4. Calcular potencia com a tensao do rail medido.

O esquematico identifica `JP4` como `IDD Measurement` no rail `VDD_MCU`.

Nota de revisao: para a variante `MB1364-H723ZG-E01`, o manual da ST indica que a medicao IDD em Standby pode ser realizada. Em revisoes antigas de placas STM32H7 Nucleo-144, alguns circuitos externos ligados ao `VDD_MCU` podiam afetar a medicao em Standby.

## Nordic nRF5340 DK

A nRF5340 DK possui pontos dedicados para medicao de corrente:

- `P22` para o dominio `VDD`.
- `P23` para o dominio `VDDH`.
- `SB40` e `SB41` aparecem no esquematico como as pontes de solda associadas a esses caminhos de alimentacao.

Procedimento tipico:

1. Verificar se o objetivo e medir o dominio `VDD` ou `VDDH`.
2. Abrir a ponte correspondente, quando necessario.
3. Inserir o instrumento de corrente em serie em `P22` ou `P23`.
4. Registrar corrente ao longo do tempo para obter energia.

## Nordic nRF52840 DK

A nRF52840 DK tambem possui pontos dedicados para medicao:

- `P22` para o dominio `VDD`.
- `P23` para o dominio `VDDH`.
- `SB40` e `SB41` aparecem no esquematico como as pontes de solda associadas a esses caminhos de alimentacao.

O fluxo de medicao e equivalente ao da nRF5340 DK.

## Comparacao pratica

| Placa | Facilidade de medicao | Melhor uso |
| --- | --- | --- |
| FRDM-MCXN947 | Alta | Medir consumo do MCU/NPU no rail do MCU. |
| Nucleo-H723ZG | Alta | Medir IDD do STM32H723 com amperimetro em `JP4`. |
| nRF5340 DK | Alta | Medir dominios `VDD` e `VDDH`, inclusive com PPK2. |
| nRF52840 DK | Alta | Medir dominios `VDD` e `VDDH`, inclusive com PPK2. |

Para comparacoes justas entre placas, manter o mesmo criterio:

- mesma tensao considerada no calculo de potencia;
- mesmo firmware ou carga computacional equivalente;
- perifericos externos desligados ou documentados;
- mesma janela temporal de medicao;
- mesmo instrumento e taxa de amostragem, quando possivel.
