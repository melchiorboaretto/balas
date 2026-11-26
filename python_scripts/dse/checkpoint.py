import csv
import json
from pathlib import Path
import time

# Número de colunas inference_us_N gravadas no CSV. Amostras além disso ficam
# só no JSON de mapeamento (campo "durations_us").
MAX_DURATION_COLUMNS = 10

CSV_FIELDNAMES = [
    "timestamp",
    "iteration_index",
    "hash_id",
    "variant_name",
    "target",
    "activation",
    "params",
    "tflite_bytes",
    "arena_estimated",
    "macs",
    "float_fallback",
    *[f"inference_us_{i}" for i in range(MAX_DURATION_COLUMNS)],
    "error",
]

# Colunas do formato antigo (antes de target/activation/params/tflite_bytes/
# float_fallback). Um CSV antigo é migrado para o cabeçalho novo na primeira
# gravação, preenchendo as colunas novas com vazio.
LEGACY_CSV_FIELDNAMES = [
    "timestamp",
    "iteration_index",
    "hash_id",
    "variant_name",
    "arena_estimated",
    "macs",
    *[f"inference_us_{i}" for i in range(MAX_DURATION_COLUMNS)],
    "error",
]


def _read_rows(csv_path: Path) -> tuple[list[str], list[dict]]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_rows(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(csv_path)


def append_result_row(csv_path: Path, row: dict) -> None:
    """Acrescenta uma linha, migrando o cabeçalho se o CSV for do formato antigo.

    ``csv.DictWriter`` em modo append não confere o cabeçalho existente: gravar
    com colunas novas num CSV antigo deslocaria todos os valores sem erro.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and csv_path.stat().st_size > 0:
        header, rows = _read_rows(csv_path)
        if header != CSV_FIELDNAMES:
            if set(header) - set(CSV_FIELDNAMES):
                raise RuntimeError(
                    f"{csv_path} tem colunas desconhecidas {sorted(set(header) - set(CSV_FIELDNAMES))}; "
                    "use outro output_csv no TOML."
                )
            _write_rows(csv_path, CSV_FIELDNAMES, rows)
        with csv_path.open("a", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES).writerow(row)
        return

    _write_rows(csv_path, CSV_FIELDNAMES, [row])


class CheckpointManager:
    """Gerencia a persistência em CSV/JSON e a verificação de testes já realizados."""

    def __init__(self, csv_path: Path, map_path: Path):
        self.csv_path = Path(csv_path)
        self.map_path = Path(map_path)
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

    def _write_map(self) -> None:
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.map_path.with_suffix(self.map_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.hash_map, indent=2), encoding="utf-8")
        tmp_path.replace(self.map_path)

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
        *,
        target: str | None = None,
        activation: str | None = None,
        params: int | None = None,
        tflite_bytes: int | None = None,
        float_fallback: bool | None = None,
        extra_map_fields: dict | None = None,
    ):
        """Salva o resultado do teste de forma incremental no CSV e no JSON."""
        timestamp_hhmm = time.strftime("%H:%M", time.localtime())

        row = {
            "timestamp": timestamp_hhmm,
            "iteration_index": iteration,
            "hash_id": hash_id,
            "variant_name": variant_name,
            "target": target or "",
            "activation": activation or "",
            "params": "" if params is None else params,
            "tflite_bytes": "" if tflite_bytes is None else tflite_bytes,
            "arena_estimated": arena_estimated,
            "macs": macs,
            "float_fallback": "" if float_fallback is None else int(bool(float_fallback)),
            "error": error_msg,
        }

        for idx in range(MAX_DURATION_COLUMNS):
            col_name = f"inference_us_{idx}"
            if durations and idx < len(durations):
                row[col_name] = durations[idx]
            else:
                row[col_name] = ""

        append_result_row(self.csv_path, row)

        entry = {
            "hash_id": hash_id,
            "hyperparameters": hp_list,
            "variant_name": variant_name,
            "config": config,
            "iteration_index": iteration,
        }
        if durations is not None:
            entry["durations_us"] = list(durations)
        if extra_map_fields:
            entry.update(extra_map_fields)
        self.hash_map[hash_id] = entry
        self._write_map()
        self.completed_hashes.add(hash_id)

    def get_iteration_row(self, iteration: int) -> dict | None:
        """Retorna a linha do CSV correspondente ao iteration_index informado, se existir."""
        if not self.csv_path.exists():
            return None
        target = str(iteration)
        with self.csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if str(row.get("iteration_index", "")).strip() == target:
                    return row
        return None

    def mark_iteration_error(self, iteration: int, error_msg: str) -> int:
        """Reescreve a coluna ``error`` das linhas de ``iteration``. Devolve quantas mudaram."""
        if not self.csv_path.exists():
            return 0
        header, rows = _read_rows(self.csv_path)
        changed = 0
        for row in rows:
            if str(row.get("iteration_index", "")).strip() == str(iteration):
                row["error"] = error_msg
                changed += 1
        if changed:
            _write_rows(self.csv_path, header or CSV_FIELDNAMES, rows)
        return changed

    def rollback_iteration(self, iteration: int) -> int:
        """Remove do CSV e do JSON map os registros associados ao iteration_index informado."""
        target = str(iteration)
        removed_rows = 0

        if self.csv_path.exists():
            fieldnames, rows = _read_rows(self.csv_path)
            kept_rows = []
            for row in rows:
                if str(row.get("iteration_index", "")).strip() == target:
                    removed_rows += 1
                else:
                    kept_rows.append(row)

            if removed_rows > 0:
                _write_rows(self.csv_path, fieldnames or CSV_FIELDNAMES, kept_rows)

        if self.map_path.exists():
            self._load_state()
            hashes_to_remove = [
                h
                for h, meta in self.hash_map.items()
                if str(meta.get("iteration_index", "")).strip() == target
            ]
            if hashes_to_remove:
                for h in hashes_to_remove:
                    self.hash_map.pop(h, None)
                    self.completed_hashes.discard(h)
                self._write_map()

        return removed_rows
