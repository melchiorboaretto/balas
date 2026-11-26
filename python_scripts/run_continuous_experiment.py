import argparse
import os
from pathlib import Path
import sys
import time
import numpy as np

# REPO_ROOT aponta para a raiz do repositório (balas/)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Imports dos utilitários do BALAS
from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
from python_scripts.mac_calculator.mac_calculator import count_macs
from python_scripts.profiler.profiler import send_array_and_get_int

# Imports do pacote modular DSE
from python_scripts.dse.boards import float_fallback
from python_scripts.dse.builders import get_builder_module, validate_grid
from python_scripts.dse.checkpoint import CheckpointManager
from python_scripts.dse.config_loader import DRY_RUN_TARGET, load_dse_config
from python_scripts.dse.hardware import HardwareAdapter
from python_scripts.dse.sampling import sample_config
from python_scripts.dse.tflite_inspect import inspect_tflite

# Prefixos de erro gravados no CSV. run_all_benchmarks.py decide o que fazer
# com cada um (ver is_critical_error / is_runtime_failure).
BUILD_FAILURE = "build_failure"      # builder/conversão/estimativa: determinístico
SERIAL_FAILURE = "serial_failure"    # placa não respondeu ou respondeu inválido


def make_profiling_samples(n_elements: int, count: int, seed: int) -> list[np.ndarray]:
    """Amostras float32 em [0, 1) para um modelo com n_elements de entrada.

    Geradas por modelo (e não uma vez só) porque o input_size da VWW muda a
    entrada de modelo para modelo.
    """
    rng = np.random.default_rng(seed)
    return [rng.uniform(0.0, 1.0, size=(n_elements,)).astype(np.float32) for _ in range(count)]


def validate_duration(value: int) -> int:
    """Rejeita respostas impossíveis (docs/001: outliers de ±160 s por dessincronização)."""
    timeout_us = float(os.environ.get("BALAS_SERIAL_TIMEOUT_SEC", "60")) * 1_000_000
    if value < 0:
        raise RuntimeError(f"{SERIAL_FAILURE}: firmware respondeu {value} (falha no Invoke ou dessincronização)")
    if value > timeout_us:
        raise RuntimeError(f"{SERIAL_FAILURE}: resposta {value} us maior que o timeout serial")
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Loop de teste contínuo em TinyML (Agnóstico a Hardware e Benchmark)"
    )
    parser.add_argument(
        "--config-toml",
        default="configs/cifar_10.toml",
        help="Caminho do arquivo TOML de configuração",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Placa alvo (nxp, stm32, nordic). Se omitido, usa BALAS_TARGET.",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Nome do benchmark (cifar_ten, visual_wake_words, keyword_spotting, anomaly_detection).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Número máximo de iterações para esta execução.",
    )
    parser.add_argument(
        "--iteration-index",
        type=int,
        default=None,
        help="Executa apenas o índice de iteração especificado (0-based).",
    )
    parser.add_argument(
        "--serial-device",
        default=None,
        help="Porta serial do microcontrolador (ex: /dev/ttyACM2). Se omitido, usa a porta do ambiente.",
    )
    parser.add_argument(
        "--profiling-samples",
        type=int,
        default=None,
        help="Quantidade de amostras para testar na serial por modelo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Modo de simulação: constrói modelos, quantiza para INT8, calcula Arena e MACs e "
            "testa inferência no PC, sem microcontrolador. Grava em arquivos separados "
            "(target 'dryrun'), para não marcar modelos como medidos na placa."
        ),
    )
    args = parser.parse_args()

    # 1. Ajusta variável de ambiente para o hardware target, se especificada
    if args.target:
        os.environ["BALAS_TARGET"] = args.target

    # 2. Instancia o adaptador de hardware
    hardware = HardwareAdapter(target=args.target)
    if not args.dry_run:
        hardware.check_supported()

    # 3. Carrega as configurações do TOML (com precedência para --serial-device da CLI)
    dse_cfg = load_dse_config(
        args.config_toml,
        serial_override=args.serial_device,
        target=DRY_RUN_TARGET if args.dry_run else hardware.target,
    )

    # 4. Sobrescreve quantidade de amostras de profiling via CLI, se informado
    if args.profiling_samples:
        dse_cfg["profiling_samples"] = args.profiling_samples

    # 5. Resolve o gerador de modelos (builder) dinamicamente
    benchmark_name = args.benchmark or dse_cfg.get("benchmark", "cifar_ten")
    builder_module = get_builder_module(benchmark_name)

    # 5.1 Confere se o grid do TOML bate com as chaves que o builder entende
    for grid_warning in validate_grid(builder_module, dse_cfg["grid"]):
        print(f"⚠️  {grid_warning}")

    # 6. Prepara o gerenciador de checkpoint e banco de dados CSV/JSON
    checkpoint = CheckpointManager(dse_cfg["output_csv"], dse_cfg["output_map"])

    tmp_dir = Path("/tmp/balas_continuous_models")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print("🔄 Loop de Execução Contínua Inicializado.")
    print(f"🎯 Placa Alvo (Hardware Target): {dse_cfg['target'].upper()}")
    print(f"🧬 Benchmark Selecionado: {benchmark_name}")
    print(f"🔌 Porta Serial Resolvedora: {dse_cfg['serial_device']}")
    print(f"📐 Formato de Entrada (Input Shape) do TOML: {dse_cfg['input_shape']}")
    if dse_cfg["constraints"]:
        print(f"📏 Restrições: {dse_cfg['constraints']}")
    print(f"📦 Modelos já processados no histórico: {len(checkpoint.completed_hashes)}")
    print(f"📄 Salvando resultados em: {dse_cfg['output_csv']}")
    print(f"🔑 Salvando mapeamento de hashes em: {dse_cfg['output_map']}\n")

    iteration = args.iteration_index if args.iteration_index is not None else 0
    try:
        while True:
            # Verifica se atingiu o limite de iterações configurado
            if args.iteration_index is None and args.max_iterations is not None and iteration >= args.max_iterations:
                print(f"🏁 Alcançado limite máximo de {args.max_iterations} iterações.")
                break

            seed = dse_cfg["base_seed"] + iteration
            sample = sample_config(dse_cfg, builder_module, seed)
            config, hp_list, hash_id, variant_name = (
                sample.config, sample.hp_list, sample.hash_id, sample.variant_name
            )

            # --- CHECKPOINT: Se o Hash já foi testado, PULA ---
            if checkpoint.is_completed(hash_id):
                if args.iteration_index is not None:
                    print(
                        f"⏭️  Modelo #{iteration+1} (iteration_index={iteration}, Hash: {hash_id}) já consta no histórico. Pulando."
                    )
                    break
                iteration += 1
                continue

            print(
                f"[{time.strftime('%H:%M:%S')}] 🚀 Modelo #{iteration+1} | Hash: {hash_id} | Variante: {variant_name}"
            )
            print(f"   Hiperparâmetros: {hp_list}")
            if sample.cost:
                print(
                    f"   Custo estimado: params={sample.cost['params']:,} macs={sample.cost['macs']:,} "
                    f"pico_ativ={sample.cost['peak_activation_bytes']:,} B (sorteio {sample.attempt})"
                )

            error_msg = ""
            estimated_arena = None
            macs = None
            durations = None
            info = None
            activation = str(config.get("activation") or "relu")
            fallback = float_fallback(dse_cfg["target"], activation, hardware.stm32_backend)

            try:
                # PASSO A: Constrói e quantiza o modelo .tflite via builder dinâmico
                try:
                    tflite_path = builder_module.build_and_quantize_model(
                        config,
                        variant_name,
                        tmp_dir,
                        input_shape=dse_cfg["input_shape"],
                        num_classes=dse_cfg.get("num_classes"),
                    )

                    # PASSO B: Estima Arena de RAM, calcula MACs e inspeciona o .tflite
                    info = inspect_tflite(tflite_path)
                    estimated_arena = estimate_tensor_arena_size(str(tflite_path))
                    macs = count_macs(str(tflite_path))
                except Exception as exc:
                    raise RuntimeError(f"{BUILD_FAILURE}: {exc}") from exc

                samples = make_profiling_samples(
                    info["input_elements"], dse_cfg["profiling_samples"], seed
                )

                if args.dry_run:
                    # PASSO C & D (DRY-RUN): Executa inferência local no PC via TFLite Interpreter
                    from python_scripts.dse.tflite_inspect import make_interpreter

                    # 1 thread e kernels builtin (sem XNNPACK, que falha em alguns
                    # modelos int8 válidos): tempo estável e comparável entre modelos.
                    interpreter = make_interpreter(tflite_path, mode="builtin", num_threads=1)
                    input_details = interpreter.get_input_details()

                    durations = []
                    for sample_in in samples:
                        in_tensor = sample_in.reshape(input_details[0]["shape"])
                        if input_details[0]["dtype"] == np.int8:
                            scale, zero_point = input_details[0]["quantization"]
                            if scale > 0:
                                in_tensor = np.clip(
                                    np.round(in_tensor / scale) + zero_point, -128, 127
                                ).astype(np.int8)
                            else:
                                in_tensor = in_tensor.astype(np.int8)
                        interpreter.set_tensor(input_details[0]["index"], in_tensor)
                        t0 = time.perf_counter()
                        interpreter.invoke()
                        t1 = time.perf_counter()
                        durations.append(int((t1 - t0) * 1_000_000))

                    avg_us = float(np.mean(durations))
                    std_us = float(np.std(durations))
                    print(
                        f"   🧪 [DRY-RUN] Sucesso no PC! Arena: {estimated_arena} B | MACs: {macs} | Host CPU: {avg_us:.1f} µs (±{std_us:.1f} µs)"
                    )
                else:
                    # PASSO C: Atualiza C++, Compila e faz Deploy
                    hardware.generate_code(str(tflite_path), estimated_arena)
                    hardware.compile()
                    hardware.deploy()

                    # Atraso pós-deploy para a MCU reiniciar e estabilizar a UART
                    hardware.post_deploy_delay()

                    # PASSO D: Transmite amostras via UART e mede as latências individuais
                    durations = []
                    for sample_in in samples:
                        try:
                            dur_us = send_array_and_get_int(dse_cfg["serial_device"], sample_in)
                        except Exception as exc:
                            raise RuntimeError(f"{SERIAL_FAILURE}: {exc}") from exc
                        durations.append(validate_duration(dur_us))

                    avg_us = float(np.mean(durations))
                    std_us = float(np.std(durations))
                    print(
                        f"   ✅ Sucesso! Arena: {estimated_arena} B | MACs: {macs} | Média MCU: {avg_us:.1f} µs (±{std_us:.1f} µs)"
                    )

            except Exception as e:
                error_msg = str(e)
                print(f"   ⚠️ Falha no ciclo: {error_msg}")

            # PASSO E: Grava o resultado incremental no CSV e JSON
            checkpoint.save_result(
                iteration=iteration,
                hash_id=hash_id,
                variant_name=variant_name,
                hp_list=hp_list,
                config=config,
                error_msg=error_msg,
                arena_estimated=estimated_arena,
                macs=macs,
                durations=durations,
                target=dse_cfg["target"],
                activation=activation,
                params=info["params"] if info else None,
                tflite_bytes=info["tflite_bytes"] if info else None,
                float_fallback=fallback,
                extra_map_fields={
                    "estimated_cost": (
                        {k: v for k, v in sample.cost.items() if k != "ops"} if sample.cost else None
                    ),
                    "sample_attempt": sample.attempt,
                    "ops": info["ops"] if info else None,
                },
            )

            iteration += 1
            print("-" * 75)
            if args.iteration_index is not None:
                break

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupção pelo usuário (Ctrl+C).")
        print(
            f"💾 Checkpoint gravado com segurança. Total no banco: {len(checkpoint.completed_hashes)}"
        )

if __name__ == "__main__":
    main()
