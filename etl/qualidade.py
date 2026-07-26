"""
Ingestão dos indicadores de qualidade (CPC/ENADE/IDD) por UF e por curso.

Uso:
    python etl/qualidade.py --cpc caminho/CPC_AAAA.xlsx

A planilha do CPC cobre apenas as áreas avaliadas no ciclo daquele ano — o ENADE
é trienal e reveza as áreas. Cursos do catálogo fora do ciclo simplesmente não
recebem indicadores de qualidade: os campos ficam null e o IAF não é calculado.
Nunca se estima um conceito ausente.

As médias por UF são ponderadas pelo nº de concluintes participantes, não simples:
um curso com 300 concluintes não pode pesar o mesmo que um com 8.
"""
import argparse
import json
import unicodedata
from pathlib import Path

import pandas as pd

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Campo interno → trecho identificador da coluna na planilha do INEP
CAMPOS = {
    "ENADE":              ("CONCEITO ENADE", "CONTINUO"),
    "IDD":                ("NOTA PADRONIZADA", "IDD"),
    "CPC_cont":           ("CPC", "CONTINUO"),
    "cpc_org_didatico":   ("NOTA BRUTA", "DIDATICO"),
    "cpc_infraestrutura": ("NOTA BRUTA", "INFRAESTRUTURA"),
    "cpc_oportunidade":   ("NOTA BRUTA", "OPORTUNIDADE"),
    "pct_doc_mestres":    ("NOTA BRUTA", "MESTRES"),
    "pct_doc_doutores":   ("NOTA BRUTA", "DOUTORES"),
    "pct_doc_regime":     ("NOTA BRUTA", "REGIME"),
}
# Campos gravados como proporção 0–1 na planilha e exibidos como percentual.
PERCENTUAIS = {"pct_doc_mestres", "pct_doc_doutores", "pct_doc_regime"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def achar_coluna(colunas, *trechos):
    for c in colunas:
        n = norm(c)
        if all(t in n for t in trechos):
            return c
    return None


def media_ponderada(grupo, campo, peso="concluintes"):
    """Média ponderada por concluintes participantes; None se não houver dado."""
    sub = grupo.dropna(subset=[campo])
    if sub.empty:
        return None
    pesos = sub[peso]
    if pesos.sum() > 0:
        return float((sub[campo] * pesos).sum() / pesos.sum())
    return float(sub[campo].mean())


def main():
    parser = argparse.ArgumentParser(description="Ingestão de qualidade (CPC/ENADE) por curso")
    parser.add_argument("--cpc", required=True, help="Planilha CPC_AAAA.xlsx do INEP")
    parser.add_argument("--aba", default="CPC_2023", help="Nome da aba na planilha")
    parser.add_argument("--cursos", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    with open(args.cursos, encoding="utf-8") as f:
        catalogo = json.load(f)["cursos"]

    print(f"[INFO] Lendo {args.cpc} (aba {args.aba}) ...")
    raw = pd.read_excel(args.cpc, sheet_name=args.aba, header=0, dtype=str)
    cols = list(raw.columns)

    c_area = achar_coluna(cols, "AREA", "AVALIA")
    c_uf = achar_coluna(cols, "SIGLA", "UF")
    c_mod = achar_coluna(cols, "MODALIDADE")
    c_conc = achar_coluna(cols, "CONCLUINTES", "PARTICIPANTES")
    c_curso = achar_coluna(cols, "CODIGO", "CURSO")
    if not all([c_area, c_uf, c_mod, c_conc]):
        raise SystemExit("[ERRO] Colunas essenciais não localizadas na planilha.")

    mapa = {campo: achar_coluna(cols, *trechos) for campo, trechos in CAMPOS.items()}
    faltando = [k for k, v in mapa.items() if v is None]
    if faltando:
        print(f"[AVISO] Colunas não encontradas (ficarão nulas): {', '.join(faltando)}")

    usadas = [c_area, c_uf, c_mod, c_conc, c_curso] + [v for v in mapa.values() if v]
    df = raw[usadas].copy()
    df.columns = (["area", "uf", "modalidade", "concluintes", "cod_curso"]
                  + [k for k, v in mapa.items() if v])
    for col in ["concluintes"] + [k for k, v in mapa.items() if v]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df["concluintes"] = df["concluintes"].fillna(0)
    df["_mod"] = df["modalidade"].apply(
        lambda x: "ead" if "DIST" in norm(x) else "presencial")

    areas_planilha = {norm(a) for a in df["area"].dropna().unique()}

    fora_do_ciclo = 0
    for curso in catalogo:
        # A área de avaliação vem declarada no catálogo (etl/catalogo.py faz a tradução
        # CINE → CPC uma vez só). Casar aqui pelo nome do curso não serve: a planilha usa
        # outra nomenclatura ("TECNOLOGIA EM RADIOLOGIA" para o rótulo "Radiologia"), e
        # match por substring capturaria "BIOMEDICINA" a partir de "MEDICINA".
        alvo = norm(curso["cpc_area"]) if curso.get("cpc_area") else None
        if alvo is None or alvo not in areas_planilha:
            fora_do_ciclo += 1
            continue

        # Vagas dos cursos avaliados: join pelo código de curso com o Censo.
        bruto_path = DATA / "cursos" / curso["slug"] / "bruto.json"
        vagas_por_curso = {}
        if bruto_path.exists():
            with open(bruto_path, encoding="utf-8") as f:
                vagas_por_curso = json.load(f).get("vagas_por_curso", {})
        else:
            print(f"  [AVISO] {bruto_path.name} ausente — rode etl/ingestao.py antes; "
                  f"vagas_avaliadas ficará nulo e o IAF não será calculado.")

        sub = df[df["area"].apply(norm) == alvo]
        por_uf = {}
        for uf, grupo in sub.groupby("uf"):
            uf = norm(uf)
            codigos = {str(c).strip() for c in grupo["cod_curso"].dropna()}
            # Só soma o que casou de fato; sem correspondência → None, nunca zero.
            casados = [vagas_por_curso[c] for c in codigos if c in vagas_por_curso]
            registro = {"vagas_avaliadas": sum(casados) if casados else None,
                        "concluintes_avaliados": int(grupo["concluintes"].sum()),
                        "n_cursos_avaliados": int(len(grupo))}
            for campo in CAMPOS:
                if mapa.get(campo) is None:
                    registro[campo] = None
                    continue
                valor = media_ponderada(grupo, campo)
                if valor is None:
                    registro[campo] = None
                elif campo in PERCENTUAIS:
                    registro[campo] = round(valor * 100, 1)
                else:
                    registro[campo] = round(valor, 2)
            # CC (Conceito de Curso) e ENADE compartilham o conceito contínuo do ENADE.
            registro["CC"] = registro.get("ENADE")

            por_modalidade = {}
            for mod, g in grupo.groupby("_mod"):
                por_modalidade[mod] = {
                    campo: (round(media_ponderada(g, campo) * (100 if campo in PERCENTUAIS else 1),
                                  1 if campo in PERCENTUAIS else 2)
                            if mapa.get(campo) is not None
                            and media_ponderada(g, campo) is not None else None)
                    for campo in CAMPOS
                }
                por_modalidade[mod]["n_cursos_avaliados"] = int(len(g))
            registro["por_modalidade"] = por_modalidade
            por_uf[uf] = registro

        destino = DATA / "cursos" / curso["slug"]
        destino.mkdir(parents=True, exist_ok=True)
        with open(destino / "qualidade.json", "w", encoding="utf-8") as f:
            json.dump({"ciclo_enade": curso.get("enade_ano"), "ufs": por_uf},
                      f, ensure_ascii=False, indent=2)
        print(f"[CURSO] {curso['nome']}: {len(por_uf)} UFs · "
              f"{len(sub)} cursos avaliados.")

    print(f"\n[OK] Qualidade ingerida. {fora_do_ciclo} cursos fora do ciclo desta "
          f"planilha — qualidade nula e IAF não calculado, como esperado do rodízio "
          f"trienal do ENADE.")


if __name__ == "__main__":
    main()
