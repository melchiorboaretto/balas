# Sanity Test: Expectativas do TCC vs Comportamento Atual do Repositorio

## Objetivo

Este documento registra, de forma clara, o que o trabalho escrito do projeto descreve como comportamento esperado do B.A.L.A.S e o que o repositorio atual efetivamente implementa no estado presente.

O foco aqui e responder a esta pergunta:

- depois de gravar o firmware existente, o que exatamente deve acontecer
- onde o CSV e gerado
- o que faz parte do firmware
- o que faz parte do host
- o que pode ser considerado um sanity test valido antes de alterar o codigo

Este documento foi produzido a partir da leitura do trabalho escrito em:

- [TG2_Bruno_Silveira.pdf](/home/christian/github/mestrado/TG2_BrunoSilveira/TG2_Bruno_Silveira.pdf)

e da comparacao com o codigo atual do repositorio.

## Resposta curta

O CSV nao deve ser gerado pela placa nem pelo firmware embarcado isoladamente.

Pelo desenho do projeto descrito no TCC e pelo fluxo implementado no repositorio, o esperado e:

1. o host gera ou atualiza o firmware
2. o host compila e faz deploy
3. a placa fica esperando entradas pela serial
4. o host envia tensores de entrada em `float32`
5. a placa devolve tempos de inferencia em microssegundos
6. o host agrega os tempos e grava um arquivo CSV

Portanto:

- o firmware sozinho nao gera CSV
- o firmware sozinho nao imprime relatorio
- o firmware sozinho nao e a ferramenta completa
- o firmware e apenas a parte embarcada do pipeline

## O que o TCC descreve

## Visao geral do projeto no texto do trabalho

Na secao 4.1 do TCC, o projeto e descrito como uma ferramenta que, dado um modelo pre-treinado, retorna um relatorio com a latencia de inferencia medida no dispositivo real.

Trecho funcional importante do fluxo descrito no trabalho:

- o sistema roda parte no computador principal e parte na placa
- o computador principal executa um script Python principal
- o deploy do firmware e automatico
- apos o deploy, o profiler envia entradas por UART
- a MCU responde com o tempo de inferencia
- o resultado final e um CSV

Isso aparece nas secoes extraidas do PDF:

- [TG2_Bruno_Silveira.pdf](/home/christian/github/mestrado/TG2_BrunoSilveira/TG2_Bruno_Silveira.pdf)

Pontos centrais identificados no texto:

- o `model_path`, `profiling_dataset` e `results` sao argumentos do fluxo principal
- o `Model Deployer` prepara e envia o firmware
- o `Model Profiler` envia entradas uma a uma
- a MCU responde com o tempo de inferencia em microssegundos
- o resultado final e gravado em CSV

## Comportamento esperado da aplicacao embarcada segundo o TCC

Na descricao da parte C++ do projeto, o firmware na MCU tem papel bem definido:

- agir como um servidor UART
- esperar entradas
- rodar inferencia
- medir o tempo
- retornar o resultado

Ou seja, pelo trabalho escrito, a aplicacao embarcada:

- nao e um terminal interativo textual
- nao e um “hello world”
- nao gera o relatorio final
- nao e a camada de agregacao de resultados

Ela e o backend embarcado do processo de profiling.

## O que o TCC diz sobre o CSV final

No texto do trabalho, o CSV final e responsabilidade da ferramenta completa no host.

Segundo a secao de relatorio do PDF, o CSV final deveria incluir campos como:

- `model`
- `arena_size`
- `macs`
- `avg_inference_time_us`
- `std_inference_us`
- `arena_time_ms`
- `mac_time_ms`
- `cpp_codegen_time_ms`
- `compile_time_ms`
- `deploy_time_ms`
- `profiling_time_ms`
- `attempts`

Conclusao importante:

- o TCC descreve um pipeline completo de benchmarking
- o CSV e um artefato do lado host
- a placa nao cria esse CSV diretamente

## O que o repositorio atual implementa

## Pipeline principal em Python

O fluxo principal do repositorio atual esta em:

- [automator.py](/home/christian/github/balas/automator.py)

Esse script:

1. estima o tamanho da tensor arena
2. calcula MACs
3. gera codigo C++
4. compila o projeto
5. faz deploy para a MCU
6. envia os dados de profiling pela serial
7. grava o relatorio CSV

Ou seja:

- o repositorio atual preserva a mesma arquitetura geral descrita no TCC
- o CSV continua sendo responsabilidade do host
- o firmware continua sendo apenas a parte que espera entrada e devolve o tempo

## Comportamento do firmware atual

O comportamento do firmware atualmente compilado pode ser lido em:

- [MCXN947_Project.cpp](/home/christian/github/balas/cpp-project/tflite-test/source/MCXN947_Project.cpp)

No `while (1)`, ele faz:

1. ler bytes da serial
2. iniciar medicao de tempo
3. rodar `model.run_inference(...)`
4. parar o cronometro
5. escrever de volta um `int` com o tempo de inferencia

Portanto, o que o firmware atual faz e:

- esperar entrada binaria
- devolver 4 bytes com o tempo de inferencia

Ele nao faz:

- imprimir texto de boas-vindas
- imprimir resultado em formato humano
- escrever CSV
- salvar relatorio em arquivo

## Configuracao serial atual

A UART usada pelo firmware atual foi configurada para:

- `115200`
- `8 data bits`
- `sem paridade`
- `1 stop bit`

Essa configuracao aparece em:

- [peripherals.c](/home/christian/github/balas/cpp-project/tflite-test/board/peripherals.c)

## Como o host atual espera conversar com a placa

O comportamento do lado host esta descrito em:

- [profiler.py](/home/christian/github/balas/python_scripts/profiler/profiler.py)

O profiler atual:

- abre a serial em `115200`
- envia arrays `float32` como bytes crus
- le 4 bytes de volta
- interpreta esses 4 bytes como `int32 little-endian`

Conclusao:

- o protocolo atual e binario
- nao e um protocolo textual
- nao foi desenhado para interacao manual em terminal comum

## Onde o CSV atual e gerado

O CSV atual e produzido em:

- [report.py](/home/christian/github/balas/python_scripts/report_writer/report.py)

O arquivo atualmente presente como exemplo e:

- [results.csv](/home/christian/github/balas/results.csv)

Os campos que o codigo atual realmente grava sao:

- `arena_size`
- `macs`
- `avg_inference_us`
- `std_inference_us`

Isso confirma novamente:

- o CSV e gerado pelo host
- o CSV nao sai direto da placa

## Diferenca entre o TCC e o codigo atual

## Arquitetura geral

Na arquitetura geral, o repositorio atual esta alinhado com o TCC:

- existe um pipeline no host
- existe firmware na MCU
- a comunicacao e por serial
- a MCU devolve tempos de inferencia
- o host grava CSV

## Conteudo do CSV

Aqui ha uma divergencia importante.

O TCC descreve um CSV final mais rico, com muitos campos de tempo e metadados do processo.

O repositorio atual implementa um CSV simplificado, contendo apenas:

- arena
- MACs
- media da inferencia
- desvio padrao

Portanto:

- a ideia do CSV continua presente
- mas o formato do CSV atual e mais simples que o descrito no trabalho

## Interacao com o firmware

O TCC descreve a MCU como um servidor UART que espera entradas e devolve resultados.

O firmware atual implementa exatamente esse conceito em alto nivel.

Portanto, no aspecto de “qual e a natureza da interacao”, o firmware atual faz sentido e esta conceitualmente alinhado ao trabalho.

## Problema tecnico importante no estado atual do repositorio

Embora a arquitetura geral esteja alinhada, o snapshot atual do codigo tem um problema tecnico importante:

- `input.h`
- `output.h`

Nesses arquivos, o campo `size` esta sendo definido como:

```cpp
this->size = sizeof(data);
```

Isso significa:

- o valor salvo nao e o tamanho real do tensor
- o valor salvo e apenas o tamanho do ponteiro

Em um MCU 32-bit, isso tende a resultar em `4`.

Impactos praticos provaveis:

- o firmware pode ler apenas 4 bytes da serial, em vez do tensor inteiro
- a quantizacao pode usar tamanho incorreto
- a dequantizacao pode usar tamanho incorreto
- o protocolo real em execucao pode nao corresponder ao protocolo planejado no TCC

Conclusao importante:

- a ideia do projeto continua correta
- mas o snapshot atual do codigo pode nao estar plenamente funcional sem ajustes

## O que deve acontecer depois do flash do firmware atual

Se voce gravar o firmware atual e abrir uma serial esperando texto, o comportamento esperado e:

- possivelmente nenhum texto aparecera
- a placa ficara esperando bytes
- ao receber bytes, tentara rodar a inferencia
- se tudo correr bem, devolvera 4 bytes com o tempo de inferencia

Logo, depois do flash:

- nao se espera um “hello world”
- nao se espera um CSV surgir automaticamente
- nao se espera um menu textual

O que se espera e um backend embarcado aguardando entrada binaria.

## O que pode ser considerado um sanity test sem alterar o codigo

Antes de modificar qualquer arquivo, um sanity test razoavel deve validar o que o sistema atual consegue fazer.

## Sanity test minimo do firmware

Validar:

1. o firmware e gravado sem erro
2. a placa enumera a serial
3. a serial abre em `115200 8N1`
4. a placa responde com 4 bytes apos receber entrada

Esse teste nao prova que o pipeline inteiro esta correto, mas prova:

- que o deploy funciona
- que a placa esta executando algo
- que a UART esta operacional
- que ha algum retorno binario do firmware

## Sanity test do fluxo host + firmware

Um segundo nivel de teste seria:

1. gravar o firmware
2. usar o profiler Python
3. enviar entradas pela serial
4. receber tempos de inferencia
5. gravar um CSV com esses tempos agregados

Esse segundo teste e o que mais se aproxima do comportamento descrito no TCC.

## O que nao deve ser usado como criterio de sucesso

Nao use como criterio de sucesso:

- aparecer texto automatico no terminal serial
- aparecer “hello world”
- gerar CSV sem o lado host
- esperar interacao manual em ASCII

Esses comportamentos nao correspondem ao desenho principal do projeto.

## Conclusao

O trabalho escrito e o repositorio atual concordam no ponto principal:

- a placa recebe entradas por serial
- mede inferencia
- devolve o tempo
- o host produz o CSV final

Entao, conceitualmente, o projeto esta desenhado para funcionar dessa forma.

No entanto, o snapshot atual do repositorio apresenta sinais de divergencia de implementacao em relacao a uma versao plenamente funcional usada no trabalho, principalmente:

- simplificacao do formato do CSV
- bug de tamanho em `input.h` e `output.h`
- possiveis fragilidades nos scripts de build e deploy

Portanto, a expectativa correta para o sanity test e:

- confirmar primeiro que o firmware responde pela serial
- confirmar depois que o host consegue transformar essas respostas em CSV

Isso respeita o desenho do TCC e evita criar uma expectativa errada de que o firmware sozinho deveria imprimir relatorios ou gerar arquivos.

## Arquivos usados nesta analise

- [TG2_Bruno_Silveira.pdf](/home/christian/github/mestrado/TG2_BrunoSilveira/TG2_Bruno_Silveira.pdf)
- [automator.py](/home/christian/github/balas/automator.py)
- [MCXN947_Project.cpp](/home/christian/github/balas/cpp-project/tflite-test/source/MCXN947_Project.cpp)
- [peripherals.c](/home/christian/github/balas/cpp-project/tflite-test/board/peripherals.c)
- [profiler.py](/home/christian/github/balas/python_scripts/profiler/profiler.py)
- [report.py](/home/christian/github/balas/python_scripts/report_writer/report.py)
- [results.csv](/home/christian/github/balas/results.csv)
- [input.h](/home/christian/github/balas/cpp-project/tflite-test/model/input.h)
- [output.h](/home/christian/github/balas/cpp-project/tflite-test/model/output.h)
