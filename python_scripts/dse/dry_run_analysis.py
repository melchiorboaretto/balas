"""Sanidade do dry-run: os MACs explicam o tempo de inferência medido no PC?

Para cada TOML, sorteia modelos do espaço (mesma amostragem do loop de DSE),
gera o .tflite, mede o tempo de ``invoke()`` no PC e compara com os MACs.

Dois modos de kernel do TFLite no PC:
  * ``builtin``: kernels otimizados do TFLite sem o delegate XNNPACK (o que o
    --dry-run usa; o XNNPACK falha em alguns modelos int8 válidos);
  * ``ref``: kernels de referência (BUILTIN_REF), sem SIMD, mais parecidos com
    o TFLM sem CMSIS-NN;
  * ``xnnpack``: o padrão do tf.lite.Interpreter (opcional, pode falhar).

Saídas: correlação de Pearson tempo × MACs (linear e log-log), µs por milhão
de MACs, e o custo extra de cada ativação na topologia de referência.

Uso:
    uv run python python_scripts/dse/dry_run_analysis.py --models 30 --json /tmp/dry.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from python_scripts.dse.builders import get_builder_module  # noqa: E402
from python_scripts.dse.builders._graph import ACTIVATIONS  # noqa: E402
from python_scripts.dse.config_loader import load_dse_config  # noqa: E402
from python_scripts.dse.sampling import sample_config  # noqa: E402

TOMLS = ["configs/cifar_10.toml", "configs/kws.toml", "configs/vww.toml", "configs/ad.toml"]


def time_model(path: Path, mode: str, repeats: int) -> float:
    """Mediana do tempo de invoke() em µs (1 thread, entrada int8 aleatória fixa)."""
    import numpy as np
    from python_scripts.dse.tflite_inspect import make_interpreter

    interp = make_interpreter(path, mode=mode, num_threads=1)
    det = interp.get_input_details()[0]
    rng = np.random.default_rng(0)
    data = rng.integers(-128, 127, size=det["shape"], dtype=np.int8)
    interp.set_tensor(det["index"], data)
    for _ in range(2):
        interp.invoke()
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        interp.invoke()
        samples.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(samples)


def pearson(xs, ys):
    if len(xs) < 3:
        return float("nan")
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")


def analyze_toml(toml: str, n_models: int, repeats: int, modes, tmp: Path) -> dict:
    cfg = load_dse_config(REPO_ROOT / toml)
    builder = get_builder_module(cfg["benchmark"])
    rows = []
    for i in range(n_models):
        s = sample_config(cfg, builder, cfg["base_seed"] + 5000 + i)
        path = builder.build_and_quantize_model(
            s.config, f"{cfg['benchmark']}_{i}", tmp, cfg["input_shape"], cfg["num_classes"]
        )
        row = {
            "variant": s.variant_name,
            "activation": s.config.get("activation") or "relu",
            "macs": s.cost["macs"],
            "params": s.cost["params"],
        }
        for mode in modes:
            row[f"us_{mode}"] = time_model(path, mode, repeats)
        rows.append(row)
        print(f"   {toml} {i + 1}/{n_models}: {row['macs'] / 1e6:8.2f} MMAC "
              + " ".join(f"{m}={row[f'us_{m}']:9.1f}us" for m in modes), flush=True)

    summary = {"toml": toml, "n": len(rows), "rows": rows}
    macs = [r["macs"] for r in rows]
    for mode in modes:
        us = [r[f"us_{mode}"] for r in rows]
        summary[mode] = {
            "pearson_linear": pearson(macs, us),
            "pearson_loglog": pearson([math.log(m) for m in macs], [math.log(u) for u in us]),
            "us_per_mmac_median": statistics.median(u / (m / 1e6) for u, m in zip(us, macs)),
        }
    return summary


def activation_overhead(benchmark: str, repeats: int, modes, tmp: Path) -> dict:
    """Tempo da topologia de referência com cada ativação, relativo à relu."""
    builder = get_builder_module(benchmark)
    out = {}
    for act in ACTIVATIONS:
        path = builder.build_and_quantize_model({"activation": act}, f"{benchmark}_act_{act}", tmp)
        out[act] = {mode: time_model(path, mode, repeats) for mode in modes}
    for act in ACTIVATIONS:
        for mode in modes:
            out[act][f"{mode}_vs_relu"] = out[act][mode] / out["relu"][mode]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", type=int, default=30, help="Modelos por TOML (padrão 30).")
    parser.add_argument("--repeats", type=int, default=15, help="Repetições de invoke() por modelo.")
    parser.add_argument("--modes", default="builtin,ref", help="builtin, ref e/ou xnnpack.")
    parser.add_argument("--tomls", nargs="*", default=TOMLS)
    parser.add_argument("--json", help="Grava os resultados completos em JSON.")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    tmp = Path(tempfile.mkdtemp(prefix="balas_dry_analysis_"))
    results = {"per_toml": [], "activation_overhead": {}}
    for toml in args.tomls:
        results["per_toml"].append(analyze_toml(toml, args.models, args.repeats, modes, tmp))
    for benchmark in ("cifar_ten", "keyword_spotting", "visual_wake_words", "anomaly_detection"):
        results["activation_overhead"][benchmark] = activation_overhead(benchmark, args.repeats, modes, tmp)

    print("\n== Correlação tempo (PC) x MACs")
    for s in results["per_toml"]:
        for mode in modes:
            m = s[mode]
            print(f"   {s['toml']:22s} {mode:8s} r={m['pearson_linear']:.3f}  r(log)={m['pearson_loglog']:.3f}  "
                  f"mediana {m['us_per_mmac_median']:.1f} us/MMAC  (n={s['n']})")
    print("\n== Tempo relativo à relu (topologia de referência)")
    for benchmark, acts in results["activation_overhead"].items():
        for mode in modes:
            print(f"   {benchmark:18s} {mode:8s} " + "  ".join(
                f"{a}={acts[a][f'{mode}_vs_relu']:.2f}x" for a in ACTIVATIONS))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
