"""
Gera data/cursos.json a partir do universo real de rótulos CINE dos microdados.

Uso:
    python etl/catalogo.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_2024.CSV \
                           --cpc caminho/CPC_2023.xlsx

O catálogo deixou de ser escrito à mão: com centenas de rótulos no Censo, uma lista
curada divergiria dos microdados a cada edição. Aqui cada rótulo distinto de
`NO_CINE_ROTULO` vira uma entrada, e a área CINE vem do próprio arquivo — não há
classificação inventada por analogia.

O vínculo com o ENADE é o único ponto que exige tradução: a "área de avaliação" da
planilha do CPC usa outra nomenclatura que a CINE ("TECNOLOGIA EM RADIOLOGIA" para o
rótulo "Radiologia"). O casamento é feito por normalização + prefixo "TECNOLOGIA EM",
e o que não casa por regra está em OVERRIDES_CPC, explícito. Rótulo sem área de
avaliação correspondente fica com `enade_ano: null` e nunca recebe IAF — o ENADE é
trienal e reveza as áreas, então a maioria dos cursos fica fora de qualquer ciclo
publicado. Isso é esperado, não falha de coleta.

Reexecutar é seguro: `cobertura` e `enade_ano` declarados à mão no catálogo anterior
são preservados por slug (ver PRESERVADOS).
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Campos declarados por curadoria humana que sobrevivem à regeração do catálogo.
PRESERVADOS = ("cobertura", "enade_ano")

# Área de avaliação do CPC → rótulo CINE, quando a regra automática não alcança.
OVERRIDES_CPC = {
    "TECNOLOGIA EM AGRONEGOCIOS": "Gestão do agronegócio",
}

MAX_SLUG = 60

NOTA = (
    "Catálogo gerado por etl/catalogo.py a partir de NO_CINE_ROTULO dos microdados "
    "do Censo — não editar à mão, exceto os campos preservados 'cobertura' e "
    "'enade_ano'. 'cine_rotulo' bate EXATAMENTE com o rótulo do Censo (match exato, "
    "nunca substring — 'Medicina' por substring capturaria 'Biomedicina' e 'Medicina "
    "veterinária'). 'cpc_area' é a área de avaliação correspondente na planilha do "
    "CPC; null quando o curso está fora do ciclo ENADE publicado, e então não há IAF. "
    "'cobertura' declara a proxy territorial de cobertura correlata; null quando não "
    "existe fonte oficial adequada — nesse caso o indicador não é exibido, jamais "
    "estimado."
)

# TP_GRAU_ACADEMICO no Censo
GRAUS = {"1": "bacharelado", "2": "licenciatura", "3": "tecnológico", "4": "sequencial"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def slugificar(nome):
    base = norm(nome).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if len(base) > MAX_SLUG:
        base = base[:MAX_SLUG].rsplit("-", 1)[0]
    return base


def areas_cpc(caminho, aba):
    """Lê as áreas de avaliação da planilha do CPC. Sem planilha, ninguém tem ENADE."""
    if not caminho:
        print("[INFO] Sem planilha de CPC — nenhum curso receberá ciclo ENADE.")
        return []
    bruto = pd.read_excel(caminho, sheet_name=aba, dtype=str)
    col = next((c for c in bruto.columns
                if "AREA" in norm(c) and "AVALIA" in norm(c)), None)
    if col is None:
        raise SystemExit("[ERRO] Coluna de área de avaliação não localizada na planilha.")
    return sorted(bruto[col].dropna().unique())


def casar_cpc(areas, rotulos):
    """Área de avaliação do CPC → rótulo CINE. Retorna {rotulo: area}."""
    por_norma = {norm(r): r for r in rotulos}
    mapa, orfas = {}, []
    for area in areas:
        alvo = OVERRIDES_CPC.get(norm(area))
        if alvo is None:
            candidato = norm(area)
            candidato = re.sub(r"^TECNOLOGIA EM ", "", candidato)
            candidato = re.sub(r" [IVX]+$", "", candidato)  # "ENGENHARIA DE COMPUTAÇÃO I"
            alvo = por_norma.get(candidato)
        if alvo is None:
            orfas.append(area)
            continue
        mapa[alvo] = area
    if orfas:
        print(f"[AVISO] {len(orfas)} áreas do CPC sem rótulo CINE correspondente "
              f"(ficam fora do IAF): {', '.join(orfas)}")
    return mapa


def main():
    parser = argparse.ArgumentParser(description="Gera o catálogo de cursos do Censo")
    parser.add_argument("--censo", required=True,
                        help="Caminho do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV")
    parser.add_argument("--cpc", help="Planilha CPC_AAAA.xlsx do INEP (opcional)")
    parser.add_argument("--aba", default="CPC_2023")
    parser.add_argument("--enade-ano", type=int, default=2023,
                        help="Ano do ciclo ENADE representado pela planilha")
    parser.add_argument("--saida", default=str(DATA / "cursos.json"))
    args = parser.parse_args()

    anterior = {}
    saida_path = Path(args.saida)
    if saida_path.exists():
        with open(saida_path, encoding="utf-8") as f:
            anterior = {c["slug"]: c for c in json.load(f).get("cursos", [])}
        print(f"[INFO] Catálogo anterior: {len(anterior)} cursos "
              f"(campos {', '.join(PRESERVADOS)} serão preservados por slug).")

    print(f"[INFO] Lendo {args.censo} ...")
    df = pd.read_csv(args.censo, sep=";", encoding="latin-1", dtype=str, low_memory=False,
                     usecols=["NO_CINE_ROTULO", "CO_CINE_ROTULO", "NO_CINE_AREA_GERAL",
                              "NO_CINE_AREA_ESPECIFICA", "TP_GRAU_ACADEMICO",
                              "QT_VG_TOTAL"])
    df["QT_VG_TOTAL"] = pd.to_numeric(df["QT_VG_TOTAL"], errors="coerce").fillna(0)
    # O CO_CINE_ROTULO vem entre aspas literais no CSV do INEP ("0916F01").
    df["CO_CINE_ROTULO"] = df["CO_CINE_ROTULO"].str.strip('"').str.strip()
    rotulos = sorted(df["NO_CINE_ROTULO"].dropna().unique())
    print(f"[INFO] {len(df)} linhas · {len(rotulos)} rótulos CINE distintos.")

    mapa_cpc = casar_cpc(areas_cpc(args.cpc, args.aba), rotulos)
    print(f"[INFO] {len(mapa_cpc)} rótulos casados com o ciclo ENADE {args.enade_ano}.")

    cursos, usados = [], {}
    for rotulo, sub in df.groupby("NO_CINE_ROTULO"):
        slug = slugificar(rotulo)
        if slug in usados:  # colisão por truncamento: desempata pelo código CINE
            slug = f"{slug}-{sorted(sub['CO_CINE_ROTULO'].dropna().unique())[0]}".lower()
        usados[slug] = rotulo

        area_geral = sorted(sub["NO_CINE_AREA_GERAL"].dropna().unique())
        area_esp = sorted(sub["NO_CINE_AREA_ESPECIFICA"].dropna().unique())
        graus = [GRAUS[g] for g in sorted(sub["TP_GRAU_ACADEMICO"].dropna().unique())
                 if g in GRAUS]
        area_cpc = mapa_cpc.get(rotulo)

        curso = {
            "slug": slug,
            "nome": rotulo,
            "cine_rotulo": rotulo,
            "cine_codigo": sorted(sub["CO_CINE_ROTULO"].dropna().unique())[0],
            "area_cine": area_geral[0] if area_geral else None,
            "area_especifica": area_esp[0] if area_esp else None,
            "graus": graus,
            "cpc_area": area_cpc,
            "enade_ano": args.enade_ano if area_cpc else None,
            "cobertura": None,
            "_vagas": int(sub["QT_VG_TOTAL"].sum()),
        }

        # Curadoria humana do catálogo anterior tem precedência sobre o automático.
        velho = anterior.get(slug)
        if velho:
            for campo in PRESERVADOS:
                if velho.get(campo) is not None and curso.get(campo) is None:
                    curso[campo] = velho[campo]
        cursos.append(curso)

    cursos.sort(key=lambda c: (-c["_vagas"], c["slug"]))
    for c in cursos:
        c.pop("_vagas")

    with open(saida_path, "w", encoding="utf-8") as f:
        json.dump({"_nota": NOTA, "cursos": cursos}, f, ensure_ascii=False, indent=2)

    novos = [c["slug"] for c in cursos if c["slug"] not in anterior]
    sumidos = [s for s in anterior if s not in usados]
    com_enade = sum(1 for c in cursos if c["enade_ano"])
    print(f"\n[OK] {len(cursos)} cursos gravados em {saida_path}")
    print(f"     {com_enade} com ciclo ENADE · {len(cursos) - com_enade} sem (IAF nulo)")
    print(f"     {len(novos)} novos · {len(sumidos)} removidos")
    if sumidos:
        print(f"     [ATENÇÃO] slugs que sumiram do Censo: {', '.join(sumidos)} "
              f"— os diretórios em data/cursos/ ficam órfãos, remova-os à mão.")


if __name__ == "__main__":
    main()
