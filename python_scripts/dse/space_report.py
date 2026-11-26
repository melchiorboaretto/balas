"""Relatório do tamanho e da composição de um espaço de busca (TOML de DSE).

Responde, sem TensorFlow e sem placa:

* **grid bruto**: produto do número de valores de cada chave do grid;
* **distintos**: quantos modelos realmente diferentes existem (combinações que
  só diferem em chaves inativas, como ``leaky_slope`` com ativação relu,
  contam uma vez só) — contagem exata;
* **na faixa**: quantos distintos obedecem às ``[hyperparameters.constraints]``
  (estimativa por Monte Carlo, com intervalo de 95%, ou exata com ``--exact``);
* **mistura por placa**: entre os modelos na faixa, a fração que cabe em todas
  as placas, em só algumas e em nenhuma, pelos orçamentos de ``boards.py``.

Uso:
    uv run python python_scripts/dse/space_report.py --config-toml configs/kws.toml
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import math
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from python_scripts.dse.boards import BOARDS, estimate_tflite_bytes, fits  # noqa: E402
from python_scripts.dse.builders import get_builder_module  # noqa: E402
from python_scripts.dse.config_loader import load_dse_config  # noqa: E402
from python_scripts.dse.sampling import check_constraints, reference_cost  # noqa: E402


def _structures(grid: dict, builder) -> list[tuple[dict, list[str], int]]:
    """Enumera as combinações das chaves de controle, já canônicas e sem repetição.

    Devolve (valores de controle canônicos, chaves livres ativas, nº de modelos).
    """
    canonicalize = getattr(builder, "canonicalize", lambda c: dict(c))
    control = [k for k in getattr(builder, "CONTROL_KEYS", ()) if k in grid]
    free = [k for k in sorted(grid) if k not in control]
    seen: dict[tuple, tuple[dict, list[str], int]] = {}

    for values in itertools.product(*(grid[k] for k in control)) if control else [()]:
        probe = {k: grid[k][0] for k in free}
        probe.update(dict(zip(control, values)))
        canon = canonicalize(probe)
        active_free = [k for k in free if canon.get(k) is not None]
        canon_control = tuple((k, canon.get(k)) for k in control)
        key = (canon_control, tuple(active_free))
        if key in seen:
            continue
        count = math.prod(len(grid[k]) for k in active_free)
        seen[key] = (dict(canon_control), active_free, count)
    return list(seen.values())


def _iter_exact(grid, structures):
    for control_values, active_free, _ in structures:
        for values in itertools.product(*(grid[k] for k in active_free)):
            config = dict(control_values)
            config.update(dict(zip(active_free, values)))
            yield config


def _iter_sampled(grid, structures, n, rng):
    weights = [s[2] for s in structures]
    for _ in range(n):
        control_values, active_free, _ = rng.choices(structures, weights=weights, k=1)[0]
        config = dict(control_values)
        config.update({k: rng.choice(grid[k]) for k in active_free})
        yield config


def _percentiles(values, qs=(0.05, 0.5, 0.95)):
    if not values:
        return {}
    values = sorted(values)
    return {f"p{int(q * 100)}": values[min(len(values) - 1, int(q * (len(values) - 1)))] for q in qs}


def analyze(toml_path, samples=20000, exact=None, seed=0, boards=None) -> dict:
    boards = BOARDS if boards is None else boards
    cfg = load_dse_config(toml_path)
    builder = get_builder_module(cfg["benchmark"])
    grid = cfg["grid"]
    constraints = cfg["constraints"]
    reference = reference_cost(cfg, builder)

    raw = math.prod(len(v) for v in grid.values()) if grid else 1
    structures = _structures(grid, builder)
    distinct = sum(s[2] for s in structures)

    if exact is None:
        exact = distinct <= 200_000
    rng = random.Random(seed)
    configs = _iter_exact(grid, structures) if exact else _iter_sampled(grid, structures, samples, rng)

    evaluated = in_band = invalid = 0
    params, macs, peaks = [], [], []
    mix = {"todas": 0, "algumas": 0, "nenhuma": 0}
    per_board = {t: 0 for t in boards}
    by_activation: dict[str, list[int]] = {}

    for config in configs:
        evaluated += 1
        try:
            cost = builder.estimate_cost(config, cfg["input_shape"], cfg["num_classes"])
        except ValueError:
            invalid += 1
            continue
        if constraints and not check_constraints(cost, constraints, reference):
            continue
        in_band += 1
        params.append(cost["params"])
        macs.append(cost["macs"])
        peaks.append(cost["peak_activation_bytes"])
        flash = estimate_tflite_bytes(cost)
        ok = {t: fits(b, flash, cost["arena_estimate"], cost["input_elements"])["fits"]
              for t, b in boards.items()}
        for t, v in ok.items():
            per_board[t] += v
        n_ok = sum(ok.values())
        mix["todas" if n_ok == len(ok) else "nenhuma" if n_ok == 0 else "algumas"] += 1
        act = str(config.get("activation") or "relu")
        stats = by_activation.setdefault(act, [0, 0])
        stats[0] += 1
        stats[1] += n_ok == len(ok)

    frac = in_band / evaluated if evaluated else 0.0
    half_width = 0.0 if exact or not evaluated else 1.96 * math.sqrt(frac * (1 - frac) / evaluated)
    ratio = lambda xs, metric: {k: round(v / reference[metric], 3) for k, v in _percentiles(xs).items()}

    return {
        "toml": str(toml_path),
        "benchmark": cfg["benchmark"],
        "constraints": {k: list(v) for k, v in constraints.items()},
        "reference": {k: reference[k] for k in ("params", "macs", "peak_activation_bytes", "arena_estimate")},
        "grid_keys": {k: len(v) for k, v in sorted(grid.items())},
        "raw_combinations": raw,
        "distinct_models": distinct,
        "method": "exato" if exact else f"monte_carlo({evaluated})",
        "in_band_fraction": frac,
        "in_band_models": round(distinct * frac),
        "in_band_ci95": [round(distinct * max(0.0, frac - half_width)),
                         round(distinct * min(1.0, frac + half_width))],
        "invalid_fraction": invalid / evaluated if evaluated else 0.0,
        "params_vs_reference": ratio(params, "params"),
        "macs_vs_reference": ratio(macs, "macs"),
        "peak_activation_bytes": _percentiles(peaks),
        "board_mix": {k: (v / in_band if in_band else 0.0) for k, v in mix.items()},
        "fits_per_board": {t: (v / in_band if in_band else 0.0) for t, v in per_board.items()},
        "fits_all_by_activation": {a: (s[1] / s[0] if s[0] else 0.0) for a, s in sorted(by_activation.items())},
    }


def _print_report(r: dict) -> None:
    pct = lambda x: f"{100 * x:.1f}%"
    print(f"== {r['toml']}  ({r['benchmark']})")
    print(f"   chaves do grid (nº de valores): {r['grid_keys']}")
    print(f"   restrições: {r['constraints'] or 'nenhuma'}")
    print(f"   referência: params={r['reference']['params']:,}  macs={r['reference']['macs']:,}  "
          f"pico={r['reference']['peak_activation_bytes']:,} B  arena≈{r['reference']['arena_estimate']:,} B")
    print(f"   grid bruto:      {r['raw_combinations']:,}")
    print(f"   distintos:       {r['distinct_models']:,}")
    print(f"   na faixa:        {r['in_band_models']:,}  ({pct(r['in_band_fraction'])} dos distintos; "
          f"IC95 {r['in_band_ci95'][0]:,}–{r['in_band_ci95'][1]:,}; {r['method']})")
    print(f"   params/ref (p5/p50/p95): {r['params_vs_reference']}")
    print(f"   MACs/ref   (p5/p50/p95): {r['macs_vs_reference']}")
    mix = r["board_mix"]
    print(f"   mistura: todas={pct(mix['todas'])}  algumas={pct(mix['algumas'])}  nenhuma={pct(mix['nenhuma'])}")
    print("   cabe em: " + "  ".join(f"{t}={pct(v)}" for t, v in r["fits_per_board"].items()))
    print("   cabe em todas, por ativação: "
          + "  ".join(f"{a}={pct(v)}" for a, v in r["fits_all_by_activation"].items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config-toml", nargs="+", required=True)
    parser.add_argument("--samples", type=int, default=20000, help="Amostras do Monte Carlo (padrão 20000).")
    parser.add_argument("--exact", action="store_true", help="Força enumeração completa.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", help="Grava o resultado em JSON neste caminho.")
    parser.add_argument("--no-heap-limit", action="store_true",
                        help="Ignora o heap fixo da NXP (simula o .cproject com heap maior).")
    args = parser.parse_args()

    boards = BOARDS
    if args.no_heap_limit:
        boards = {t: dataclasses.replace(b, input_heap_bytes=None) for t, b in BOARDS.items()}
        print("(sem limite de heap: simula firmware NXP com heap >= buffer de entrada)")

    results = []
    for toml in args.config_toml:
        r = analyze(toml, samples=args.samples, exact=True if args.exact else None, seed=args.seed,
                    boards=boards)
        results.append(r)
        _print_report(r)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
