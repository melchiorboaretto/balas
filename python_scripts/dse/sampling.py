"""Amostragem do espaço de busca com restrições de tamanho.

``sample_config`` é o único ponto que transforma (TOML, seed) em uma
configuração. É usado tanto por ``run_continuous_experiment.py`` quanto por
``run_all_benchmarks.py`` para que os dois sempre concordem sobre qual modelo
corresponde a cada ``iteration_index``.

Restrições aceitas em ``[hyperparameters.constraints]``:

* ``params_ratio = [min, max]``: params do modelo / params da referência.
* ``macs_ratio = [min, max]``: MACs do modelo / MACs da referência.
* ``params_range = [min, max]``: params absolutos.
* ``macs_range = [min, max]``: MACs absolutos.

A referência é o modelo que o builder gera com os defaults (o modelo do
MLPerf Tiny), usando o ``input_shape``/``num_classes`` do TOML. As restrições
usam o custo analítico (``builder.estimate_cost``), que não precisa do
TensorFlow e coincide com o .tflite gerado.

A amostragem é por rejeição e determinística: para o seed s, tenta-se o
sorteio 0, 1, 2, ... até achar uma configuração válida. Sem restrições, o
sorteio 0 é sempre aceito e reproduz o comportamento antigo.
"""

from __future__ import annotations

from dataclasses import dataclass

from python_scripts.dse.hashing import sample_hyperparameters_for_seed

CONSTRAINT_KEYS = ("params_ratio", "macs_ratio", "params_range", "macs_range")
DEFAULT_MAX_ATTEMPTS = 5000


@dataclass
class Sample:
    config: dict
    hp_list: list
    hash_id: str
    variant_name: str
    attempt: int
    cost: dict | None


def validate_constraints(constraints: dict) -> dict:
    """Confere nomes e formato das restrições; devolve cópia normalizada."""
    normalized = {}
    for key, value in (constraints or {}).items():
        if key not in CONSTRAINT_KEYS:
            raise ValueError(
                f"Restrição desconhecida: {key!r}. Opções: {', '.join(CONSTRAINT_KEYS)}."
            )
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"Restrição {key} deve ser [min, max]; recebido {value!r}.")
        lo, hi = float(value[0]), float(value[1])
        if lo < 0 or hi < lo:
            raise ValueError(f"Restrição {key} inválida: [{lo}, {hi}].")
        normalized[key] = (lo, hi)
    return normalized


def reference_cost(dse_cfg: dict, builder) -> dict:
    return builder.estimate_cost({}, dse_cfg.get("input_shape"), dse_cfg.get("num_classes"))


def check_constraints(cost: dict, constraints: dict, reference: dict | None) -> bool:
    for key, (lo, hi) in constraints.items():
        metric = "params" if key.startswith("params") else "macs"
        value = float(cost[metric])
        if key.endswith("_ratio"):
            value /= float(reference[metric])
        if not lo <= value <= hi:
            return False
    return True


def sample_config(
    dse_cfg: dict,
    builder,
    seed: int,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Sample:
    """Devolve a configuração do seed, respeitando as restrições do TOML."""
    grid = dse_cfg["grid"]
    constraints = validate_constraints(dse_cfg.get("constraints") or {})
    canonicalize = getattr(builder, "canonicalize", None)
    estimate = getattr(builder, "estimate_cost", None)
    reference = reference_cost(dse_cfg, builder) if constraints else None

    if constraints and estimate is None:
        raise ValueError("Builder sem estimate_cost não suporta [hyperparameters.constraints].")

    for attempt in range(max_attempts):
        config, hp_list, hash_id, variant_name = sample_hyperparameters_for_seed(
            grid, seed, attempt=attempt, canonicalize=canonicalize
        )
        cost = None
        if estimate is not None:
            try:
                cost = estimate(config, dse_cfg.get("input_shape"), dse_cfg.get("num_classes"))
            except ValueError:
                # Configuração inválida para o builder (ex.: largura 0): rejeita.
                if constraints:
                    continue
                cost = None
        if constraints and not check_constraints(cost, constraints, reference):
            continue
        return Sample(config, hp_list, hash_id, variant_name, attempt, cost)

    raise RuntimeError(
        f"Nenhuma configuração do grid satisfez as restrições após {max_attempts} "
        f"tentativas (seed {seed}). Revise [hyperparameters.constraints]."
    )
