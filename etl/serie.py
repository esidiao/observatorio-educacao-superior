"""
Série histórica: agrega um ano do Censo e acumula em data/cursos/<slug>/serie.json.

Uso (uma vez por edição do Censo):
    python etl/serie.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2023.CSV \
                        --ies   caminho/MICRODADOS_ED_SUP_IES_2023.CSV

Por que um arquivo separado do bruto.json: a série não precisa dos 45 indicadores
de cada ano — precisa de poucos, comparáveis, ao longo do tempo. Guardar o bruto
inteiro de cada edição multiplicaria o repositório por nada.

Idempotente por ano: rodar de novo para 2023 substitui 2023 e preserva os demais.

CUIDADO com o que a série NÃO autoriza a dizer. O Censo é um retrato anual de
estoques. A diferença de matrículas entre dois anos não é evasão: não acompanha
os mesmos estudantes, e mistura quem entrou, quem saiu, quem trancou e quem
concluiu. Evasão exige acompanhamento de coorte (os indicadores de fluxo do INEP,
publicados à parte). Aqui não se calcula evasão — o que existe é variação de
estoque, rotulada como tal.

Rótulos CINE podem mudar entre edições. Um curso que não existe num ano fica
ausente daquele ponto da série, nunca zerado: zero significaria "existia e não
tinha vaga", e a diferença importa.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

from referencias import MUN_TOTAL_UF

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

COLUNAS = [
    "NU_ANO_CENSO", "SG_UF", "NO_MUNICIPIO", "CO_IES", "NO_CINE_ROTULO",
    "TP_MODALIDADE_ENSINO", "TP_REDE", "QT_VG_TOTAL", "QT_CURSO",
    "QT_ING", "QT_MAT", "QT_CONC",
]
MOD_PRESENCIAL, MOD_EAD = "1", "2"
REDE_PUBLICA = "1"

# O que vale a pena acompanhar no tempo. Deliberadamente curto: série longa de
# indicador derivado (ICT, IAF) confunde mudança de realidade com mudança de
# metodologia entre edições.
CAMPOS = ["vagas_total", "vagas_presencial", "vagas_ead", "matriculas",
          "matriculas_ead", "ingressos", "concluintes", "n_ies",
          "municipios_oferta", "vagas_publicas"]


def agregar(presencial, ead_sede, ead_polo):
    vagas_presencial = int(presencial["QT_VG_TOTAL"].sum())
    vagas_ead = int(ead_sede["QT_VG_TOTAL"].sum())
    capacidade = pd.concat([presencial, ead_sede])
    ies = {str(i) for i, sub in capacidade.groupby("CO_IES")
           if int(sub["QT_VG_TOTAL"].sum()) > 0}
    return {
        "vagas_total": vagas_presencial + vagas_ead,
        "vagas_presencial": vagas_presencial,
        "vagas_ead": vagas_ead,
        "matriculas": int(presencial["QT_MAT"].sum()),
        "matriculas_ead": int(ead_polo["QT_MAT"].sum()),
        "ingressos": int(presencial["QT_ING"].sum()),
        "concluintes": int(presencial["QT_CONC"].sum()),
        "n_ies": len(ies),
        "municipios_oferta": presencial["NO_MUNICIPIO"].dropna().nunique(),
        "vagas_publicas": int(
            capacidade[capacidade["TP_REDE"] == REDE_PUBLICA]["QT_VG_TOTAL"].sum()),
    }


def main():
    parser = argparse.ArgumentParser(description="Acumula um ano do Censo na série")
    parser.add_argument("--censo", required=True)
    parser.add_argument("--ies", required=True)
    parser.add_argument("--cursos", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    with open(args.cursos, encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    print(f"[INFO] Cadastro de IES: {args.ies}")
    ies = pd.read_csv(args.ies, sep=";", encoding="latin-1", dtype=str,
                      low_memory=False, usecols=["CO_IES", "SG_UF_IES"])
    uf_da_ies = dict(zip(ies["CO_IES"], ies["SG_UF_IES"]))

    print(f"[INFO] Lendo {args.censo} ...")
    df = pd.read_csv(args.censo, sep=";", encoding="latin-1", dtype=str,
                     low_memory=False, usecols=COLUNAS)
    for col in COLUNAS:
        if col.startswith("QT_"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    ano = str(df["NU_ANO_CENSO"].iloc[0])
    print(f"[INFO] {len(df)} linhas · Censo {ano}")

    grupos = dict(list(df.groupby("NO_CINE_ROTULO")))
    escritos = ausentes = 0

    for curso in catalogo:
        sub = grupos.get(curso["cine_rotulo"])
        destino = DATA / "cursos" / curso["slug"]
        caminho = destino / "serie.json"

        serie = {}
        if caminho.exists():
            with open(caminho, encoding="utf-8") as f:
                serie = json.load(f).get("anos", {})

        if sub is None or sub.empty:
            # Rótulo inexistente nesta edição: o ponto some da série, não vira zero.
            serie.pop(ano, None)
            ausentes += 1
        else:
            presencial = sub[sub["TP_MODALIDADE_ENSINO"] == MOD_PRESENCIAL]
            ead = sub[sub["TP_MODALIDADE_ENSINO"] == MOD_EAD]
            ead_sede = ead[ead["SG_UF"].isna()].copy()
            ead_sede["UF_SEDE"] = ead_sede["CO_IES"].map(uf_da_ies)
            ead_polo = ead[ead["SG_UF"].notna()]

            por_uf = {}
            for uf in sorted(MUN_TOTAL_UF):
                p = presencial[presencial["SG_UF"] == uf]
                s = ead_sede[ead_sede["UF_SEDE"] == uf]
                pl = ead_polo[ead_polo["SG_UF"] == uf]
                if p.empty and s.empty and pl.empty:
                    continue
                por_uf[uf] = agregar(p, s, pl)

            if not por_uf:
                serie.pop(ano, None)
                ausentes += 1
            else:
                brasil = {c: sum(u[c] for u in por_uf.values()) for c in CAMPOS}
                # n_ies e municipios_oferta somados por UF contam duas vezes quem
                # atua em mais de uma; recalculados no universo inteiro.
                brasil["n_ies"] = int(pd.concat([presencial, ead_sede])["CO_IES"].nunique())
                brasil["municipios_oferta"] = int(
                    presencial["NO_MUNICIPIO"].dropna().nunique())
                serie[ano] = {"BR": brasil, "ufs": por_uf}
                escritos += 1

        if serie:
            destino.mkdir(parents=True, exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"campos": CAMPOS, "anos": dict(sorted(serie.items()))},
                          f, ensure_ascii=False, indent=1)

    print(f"\n[OK] Censo {ano} acumulado: {escritos} cursos com dados · "
          f"{ausentes} sem o rótulo nesta edição (ponto ausente, não zero).")


if __name__ == "__main__":
    main()
