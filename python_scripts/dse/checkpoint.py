
import json
from pathlib import Path
import time
from python_scripts.experiments.common import csv_append_row

CSV_FIELDNAMES = [
    "timestamp",
    "iteration_index",
    "hash_id",
    "variant_name",
    "arena_estimated",
    "macs",
    "inference_us_0",
    "inference_us_1",
    "inference_us_2",
    "inference_us_3",
    "inference_us_4",
    "inference_us_5",
    "inference_us_6",
    "inference_us_7",
    "inference_us_8",
    "inference_us_9",
    "error",
]


class CheckpointManager:
    """Gerencia a persistência em CSV/JSON e a verificação de testes já realizados."""

    def __init__(self, csv_path: Path, map_path: Path):
        self.csv_path = csv_path
        self.map_path = map_path
        self.completed_hashes = set()
        self.hash_map = {}
        self._load_state()

    def _load_state(self):
        """Carrega o histórico de hashes do JSON de checkpoint."""
        if self.map_path.exists():
            try:
                self.hash_map = json.loads(self.map_path.read_text(encoding="utf-8"))
                self.completed_hashes.update(self.hash_map.keys())
            except Exception as e:
                print(f"⚠️ Alerta ao carregar checkpoint: {e}")

    def is_completed(self, hash_id: str) -> bool:
        """Verifica se o hash já foi processado anteriormente."""
        return hash_id in self.completed_hashes

    def save_result(
        self,
        iteration: int,
        hash_id: str,
        variant_name: str,
        hp_list: list,
        config: dict,
        error_msg: str,
        arena_estimated: int | None,
        macs: int | None,
        durations: list | None,
    ):
        """Salva o resultado do teste de forma incremental no CSV e no JSON."""
        timestamp_hhmm = time.strftime("%H:%M", time.localtime())
        
        row = {
            "timestamp": timestamp_hhmm,
            "iteration_index": iteration,
            "hash_id": hash_id,
            "variant_name": variant_name,
            "arena_estimated": arena_estimated,
            "macs": macs,
            "error": error_msg,
        }

        # Preenche as 10 colunas individuais de latência em microssegundos
        for idx in range(10):
            col_name = f"inference_us_{idx}"
            if durations and idx < len(durations):
                row[col_name] = durations[idx]
            else:
                row[col_name] = ""

        csv_append_row(self.csv_path, CSV_FIELDNAMES, row)

        self.hash_map[hash_id] = {
            "hash_id": hash_id,
            "hyperparameters": hp_list,
            "variant_name": variant_name,
            "config": config,
            "iteration_index": iteration,
        }
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        self.map_path.write_text(json.dumps(self.hash_map, indent=2), encoding="utf-8")
        self.completed_hashes.add(hash_id)
