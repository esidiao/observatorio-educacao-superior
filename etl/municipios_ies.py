"""
Contagem exata de instituições e de cursos por município.

    python etl/municipios_ies.py --censo .../MICRODADOS_CADASTRO_CURSOS_2024.CSV

Produz data/municipios_ies.json: código IBGE → instituições distintas, rótulos
CINE distintos e ofertas.

Por que existe. O pipeline principal agrega **por curso** e depois soma os
municípios. Nessa ordem, contar instituições vira problema: a mesma
universidade aparece na linha de Medicina, na de Direito e em mais dezoito, e
somar daria vinte para uma. O acumulador guardava o **máximo** entre os cursos —
um piso honesto, rotulado como tal (`n_ies_minimo`), mas piso. Para um mapa que
mostra "quantas instituições existem aqui", piso não serve.

Contar distintos exige as linhas na mão, e é só isso que este arquivo faz: lê o
microdado uma vez e conta conjuntos.

Três decisões de recorte, todas com consequência no número:

  · Conta-se a instituição que tem oferta PRESENCIAL no município. Polo de EaD
    fica de fora: o polo não é a instituição, é um ponto de apoio dela, e somar
    os dois faria municípios sem nenhum campus aparecerem com dez instituições.
  · "Cursos distintos" são rótulos CINE diferentes. Duas turmas de Direito, em
    dois turnos, são um curso — não dois.
  · "Ofertas" é a contagem de linhas, que responde outra pergunta: quantas
    combinações de curso, instituição e turno existem ali. Os dois números vão
    juntos porque a diferença entre eles é informação.

O casamento com o resto do site é por código IBGE, nunca por nome — há dezenas
de municípios homônimos no país.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

COLUNAS = ["NU_ANO_CENSO", "SG_UF", "NO_MUNICIPIO", "CO_MUNICIPIO", "CO_IES",
           "NO_CINE_ROTULO", "TP_MODALIDADE_ENSINO", "QT_MAT", "QT_VG_TOTAL"]
MOD_PRESENCIAL = "1"


def main():
    parser = argparse.ArgumentParser(
        description="Conta instituições e cursos distintos por município")
    parser.add_argument("--censo", required=True)
    args = parser.parse_args()

    print(f"[INFO] Lendo {args.censo} ...")
    df = pd.read_csv(args.censo, sep=";", encoding="latin-1", dtype=str,
                     low_memory=False, usecols=COLUNAS)
    ano = str(df["NU_ANO_CENSO"].iloc[0])
    for col in ("QT_MAT", "QT_VG_TOTAL"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    presencial = df[df["TP_MODALIDADE_ENSINO"] == MOD_PRESENCIAL]
    presencial = presencial[presencial["CO_MUNICIPIO"].notna()]
    print(f"[INFO] {len(presencial)} linhas presenciais · Censo {ano}")

    municipios = {}
    for codigo, sub in presencial.groupby("CO_MUNICIPIO"):
        codigo = str(codigo).strip()
        municipios[codigo] = {
            "nome": sub["NO_MUNICIPIO"].iloc[0],
            "uf": sub["SG_UF"].iloc[0],
            "n_ies": int(sub["CO_IES"].nunique()),
            "n_cursos_distintos": int(sub["NO_CINE_ROTULO"].nunique()),
            "n_ofertas": int(len(sub)),
            "matriculas": int(sub["QT_MAT"].sum()),
            "vagas": int(sub["QT_VG_TOTAL"].sum()),
        }

    saida = {
        "_fonte": f"INEP — Censo da Educação Superior {ano}, cadastro de cursos",
        "_nota": ("Conta instituições com oferta PRESENCIAL no município. Polo de "
                  "EaD não entra: o polo é ponto de apoio, não a instituição, e "
                  "contá-lo faria municípios sem campus aparecerem com dezenas "
                  "de instituições. Cursos distintos são rótulos CINE diferentes; "
                  "ofertas são as combinações de curso, instituição e turno."),
        "versao_censo": ano,
        "municipios": municipios,
    }
    destino = DATA / "municipios_ies.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")

    total_ies = presencial["CO_IES"].nunique()
    soma = sum(m["n_ies"] for m in municipios.values())
    print(f"[OK] {destino.relative_to(REPO)} — {len(municipios)} municípios")
    print(f"     IES distintas no país : {total_ies}")
    print(f"     Soma por município    : {soma} — maior de propósito: uma "
          f"instituição com campus em várias cidades conta em cada uma.")


if __name__ == "__main__":
    main()
