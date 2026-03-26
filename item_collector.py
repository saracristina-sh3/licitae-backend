"""
Coletor de itens e resultados — thin wrapper para pncp_collector v2.

Mantém compatibilidade com main.py e CLI.

Uso:
    python item_collector.py                          # Coleta pendentes (limite 100)
    python item_collector.py --limite 50              # Coleta 50 pendentes
    python item_collector.py --plataforma 121         # Coleta da SH3
    python item_collector.py --plataforma 121 --uf MG # SH3, só MG
    python item_collector.py --resultados-pendentes   # Coleta resultados pendentes
"""

from pncp_collector.services.orchestration import (  # noqa: F401
    coletar_itens_contratacao,
    coletar_pendentes,
    coletar_por_plataforma,
    coletar_resultados_pendentes,
)

if __name__ == "__main__":
    import argparse
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Coletor de itens e resultados PNCP")
    parser.add_argument("--limite", type=int, default=100, help="Limite de registros (padrão: 100)")
    parser.add_argument("--plataforma", type=int, help="idUsuario da plataforma para coleta direta")
    parser.add_argument("--uf", help="Filtrar por UF (ex: MG)")
    parser.add_argument("--dias", type=int, default=30, help="Dias retroativos (padrão: 30)")
    parser.add_argument(
        "--resultados-pendentes",
        action="store_true",
        help="Coletar apenas resultados pendentes",
    )
    args = parser.parse_args()

    if args.resultados_pendentes:
        coletar_resultados_pendentes(args.limite)
    elif args.plataforma:
        coletar_por_plataforma(
            id_usuario=args.plataforma,
            dias=args.dias,
            uf=args.uf,
        )
    else:
        coletar_pendentes(limite=args.limite)
