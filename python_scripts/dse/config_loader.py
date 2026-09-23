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


def load_dse_config(config_toml_path: str = "configs/continuous_search.toml") -> dict:
    """Carrega a configuração TOML do experimento e resolve os caminhos do repositório."""
    toml_file = repo_root() / config_toml_path
    if not toml_file.exists():
        raise FileNotFoundError(f"Arquivo de configuração TOML não encontrado: {toml_file}")

    with toml_file.open("rb") as handle:
        toml_data = toml_parser.load(handle)

    exp_cfg = toml_data.get("experiment", {})
    grid_cfg = toml_data.get("hyperparameters", {}).get("grid", {})
    model_specs = toml_data.get("model_specs", {})

    return {
        "grid": grid_cfg,
        "base_seed": exp_cfg.get("base_seed", 1000),
        "profiling_samples": exp_cfg.get("profiling_samples", 10),
        "output_csv": repo_root() / exp_cfg.get("output_csv", "artifacts/continuous_database.csv"),
        "output_map": repo_root() / exp_cfg.get("output_map", "artifacts/hyperparameters_map.json"),
        "serial_device": default_serial_port(),
        "input_shape": tuple(model_specs.get("input_shape", [32, 32, 3])),
        "num_classes": model_specs.get("num_classes", 10),
    }
