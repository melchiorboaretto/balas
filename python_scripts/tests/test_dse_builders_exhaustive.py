"""
Suíte de testes exaustiva para os Builders DSE do BALAS.
Valida a fidelidade com o MLPerf Tiny oficial e a estabilidade da exploração paramétrica.
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf

from python_scripts.dse.builders import get_builder_module, validate_grid
from python_scripts.dse.config_loader import load_dse_config
from python_scripts.dse.hashing import sample_hyperparameters_for_seed
from python_scripts.mac_calculator.mac_calculator import count_macs


class TestMLPerfTinyBuildersExhaustive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="balas_exhaustive_tests_"))
        print(f"\n📂 Diretório temporário de testes: {cls.tmp_dir}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)
        print(f"🧹 Limpeza concluída do diretório temporário.")

    # -----------------------------------------------------------------------
    # 1. VALIDAÇÃO DOS GRIDS TOML
    # -----------------------------------------------------------------------
    def test_01_grid_validation_reference_configs(self):
        """Garante que nenhum arquivo *_reference.toml gere avisos de chaves desconhecidas."""
        configs = [
            ("ad_reference.toml", "anomaly_detection"),
            ("kws_reference.toml", "keyword_spotting"),
            ("vww_reference.toml", "visual_wake_words"),
            ("cifar_10_reference.toml", "cifar_ten"),
        ]
        for filename, bench_name in configs:
            path = REPO_ROOT / "configs" / filename
            self.assertTrue(path.exists(), f"Arquivo não encontrado: {path}")
            cfg = load_dse_config(str(path))
            builder = get_builder_module(bench_name)
            warnings = validate_grid(builder, cfg["grid"])
            self.assertEqual(
                len(warnings),
                0,
                f"Config {filename} gerou avisos de grid: {warnings}",
            )

    def test_02_grid_validation_dse_configs(self):
        """Garante que os arquivos de busca DSE *.toml não possuam chaves ignoradas/desconhecidas."""
        configs = [
            ("ad.toml", "anomaly_detection"),
            ("kws.toml", "keyword_spotting"),
            ("vww.toml", "visual_wake_words"),
            ("cifar_10.toml", "cifar_ten"),
        ]
        for filename, bench_name in configs:
            path = REPO_ROOT / "configs" / filename
            self.assertTrue(path.exists(), f"Arquivo não encontrado: {path}")
            cfg = load_dse_config(str(path))
            builder = get_builder_module(bench_name)
            warnings = validate_grid(builder, cfg["grid"])
            # Filtra apenas avisos de chaves ignoradas (chaves ausentes que usam default são intencionais)
            unknown_warnings = [w for w in warnings if "ignoradas" in w]
            self.assertEqual(
                len(unknown_warnings),
                0,
                f"Config {filename} possui chaves ignoradas pelo builder: {unknown_warnings}",
            )

    # -----------------------------------------------------------------------
    # 2. FIDELIDADE MATEMÁTICA COM O MLPERF TINY OFICIAL
    # -----------------------------------------------------------------------
    def test_03_anomaly_detection_reference_exact_match(self):
        """Valida que o builder de AD com defaults reproduz exatamente os 264.192 MACs do MLPerf Tiny."""
        builder = get_builder_module("anomaly_detection")
        tflite = builder.build_and_quantize_model({}, "ad_ref_test", self.tmp_dir)
        self.assertTrue(tflite.exists())

        interp = tf.lite.Interpreter(model_path=str(tflite))
        interp.allocate_tensors()

        in_det = interp.get_input_details()[0]
        out_det = interp.get_output_details()[0]
        self.assertEqual(in_det["shape"].tolist(), [1, 640])
        self.assertEqual(out_det["shape"].tolist(), [1, 640])
        self.assertEqual(in_det["dtype"].__name__, "int8")
        self.assertEqual(out_det["dtype"].__name__, "int8")

        macs = count_macs(str(tflite))
        self.assertEqual(
            macs,
            264192,
            f"MACs de AD diferem do MLPerf Tiny oficial (esperado 264.192, obtido {macs})",
        )

    def test_04_keyword_spotting_reference_exact_match(self):
        """Valida que o builder de KWS com defaults reproduz exatamente os 2.656.768 MACs do MLPerf Tiny."""
        builder = get_builder_module("keyword_spotting")
        tflite = builder.build_and_quantize_model({}, "kws_ref_test", self.tmp_dir)
        self.assertTrue(tflite.exists())

        interp = tf.lite.Interpreter(model_path=str(tflite))
        interp.allocate_tensors()

        in_det = interp.get_input_details()[0]
        out_det = interp.get_output_details()[0]
        self.assertEqual(in_det["shape"].tolist(), [1, 49, 10, 1])
        self.assertEqual(out_det["shape"].tolist(), [1, 12])
        self.assertEqual(in_det["dtype"].__name__, "int8")
        self.assertEqual(out_det["dtype"].__name__, "int8")

        macs = count_macs(str(tflite))
        self.assertEqual(
            macs,
            2656768,
            f"MACs de KWS diferem do MLPerf Tiny oficial (esperado 2.656.768, obtido {macs})",
        )

    def test_05_visual_wake_words_reference_exact_match(self):
        """Valida que o builder de VWW com defaults reproduz exatamente os 7.489.664 MACs do MLPerf Tiny."""
        builder = get_builder_module("visual_wake_words")
        tflite = builder.build_and_quantize_model({}, "vww_ref_test", self.tmp_dir)
        self.assertTrue(tflite.exists())

        interp = tf.lite.Interpreter(model_path=str(tflite))
        interp.allocate_tensors()

        in_det = interp.get_input_details()[0]
        out_det = interp.get_output_details()[0]
        self.assertEqual(in_det["shape"].tolist(), [1, 96, 96, 3])
        self.assertEqual(out_det["shape"].tolist(), [1, 2])
        self.assertEqual(in_det["dtype"].__name__, "int8")
        self.assertEqual(out_det["dtype"].__name__, "int8")

        macs = count_macs(str(tflite))
        self.assertEqual(
            macs,
            7489664,
            f"MACs de VWW diferem do MLPerf Tiny oficial (esperado 7.489.664, obtido {macs})",
        )

    def test_06_cifar_ten_reference_exact_match(self):
        """Valida que o builder de CIFAR-10 com defaults reproduz exatamente os 12.501.632 MACs do MLPerf Tiny."""
        builder = get_builder_module("cifar_ten")
        tflite = builder.build_and_quantize_model({}, "cifar_ref_test", self.tmp_dir)
        self.assertTrue(tflite.exists())

        interp = tf.lite.Interpreter(model_path=str(tflite))
        interp.allocate_tensors()

        in_det = interp.get_input_details()[0]
        out_det = interp.get_output_details()[0]
        self.assertEqual(in_det["shape"].tolist(), [1, 32, 32, 3])
        self.assertEqual(out_det["shape"].tolist(), [1, 10])
        self.assertEqual(in_det["dtype"].__name__, "int8")
        self.assertEqual(out_det["dtype"].__name__, "int8")

        macs = count_macs(str(tflite))
        self.assertEqual(
            macs,
            12501632,
            f"MACs de CIFAR-10 diferem do MLPerf Tiny oficial (esperado 12.501.632, obtido {macs})",
        )

    def test_06b_reference_operator_sequence(self):
        """Valida que as referências têm a mesma sequência de operadores dos .tflite oficiais.

        MACs iguais não bastam: GlobalAveragePooling2D (MEAN) e AveragePooling2D
        (AVERAGE_POOL_2D) fazem a mesma conta, mas são operadores diferentes
        para a CPU e para a NPU. Também confere que as FULLY_CONNECTED têm bias
        e quantização por tensor, como nos modelos oficiais. O único desvio
        aceito é o RESHAPE entre o pooling e a FULLY_CONNECTED dos oficiais,
        que o conversor atual remove por não fazer cálculo.
        """
        conv_dw = ["DEPTHWISE_CONV_2D", "CONV_2D"]
        residual = ["CONV_2D", "CONV_2D", "CONV_2D", "ADD"]
        head = ["AVERAGE_POOL_2D", "FULLY_CONNECTED", "SOFTMAX"]
        expected = {
            "anomaly_detection": ["FULLY_CONNECTED"] * 10,
            "keyword_spotting": ["CONV_2D"] + conv_dw * 4 + head,
            "visual_wake_words": ["CONV_2D"] + conv_dw * 13 + head,
            "cifar_ten": residual * 3 + head,
        }
        for benchmark, expected_ops in expected.items():
            with self.subTest(benchmark=benchmark):
                builder = get_builder_module(benchmark)
                tflite = builder.build_and_quantize_model(
                    {}, f"{benchmark}_ops_test", self.tmp_dir
                )
                interp = tf.lite.Interpreter(model_path=str(tflite))
                interp.allocate_tensors()
                ops = [op for op in interp._get_ops_details() if op["op_name"] != "DELEGATE"]
                self.assertEqual([op["op_name"] for op in ops], expected_ops)

                tensors = {t["index"]: t for t in interp.get_tensor_details()}
                for op in ops:
                    if op["op_name"] != "FULLY_CONNECTED":
                        continue
                    inputs = list(op["inputs"])
                    self.assertTrue(len(inputs) > 2 and inputs[2] >= 0, "FULLY_CONNECTED sem bias")
                    scales = tensors[inputs[1]]["quantization_parameters"]["scales"]
                    self.assertEqual(len(scales), 1, "FULLY_CONNECTED deveria ser quantizada por tensor")

    # -----------------------------------------------------------------------
    # 3. TESTES EXAUSTIVOS DO ESPAÇO DE EXPLORAÇÃO
    # -----------------------------------------------------------------------
    def _run_dse_sampling_test(self, toml_name: str, benchmark_name: str, samples_count: int = 5):
        toml_path = REPO_ROOT / "configs" / toml_name
        cfg = load_dse_config(str(toml_path))
        builder = get_builder_module(benchmark_name)

        print(f"\n🔬 Testando {samples_count} variantes de {benchmark_name} ({toml_name})...")
        tested_models = 0
        iteration = 0

        while tested_models < samples_count:
            seed = cfg["base_seed"] + iteration
            iteration += 1

            sampled_config, hp_list, hash_id, variant_name = sample_hyperparameters_for_seed(
                cfg["grid"], seed
            )

            tflite_path = builder.build_and_quantize_model(
                sampled_config,
                variant_name,
                self.tmp_dir,
                input_shape=cfg["input_shape"],
                num_classes=cfg.get("num_classes"),
            )
            self.assertTrue(tflite_path.exists())

            interp = tf.lite.Interpreter(model_path=str(tflite_path))
            interp.allocate_tensors()

            macs = count_macs(str(tflite_path))
            self.assertGreater(macs, 0, f"MACs inválidos para {variant_name}")
            tested_models += 1
            print(f"  [{tested_models:02d}/{samples_count:02d}] {variant_name[:50]}... -> {macs:,} MACs")

    def test_07_dse_ad_multi_sample(self):
        """Testa 5 variantes arquiteturais de Anomaly Detection no espaço DSE."""
        self._run_dse_sampling_test("ad.toml", "anomaly_detection", samples_count=5)

    def test_08_dse_kws_multi_sample(self):
        """Testa 5 variantes arquiteturais de Keyword Spotting no espaço DSE."""
        self._run_dse_sampling_test("kws.toml", "keyword_spotting", samples_count=5)

    def test_09_dse_vww_multi_sample(self):
        """Testa 5 variantes arquiteturais de Visual Wake Words no espaço DSE."""
        self._run_dse_sampling_test("vww.toml", "visual_wake_words", samples_count=5)

    def test_10_dse_cifar10_multi_sample(self):
        """Testa 5 variantes arquiteturais de Image Classification no espaço DSE."""
        self._run_dse_sampling_test("cifar_10.toml", "cifar_ten", samples_count=5)

    # -----------------------------------------------------------------------
    # 4. COMPATIBILIDADE REGRESSIVA COM CHAVES LEGADAS
    # -----------------------------------------------------------------------
    def test_11_legacy_compatibility(self):
        """Garante que dicionários com nomes de chaves antigos continuem funcionando."""
        # AD legado (large_fc, medium_fc, small_fc)
        ad_builder = get_builder_module("anomaly_detection")
        ad_legacy = {"large_fc": 256, "medium_fc": 128, "small_fc": 32}
        ad_path = ad_builder.build_and_quantize_model(ad_legacy, "ad_legacy", self.tmp_dir)
        self.assertTrue(ad_path.exists())

        # KWS legado (channels, kernel, first_kernel)
        kws_builder = get_builder_module("keyword_spotting")
        kws_legacy = {"channels": 32, "kernel": 5, "first_kernel": "10x4"}
        kws_path = kws_builder.build_and_quantize_model(kws_legacy, "kws_legacy", self.tmp_dir)
        self.assertTrue(kws_path.exists())

        # VWW legado (initial_channels, kernel)
        vww_builder = get_builder_module("visual_wake_words")
        vww_legacy = {"initial_channels": 8, "kernel": 3}
        vww_path = vww_builder.build_and_quantize_model(vww_legacy, "vww_legacy", self.tmp_dir)
        self.assertTrue(vww_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
