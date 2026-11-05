"""
DSE CPU x NPU na FRDM-MCXN947.

Para cada variante de modelo (a de referência do MLPerf Tiny ou as do grid de
DSE dos configs/*.toml):

  1. constrói e quantiza o .tflite com o builder do BALAS (pesos aleatórios);
  2. calcula MACs e estima a arena no PC (mesmas funções do fluxo antigo);
  3. converte com o neutron_compiler 3.2.2 e registra, de forma explícita,
     o que foi para a NPU e o que ficou na CPU (lista de operadores + log);
  4. grava na placa e mede o modelo ORIGINAL (tudo na CPU, CMSIS-NN);
  5. grava na placa e mede o modelo CONVERTIDO (NPU + o que sobrou na CPU);
  6. confere se as saídas da placa batem com a saída do TFLite no PC;
  7. escreve uma linha no CSV (CPU e NPU lado a lado) e um JSON de detalhes.

As duas medições usam o MESMO firmware (cpp-project/npu-tflite-test, baseado
no exemplo tflm_kws do SDK 26.09), o mesmo TFLM e o mesmo cronômetro, para a
comparação ser justa. O tempo é só o Invoke(), média de 10 execuções depois
de 1 de aquecimento.

Uso (rode da raiz do balas):

  # 1) só o KWS de referência (já sabemos que funciona)
  .venv/bin/python python_scripts/npu/cpu_vs_npu.py --modelos kws

  # 2) as referências dos outros três
  .venv/bin/python python_scripts/npu/cpu_vs_npu.py --modelos vww,ic,ad

  # 3) DSE: 50 variantes do grid do KWS
  .venv/bin/python python_scripts/npu/cpu_vs_npu.py --modelos kws --modo dse --max-variantes 50

  # Sem placa: só constrói, converte e diz o que cabe (rápido, para conferir o grid)
  .venv/bin/python python_scripts/npu/cpu_vs_npu.py --modelos all --modo dse --max-variantes 20 --sem-placa

  # 4) DSE com os grids novos (configs/cpu_vs_npu/*_dse_novo.toml): roda TODAS
  #    as combinações, numa ordem embaralhada fixa (se parar no meio, o que já
  #    rodou é uma amostra espalhada do grid, não um canto dele)
  .venv/bin/python python_scripts/npu/cpu_vs_npu.py --modelos kws --modo dse_novo

Antes de mexer na placa o script mostra o plano e pede confirmação; --sim
pula a pergunta (para deixar rodando sozinho). Ctrl+C para com segurança: o
que já foi medido fica no CSV, e rodar de novo continua de onde parou.
"""

import argparse
import contextlib
import csv
import itertools
import operator
import random
import json
import os
import re
import shutil
import subprocess
import sys
import time
import warnings

warnings.filterwarnings("ignore")
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import numpy as np  # noqa: E402

from python_scripts.config import default_serial_port  # noqa: E402
from python_scripts.dse.builders import get_builder_module, validate_grid  # noqa: E402
from python_scripts.dse.config_loader import load_dse_config  # noqa: E402
from python_scripts.dse.hashing import generate_hp_hash, sample_hyperparameters_for_seed  # noqa: E402

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

MODELOS = {
    # apelido: {modo: toml}
    #   referencia = só o modelo do MLPerf Tiny
    #   dse        = grids antigos (sorteio), mantidos como estavam
    #   dse_novo   = grids revisados em 29/10/2026 (todas as combinações);
    #                ver docs/028, parte 7
    "kws": {"referencia": "configs/kws_reference.toml", "dse": "configs/kws.toml",
            "dse_novo": "configs/cpu_vs_npu/kws_dse_novo.toml"},
    "vww": {"referencia": "configs/vww_reference.toml", "dse": "configs/vww.toml",
            "dse_novo": "configs/cpu_vs_npu/vww_dse_novo.toml"},
    "ic": {"referencia": "configs/cifar_10_reference.toml", "dse": "configs/cifar_10.toml",
           "dse_novo": "configs/cpu_vs_npu/ic_dse_novo.toml"},
    "ad": {"referencia": "configs/ad_reference.toml", "dse": "configs/ad.toml",
           "dse_novo": "configs/cpu_vs_npu/ad_dse_novo.toml"},
}

FIRMWARE_DIR = REPO_ROOT / "cpp-project" / "npu-tflite-test"
FIRMWARE_BUILD_DIR = FIRMWARE_DIR / "Debug"
FIRMWARE_PROJECT = "frdmmcxn947_tflm_kws_cm33_core0"
FIRMWARE_AXF = FIRMWARE_BUILD_DIR / f"{FIRMWARE_PROJECT}.axf"
MODEL_HEADER = FIRMWARE_DIR / "source" / "model" / "model_data.h"
TOOLCHAIN_BIN = os.environ.get("MCUX_TOOLCHAIN_BIN", "/usr/local/mcuxpressoide/ide/tools/bin")
NEUTRON_COMPILER = os.environ.get(
    "NEUTRON_COMPILER", str(Path.home() / "venvs" / "neutron" / "bin" / "neutron_compiler")
)
NEUTRON_TARGET = "mcxn94x"

# Arena fixa do firmware. A SRAM principal tem 384 KB; o resto do firmware
# (heap 32 KB, pilha 8 KB, drivers) usa ~45 KB. O modelo fica na flash.
ARENA_BYTES = int(os.environ.get("BALAS_NPU_ARENA_BYTES", str(320 * 1024)))
# Flash 0 tem 1 MB e o código do firmware ocupa ~110 KB.
FLASH_MODEL_LIMIT = 1024 * 1024 - 140 * 1024

# Operadores registrados em source/model/model_ds_cnn_ops_npu.cpp.
FIRMWARE_OPS = {
    "NeutronGraph", "CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED",
    "AVERAGE_POOL_2D", "MAX_POOL_2D", "ADD", "MUL", "SUB", "PAD", "RESHAPE",
    "SOFTMAX", "LOGISTIC", "RELU", "RELU6", "MEAN", "QUANTIZE", "DEQUANTIZE",
    "CONCATENATION", "SHAPE", "STRIDED_SLICE", "PACK", "SQUEEZE", "TANH",
}

SAIDA_DIR = REPO_ROOT / "artifacts" / "cpu_vs_npu"

CSV_CAMPOS = [
    "data_hora", "modelo", "modo", "iteracao", "hash_id", "variante", "hiperparametros",
    "macs", "tflite_bytes", "arena_estimada_pc", "arena_pico_ativacoes", "previsao_cabe",
    "ops_originais", "n_ops_originais",
    "npu_ops_convertidos", "npu_ops_total", "npu_razao_conversao",
    "npu_ops_que_ficam_na_cpu", "npu_ciclos_estimados_conversor", "npu_tflite_bytes",
    "cpu_status", "cpu_media_us", "cpu_min_us", "cpu_max_us", "cpu_desvio_us",
    "cpu_tempos_us", "cpu_arena_usada", "cpu_saida_vs_pc",
    "npu_status", "npu_media_us", "npu_min_us", "npu_max_us", "npu_desvio_us",
    "npu_tempos_us", "npu_arena_usada", "npu_saida_vs_pc",
    "speedup_cpu_sobre_npu", "erro",
]

# Status que encerram a variante (não precisa medir de novo).
STATUS_FINAIS = {"ok", "nao_cabe_flash", "nao_cabe_ram", "op_nao_suportado", "sem_placa"}


# ---------------------------------------------------------------------------
# Leitura de .tflite
# ---------------------------------------------------------------------------

def listar_ops(tflite_path: Path) -> list[str]:
    """Operadores do subgrafo principal, na ordem de execução."""
    from tensorflow.lite.python import schema_py_generated as schema

    buf = tflite_path.read_bytes()
    model = schema.ModelT.InitFromPackedBuf(buf, 0)
    nomes = {v: k for k, v in vars(schema.BuiltinOperator).items() if not k.startswith("_")}
    ops = []
    for op in model.subgraphs[0].operators:
        code = model.operatorCodes[op.opcodeIndex]
        builtin = max(code.builtinCode, code.deprecatedBuiltinCode)
        if nomes.get(builtin) == "CUSTOM":
            custom = code.customCode
            ops.append(custom.decode() if isinstance(custom, bytes) else str(custom))
        else:
            ops.append(nomes.get(builtin, f"OP_{builtin}"))
    return ops


def pico_ativacoes(tflite_path: Path) -> int:
    """Estimativa da arena: maior soma de tensores de ativação vivos ao mesmo tempo.

    O estimate_tensor_arena_size do BALAS soma todos os tensores (inclusive os
    pesos, que ficam na flash) e superestima a arena de 4 a 130x. O TFLM reusa a
    memória de tensores que já morreram; isto aproxima esse planejamento.
    """
    from tensorflow.lite.python import schema_py_generated as schema

    model = schema.ModelT.InitFromPackedBuf(tflite_path.read_bytes(), 0)
    sg = model.subgraphs[0]
    tamanhos_tipo = {0: 4, 1: 2, 2: 4, 3: 1, 4: 8, 7: 2, 9: 1, 10: 8, 16: 4}

    def tamanho(t):
        n = int(np.prod(t.shape)) if t.shape is not None and len(t.shape) else 1
        return n * tamanhos_tipo.get(t.type, 1)

    def constante(i):
        b = model.buffers[sg.tensors[i].buffer]
        return b is not None and b.data is not None and len(b.data) > 0

    nascimento, morte = {}, {}
    for i in list(sg.inputs):
        nascimento[i] = 0
    for k, op in enumerate(sg.operators):
        for i in op.outputs if op.outputs is not None else []:
            nascimento.setdefault(i, k)
        for i in op.inputs if op.inputs is not None else []:
            if i >= 0 and not constante(i):
                morte[i] = k
    for i in list(sg.outputs):
        morte[i] = len(sg.operators)
    pico = 0
    for k in range(len(sg.operators)):
        vivos = sum(
            (tamanho(sg.tensors[i]) + 15) // 16 * 16
            for i, n in nascimento.items()
            if n <= k <= morte.get(i, n) and not constante(i)
        )
        pico = max(pico, vivos)
    return pico


def prever_cabe(pico: int, modelo_bytes: int) -> str:
    """Previsão sem placa. Nas 4 referências a arena real ficou entre 1,1x e
    3,4x o pico de ativações (KWS 16,0->22,7 KB; VWW 55->101 KB; IC 49->55 KB;
    AD 0,8->2,6 KB), então 2x + 8 KB é uma margem conservadora."""
    if modelo_bytes > FLASH_MODEL_LIMIT:
        return "nao_cabe_flash"
    if pico > ARENA_BYTES:
        return "nao_cabe_ram"
    if 2 * pico + 8 * 1024 <= ARENA_BYTES:
        return "cabe"
    return "incerto"


def resumir_ops(ops: list[str]) -> str:
    contagem = Counter(ops)
    return "; ".join(f"{op} x{n}" for op, n in contagem.items())


def entrada_deterministica(n_bytes: int) -> np.ndarray:
    """Mesma entrada que o firmware usa: byte i = (i * 37) & 0xFF."""
    return ((np.arange(n_bytes, dtype=np.uint32) * 37) & 0xFF).astype(np.uint8)


def saida_no_pc(tflite_path: Path) -> bytes:
    """Roda o modelo original no TFLite do PC com a entrada do firmware."""
    import tensorflow as tf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        interp = tf.lite.Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    n = int(np.prod(inp["shape"])) * np.dtype(inp["dtype"]).itemsize
    dados = entrada_deterministica(n).view(inp["dtype"]).reshape(inp["shape"])
    interp.set_tensor(inp["index"], dados)
    interp.invoke()
    return interp.get_tensor(out["index"]).tobytes()


def comparar_saidas(placa_hex: str | None, pc: bytes) -> str:
    """'igual', 'dif_max=N' (em passos de int8) ou '' se não houver saída."""
    if not placa_hex:
        return ""
    try:
        placa = np.frombuffer(bytes.fromhex(placa_hex), dtype=np.int8).astype(int)
    except ValueError:
        return "saida_ilegivel"
    ref = np.frombuffer(pc, dtype=np.int8).astype(int)
    if placa.shape != ref.shape:
        return f"tamanho_diferente({placa.size}vs{ref.size})"
    dif = int(np.max(np.abs(placa - ref))) if placa.size else 0
    return "igual" if dif == 0 else f"dif_max={dif}"


# ---------------------------------------------------------------------------
# Conversão para a NPU
# ---------------------------------------------------------------------------

def converter_npu(original: Path, destino: Path, log_path: Path) -> dict:
    proc = subprocess.run(
        [NEUTRON_COMPILER, "--input", str(original), "--output", str(destino),
         "--target", NEUTRON_TARGET],
        capture_output=True, text=True,
    )
    log = proc.stdout + proc.stderr
    log_path.write_text(log, encoding="utf-8")
    if proc.returncode != 0 or not destino.exists():
        raise RuntimeError(f"neutron_compiler falhou (código {proc.returncode}); veja {log_path}")

    def numero(padrao):
        m = re.search(padrao, log)
        return int(m.group(1).replace(",", "")) if m else None

    convertidos = numero(r"Number of operators converted\s*=\s*([\d,]+)")
    total = numero(r"Number of operators total\s*=\s*([\d,]+)")
    ops_npu = listar_ops(destino)
    return {
        "ops_convertidos": convertidos,
        "ops_total": total,
        "razao": f"{convertidos}/{total}" if convertidos is not None and total else "",
        "ops_que_ficam_na_cpu": [op for op in ops_npu if op != "NeutronGraph"],
        "n_neutron_graphs": ops_npu.count("NeutronGraph"),
        "ops_modelo_convertido": ops_npu,
        "ciclos_estimados": numero(r"Cycle estimation\s*=\s*([\d,]+) \(cycles\) \(NPU only\)"),
        "tflite_bytes": destino.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Firmware: gerar, compilar, gravar, medir
# ---------------------------------------------------------------------------

def escrever_header(tflite_path: Path, nome: str) -> None:
    dados = tflite_path.read_bytes()
    linhas = []
    for i in range(0, len(dados), 12):
        linhas.append("  " + ", ".join(f"0x{b:02x}" for b in dados[i:i + 12]) + ",")
    MODEL_HEADER.write_text(
        f"""/* Gerado por python_scripts/npu/cpu_vs_npu.py. Não edite. */
#ifndef _MODEL_DATA_H_
#define _MODEL_DATA_H_

#ifdef __arm__
#include <cmsis_compiler.h>
#else
#define __ALIGNED(x) __attribute__((aligned(x)))
#endif

#if defined(MCXN947_cm33_core0_SERIES)
#define __PLACEMENT __attribute__((section(".model")))
#else
#define __PLACEMENT
#endif

#define MODEL_NAME "{nome}"
#define MODEL_INPUT_MEAN 0.0f
#define MODEL_INPUT_STD 1.0f

constexpr int kTensorArenaSize = {ARENA_BYTES};

static const uint8_t model_data[] __ALIGNED(16) __PLACEMENT = {{
{chr(10).join(linhas)}
}};
static const unsigned int model_data_len = {len(dados)};

#endif
""",
        encoding="utf-8",
    )


def compilar_firmware() -> tuple[str, str]:
    """Retorna (status, trecho do log). status: ok, nao_cabe_flash, nao_cabe_ram, erro_compilacao."""
    env = dict(os.environ)
    env["PATH"] = f"{TOOLCHAIN_BIN}:{env.get('PATH', '')}"
    # model.o depende do header; apaga para garantir a recompilação.
    (FIRMWARE_BUILD_DIR / "source" / "model" / "model.o").unlink(missing_ok=True)
    proc = subprocess.run(
        ["make", "-r", "-j8", "all"], cwd=FIRMWARE_BUILD_DIR, env=env,
        capture_output=True, text=True,
    )
    log = proc.stdout + proc.stderr
    if proc.returncode == 0 and FIRMWARE_AXF.exists():
        return "ok", ""
    if re.search(r"PROGRAM_FLASH\d?'? overflowed|will not fit in region `PROGRAM_FLASH", log):
        return "nao_cabe_flash", _ultimas_linhas(log)
    if re.search(r"SRAM\w*'? overflowed|will not fit in region `SRAM", log):
        return "nao_cabe_ram", _ultimas_linhas(log)
    return "erro_compilacao", _ultimas_linhas(log)


def _ultimas_linhas(texto: str, n: int = 6) -> str:
    linhas = [l for l in texto.strip().splitlines() if l.strip()]
    return " | ".join(linhas[-n:])


def gravar_firmware(tentativas: int = 3, timeout_s: float = 180) -> None:
    env = dict(os.environ)
    env.update(
        BUILD_DIR=str(FIRMWARE_BUILD_DIR),
        AXF_FILE=str(FIRMWARE_AXF),
        PROJECT_NAME=FIRMWARE_PROJECT,
    )
    ultimo = ""
    for tentativa in range(1, tentativas + 1):
        try:
            proc = subprocess.run(
                [str(REPO_ROOT / "deploy.sh")], cwd=REPO_ROOT, env=env,
                capture_output=True, text=True, timeout=timeout_s,
            )
            if proc.returncode == 0:
                return
            ultimo = _ultimas_linhas(proc.stdout + proc.stderr, 3)
        except subprocess.TimeoutExpired:
            ultimo = f"deploy.sh travou por mais de {int(timeout_s)} s"
        print(f"      gravação falhou (tentativa {tentativa}/{tentativas}): {ultimo}")
        time.sleep(5)
    raise RuntimeError(f"deploy.sh falhou {tentativas}x: {ultimo}")


def gravar_e_medir(porta: str, log_path: Path, timeout_ocioso_s: float) -> dict:
    """Grava o firmware e lê as linhas BALAS_* até BALAS_DONE.

    A serial é aberta ANTES da gravação para não perder o BALAS_BOOT do
    firmware novo; só então o PC manda 'r' para começar a medição.
    """
    import serial

    resultado = {"tempos_us": [], "saida_hex": None, "erro": None, "info": {}, "log": ""}
    linhas_log = []
    with serial.Serial(porta, 115200, timeout=0.5) as ser:
        ser.reset_input_buffer()
        gravar_firmware()
        buffer = b""
        limite_boot = time.monotonic() + 5
        while b"BALAS_BOOT" not in buffer and time.monotonic() < limite_boot:
            buffer += ser.read(4096)
        # Descarta o que veio antes do boot (restos do firmware anterior).
        buffer = buffer[buffer.index(b"BALAS_BOOT"):] if b"BALAS_BOOT" in buffer else b""
        time.sleep(0.2)
        ser.write(b"r")
        ser.flush()
        ultimo_dado = time.monotonic()
        reenvios = 0
        terminou = False
        while not terminou:
            pedaco = ser.read(4096)
            agora = time.monotonic()
            if pedaco:
                ultimo_dado = agora
                buffer += pedaco
            elif len(linhas_log) <= 1 and reenvios < 3 and agora - ultimo_dado > 5:
                # Nada além do boot: talvez a placa não estivesse esperando ainda.
                ser.write(b"r")
                ser.flush()
                reenvios += 1
                ultimo_dado = agora
            elif agora - ultimo_dado > timeout_ocioso_s:
                resultado["erro"] = f"placa_sem_resposta_por_{int(timeout_ocioso_s)}s"
                break
            while b"\n" in buffer:
                linha_b, buffer = buffer.split(b"\n", 1)
                linha = linha_b.decode("utf-8", errors="replace").strip()
                if not linha:
                    continue
                linhas_log.append(linha)
                if linha.startswith("BALAS_INFO"):
                    resultado["info"] = dict(re.findall(r"(\w+)=(\S+)", linha))
                elif linha.startswith("BALAS_RUN"):
                    m = re.search(r"us=(\d+)", linha)
                    if m:
                        resultado["tempos_us"].append(int(m.group(1)))
                elif linha.startswith("BALAS_OUTPUT"):
                    partes = linha.split()
                    resultado["saida_hex"] = partes[1] if len(partes) > 1 else ""
                elif linha.startswith("BALAS_ERROR"):
                    resultado["erro"] = linha.split(maxsplit=1)[1] if " " in linha else "erro"
                elif linha.startswith("BALAS_DONE"):
                    terminou = True
                    break
    resultado["log"] = "\n".join(linhas_log)
    log_path.write_text(resultado["log"] + "\n", encoding="utf-8")
    return resultado


def rodar_backend(tflite_path: Path, nome: str, porta: str, pasta: Path, backend: str,
                  timeout_ocioso_s: float) -> dict:
    """Mede um .tflite na placa. Retorna o dicionário de colunas do backend."""
    r = {"status": "", "media_us": "", "min_us": "", "max_us": "", "desvio_us": "",
         "tempos_us": "", "arena_usada": "", "saida_hex": None, "erro": ""}
    if tflite_path.stat().st_size > FLASH_MODEL_LIMIT:
        r["status"] = "nao_cabe_flash"
        r["erro"] = f"{backend}: modelo de {tflite_path.stat().st_size} B > {FLASH_MODEL_LIMIT} B livres na flash"
        return r

    escrever_header(tflite_path, nome)
    status, log = compilar_firmware()
    if status != "ok":
        r["status"] = status
        r["erro"] = f"{backend}: {log}"
        return r

    med = gravar_e_medir(porta, pasta / f"serial_{backend}.txt", timeout_ocioso_s)
    r["arena_usada"] = med["info"].get("arena_used", "")
    r["saida_hex"] = med["saida_hex"]
    if med["erro"]:
        texto = med["log"]
        if re.search(r"Failed to resize buffer|too small|AllocateTensors\(\) failed", texto):
            r["status"] = "nao_cabe_ram"
        elif "Didn't find op" in texto or "is not supported" in texto:
            r["status"] = "op_nao_suportado"
        else:
            r["status"] = "falha"
        r["erro"] = f"{backend}: {med['erro']} | {_ultimas_linhas(texto, 4)}"
        return r

    tempos = med["tempos_us"]
    if not tempos:
        r["status"] = "falha"
        r["erro"] = f"{backend}: nenhuma medição recebida"
        return r
    r.update(
        status="ok",
        media_us=round(float(np.mean(tempos)), 1),
        min_us=min(tempos),
        max_us=max(tempos),
        desvio_us=round(float(np.std(tempos)), 1),
        tempos_us=";".join(str(t) for t in tempos),
    )
    return r


# ---------------------------------------------------------------------------
# CSV (com retomada)
# ---------------------------------------------------------------------------

def ler_csv(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def hashes_concluidos(csv_path: Path) -> set[str]:
    feitos = set()
    for linha in ler_csv(csv_path):
        if linha.get("cpu_status") in STATUS_FINAIS and linha.get("npu_status") in STATUS_FINAIS:
            feitos.add(linha["hash_id"])
    return feitos


def gravar_linha(csv_path: Path, linha: dict) -> None:
    """Acrescenta a linha, removendo tentativas anteriores do mesmo hash."""
    linhas = [l for l in ler_csv(csv_path) if l.get("hash_id") != linha["hash_id"]]
    linhas.append(linha)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_CAMPOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    tmp.replace(csv_path)


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def processar_variante(apelido, modo, iteracao, cfg, builder, config, hp_list, hash_id,
                       variante, args, porta) -> dict:
    sufixo = "_sem_placa" if args.sem_placa else ""
    pasta = SAIDA_DIR / f"{apelido}_{modo}{sufixo}" / hash_id
    pasta.mkdir(parents=True, exist_ok=True)
    linha = {c: "" for c in CSV_CAMPOS}
    linha.update(
        data_hora=time.strftime("%Y-%m-%d %H:%M:%S"), modelo=apelido, modo=modo,
        iteracao=iteracao, hash_id=hash_id, variante=variante,
        hiperparametros=json.dumps(config, sort_keys=True),
    )
    detalhes = {"modelo": apelido, "modo": modo, "hash_id": hash_id, "variante": variante,
                "hiperparametros": config}
    erros = []

    # 1. Constrói o .tflite original
    tmp = Path("/tmp/balas_cpu_vs_npu")
    tmp.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "w") as nulo, contextlib.redirect_stdout(nulo), contextlib.redirect_stderr(nulo):
        gerado = builder.build_and_quantize_model(
            config, variante, tmp, input_shape=cfg["input_shape"], num_classes=cfg.get("num_classes"),
        )
    original = pasta / "original.tflite"
    shutil.copy(gerado, original)
    linha["tflite_bytes"] = original.stat().st_size

    # 2. Métricas no PC
    from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
    from python_scripts.mac_calculator.mac_calculator import count_macs
    try:
        linha["macs"] = count_macs(str(original))
    except Exception as e:  # noqa: BLE001
        erros.append(f"macs: {e}")
    try:
        linha["arena_estimada_pc"] = estimate_tensor_arena_size(str(original))
    except Exception as e:  # noqa: BLE001
        erros.append(f"arena: {e}")

    pico = pico_ativacoes(original)
    linha["arena_pico_ativacoes"] = pico
    linha["previsao_cabe"] = prever_cabe(pico, original.stat().st_size)

    ops = listar_ops(original)
    linha["ops_originais"] = resumir_ops(ops)
    linha["n_ops_originais"] = len(ops)
    detalhes["ops_originais"] = ops

    # 3. Conversão para a NPU
    npu_tflite = pasta / "npu.tflite"
    conv = converter_npu(original, npu_tflite, pasta / "neutron.log")
    linha.update(
        npu_ops_convertidos=conv["ops_convertidos"], npu_ops_total=conv["ops_total"],
        npu_razao_conversao=conv["razao"],
        npu_ops_que_ficam_na_cpu=resumir_ops(conv["ops_que_ficam_na_cpu"]) or "(nenhum)",
        npu_ciclos_estimados_conversor=conv["ciclos_estimados"],
        npu_tflite_bytes=conv["tflite_bytes"],
    )
    detalhes["npu"] = conv

    faltando = sorted((set(ops) | set(conv["ops_modelo_convertido"])) - FIRMWARE_OPS)
    saida_pc = saida_no_pc(original)
    detalhes["saida_pc_hex"] = saida_pc.hex()

    # 4/5. Placa
    resultados = {}
    for backend, arquivo in (("cpu", original), ("npu", npu_tflite)):
        if backend not in args.backends:
            resultados[backend] = {"status": "pulado"}
            continue
        previsao = prever_cabe(pico, arquivo.stat().st_size)
        if previsao in ("nao_cabe_flash", "nao_cabe_ram"):
            # Certeza de que não cabe: nem grava na placa.
            resultados[backend] = {"status": previsao,
                                   "erro": f"{backend}: {previsao} (pico de ativações {pico} B, "
                                           f"modelo {arquivo.stat().st_size} B)"}
            continue
        if args.sem_placa:
            resultados[backend] = {"status": "sem_placa"}
            continue
        if faltando:
            resultados[backend] = {"status": "op_nao_suportado",
                                   "erro": f"{backend}: firmware não registra {faltando}"}
            continue
        print(f"   [{backend.upper()}] compilando, gravando e medindo...")
        r = rodar_backend(arquivo, f"{apelido}_{hash_id}_{backend}", porta, pasta, backend,
                          args.timeout_ocioso)
        r["saida_vs_pc"] = comparar_saidas(r.get("saida_hex"), saida_pc)
        resultados[backend] = r
        if r["status"] == "ok":
            print(f"   [{backend.upper()}] {r['media_us'] / 1000:.2f} ms "
                  f"(±{r['desvio_us'] / 1000:.2f}) | arena usada {r['arena_usada']} B | "
                  f"saída vs PC: {r['saida_vs_pc']}")
        else:
            print(f"   [{backend.upper()}] {r['status']}: {r.get('erro', '')}")

    for backend, r in resultados.items():
        for campo in ("status", "media_us", "min_us", "max_us", "desvio_us", "tempos_us",
                      "arena_usada", "saida_vs_pc"):
            linha[f"{backend}_{campo}"] = r.get(campo, "")
        if r.get("erro"):
            erros.append(r["erro"])
    if resultados.get("cpu", {}).get("status") == "ok" and resultados.get("npu", {}).get("status") == "ok":
        linha["speedup_cpu_sobre_npu"] = round(resultados["cpu"]["media_us"] / resultados["npu"]["media_us"], 2)
    linha["erro"] = " || ".join(erros)

    detalhes["resultados"] = {b: {k: v for k, v in r.items() if k != "saida_hex"} | {"saida_hex": r.get("saida_hex")}
                              for b, r in resultados.items()}
    detalhes["linha_csv"] = linha
    if all(str(r.get("status", "")).startswith("nao_cabe") or r.get("status") == "pulado"
           for r in resultados.values()):
        # Modelos que não cabem podem ter vários MB; guarda só o log e o JSON.
        for arquivo in (original, npu_tflite):
            arquivo.unlink(missing_ok=True)
    (pasta / "detalhes.json").write_text(json.dumps(detalhes, indent=2, default=str), encoding="utf-8")
    return linha


_OPERADORES = {"<=": operator.le, "<": operator.lt, "==": operator.eq,
               ">=": operator.ge, ">": operator.gt}


def ler_restricoes(toml_path: Path) -> list[tuple[str, str, str]]:
    """Lê a seção [restricoes] (regras "a <= b") do toml, se existir."""
    import tomllib
    with open(toml_path, "rb") as f:
        regras = tomllib.load(f).get("restricoes", {}).get("regras", [])
    saida = []
    for regra in regras:
        m = re.fullmatch(r"\s*(\w+)\s*(<=|<|==|>=|>)\s*(\w+)\s*", regra)
        if not m:
            raise ValueError(f"restrição inválida em {toml_path.name}: {regra!r}")
        saida.append(m.groups())
    return saida


def combinacoes_validas(grid: dict, restricoes) -> list[dict]:
    """Todas as combinações do grid que obedecem às restrições."""
    chaves = sorted(grid)
    validas = []
    for valores in itertools.product(*(grid[k] for k in chaves)):
        config = dict(zip(chaves, valores))
        if all(_OPERADORES[op](config[a], config[b]) for a, op, b in restricoes):
            validas.append(config)
    return validas


def _variantes_exaustivas(toml_path: Path, max_variantes: int | None):
    """Todas as combinações válidas, numa ordem embaralhada fixa (base_seed)."""
    cfg = load_dse_config(toml_path)
    todas = combinacoes_validas(cfg["grid"], ler_restricoes(toml_path))
    random.Random(cfg["base_seed"]).shuffle(todas)
    for iteracao, config in enumerate(todas[:max_variantes]):
        hp_list = [config[k] for k in sorted(config)]
        variante = "_".join(f"{k}-{config[k]}" for k in sorted(config))
        yield iteracao, cfg, config, hp_list, generate_hp_hash(hp_list), variante


def variantes(apelido: str, modo: str, max_variantes: int | None):
    """Gera (iteracao, cfg, config, hp_list, hash_id, variante) sem repetir hash."""
    toml_path = REPO_ROOT / MODELOS[apelido][modo]
    if modo == "dse_novo":
        yield from _variantes_exaustivas(toml_path, max_variantes)
        return
    cfg = load_dse_config(toml_path)
    vistos = set()
    iteracao = 0
    entregues = 0
    tentativas_sem_novidade = 0
    while max_variantes is None or entregues < max_variantes:
        config, hp_list, hash_id, variante = sample_hyperparameters_for_seed(
            cfg["grid"], cfg["base_seed"] + iteracao
        )
        iteracao += 1
        if hash_id in vistos:
            tentativas_sem_novidade += 1
            if tentativas_sem_novidade > 1000:  # grid esgotado
                return
            continue
        tentativas_sem_novidade = 0
        vistos.add(hash_id)
        entregues += 1
        yield iteracao - 1, cfg, config, hp_list, hash_id, variante


def main() -> int:
    p = argparse.ArgumentParser(description="DSE CPU x NPU na FRDM-MCXN947")
    p.add_argument("--check-env", action="store_true",
                   help="executa diagnóstico completo do ambiente NXP (IDE, SDK, Neutron, permissões)")
    p.add_argument("--modelos", default=None,
                   help="kws, vww, ic, ad (separados por vírgula) ou all")
    p.add_argument("--modo", choices=["referencia", "dse", "dse_novo"], default="referencia",
                   help="referencia = só o modelo do MLPerf Tiny; dse = sorteio nos grids antigos; "
                        "dse_novo = todas as combinações dos grids novos (configs/cpu_vs_npu)")
    p.add_argument("--max-variantes", type=int, default=None,
                   help="limite de variantes por modelo no modo dse (padrão: até esgotar o grid)")
    p.add_argument("--backends", default="cpu,npu", help="cpu,npu (padrão), só cpu ou só npu")
    p.add_argument("--sem-placa", action="store_true",
                   help="não usa a placa: constrói, converte e prevê se cabe")
    p.add_argument("--sim", action="store_true", help="não pede confirmação")
    p.add_argument("--porta", default=None, help="porta serial (padrão: BALAS_SERIAL_PORT do .balas.env)")
    p.add_argument("--timeout-ocioso", type=float, default=180.0,
                   help="segundos sem receber nada da placa até desistir (padrão 180)")
    args = p.parse_args()

    if args.check_env:
        try:
            from python_scripts.npu.check_environment import run_diagnostics
            return 0 if run_diagnostics() else 1
        except Exception as e:
            print(f"Erro ao executar diagnóstico de ambiente: {e}")
            return 1

    if not args.modelos:
        p.error("o argumento --modelos é obrigatório (a menos que use --check-env)")

    args.backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    apelidos = list(MODELOS) if args.modelos == "all" else [m.strip() for m in args.modelos.split(",")]
    for a in apelidos:
        if a not in MODELOS:
            p.error(f"modelo desconhecido: {a} (use {', '.join(MODELOS)})")

    _carregar_env()
    porta = args.porta or default_serial_port()

    if not Path(NEUTRON_COMPILER).exists():
        print(f"neutron_compiler não encontrado em {NEUTRON_COMPILER} (defina NEUTRON_COMPILER)")
        return 1

    print("Plano:")
    print(f"  modelos:  {', '.join(apelidos)}")
    print(f"  modo:     {args.modo}" + (f" (até {args.max_variantes} variantes por modelo)"
                                         if args.modo != "referencia" and args.max_variantes else ""))
    if args.modo == "dse_novo":
        for a in apelidos:
            toml_path = REPO_ROOT / MODELOS[a]["dse_novo"]
            n = len(combinacoes_validas(load_dse_config(toml_path)["grid"], ler_restricoes(toml_path)))
            print(f"    {a}: {n} combinações no grid ({toml_path.relative_to(REPO_ROOT)})")
    print(f"  backends: {', '.join(args.backends)}")
    print(f"  placa:    {'NÃO (só PC)' if args.sem_placa else porta}")
    print(f"  saída:    {SAIDA_DIR.relative_to(REPO_ROOT)}/<modelo>_{args.modo}.csv")
    if not args.sem_placa and not args.sim:
        if input("Continuar? [s/N] ").strip().lower() not in ("s", "sim", "y", "yes"):
            print("Cancelado.")
            return 1

    try:
        for apelido in apelidos:
            sufixo = "_sem_placa" if args.sem_placa else ""
            csv_path = SAIDA_DIR / f"{apelido}_{args.modo}{sufixo}.csv"
            feitos = hashes_concluidos(csv_path)
            print(f"\n=== {apelido.upper()} ({args.modo}) -> {csv_path.relative_to(REPO_ROOT)} "
                  f"| já concluídos: {len(feitos)}")
            builder = None
            for iteracao, cfg, config, hp_list, hash_id, variante in variantes(
                apelido, args.modo, args.max_variantes
            ):
                if builder is None:
                    builder = get_builder_module(cfg["benchmark"])
                    for aviso in validate_grid(builder, cfg["grid"]):
                        print(f"   aviso: {aviso}")
                if hash_id in feitos:
                    continue
                inicio = time.monotonic()
                print(f"\n[{time.strftime('%H:%M:%S')}] {apelido} #{iteracao} {hash_id} {variante}")
                try:
                    linha = processar_variante(apelido, args.modo, iteracao, cfg, builder, config,
                                               hp_list, hash_id, variante, args, porta)
                except KeyboardInterrupt:
                    raise
                except Exception as e:  # noqa: BLE001
                    print(f"   ERRO: {e}")
                    linha = {c: "" for c in CSV_CAMPOS}
                    linha.update(data_hora=time.strftime("%Y-%m-%d %H:%M:%S"), modelo=apelido,
                                 modo=args.modo, iteracao=iteracao, hash_id=hash_id,
                                 variante=variante, hiperparametros=json.dumps(config, sort_keys=True),
                                 cpu_status="falha", npu_status="falha", erro=str(e))
                gravar_linha(csv_path, linha)
                resumo = f"   -> CPU {linha['cpu_status']} | NPU {linha['npu_status']}"
                if linha.get("speedup_cpu_sobre_npu"):
                    resumo += f" | NPU {linha['speedup_cpu_sobre_npu']}x mais rápida"
                print(f"{resumo} | {time.monotonic() - inicio:.0f} s | NPU: "
                      f"{linha['npu_razao_conversao']} ops convertidos, na CPU: "
                      f"{linha['npu_ops_que_ficam_na_cpu']}")
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi medido está no CSV; rode de novo para continuar.")
        return 130
    return 0


def _carregar_env() -> None:
    """Lê o .balas.env (porta serial, PROBE_SERIAL) sem sobrescrever o ambiente."""
    env_file = REPO_ROOT / ".balas.env"
    if not env_file.exists():
        return
    for linha in env_file.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


if __name__ == "__main__":
    sys.exit(main())
