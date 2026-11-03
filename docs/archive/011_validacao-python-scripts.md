# Validacao de `python_scripts`

## Objetivo

Este documento registra o estado de validacao dos scripts em `python_scripts/` apos os testes executados nesta sessao.

O objetivo e responder de forma objetiva:

- quais scripts foram testados
- como foram testados
- qual evidencia existe para cada um

## Criterios usados

Os scripts foram avaliados nos seguintes niveis:

- `sintaxe`: o arquivo compila em Python sem erro
- `import`: o modulo pode ser importado corretamente
- `funcional local`: o comportamento foi exercitado com arquivos temporarios ou entradas locais
- `funcional real`: o script participou de um fluxo real com ferramenta externa, serial, build ou hardware

## Resultado geral

Todos os `.py` em `python_scripts/` passaram em validacao sintatica.

Comando executado:

```bash
source .venv/bin/activate
python -m compileall -q python_scripts
```

## Matriz de validacao

| Script | Tipo | Status | Como foi testado | Evidencia |
| --- | --- | --- | --- | --- |
| `python_scripts/config.py` | configuracao | validado em uso real | usado pelo fluxo do `automator.py` e pelos scripts de experimento | localizou serial, paths e `stm32tflm` corretamente |
| `python_scripts/arena_estimator/estimator.py` | pipeline principal | validado em uso real | chamado sobre modelo TFLite real | retornou arena com `stm32tflm` funcional |
| `python_scripts/code_generator/generator.py` | pipeline principal | validado em uso real | usado no `automator.py` e no runner de experimentos | gerou `model_data.h` e firmware compativel |
| `python_scripts/deployer/deployer.py` | pipeline principal | validado em uso real | `compile_cpp_project()` e `deploy_to_mcu()` executados diretamente | build real OK, flash real OK, resposta serial pos-deploy OK |
| `python_scripts/mac_calculator/mac_calculator.py` | pipeline principal | validado em uso real | usado em `automator.py` e experimento reduzido | calculou `12501632` MACs para o fixture |
| `python_scripts/profiler/profiler.py` | pipeline principal | validado em uso real | envio serial real com dataset `.bin` e leitura de tempos | placa respondeu com tempos de inferencia coerentes |
| `python_scripts/report_writer/report.py` | pipeline principal | validado em uso real | usado pelo `automator.py` | gerou `results.csv` simples com media e desvio |
| `python_scripts/recover_tflite_from_header.py` | fixture | validado em uso real | recuperou `.tflite` de `model_data.h` | gerou arquivo de `94504` bytes e passou em TensorFlow Lite |
| `python_scripts/generate_float32_dataset.py` | fixture | validado em uso real | gerou dataset congelado do sanity test | criou 10 `.bin` em `float32`, 12288 bytes por amostra |
| `python_scripts/experiments/run_benchmark_suite.py` | experimento | validado em uso real | executado contra a FRDM conectada | gerou `/tmp/reduced-suite.csv` com linha experimental |
| `python_scripts/experiments/analyze_benchmark_suite.py` | experimento | validado em uso real | leu CSV experimental e gerou relatorio | gerou `/tmp/reduced-suite-report.md` |
| `python_scripts/experiments/common.py` | suporte de experimento | validado funcional local | manifesto temporario, `.bin`, CSV e correlacao | testes locais passaram |
| `python_scripts/file_utils.py` | utilitario interno | validado funcional local | arquivos e diretorios temporarios | copia, replace, append, chmod e mkdir passaram |
| `python_scripts/code_generator/resolver_map.py` | suporte interno | validado por import e consistencia | import do modulo e checagem de chaves | `CONV_2D`, `FULLY_CONNECTED`, `SOFTMAX`, `RESHAPE` presentes |
| `python_scripts/code_generator/gen_resolver_map.py` | utilitario interno | validado funcional local | executado em sandbox temporaria com header real do TFLM | gerou `resolver_map.py` coerente |
| `python_scripts/experiments/__init__.py` | marcador de pacote | validado por import | import direto do pacote | pacote carregado sem erro |

## Evidencias principais

## 1. Build e deploy reais

O teste mais forte da sessao foi a validacao real de:

- `python_scripts/deployer/deployer.py`

Fluxo exercitado:

1. compilacao real via `compile_cpp_project()`
2. flash real via `deploy_to_mcu()`
3. teste serial pos-deploy com `sample_001.bin`

Resultado observado:

- build concluido com `0 errors, 0 warnings`
- LinkServer gravou a imagem com sucesso
- resposta serial pos-deploy: `234684 us`

## 2. Experimento reduzido funcional

Tambem foi validado o pipeline novo de reproducao reduzida do artigo:

- `python_scripts/experiments/run_benchmark_suite.py`
- `python_scripts/experiments/analyze_benchmark_suite.py`

Resultado observado no CSV:

- familia: `image_classification`
- `macs = 12501632`
- `workstation_avg_us = 187.0822`
- `mcu_avg_us = 234684.4`
- `arena_final = 57344`

## 3. Utilitarios internos

Os scripts auxiliares que nao dependem de placa foram exercitados com testes locais controlados:

- `file_utils.py`
- `experiments/common.py`
- `gen_resolver_map.py`
- `resolver_map.py`

Isso fecha a lacuna que ainda existia sobre scripts nao testados.

## Conclusao

No estado atual do projeto:

- todos os scripts em `python_scripts/` passaram em validacao sintatica
- os pontos de entrada principais foram validados em uso real
- os utilitarios restantes foram validados por testes locais e import

Portanto, a afirmacao pratica correta agora e:

- os scripts de `python_scripts/` estao testados no nivel adequado para o estado atual do repositorio

## Observacao final

Isso nao significa cobertura total de todos os caminhos internos possiveis.

Significa:

- sem erro de sintaxe
- sem erro basico de import
- fluxo principal funcionando
- fixture funcionando
- experimento reduzido funcionando
- utilitarios restantes exercitados de forma direta
