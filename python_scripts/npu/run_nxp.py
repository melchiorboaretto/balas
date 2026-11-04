#!/usr/bin/env python3
"""
Launcher unificado para testes na NXP MCXN947 (CPU e NPU).

Comandos disponíveis:
  check        Diagnostica o ambiente (IDE, SDK, compilador Neutron, permissões)
  dry-run      Executa teste rápido de 1 modelo de cada benchmark no PC (sem placa)
  referencia   Executa os 4 modelos de referência do MLPerf Tiny na placa
  aleatorio    Executa busca aleatória nos grids DSE (formato clássico do BALAS)
  completo     Executa a bateria sistemática completa (todas as variantes dos grids novos)

Exemplos de uso:
  python python_scripts/npu/run_nxp.py check
  python python_scripts/npu/run_nxp.py dry-run
  python python_scripts/npu/run_nxp.py referencia --modelos kws,vww
  python python_scripts/npu/run_nxp.py aleatorio --modelos kws --max-variantes 50
  python python_scripts/npu/run_nxp.py completo --modelos kws
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launcher Unificado NXP MCXN947 (CPU & NPU) — B.A.L.A.S",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="comando", help="Comando a executar")

    # 1. check
    subparsers.add_parser("check", help="Executa o diagnóstico completo do ambiente")

    # 2. dry-run
    p_dry = subparsers.add_parser("dry-run", help="Executa 1 modelo de cada no PC sem usar a placa")
    p_dry.add_argument("--modelos", default="all", help="Modelos a testar (padrão: all)")

    # 3. referencia
    p_ref = subparsers.add_parser("referencia", help="Executa os modelos de referência do MLPerf Tiny na placa")
    p_ref.add_argument("--modelos", default="all", help="kws, vww, ic, ad ou all (padrão: all)")
    p_ref.add_argument("--backends", default="cpu,npu", help="cpu,npu (padrão), só cpu ou só npu")
    p_ref.add_argument("--sim", action="store_true", help="Pula confirmação interativa")

    # 4. aleatorio
    p_aleat = subparsers.add_parser("aleatorio", help="Busca DSE aleatória (grid histórico do BALAS)")
    p_aleat.add_argument("--modelos", default="all", help="kws, vww, ic, ad ou all (padrão: all)")
    p_aleat.add_argument("--max-variantes", type=int, default=20, help="Quantidade de variantes sorteadas (padrão: 20)")
    p_aleat.add_argument("--backends", default="cpu,npu", help="cpu,npu (padrão), só cpu ou só npu")
    p_aleat.add_argument("--sem-placa", action="store_true", help="Simula apenas no PC")
    p_aleat.add_argument("--sim", action="store_true", help="Pula confirmação interativa")

    # 5. completo
    p_comp = subparsers.add_parser("completo", help="Bateria completa do DSE novo (todas as combinações)")
    p_comp.add_argument("--modelos", default="all", help="kws, vww, ic, ad ou all (padrão: all)")
    p_comp.add_argument("--max-variantes", type=int, default=None, help="Limite opcional de variantes")
    p_comp.add_argument("--backends", default="cpu,npu", help="cpu,npu (padrão), só cpu ou só npu")
    p_comp.add_argument("--sem-placa", action="store_true", help="Simula apenas no PC")
    p_comp.add_argument("--sim", action="store_true", default=True, help="Pula confirmação interativa (padrão True)")

    args, restantes = parser.parse_known_args()

    if not args.comando:
        parser.print_help()
        return 0

    if args.comando == "check":
        from python_scripts.npu.check_environment import run_diagnostics
        return 0 if run_diagnostics() else 1

    from python_scripts.npu import cpu_vs_npu

    cli_args = []
    if args.comando == "dry-run":
        cli_args = ["--modelos", args.modelos, "--modo", "referencia", "--sem-placa", "--sim"]
    elif args.comando == "referencia":
        cli_args = ["--modelos", args.modelos, "--modo", "referencia", "--backends", args.backends]
        if args.sim:
            cli_args.append("--sim")
    elif args.comando == "aleatorio":
        cli_args = ["--modelos", args.modelos, "--modo", "dse", "--max-variantes", str(args.max_variantes),
                    "--backends", args.backends]
        if args.sem_placa:
            cli_args.append("--sem-placa")
        if args.sim:
            cli_args.append("--sim")
    elif args.comando == "completo":
        cli_args = ["--modelos", args.modelos, "--modo", "dse_novo", "--backends", args.backends]
        if args.max_variantes:
            cli_args.extend(["--max-variantes", str(args.max_variantes)])
        if args.sem_placa:
            cli_args.append("--sem-placa")
        if args.sim:
            cli_args.append("--sim")

    cli_args.extend(restantes)
    sys.argv = [sys.argv[0]] + cli_args
    return cpu_vs_npu.main()


if __name__ == "__main__":
    sys.exit(main())

