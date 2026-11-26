import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from python_scripts.dse.builders import get_builder_module
from python_scripts.dse.checkpoint import CheckpointManager
from python_scripts.dse.config_loader import DRY_RUN_TARGET, load_dse_config
from python_scripts.dse.sampling import sample_config

# Prefixos gravados por run_continuous_experiment.py.
_NON_CRITICAL_PREFIXES = ("build_failure:", "runtime_failure:")
_SERIAL_FAILURE_PREFIX = "serial_failure:"
RUNTIME_FAILURE_PREFIX = "runtime_failure:"
COMPILE_ENV_ERROR = "compile.sh: env_error"
# Última linha das checagens de ambiente do compile.sh antes de elas saírem com
# BALAS_ENV_ERROR. Linhas antigas com esses textos foram gravadas como
# "compile.sh: build_error" mas são falha da máquina: tratá-las como críticas faz
# o loop refazer a iteração em vez de manter o modelo como "não compilou".
_LEGACY_COMPILE_ENV_ERRORS = (
    "sdk-manager install",
    "Install nRF Util and its sdk-manager command",
    "Set NORDIC_NCS_DIR to the installed SDK workspace",
    "or set NORDIC_TFLM_MODULE_DIR",
    "Set MCUXPRESSO_IDE_BIN in the environment",
    "Set MCUX_WORKSPACE_DIR to the directory",
    "Use BALAS_TARGET=nxp",
)


def is_compile_env_error(error_msg: str | None) -> bool:
    """Falha do compile.sh causada pelo ambiente (ferramenta/SDK ausente), não pelo modelo."""
    if not error_msg or "compile.sh" not in error_msg:
        return False
    return COMPILE_ENV_ERROR in error_msg or any(
        legacy in error_msg for legacy in _LEGACY_COMPILE_ENV_ERRORS
    )


def discover_config_tomls(configs_dir: Path) -> list[Path]:
    """Retorna todos os arquivos .toml diretamente em configs_dir (ignora subpastas)."""
    if not configs_dir.exists():
        raise FileNotFoundError(
            f"Diretório de configurações não encontrado: {configs_dir}"
        )
    tomls = sorted(
        p for p in configs_dir.iterdir() if p.is_file() and p.suffix.lower() == ".toml"
    )
    if not tomls:
        raise FileNotFoundError(
            f"Nenhum arquivo .toml encontrado na raiz de: {configs_dir}"
        )
    return tomls


def is_critical_error(error_msg: str | None) -> bool:
    """
    Classifica se o erro registrado em uma execução é crítico.
    - Sem erro (""): não é crítico (False).
    - Erro de compile.sh: aceitável (False), pois indica que a arena/modelo não coube na FLASH/RAM
      ou que o modelo não compila.
    - Exceto ``compile.sh: env_error`` (ferramenta/SDK ausente na máquina): crítico (True),
      como as linhas antigas gravadas antes dessa classificação existir (ver
      _LEGACY_COMPILE_ENV_ERRORS).
    - build_failure: (builder/conversão/estimativa) é determinístico: repetir não muda nada (False).
    - runtime_failure: falha na placa que se repetiu além do limite de tentativas (False).
    - Erro de deploy.sh, falha na serial ou qualquer outro erro: crítico (True).
    """
    if not error_msg or not error_msg.strip():
        return False
    if "compile.sh" in error_msg:
        return is_compile_env_error(error_msg)
    if error_msg.strip().startswith(_NON_CRITICAL_PREFIXES):
        return False
    return True


def is_runtime_failure_candidate(error_msg: str | None) -> bool:
    """Falha serial depois de um deploy bem-sucedido: pode ser do próprio modelo.

    Ex.: arena que compila mas não cabe no AllocateTensors, buffer de entrada que
    não cabe no heap, ou inferência mais lenta que o timeout. Esses casos se
    repetem a cada tentativa, então viram resultado depois de N repetições.
    Erros de deploy.sh (placa desconectada, probe) nunca entram aqui.
    """
    if not error_msg:
        return False
    msg = error_msg.strip()
    return msg.startswith(_SERIAL_FAILURE_PREFIX) and "deploy.sh" not in msg


def rollback_iteration_across_configs(configs_meta: list[dict], iteration: int) -> None:
    """Apaga as linhas do CSV e entradas do JSON correspondentes a `iteration` em todos os benchmarks."""
    for meta in configs_meta:
        cp = CheckpointManager(
            meta["dse_cfg"]["output_csv"], meta["dse_cfg"]["output_map"]
        )
        removed = cp.rollback_iteration(iteration)
        if removed > 0:
            print(
                f"   🧹 Rollback [iteration_index={iteration}] em {meta['toml_path'].name}: "
                f"removida(s) {removed} linha(s) de {meta['dse_cfg']['output_csv'].name}"
            )


def sync_to_results(configs_meta: list[dict], results_dir: Path) -> None:
    """Copia os arquivos CSV e JSON de todos os benchmarks para o diretório results/."""
    results_dir.mkdir(parents=True, exist_ok=True)
    copied_files = []
    for meta in configs_meta:
        csv_path: Path = meta["dse_cfg"]["output_csv"]
        map_path: Path = meta["dse_cfg"]["output_map"]
        for src_path in (csv_path, map_path):
            if src_path.exists():
                dst_path = results_dir / src_path.name
                shutil.copy2(src_path, dst_path)
                copied_files.append(dst_path.name)

    print(
        f"📦 [Batch Sync] Copiados {len(copied_files)} arquivo(s) para {results_dir}/: "
        f"{', '.join(copied_files)}"
    )


def check_config_iteration_status(meta: dict, iteration: int) -> tuple[bool, bool, str]:
    """
    Verifica o estado de `iteration` para um benchmark específico.
    Retorna (completed, has_critical_error, error_msg).
    """
    dse_cfg = meta["dse_cfg"]
    cp = CheckpointManager(dse_cfg["output_csv"], dse_cfg["output_map"])
    row = cp.get_iteration_row(iteration)
    if row is not None:
        err = row.get("error", "")
        if is_critical_error(err):
            return False, True, err
        return True, False, err

    seed = dse_cfg["base_seed"] + iteration
    hash_id = sample_config(dse_cfg, meta["builder"], seed).hash_id
    if cp.is_completed(hash_id):
        return True, False, ""

    return False, False, ""


def run_single_benchmark_iteration(
    toml_path: Path,
    iteration: int,
    target: str | None,
    serial_device: str | None,
    profiling_samples: int | None,
    dry_run: bool = False,
) -> int:
    """Invoca run_continuous_experiment.py para um único benchmark e iteration_index."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "python_scripts" / "run_continuous_experiment.py"),
        "--config-toml",
        str(toml_path),
        "--iteration-index",
        str(iteration),
    ]
    if target:
        cmd.extend(["--target", target])
    if serial_device:
        cmd.extend(["--serial-device", serial_device])
    if profiling_samples is not None:
        cmd.extend(["--profiling-samples", str(profiling_samples)])
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if proc.returncode in (-2, 130):
        raise KeyboardInterrupt
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Wrapper para executar todos os benchmarks de configs/ sincronizados por iteration_index."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Quantidade de iterações completas antes de copiar os resultados para results/ (padrão: 10).",
    )
    parser.add_argument(
        "--configs-dir",
        default="configs",
        help="Diretório com os arquivos .toml (apenas o nível raiz do diretório é lido).",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Diretório na raiz do repositório para salvar os resultados oficiais a cada batch.",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Placa alvo (nxp, stm32, nordic). Se omitido, usa BALAS_TARGET.",
    )
    parser.add_argument(
        "--serial-device",
        default=None,
        help="Porta serial do microcontrolador (ex: /dev/ttyACM0). Se omitido, usa a porta do ambiente.",
    )
    parser.add_argument(
        "--profiling-samples",
        type=int,
        default=None,
        help="Quantidade de amostras para testar na serial por modelo.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Limite máximo de iterações (opcional).",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="Tempo de espera em segundos antes de tentar novamente uma iteração após erro crítico.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa em modo de simulação (host-only), pulando compilação, deploy e serial.",
    )
    parser.add_argument(
        "--max-runtime-retries",
        type=int,
        default=2,
        help=(
            "Quantas vezes repetir uma falha serial do mesmo modelo antes de gravá-la como "
            "runtime_failure e seguir em frente (padrão: 2)."
        ),
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size deve ser maior ou igual a 1.")
    if args.max_runtime_retries < 0:
        parser.error("--max-runtime-retries deve ser >= 0.")

    if args.target:
        os.environ["BALAS_TARGET"] = args.target

    if not args.dry_run:
        from python_scripts.dse.hardware import HardwareAdapter

        try:
            HardwareAdapter(target=args.target).check_supported()
        except RuntimeError as exc:
            print(f"❌ {exc}")
            sys.exit(2)

    configs_dir = (REPO_ROOT / args.configs_dir).resolve()
    results_dir = (REPO_ROOT / args.results_dir).resolve()
    toml_files = discover_config_tomls(configs_dir)
    load_target = DRY_RUN_TARGET if args.dry_run else None

    configs_meta = []
    for toml_path in toml_files:
        dse_cfg = load_dse_config(toml_path, serial_override=args.serial_device, target=load_target)
        configs_meta.append(
            {
                "toml_path": toml_path,
                "dse_cfg": dse_cfg,
                "builder": get_builder_module(dse_cfg["benchmark"]),
            }
        )
    # Falhas seriais por (toml, iteration_index), para o limite de repetições.
    runtime_failures: dict[tuple[str, int], int] = {}

    print("=" * 75)
    print("🚀 Inicializando Execução Orquestrada de Todos os Benchmarks")
    print(f"📂 Diretório de configs: {configs_dir}")
    print(
        f"📋 Benchmarks encontrados ({len(configs_meta)}): "
        f"{', '.join(m['toml_path'].name for m in configs_meta)}"
    )
    print(f"📦 Tamanho do lote (--batch-size): {args.batch_size}")
    print(f"📁 Diretório oficial de resultados: {results_dir}")
    print("=" * 75)

    iteration = 0
    iterations_since_sync = 0

    try:
        while True:
            if args.max_iterations is not None and iteration >= args.max_iterations:
                print(f"🏁 Alcançado limite máximo de {args.max_iterations} iterações.")
                break

            # Verifica se algum benchmark tinha erro crítico pendente nesta iteração
            statuses = [
                check_config_iteration_status(meta, iteration) for meta in configs_meta
            ]
            if any(has_crit for _, has_crit, _ in statuses):
                print(
                    f"⚠️  Erro crítico anterior detectado na iteração #{iteration+1} "
                    f"(iteration_index={iteration}). Executando rollback antes de reprocessar..."
                )
                rollback_iteration_across_configs(configs_meta, iteration)
                statuses = [(False, False, "") for _ in configs_meta]

            # Se todos os benchmarks já concluíram esta iteração sem erro crítico, avança
            if all(done for done, _, _ in statuses):
                print(
                    f"⏭️  Iteração #{iteration+1} (iteration_index={iteration}) "
                    f"já concluída em todos os benchmarks. Pulando."
                )
                iteration += 1
                continue

            # Loop de tentativa para a iteração atual (repete em caso de erro crítico)
            while True:
                print(
                    f"\n🔄 [Iteração #{iteration+1} | iteration_index={iteration}] "
                    f"Executando {len(configs_meta)} benchmark(s)..."
                )
                critical_failure = False
                failed_benchmark = ""
                failure_reason = ""

                for meta in configs_meta:
                    toml_path = meta["toml_path"]
                    done, has_crit, prev_err = check_config_iteration_status(
                        meta, iteration
                    )
                    if has_crit:
                        critical_failure = True
                        failed_benchmark = toml_path.name
                        failure_reason = prev_err
                        break
                    if done:
                        print(
                            f"   ⏭️  [{toml_path.name}] iteration_index={iteration} já concluído."
                        )
                        continue

                    print(f"\n▶️  [{toml_path.name}] Iniciando iteration_index={iteration}...")
                    returncode = run_single_benchmark_iteration(
                        toml_path=toml_path,
                        iteration=iteration,
                        target=args.target,
                        serial_device=args.serial_device,
                        profiling_samples=args.profiling_samples,
                        dry_run=args.dry_run,
                    )

                    if returncode != 0:
                        critical_failure = True
                        failed_benchmark = toml_path.name
                        failure_reason = (
                            f"Subprocesso encerrou com código de saída {returncode}"
                        )
                        break

                    done_after, has_crit_after, err_after = (
                        check_config_iteration_status(meta, iteration)
                    )
                    if has_crit_after and is_runtime_failure_candidate(err_after):
                        key = (toml_path.name, iteration)
                        runtime_failures[key] = runtime_failures.get(key, 0) + 1
                        if runtime_failures[key] > args.max_runtime_retries:
                            cp = CheckpointManager(
                                meta["dse_cfg"]["output_csv"], meta["dse_cfg"]["output_map"]
                            )
                            cp.mark_iteration_error(
                                iteration, f"{RUNTIME_FAILURE_PREFIX} {err_after}"
                            )
                            print(
                                f"   ℹ️  [{toml_path.name}] Falha serial repetida "
                                f"{runtime_failures[key]}x no mesmo modelo; gravada como "
                                f"runtime_failure e mantida."
                            )
                            done_after, has_crit_after = True, False
                    if has_crit_after:
                        critical_failure = True
                        failed_benchmark = toml_path.name
                        failure_reason = err_after
                        break
                    if not done_after:
                        critical_failure = True
                        failed_benchmark = toml_path.name
                        failure_reason = (
                            "Nenhum resultado foi registrado no CSV/JSON para a iteração"
                        )
                        break

                    if err_after and "compile.sh" in err_after:
                        print(
                            f"   ℹ️  [{toml_path.name}] Erro de compile.sh aceito "
                            f"(arena não coube na FLASH/RAM). Mantendo registro."
                        )

                if critical_failure:
                    print(
                        f"\n❌ Erro crítico em [{failed_benchmark}] na iteração #{iteration+1} "
                        f"(iteration_index={iteration}): {failure_reason}"
                    )
                    print(
                        f"🧹 Apagando registros de iteration_index={iteration} em todos os CSVs e JSONs..."
                    )
                    rollback_iteration_across_configs(configs_meta, iteration)
                    print(
                        f"⏳ Aguardando {args.retry_delay:.1f}s antes de tentar novamente "
                        f"a iteração #{iteration+1} (iteration_index={iteration})..."
                    )
                    time.sleep(args.retry_delay)
                    continue

                # Todos os benchmarks finalizaram a iteração atual sem erro crítico
                break

            iteration += 1
            iterations_since_sync += 1

            if iterations_since_sync >= args.batch_size:
                sync_to_results(configs_meta, results_dir)
                iterations_since_sync = 0

        if iterations_since_sync > 0:
            sync_to_results(configs_meta, results_dir)

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupção pelo usuário (Ctrl+C).")
        print(f"📍 Parado na iteração #{iteration+1} (iteration_index={iteration}).")


if __name__ == "__main__":
    main()
