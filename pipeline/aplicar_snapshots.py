# -*- coding: utf-8 -*-
"""
Aplica snapshots de coleta (JSON gravados por coletar_*.py --snapshot) na base.

A rodada local separa COLETAR de PUBLICAR: cada coletor grava o que leu num
snapshot; este script reaplica todos os snapshots pendentes, em ordem de
coleta, sobre a base recem-baixada do repositório. Se o push falhar porque o
Actions publicou no meio, a rodada volta a base para origin/main e roda este
script de novo. Nunca há merge de CSV.

Uso:
  python aplicar_snapshots.py --csv pipeline/base pipeline/_coleta/*.json
Sai 0 se aplicou algo, 3 se não havia snapshot válido.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saturno
from saturno import Base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshots", nargs="*")
    ap.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "base"))
    ap.add_argument("--base", default=os.path.join(os.path.dirname(__file__), "base_atual.xlsx"))
    a = ap.parse_args()

    pendentes = []
    for s in a.snapshots:
        try:
            pendentes.append((saturno.carregar_snapshot(s), s))
        except Exception as e:
            print("AVISO snapshot ilegível %s: %s" % (s, e))
    if not pendentes:
        print("nenhum snapshot válido"); return 3
    pendentes.sort(key=lambda x: x[0][0])        # por data-hora da coleta

    if not os.path.exists(a.base):
        saturno.carregar_base_dos_csv(a.csv, a.base)
    base = Base(a.base)
    ultimo = ""
    for (coleta, hoje, posts, cont), caminho in pendentes:
        if posts:
            base.aplicar_posts(posts, coleta)
        if cont:
            base.aplicar_contadores(cont, hoje)
        if posts:
            base.aplicar_leituras(posts, coleta, hoje)
        ultimo = max(ultimo, coleta)
        print("aplicado %s: %d posts, %d contadores (%s)" % (os.path.basename(caminho), len(posts), len(cont), coleta))
    base.salvar(csv_dir=a.csv)
    print(base.resumo())
    ge = os.environ.get("GITHUB_ENV")
    if ge and ultimo:
        with open(ge, "a") as f:
            f.write("COLETA=%s\nHOJE=%s\n" % (ultimo, ultimo[:10]))
    print("COLETA=%s" % ultimo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
