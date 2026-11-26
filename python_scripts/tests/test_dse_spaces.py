"""Testes dos espaços de DSE: custo analítico, amostragem, hashes, checkpoint,
ativações e regressões dos erros já documentados em docs/.

Rodar (da raiz do repositório):
    uv run python -m unittest python_scripts.tests.test_dse_spaces -v

Variáveis de ambiente:
    BALAS_TEST_MODELS_PER_TOML  modelos .tflite gerados por TOML nos testes com TF (padrão 6)
"""

import csv
import hashlib
import itertools
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from python_scripts.code_generator.resolver_map import resolver_map  # noqa: E402
from python_scripts.dse.boards import BOARDS, estimate_tflite_bytes, float_fallback  # noqa: E402
from python_scripts.dse.builders import BUILDER_MAP, get_builder_module, validate_grid  # noqa: E402
from python_scripts.dse.builders._graph import ACTIVATIONS, ACTIVATION_TFLITE_OP  # noqa: E402
from python_scripts.dse.checkpoint import CSV_FIELDNAMES, LEGACY_CSV_FIELDNAMES, CheckpointManager  # noqa: E402
from python_scripts.dse.config_loader import DRY_RUN_TARGET, load_dse_config, resolve_output_path  # noqa: E402
from python_scripts.dse.hashing import generate_hp_hash, sample_hyperparameters_for_seed  # noqa: E402
from python_scripts.dse.sampling import sample_config, validate_constraints  # noqa: E402
from python_scripts.dse.space_report import _structures, analyze  # noqa: E402

CONFIGS = REPO_ROOT / "configs"
NEW_TOMLS = {
    "cifar_10.toml": "cifar_ten",
    "kws.toml": "keyword_spotting",
    "vww.toml": "visual_wake_words",
    "ad.toml": "anomaly_detection",
}
REFERENCE_TOMLS = {
    "cifar_10_reference.toml": "cifar_ten",
    "kws_reference.toml": "keyword_spotting",
    "vww_reference.toml": "visual_wake_words",
    "ad_reference.toml": "anomaly_detection",
}
# Números do MLPerf Tiny conferidos nos .tflite oficiais (mlcommons/tiny).
OFFICIAL = {
    "cifar_ten": {"macs": 12_501_632, "params": 77_706, "peak": 49_152},
    "keyword_spotting": {"macs": 2_656_768, "params": 22_604, "peak": 16_000},
    "visual_wake_words": {"macs": 7_489_664, "params": 210_850, "peak": 55_296},
    "anomaly_detection": {"macs": 264_192, "params": 265_864, "peak": 768},
}
FORBIDDEN_OPS = {"SHAPE", "STRIDED_SLICE", "PACK", "MEAN", "GELU", "MAX_POOL_2D"}


def legacy_sample(grid: dict, seed: int):
    """Cópia congelada do sample_hyperparameters_for_seed anterior (antes das mudanças)."""
    config, hp_list, parts = {}, [], []
    for key in sorted(grid.keys()):
        choices = grid[key]
        hash_val = hashlib.sha1(f"{seed}_{key}".encode("utf-8")).hexdigest()
        val = choices[int(hash_val, 16) % len(choices)]
        config[key] = val
        hp_list.append(val)
        parts.append(f"{key}-{val}")
    return config, hp_list, generate_hp_hash(hp_list), "_".join(parts)


def all_tomls_with_benchmark():
    out = []
    for path in sorted(CONFIGS.glob("*.toml")) + sorted((CONFIGS / "cpu_vs_npu").glob("*.toml")) \
            + sorted((CONFIGS / "board_tests").glob("*.toml")):
        cfg = load_dse_config(path)
        out.append((path, cfg))
    return out


# ===========================================================================
# 1. Custo analítico, sem TensorFlow
# ===========================================================================
class TestAnalyticCost(unittest.TestCase):
    def test_reference_costs_match_official(self):
        for benchmark, ref in OFFICIAL.items():
            with self.subTest(benchmark=benchmark):
                cost = get_builder_module(benchmark).estimate_cost({})
                self.assertEqual(cost["macs"], ref["macs"])
                self.assertEqual(cost["params"], ref["params"])
                self.assertEqual(cost["peak_activation_bytes"], ref["peak"])

    def test_reference_op_sequences(self):
        conv_dw = ["DEPTHWISE_CONV_2D", "CONV_2D"]
        head = ["AVERAGE_POOL_2D", "FULLY_CONNECTED", "SOFTMAX"]
        expected = {
            "anomaly_detection": ["FULLY_CONNECTED"] * 10,
            "keyword_spotting": ["CONV_2D"] + conv_dw * 4 + head,
            "visual_wake_words": ["CONV_2D"] + conv_dw * 13 + head,
            "cifar_ten": ["CONV_2D", "CONV_2D", "CONV_2D", "ADD"] * 3 + head,
        }
        for benchmark, ops in expected.items():
            with self.subTest(benchmark=benchmark):
                self.assertEqual(get_builder_module(benchmark).estimate_cost({})["ops"], ops)

    def test_non_fused_activation_adds_one_op_per_activation(self):
        # relu e relu6 são fundidas; as demais aparecem uma vez por ativação.
        counts = {"cifar_ten": 7, "keyword_spotting": 9, "visual_wake_words": 27, "anomaly_detection": 9}
        for benchmark, n_acts in counts.items():
            builder = get_builder_module(benchmark)
            base = len(builder.estimate_cost({})["ops"])
            for act in ACTIVATIONS:
                with self.subTest(benchmark=benchmark, activation=act):
                    cost = builder.estimate_cost({"activation": act})
                    extra = 0 if act in ("relu", "relu6") else n_acts
                    self.assertEqual(len(cost["ops"]), base + extra)
                    if extra:
                        self.assertEqual(cost["ops"].count(ACTIVATION_TFLITE_OP[act]), n_acts)

    def test_activation_does_not_change_params_or_macs(self):
        for benchmark in OFFICIAL:
            builder = get_builder_module(benchmark)
            ref = builder.estimate_cost({})
            for act in ACTIVATIONS:
                cost = builder.estimate_cost({"activation": act})
                self.assertEqual((cost["params"], cost["macs"]), (ref["params"], ref["macs"]))
                # Ativação separada nunca reduz o pico de RAM.
                self.assertGreaterEqual(cost["peak_activation_bytes"], ref["peak_activation_bytes"])

    def test_vww_middle_blocks_monotonic(self):
        # docs/025: middle_blocks varia o nº total de blocos; DW = 8 + middle_blocks.
        builder = get_builder_module("visual_wake_words")
        previous = 0
        for middle in range(0, 8):
            cost = builder.estimate_cost({"middle_blocks": middle})
            self.assertEqual(cost["ops"].count("DEPTHWISE_CONV_2D"), 8 + middle)
            self.assertGreater(cost["macs"], previous)
            previous = cost["macs"]

    def test_invalid_values_raise(self):
        with self.assertRaises(ValueError):
            get_builder_module("cifar_ten").estimate_cost({"activation": "gelu"})
        with self.assertRaises(ValueError):
            get_builder_module("cifar_ten").estimate_cost({"block_type_1": "bottleneck_1"})
        with self.assertRaises(ValueError):
            get_builder_module("keyword_spotting").estimate_cost({"ds_blocks": 0})
        with self.assertRaises(ValueError):
            get_builder_module("anomaly_detection").estimate_cost({"enc_layers": 99})
        with self.assertRaises(ValueError):
            get_builder_module("visual_wake_words").estimate_cost(
                {"activation": "leaky_relu", "leaky_slope": 1.5}
            )


# ===========================================================================
# 2. Hashes, canonicalização e contagem de distintos
# ===========================================================================
class TestHashingAndCanonical(unittest.TestCase):
    def test_existing_tomls_keep_legacy_hashes(self):
        """TOMLs sem restrição e sem chaves novas mantêm exatamente os hashes antigos."""
        for path, cfg in all_tomls_with_benchmark():
            if cfg["constraints"]:
                continue
            builder = get_builder_module(cfg["benchmark"])
            keys = set(cfg["grid"])
            if keys & set(getattr(builder, "OPTIONAL_GRID_KEYS", ())):
                continue
            with self.subTest(toml=path.name):
                for seed in range(cfg["base_seed"], cfg["base_seed"] + 40):
                    new = sample_config(cfg, builder, seed)
                    old = legacy_sample(cfg["grid"], seed)
                    self.assertEqual(new.hash_id, old[2])
                    self.assertEqual(new.variant_name, old[3])
                    self.assertEqual(new.attempt, 0)

    def test_plain_function_unchanged_for_attempt_zero(self):
        grid = {"a": [1, 2, 3], "b": ["x", "y"], "c": [0.1, 0.2, 0.3, 0.4]}
        for seed in range(100):
            self.assertEqual(sample_hyperparameters_for_seed(grid, seed), legacy_sample(grid, seed))

    def test_canonicalize_rules(self):
        ic = get_builder_module("cifar_ten")
        self.assertIsNone(ic.canonicalize({"activation": "relu", "leaky_slope": 0.3})["leaky_slope"])
        self.assertEqual(ic.canonicalize({"activation": "leaky_relu", "leaky_slope": 0.3})["leaky_slope"], 0.3)

        kws = get_builder_module("keyword_spotting")
        self.assertEqual(kws.canonicalize({"ds_blocks": 2, "ds_downsample_block": 3})["ds_downsample_block"], 0)
        self.assertEqual(kws.canonicalize({"ds_blocks": 4, "ds_downsample_block": 3})["ds_downsample_block"], 3)

        ad = get_builder_module("anomaly_detection")
        c = ad.canonicalize({"enc_layers": 2, "dec_layers": 1, "enc_units_1": 64, "enc_units_2": 64,
                             "enc_units_3": 512, "dec_units_1": 64, "dec_units_2": 128,
                             "hidden_units": 128, "num_hidden_layers": 4})
        self.assertIsNone(c["enc_units_3"])
        self.assertIsNone(c["dec_units_2"])
        self.assertIsNone(c["hidden_units"])
        self.assertIsNone(c["num_hidden_layers"])

        vww = get_builder_module("visual_wake_words")
        widths = {"width_stem": 8, "width_2": 32, "width_3": 64, "width_4": 128, "width_5": 256}
        self.assertIsNone(vww.canonicalize({"alpha": 0.5, **widths})["alpha"])
        self.assertEqual(vww.canonicalize({"alpha": 0.5, "width_2": 32})["alpha"], 0.5)

    def test_canonical_equal_means_same_model(self):
        """Configs que só diferem em chaves inativas têm o mesmo custo (mesmo modelo)."""
        rng = random.Random(3)
        for toml, benchmark in NEW_TOMLS.items():
            cfg = load_dse_config(CONFIGS / toml)
            builder = get_builder_module(benchmark)
            grid = cfg["grid"]
            for _ in range(200):
                c = {k: rng.choice(v) for k, v in grid.items()}
                canon = builder.canonicalize(c)
                perturbed = dict(c)
                for k in grid:
                    if canon.get(k) is None:
                        perturbed[k] = rng.choice(grid[k])
                with self.subTest(toml=toml):
                    a = builder.estimate_cost(c, cfg["input_shape"], cfg["num_classes"])
                    b = builder.estimate_cost(perturbed, cfg["input_shape"], cfg["num_classes"])
                    self.assertEqual(a["ops"], b["ops"])
                    self.assertEqual((a["params"], a["macs"]), (b["params"], b["macs"]))

    def test_distinct_count_matches_brute_force(self):
        """A contagem de distintos do space_report bate com força bruta em grids reduzidos."""
        for toml, benchmark in NEW_TOMLS.items():
            cfg = load_dse_config(CONFIGS / toml)
            builder = get_builder_module(benchmark)
            # Reduz cada lista a até 2 valores (mantendo chaves de controle com 3).
            control = set(getattr(builder, "CONTROL_KEYS", ()))
            small = {k: v[: (3 if k in control else 2)] for k, v in cfg["grid"].items()}
            if benchmark == "anomaly_detection":
                small["enc_layers"] = [1, 2, 3]
                small["dec_layers"] = [1, 3]
            keys = sorted(small)
            seen = set()
            for values in itertools.product(*(small[k] for k in keys)):
                canon = builder.canonicalize(dict(zip(keys, values)))
                seen.add(json.dumps([canon.get(k) for k in keys]))
            with self.subTest(toml=toml):
                self.assertEqual(sum(s[2] for s in _structures(small, builder)), len(seen))


# ===========================================================================
# 3. Amostragem com restrições
# ===========================================================================
class TestConstrainedSampling(unittest.TestCase):
    def test_new_tomls_respect_constraints_and_are_deterministic(self):
        for toml, benchmark in NEW_TOMLS.items():
            cfg = load_dse_config(CONFIGS / toml)
            builder = get_builder_module(benchmark)
            ref = builder.estimate_cost({}, cfg["input_shape"], cfg["num_classes"])
            lo, hi = cfg["constraints"]["params_ratio"]
            acts = set()
            for seed in range(cfg["base_seed"], cfg["base_seed"] + 150):
                s = sample_config(cfg, builder, seed)
                with self.subTest(toml=toml, seed=seed):
                    self.assertTrue(lo <= s.cost["params"] / ref["params"] <= hi)
                    self.assertEqual(s.hash_id, sample_config(cfg, builder, seed).hash_id)
                    self.assertEqual(s.config, builder.canonicalize(s.config))
                acts.add(s.config.get("activation"))
            self.assertEqual(acts, set(ACTIVATIONS), f"{toml}: nem todas as ativações apareceram")

    def test_unsatisfiable_constraints_raise(self):
        cfg = load_dse_config(CONFIGS / "kws.toml")
        cfg = dict(cfg, constraints={"params_ratio": (100.0, 200.0)})
        with self.assertRaises(RuntimeError):
            sample_config(cfg, get_builder_module("keyword_spotting"), 1, max_attempts=50)

    def test_validate_constraints(self):
        self.assertEqual(validate_constraints({"params_ratio": [0.3, 3]}), {"params_ratio": (0.3, 3.0)})
        for bad in ({"foo": [1, 2]}, {"params_ratio": [3, 1]}, {"params_ratio": 2}, {"macs_ratio": [-1, 2]}):
            with self.assertRaises(ValueError):
                validate_constraints(bad)

    def test_space_report_numbers_in_millions(self):
        for toml in NEW_TOMLS:
            with self.subTest(toml=toml):
                r = analyze(CONFIGS / toml, samples=3000, seed=1)
                self.assertGreaterEqual(r["in_band_models"], 1_000_000)
                self.assertLessEqual(r["in_band_models"], 10_000_000)
                self.assertGreater(r["distinct_models"], r["in_band_models"])

    def test_nxp_heap_limit_blocks_vww_only(self):
        import dataclasses

        from python_scripts.dse.boards import BOARDS

        no_heap = {t: dataclasses.replace(b, input_heap_bytes=None) for t, b in BOARDS.items()}
        vww = analyze(CONFIGS / "vww.toml", samples=600, seed=2)
        vww_free = analyze(CONFIGS / "vww.toml", samples=600, seed=2, boards=no_heap)
        self.assertEqual(vww["fits_per_board"]["nxp"], 0.0)
        self.assertGreater(vww_free["fits_per_board"]["nxp"], 0.8)
        # Os outros benchmarks têm entrada pequena: o heap de 32 KB não muda nada.
        ic = analyze(CONFIGS / "cifar_10.toml", samples=600, seed=2)
        ic_free = analyze(CONFIGS / "cifar_10.toml", samples=600, seed=2, boards=no_heap)
        self.assertEqual(ic["fits_per_board"], ic_free["fits_per_board"])


# ===========================================================================
# 4. Configuração, checkpoint e classificação de erros
# ===========================================================================
class TestConfigCheckpointErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="balas_ckpt_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_output_paths_per_target(self):
        cfg_nxp = load_dse_config(CONFIGS / "kws.toml", target="nxp")
        cfg_stm = load_dse_config(CONFIGS / "kws.toml", target="stm32")
        cfg_dry = load_dse_config(CONFIGS / "kws.toml", target=DRY_RUN_TARGET)
        self.assertNotEqual(cfg_nxp["output_csv"], cfg_stm["output_csv"])
        self.assertIn("/nxp/", str(cfg_nxp["output_csv"]))
        self.assertIn("/dryrun/", str(cfg_dry["output_csv"]))
        # TOML antigo sem {target}: placa real mantém o caminho; dry-run ganha sufixo.
        self.assertEqual(resolve_output_path("artifacts/x.csv", "nxp").name, "x.csv")
        self.assertEqual(resolve_output_path("artifacts/x.csv", DRY_RUN_TARGET).name, "x_dryrun.csv")

    def test_legacy_csv_is_migrated_without_shifting_columns(self):
        csv_path, map_path = self.tmp / "db.csv", self.tmp / "map.json"
        old_row = {k: "" for k in LEGACY_CSV_FIELDNAMES}
        old_row.update(iteration_index="0", hash_id="aaa", macs="123", inference_us_0="456", error="")
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LEGACY_CSV_FIELDNAMES)
            w.writeheader()
            w.writerow(old_row)
        cp = CheckpointManager(csv_path, map_path)
        cp.save_result(1, "bbb", "v", [1], {"a": 1}, "", 1000, 789, [11, 12], target="nxp",
                       activation="tanh", params=50, tflite_bytes=60, float_fallback=False)
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, CSV_FIELDNAMES)
            rows = list(reader)
        self.assertEqual((rows[0]["hash_id"], rows[0]["macs"], rows[0]["inference_us_0"]), ("aaa", "123", "456"))
        self.assertEqual((rows[1]["macs"], rows[1]["activation"], rows[1]["inference_us_1"]), ("789", "tanh", "12"))
        self.assertEqual(json.loads(map_path.read_text())["bbb"]["durations_us"], [11, 12])

    def test_mark_error_and_rollback(self):
        cp = CheckpointManager(self.tmp / "db.csv", self.tmp / "map.json")
        for i in range(3):
            cp.save_result(i, f"h{i}", "v", [i], {}, "serial_failure: x" if i == 1 else "", 1, 2, [3])
        self.assertEqual(cp.mark_iteration_error(1, "runtime_failure: serial_failure: x"), 1)
        self.assertEqual(cp.get_iteration_row(1)["error"], "runtime_failure: serial_failure: x")
        self.assertEqual(cp.rollback_iteration(2), 1)
        cp2 = CheckpointManager(self.tmp / "db.csv", self.tmp / "map.json")
        self.assertEqual(cp2.completed_hashes, {"h0", "h1"})

    def test_error_classification(self):
        import run_all_benchmarks as rab

        cases = {
            "": False,
            "Command '['./compile.sh']' returned non-zero exit status 1.": False,
            "compile.sh: memory_overflow (exit 1): region `RAM' overflowed by 12 bytes": False,
            "compile.sh: build_error (exit 1): error: 'AddGelu' is not a member": False,
            "compile.sh: env_error (exit 3): nRF Util not found: nrfutil": True,
            # Gravada antes do env_error existir (última linha da checagem do SDK).
            "compile.sh: build_error (exit 1): Install it with: /x/nrfutil sdk-manager install v3.4.0": True,
            "build_failure: ValueError ...": False,
            "runtime_failure: serial_failure: Did not receive 4 bytes from device": False,
            "Command '['./deploy.sh']' returned non-zero exit status 1.": True,
            "serial_failure: Did not receive 4 bytes from device": True,
            "Did not receive 4 bytes from device": True,
        }
        for msg, critical in cases.items():
            with self.subTest(msg=msg):
                self.assertEqual(rab.is_critical_error(msg), critical)
        self.assertTrue(rab.is_runtime_failure_candidate("serial_failure: timeout"))
        self.assertFalse(rab.is_runtime_failure_candidate("Command '['./deploy.sh']' failed"))
        self.assertFalse(rab.is_runtime_failure_candidate("compile.sh"))
        self.assertFalse(rab.is_runtime_failure_candidate("compile.sh: env_error (exit 3): x"))

    def test_duration_validation(self):
        from python_scripts.run_continuous_experiment import validate_duration

        self.assertEqual(validate_duration(1234), 1234)
        for bad in (-1, -161_010_189, 10**12):
            with self.assertRaises(RuntimeError):
                validate_duration(bad)

    def test_float_fallback_rules(self):
        self.assertTrue(float_fallback("stm32", "tanh"))
        self.assertTrue(float_fallback("stm32", "sigmoid", "stedgeai"))
        self.assertFalse(float_fallback("stm32", "tanh", "tflm"))
        self.assertFalse(float_fallback("stm32", "leaky_relu"))
        self.assertFalse(float_fallback("nxp", "tanh"))
        self.assertFalse(float_fallback("nordic", "hard_swish"))

    def test_stm32_stedgeai_dse_is_rejected(self):
        from python_scripts.dse.hardware import HardwareAdapter

        old = {k: os.environ.get(k) for k in ("BALAS_STM32_MODEL_BACKEND", "BALAS_STM32_ENABLE_MODEL")}
        try:
            os.environ["BALAS_STM32_MODEL_BACKEND"] = "stedgeai"
            with self.assertRaises(RuntimeError):
                HardwareAdapter("stm32").check_supported()
            os.environ["BALAS_STM32_MODEL_BACKEND"] = "tflm"
            os.environ["BALAS_STM32_ENABLE_MODEL"] = "OFF"
            with self.assertRaises(RuntimeError):
                HardwareAdapter("stm32").check_supported()
            os.environ["BALAS_STM32_ENABLE_MODEL"] = "ON"
            HardwareAdapter("stm32").check_supported()
            HardwareAdapter("nxp").check_supported()
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_grid_validation(self):
        for toml, benchmark in {**NEW_TOMLS, **REFERENCE_TOMLS}.items():
            cfg = load_dse_config(CONFIGS / toml)
            with self.subTest(toml=toml):
                self.assertEqual(validate_grid(get_builder_module(benchmark), cfg["grid"]), [])

    def test_resolver_covers_every_reachable_op(self):
        reachable = set()
        for benchmark in OFFICIAL:
            for act in ACTIVATIONS:
                reachable.update(get_builder_module(benchmark).estimate_cost({"activation": act})["ops"])
        self.assertTrue(reachable <= set(resolver_map), reachable - set(resolver_map))

    def test_greedy_planner_matches_tflm(self):
        from python_scripts.dse.builders._graph import greedy_memory_plan

        # Valores de ``print_allocations`` (head) do TFLM real, pacote tflite-micro
        # 0.dev20261119, nos modelos de referência gerados pelos builders.
        tflm_head = {"cifar_ten": 49152, "keyword_spotting": 16000,
                     "visual_wake_words": 73728, "anomaly_detection": 768}
        for benchmark, head in tflm_head.items():
            cost = get_builder_module(benchmark).estimate_cost({})
            with self.subTest(benchmark=benchmark):
                self.assertEqual(cost["planned_activation_bytes"], head)
                self.assertGreaterEqual(cost["planned_activation_bytes"], cost["peak_activation_bytes"])
        # MobileNetV1: o planner fragmenta (73.728 B) acima do pico de liveness (55.296 B).
        self.assertEqual(get_builder_module("visual_wake_words").estimate_cost({})["peak_activation_bytes"], 55296)
        # Caso pequeno à mão: A(0-1,32) B(1-2,16) C(2-3,32). Ordem do planner: C, A, B.
        # C em 0; A conflita? não (0-1 x 2-3) -> 0; B conflita com A e C -> 32. Máx 48.
        self.assertEqual(greedy_memory_plan([(32, 0, 1), (16, 1, 2), (32, 2, 3)]), 48)
        self.assertEqual(greedy_memory_plan([]), 0)
        self.assertEqual(greedy_memory_plan([(64, 0, 5)]), 64)

    def test_board_budgets_are_consistent(self):
        for board in BOARDS.values():
            self.assertGreater(board.model_flash_budget, 0)
            self.assertGreater(board.ram_budget, 0)
        # Referências do MLPerf Tiny devem caber em todas as placas, exceto a VWW:
        # na STM32 pela RAM (buffer float de 110 KB + arena) e na NXP pelo heap
        # fixo de 32 KB do .cproject, onde mora o ``new float[n]`` da entrada.
        from python_scripts.dse.boards import fits

        for benchmark in OFFICIAL:
            cost = get_builder_module(benchmark).estimate_cost({})
            for target, board in BOARDS.items():
                r = fits(board, estimate_tflite_bytes(cost), cost["arena_estimate"], cost["input_elements"])
                with self.subTest(benchmark=benchmark, target=target):
                    vww = benchmark == "visual_wake_words"
                    self.assertEqual(r["fits"], not (vww and target in ("stm32", "nxp")))
                    self.assertEqual(r["heap_ok"], not (vww and target == "nxp"))


# ===========================================================================
# 4b. Loop do run_all_benchmarks com execução simulada (sem placa)
# ===========================================================================
class TestRunAllBenchmarksLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="balas_rab_"))
        self.configs = self.tmp / "configs"
        self.configs.mkdir()
        toml = (CONFIGS / "kws_reference.toml").read_text()
        toml = toml.replace('"artifacts/kws_reference.csv"', f'"{self.tmp}/out.csv"')
        toml = toml.replace('"artifacts/kws_reference_map.json"', f'"{self.tmp}/out_map.json"')
        (self.configs / "kws_reference.toml").write_text(toml)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, errors, extra_args=()):
        """Roda o main() com um run_single_benchmark_iteration falso que grava ``errors`` em sequência."""
        import run_all_benchmarks as rab
        from unittest import mock

        calls = []

        def fake_run(toml_path, iteration, target, serial_device, profiling_samples, dry_run=False):
            cfg = load_dse_config(toml_path, target=DRY_RUN_TARGET if dry_run else None)
            sample = sample_config(cfg, get_builder_module(cfg["benchmark"]), cfg["base_seed"] + iteration)
            err = errors[min(len(calls), len(errors) - 1)]
            calls.append(err)
            CheckpointManager(cfg["output_csv"], cfg["output_map"]).save_result(
                iteration, sample.hash_id, sample.variant_name, sample.hp_list, sample.config,
                err, 1000, 2000, None if err else [5] * 10,
            )
            return 0

        argv = ["run_all_benchmarks.py", "--configs-dir", str(self.configs), "--results-dir",
                str(self.tmp / "results"), "--max-iterations", "1", "--dry-run", *extra_args]
        with mock.patch.object(rab, "run_single_benchmark_iteration", fake_run), \
                mock.patch.object(rab.time, "sleep", lambda *_: None), \
                mock.patch.object(sys, "argv", argv):
            rab.main()
        cfg = load_dse_config(self.configs / "kws_reference.toml", target=DRY_RUN_TARGET)
        return calls, CheckpointManager(cfg["output_csv"], cfg["output_map"]).get_iteration_row(0)

    def test_repeated_serial_failure_becomes_runtime_failure(self):
        calls, row = self._run(["serial_failure: Did not receive 4 bytes from device"],
                               ["--max-runtime-retries", "2"])
        self.assertEqual(len(calls), 3)  # tentativa inicial + 2 repetições
        self.assertTrue(row["error"].startswith("runtime_failure: serial_failure:"))

    def test_compile_env_error_is_retried_until_success(self):
        env = "compile.sh: env_error (exit 3): nRF Connect SDK v3.4.0 not listed by 'nrfutil sdk-manager list'."
        calls, row = self._run([env, env, ""], ["--max-runtime-retries", "0"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(row["error"], "")

    def test_legacy_compile_env_error_is_retried(self):
        """Texto antigo da checagem do SDK (gravado como build_error) também é refeito."""
        legacy = ("compile.sh: build_error (exit 1): Install it with: "
                  "/x/nrfutil sdk-manager install v3.4.0")
        calls, row = self._run([legacy, ""], ["--max-runtime-retries", "0"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(row["error"], "")

    def test_existing_legacy_env_error_row_is_rolled_back(self):
        """Uma CSV que já tem a linha antiga é refeita ao religar o loop."""
        import run_all_benchmarks as rab

        legacy = ("compile.sh: build_error (exit 1): Install it with: "
                  "/x/nrfutil sdk-manager install v3.4.0")
        cfg = load_dse_config(self.configs / "kws_reference.toml", target=DRY_RUN_TARGET)
        sample = sample_config(cfg, get_builder_module(cfg["benchmark"]), cfg["base_seed"])
        CheckpointManager(cfg["output_csv"], cfg["output_map"]).save_result(
            0, sample.hash_id, sample.variant_name, sample.hp_list, sample.config, legacy, 1000, 2000, None,
        )
        meta = {"dse_cfg": cfg, "builder": get_builder_module(cfg["benchmark"]),
                "toml_path": self.configs / "kws_reference.toml"}
        self.assertEqual(rab.check_config_iteration_status(meta, 0), (False, True, legacy))
        calls, row = self._run([""])
        self.assertEqual(len(calls), 1)
        self.assertEqual(row["error"], "")

    def test_deploy_failure_is_retried_until_success(self):
        deploy = "Command '['./deploy.sh']' returned non-zero exit status 1."
        calls, row = self._run([deploy, deploy, deploy, deploy, ""], ["--max-runtime-retries", "0"])
        self.assertEqual(len(calls), 5)
        self.assertEqual(row["error"], "")

    def test_compile_and_build_failures_are_kept(self):
        for err in ("compile.sh: memory_overflow (exit 1): region `RAM' overflowed by 12 bytes",
                    "build_failure: ValueError: ..."):
            with self.subTest(err=err):
                for f in self.tmp.glob("out*"):
                    f.unlink()
                calls, row = self._run([err])
                self.assertEqual(len(calls), 1)
                self.assertEqual(row["error"], err)

    def test_compile_failure_classification(self):
        from python_scripts.deployer.deployer import classify_compile_output

        self.assertEqual(classify_compile_output("ld: region `RAM' overflowed by 3456 bytes"), "memory_overflow")
        self.assertEqual(classify_compile_output("section `.bss' will not fit in region `DTCMRAM'"),
                         "memory_overflow")
        self.assertEqual(classify_compile_output("error: 'AddGelu' is not a member"), "build_error")
        self.assertEqual(
            classify_compile_output("Install it with: nrfutil sdk-manager install v3.4.0\n"
                                    "BALAS_ENV_ERROR: nRF Connect SDK v3.4.0 not listed"),
            "env_error",
        )


class TestCompileScriptEnvErrors(unittest.TestCase):
    """compile.sh acusa ambiente quebrado com exit 3 + BALAS_ENV_ERROR (sem compilar nada)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="balas_compile_env_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _compile(self, **env):
        import subprocess

        full_env = {**os.environ, "BALAS_CONFIG_FILE": str(self.tmp / "none.env"), **env}
        return subprocess.run(
            [str(REPO_ROOT / "compile.sh")], cwd=REPO_ROOT, env=full_env,
            capture_output=True, text=True, timeout=60,
        )

    def _fake_nrfutil(self, listing: str) -> Path:
        fake = self.tmp / "nrfutil"
        fake.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' {listing!r}\n")
        fake.chmod(0o755)
        return fake

    def test_unsupported_target(self):
        proc = self._compile(BALAS_TARGET="bogus")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("BALAS_ENV_ERROR: Unsupported BALAS_TARGET: bogus", proc.stderr)

    def test_missing_nrfutil(self):
        proc = self._compile(BALAS_TARGET="nordic", NRFUTIL_BIN=str(self.tmp / "missing"))
        self.assertEqual(proc.returncode, 3)
        self.assertIn("BALAS_ENV_ERROR: nRF Util not found", proc.stderr)

    def test_sdk_not_listed_prints_listing(self):
        fake = self._fake_nrfutil("SDK Type  SDK Version  SDK Status\nnrf       v3.0.0       Installed")
        proc = self._compile(BALAS_TARGET="nordic", NRFUTIL_BIN=str(fake), NORDIC_NCS_VERSION="v3.4.0")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("nrf       v3.0.0       Installed", proc.stderr)  # diagnóstico
        self.assertIn("--- HOME=", proc.stderr)
        self.assertTrue(proc.stderr.rstrip().endswith(
            f"BALAS_ENV_ERROR: nRF Connect SDK v3.4.0 not listed by '{fake} sdk-manager list'."))

    def test_missing_ncs_workspace(self):
        fake = self._fake_nrfutil("nrf       v3.4.0       Installed   Installed")
        proc = self._compile(BALAS_TARGET="nordic", NRFUTIL_BIN=str(fake),
                             NORDIC_NCS_DIR=str(self.tmp / "ncs"))
        self.assertEqual(proc.returncode, 3)
        self.assertIn("BALAS_ENV_ERROR: nRF Connect SDK workspace not found", proc.stderr)

    def test_compile_cpp_project_reports_env_error(self):
        from unittest import mock
        from python_scripts.deployer import deployer

        output = ("--- 'nrfutil sdk-manager list' output:\n\nInstall it with: nrfutil sdk-manager install v3.4.0\n"
                  "BALAS_ENV_ERROR: nRF Connect SDK v3.4.0 not listed by 'nrfutil sdk-manager list'.\n")
        with mock.patch.object(deployer, "_run_tee", return_value=(3, output)):
            with self.assertRaises(RuntimeError) as ctx:
                deployer.compile_cpp_project()
        self.assertEqual(
            str(ctx.exception),
            "compile.sh: env_error (exit 3): nRF Connect SDK v3.4.0 not listed by 'nrfutil sdk-manager list'.",
        )


# ===========================================================================
# 5. Testes com TensorFlow: o .tflite gerado bate com o custo analítico
# ===========================================================================
class TestGeneratedModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tensorflow as tf  # noqa: F401

        cls.tmp = Path(tempfile.mkdtemp(prefix="balas_dse_models_"))
        cls.per_toml = int(os.environ.get("BALAS_TEST_MODELS_PER_TOML", "6"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _check_model(self, path, cost, label):
        import numpy as np
        import tensorflow as tf
        from python_scripts.dse.tflite_inspect import inspect_tflite
        from python_scripts.mac_calculator.mac_calculator import count_macs

        info = inspect_tflite(path)
        self.assertEqual(count_macs(str(path)), cost["macs"], f"{label}: MACs")
        self.assertEqual(info["params"], cost["params"], f"{label}: params")
        self.assertEqual(info["ops"], cost["ops"], f"{label}: sequência de ops")
        # O pico do inspect alinha cada tensor a 16 B; o analítico não.
        self.assertLessEqual(abs(info["peak_activation_bytes"] - cost["peak_activation_bytes"]),
                             16 * 4, f"{label}: pico de ativação")
        # Planner do TFLM simulado: o analítico tem de bater exatamente com o .tflite.
        self.assertEqual(info["planned_activation_bytes"], cost["planned_activation_bytes"],
                         f"{label}: ativações planejadas (GreedyMemoryPlanner)")
        self.assertFalse(set(info["ops"]) & FORBIDDEN_OPS, f"{label}: op proibido {info['ops']}")
        self.assertTrue(set(info["ops"]) <= set(resolver_map), f"{label}: op fora do resolver")
        self.assertEqual(info["input_shape"][1:], tuple(cost["input_shape"]), f"{label}: entrada")
        est = estimate_tflite_bytes(cost)
        # Calibração: erro máximo de 14,4% (AD) em 88 modelos; 20% detecta regressão.
        self.assertLess(abs(est - info["tflite_bytes"]) / info["tflite_bytes"], 0.20,
                        f"{label}: tamanho estimado {est} vs real {info['tflite_bytes']}")

        from python_scripts.dse.tflite_inspect import make_interpreter

        interp = make_interpreter(path)
        self.assertEqual(interp.get_input_details()[0]["dtype"], np.int8)
        self.assertEqual(interp.get_output_details()[0]["dtype"], np.int8)
        self.assertGreater(interp.get_input_details()[0]["quantization"][0], 0)
        tensors = {t["index"]: t for t in interp.get_tensor_details()}
        for op in interp._get_ops_details():
            inputs = [int(i) for i in op["inputs"]]
            if op["op_name"] == "FULLY_CONNECTED":
                self.assertTrue(len(inputs) > 2 and inputs[2] >= 0, f"{label}: FC sem bias")
                self.assertEqual(len(tensors[inputs[1]]["quantization_parameters"]["scales"]), 1,
                                 f"{label}: FC deveria ser por tensor")
            elif op["op_name"] in ("CONV_2D", "DEPTHWISE_CONV_2D"):
                self.assertGreater(len(tensors[inputs[1]]["quantization_parameters"]["scales"]), 1,
                                   f"{label}: conv deveria ser por canal")
            elif op["op_name"] == "AVERAGE_POOL_2D":
                out = tensors[int(op["outputs"][0])]["shape"]
                self.assertEqual(list(out[1:3]), [1, 1], f"{label}: pooling não é global")
        return info

    def test_sampled_models_match_estimates(self):
        for toml, benchmark in NEW_TOMLS.items():
            cfg = load_dse_config(CONFIGS / toml)
            builder = get_builder_module(benchmark)
            for i in range(self.per_toml):
                s = sample_config(cfg, builder, cfg["base_seed"] + 1000 + i)
                label = f"{toml}#{i} {s.variant_name[:60]}"
                with self.subTest(model=label):
                    path = builder.build_and_quantize_model(
                        s.config, f"{benchmark}_{i}", self.tmp, cfg["input_shape"], cfg["num_classes"]
                    )
                    self._check_model(path, s.cost, label)

    def test_every_activation_on_reference_topology(self):
        from python_scripts.dse.tflite_inspect import inspect_tflite

        for benchmark in OFFICIAL:
            builder = get_builder_module(benchmark)
            for act in ACTIVATIONS:
                config = {"activation": act}
                if act == "leaky_relu":
                    config["leaky_slope"] = 0.3
                cost = builder.estimate_cost(config)
                with self.subTest(benchmark=benchmark, activation=act):
                    path = builder.build_and_quantize_model(config, f"{benchmark}_{act}", self.tmp)
                    self._check_model(path, cost, f"{benchmark}/{act}")
                    if act == "leaky_relu":
                        self.assertEqual(self._leaky_alphas(path), {0.3})
                    ops = inspect_tflite(path)["ops"]
                    if act in ("relu", "relu6"):
                        self.assertFalse(set(ops) & set(ACTIVATION_TFLITE_OP.values()))

    @staticmethod
    def _leaky_alphas(path):
        from tensorflow.lite.python import schema_py_generated as schema

        model = schema.ModelT.InitFromPackedBuf(Path(path).read_bytes(), 0)
        alphas = set()
        for op in model.subgraphs[0].operators:
            if isinstance(op.builtinOptions, schema.LeakyReluOptionsT):
                alphas.add(round(float(op.builtinOptions.alpha), 6))
        return alphas

    def test_generation_is_deterministic(self):
        # docs: mesmo config + mesma calibração (seed 72) -> .tflite idêntico.
        cfg = load_dse_config(CONFIGS / "kws.toml")
        builder = get_builder_module("keyword_spotting")
        s = sample_config(cfg, builder, 4242)
        a = builder.build_and_quantize_model(s.config, "det_a", self.tmp, cfg["input_shape"], cfg["num_classes"])
        b = builder.build_and_quantize_model(s.config, "det_b", self.tmp, cfg["input_shape"], cfg["num_classes"])
        self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(), hashlib.sha256(b.read_bytes()).hexdigest())

    def test_vww_input_size_changes_model_input(self):
        builder = get_builder_module("visual_wake_words")
        from python_scripts.dse.tflite_inspect import inspect_tflite

        path = builder.build_and_quantize_model({"input_size": 64}, "vww64", self.tmp, (96, 96, 3), 2)
        self.assertEqual(inspect_tflite(path)["input_shape"], (1, 64, 64, 3))

    def test_arena_fallback_is_close_to_stm32tflm(self):
        """docs/010: stm32tflm = 56.832 B para o ResNet8; o fallback antigo dava ~248 KB."""
        from python_scripts.dse.tflite_inspect import estimate_tflm_arena, inspect_tflite

        arena = estimate_tflm_arena(inspect_tflite(REPO_ROOT / "testdata/sanity-model/model_quant.tflite"))
        self.assertLess(abs(arena - 56_832) / 56_832, 0.03, arena)
        builder = get_builder_module("cifar_ten")
        path = builder.build_and_quantize_model({}, "arena_ref", self.tmp)
        arena_ref = estimate_tflm_arena(inspect_tflite(path))
        self.assertLess(abs(arena_ref - 56_832) / 56_832, 0.03, arena_ref)
        self.assertEqual(arena_ref, builder.estimate_cost({})["arena_estimate"])

    def test_dry_run_end_to_end(self):
        """run_continuous_experiment --dry-run grava linhas completas e não toca resultados reais."""
        from unittest import mock

        import python_scripts.run_continuous_experiment as rce

        toml = (CONFIGS / "vww.toml").read_text()
        toml = toml.replace('"artifacts/{target}/dse_vww.csv"', f'"{self.tmp}/{{target}}/vww.csv"')
        toml = toml.replace('"artifacts/{target}/dse_vww_map.json"', f'"{self.tmp}/{{target}}/vww_map.json"')
        toml_path = self.tmp / "vww_e2e.toml"
        toml_path.write_text(toml)
        argv = ["rce", "--config-toml", str(toml_path), "--max-iterations", "3", "--dry-run",
                "--profiling-samples", "3"]
        with mock.patch.object(sys, "argv", argv):
            rce.main()
        csv_path = self.tmp / "dryrun" / "vww.csv"
        self.assertTrue(csv_path.exists())
        self.assertFalse((self.tmp / "nxp").exists())
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        mapping = json.loads((self.tmp / "dryrun" / "vww_map.json").read_text())
        for row in rows:
            with self.subTest(row=row["hash_id"]):
                self.assertEqual(row["error"], "")
                self.assertEqual(row["target"], DRY_RUN_TARGET)
                self.assertIn(row["activation"], ACTIVATIONS)
                self.assertGreater(int(row["params"]), 0)
                self.assertGreater(int(row["tflite_bytes"]), int(row["params"]) // 2)
                self.assertTrue(row["inference_us_2"] and not row["inference_us_3"])
                entry = mapping[row["hash_id"]]
                self.assertEqual(entry["estimated_cost"]["macs"], int(row["macs"]))
                self.assertEqual(entry["estimated_cost"]["params"], int(row["params"]))
                self.assertEqual(len(entry["durations_us"]), 3)

    def test_sanity_fixture_mac_count(self):
        from python_scripts.mac_calculator.mac_calculator import count_macs

        self.assertEqual(count_macs(str(REPO_ROOT / "testdata/sanity-model/model_quant.tflite")), 12_501_632)

    def test_code_generator_emits_activation_resolvers(self):
        """O resolver gerado para a NXP inclui os ops das ativações e N_OPS correto."""
        from python_scripts.code_generator.generator import generate_cpp_code
        from python_scripts.dse.tflite_inspect import inspect_tflite

        builder = get_builder_module("keyword_spotting")
        for act in ("tanh", "hard_swish", "leaky_relu", "sigmoid"):
            with self.subTest(activation=act):
                path = builder.build_and_quantize_model({"activation": act}, f"gen_{act}", self.tmp)
                out_dir = self.tmp / f"nxp_{act}"
                out_dir.mkdir()
                cwd = os.getcwd()
                try:
                    os.chdir(REPO_ROOT)
                    generate_cpp_code(str(path), 12345, model_dir=out_dir)
                finally:
                    os.chdir(cwd)
                cpp = (out_dir / "model.cpp").read_text()
                header = (out_dir / "model.h").read_text()
                ops = set(inspect_tflite(path)["ops"])
                for op in ops:
                    self.assertIn(f"resolver.{resolver_map[op]}();", cpp)
                self.assertIn(f"#define N_OPS {len(ops)}", header)
                self.assertIn("#define TENSOR_ARENA_SIZE 12345", header)
                self.assertIn("unsigned int model_data_len", (out_dir / "model_data.h").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
