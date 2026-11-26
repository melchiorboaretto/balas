import os
from pathlib import Path
import sys

# File: balas/python_scripts/dse/config_loader.py
# parents[0] = python_scripts/dse
# parents[1] = python_scripts
# parents[2] = balas (raiz do repositório)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import tomllib as toml_parser
except ImportError:
    import tomli as toml_parser

from python_scripts.config import default_serial_port, repo_root
from python_scripts.dse.sampling import validate_constraints

DRY_RUN_TARGET = "dryrun"


def resolve_output_path(template: str, target: str) -> Path:
    """Resolve ``{target}`` no caminho de saída.

    TOMLs antigos (sem ``{target}``) continuam gravando no mesmo arquivo para
    qualquer placa, exceto no dry-run: ali o arquivo ganha o sufixo
    ``_dryrun`` para que resultados simulados nunca marquem um hash como
    "já medido" na placa real.
    """
    if "{target}" in template:
        return repo_root() / template.replace("{target}", target)
    path = repo_root() / template
    if target == DRY_RUN_TARGET:
        path = path.with_name(f"{path.stem}_{DRY_RUN_TARGET}{path.suffix}")
    return path


def load_dse_config(toml_path, serial_override=None, target=None):
    with open(toml_path, "rb") as f:
        data = toml_parser.load(f)

    exp = data.get("experiment", {})
    specs = data.get("model_specs", {})
    hyper = data.get("hyperparameters", {})

    # Converte lista em tupla (1, 640) se necessário
    raw_shape = specs.get("input_shape") or exp.get("input_shape")
    input_shape = tuple(raw_shape) if raw_shape else None

    serial_device = (
        serial_override
        or exp.get("serial_device")
        or default_serial_port()
    )

    target = target or os.environ.get("BALAS_TARGET", "nxp")

    return {
        "benchmark": exp.get("benchmark", "cifar_ten"),
        "base_seed": exp.get("base_seed", 72),
        "profiling_samples": exp.get("profiling_samples", 10),
        "output_csv": resolve_output_path(exp.get("output_csv", "artifacts/database.csv"), target),
        "output_map": resolve_output_path(exp.get("output_map", "artifacts/map.json"), target),
        "grid": hyper.get("grid", {}),
        "constraints": validate_constraints(hyper.get("constraints", {})),
        "input_shape": input_shape,
        "num_classes": specs.get("num_classes") or exp.get("num_classes"),
        "serial_device": serial_device,
        "target": target,
    }
