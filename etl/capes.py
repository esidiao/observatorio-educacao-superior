"""
Pós-graduação stricto sensu: programas e conceitos CAPES por instituição.

Uso:
    python etl/capes.py --programas caminho/br-capes-colsucup-prog-2024.csv

Baixe em https://dadosabertos.capes.gov.br (conjunto "Programas da Pós-Graduação
Stricto Sensu no Brasil"). O arquivo anual tem ~2 MB.

A junção com o Censo é EXATA, não heurística: o campo `CD_ENTIDADE_EMEC` da CAPES
é o mesmo código de instituição usado pelo INEP. Medido: 353 das 375 IES da CAPES
casam com o cadastro do observatório. As 22 restantes são entidades que não ofertam
graduação nos rótulos acompanhados — institutos de pesquisa, sobretudo —, e ficam
de fora por não terem onde aparecer, não por falha de casamento.

TRÊS CUIDADOS QUE ESTE ARQUIVO CARREGA:

1. O conceito CAPES vai de 1 a 7 e NÃO é comparável ao IGC nem ao CPC, que vão de
   1 a 5. São escalas diferentes sobre objetos diferentes: um avalia programa de
   pós, os outros avaliam graduação e instituição. Nunca somar, mediar ou ranquear
   os três juntos.

2. Isto descreve a face de PESQUISA da instituição, não os cursos de graduação que
   o observatório acompanha. Uma universidade pode ter doutorado nota 7 em Física
   e graduação medíocre em outra área — e vice-versa.

3. Ausência aqui significa "não tem programa stricto sensu", que é um FATO sobre a
   instituição, não dado faltante. É diferente da ausência de IGC, que significa
   "não foi avaliada". A distinção vai explícita para o site.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

CONCEITO_MIN, CONCEITO_MAX = 1, 7
# Situações que indicam programa em funcionamento. O arquivo traz também
# desativados e em desativação, que não descrevem a capacidade atual.
SITUACOES_ATIVAS = {"EM FUNCIONAMENTO"}


def limpar(valor):
    return (valor or "").strip()


def inteiro(valor):
    texto = limpar(valor)
    if not texto or not texto.isdigit():
        return None
    return int(texto)


def main():
    parser = argparse.ArgumentParser(description="Pós-graduação stricto sensu (CAPES)")
    parser.add_argument("--programas", required=True,
                        help="CSV br-capes-colsucup-prog-AAAA.csv")
    parser.add_argument("--saida", default=str(DATA / "capes.json"))
    args = parser.parse_args()

    print(f"[INFO] Lendo {args.programas} ...")
    linhas = []
    with open(args.programas, encoding="latin-1", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            linhas.append(linha)
    print(f"[INFO] {len(linhas)} programas no arquivo.")

    situacoes = Counter(limpar(l.get("DS_SITUACAO_PROGRAMA")).upper() for l in linhas)
    print("[INFO] situações encontradas: "
          + " · ".join(f"{s or '(vazio)'}={n}" for s, n in situacoes.most_common(6)))

    ano = Counter(limpar(l.get("AN_BASE")) for l in linhas).most_common(1)
    ano = ano[0][0] if ano and ano[0][0] else None

    por_ies, ignorados = {}, 0
    for l in linhas:
        situacao = limpar(l.get("DS_SITUACAO_PROGRAMA")).upper()
        if SITUACOES_ATIVAS and situacao not in SITUACOES_ATIVAS:
            ignorados += 1
            continue
        codigo = limpar(l.get("CD_ENTIDADE_EMEC"))
        if not codigo:
            ignorados += 1
            continue

        alvo = por_ies.setdefault(codigo, {
            "nome_capes": limpar(l.get("NM_ENTIDADE_ENSINO")),
            "programas": 0,
            "conceitos": [],
            "por_grau": Counter(),
            "areas": Counter(),
            "modalidades": Counter(),
        })
        alvo["programas"] += 1
        conceito = inteiro(l.get("CD_CONCEITO_PROGRAMA"))
        if conceito is not None and CONCEITO_MIN <= conceito <= CONCEITO_MAX:
            alvo["conceitos"].append(conceito)
        grau = limpar(l.get("NM_GRAU_PROGRAMA"))
        if grau:
            alvo["por_grau"][grau] += 1
        area = limpar(l.get("NM_AREA_AVALIACAO"))
        if area:
            alvo["areas"][area] += 1
        mod = limpar(l.get("NM_MODALIDADE_PROGRAMA"))
        if mod:
            alvo["modalidades"][mod] += 1

    saida = {}
    for codigo, d in por_ies.items():
        conceitos = d["conceitos"]
        saida[codigo] = {
            "nome_capes": d["nome_capes"],
            "programas": d["programas"],
            "programas_com_conceito": len(conceitos),
            # Média simples entre programas: cada programa é avaliado como uma
            # unidade, e não há peso público de matrículas por programa aqui.
            "conceito_medio": round(sum(conceitos) / len(conceitos), 2) if conceitos else None,
            "conceito_maximo": max(conceitos) if conceitos else None,
            "por_grau": dict(d["por_grau"].most_common()),
            "areas": dict(d["areas"].most_common(10)),
            "modalidades": dict(d["modalidades"].most_common()),
        }

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("Conceito CAPES vai de 1 a 7 e NÃO é comparável ao IGC nem ao "
                      "CPC (1 a 5) — escalas diferentes sobre objetos diferentes. "
                      "Descreve a pós-graduação stricto sensu, não os cursos de "
                      "graduação acompanhados. Ausência significa que a instituição "
                      "não tem programa stricto sensu, o que é um fato sobre ela e "
                      "não dado faltante."),
            "ano_base": ano,
            "instituicoes": saida,
        }, f, ensure_ascii=False, indent=1)

    caminho_ies = DATA / "instituicoes.json"
    print(f"\n[OK] {len(saida)} instituições com pós stricto sensu em {args.saida}")
    print(f"     {ignorados} programas ignorados (fora de funcionamento ou sem código)")
    if caminho_ies.exists():
        with open(caminho_ies, encoding="utf-8") as f:
            nossas = json.load(f)["instituicoes"]
        casadas = [c for c in saida if c in nossas]
        print(f"     {len(casadas)} casadas com o observatório · "
              f"{len(saida) - len(casadas)} fora dele (não ofertam graduação "
              f"nos rótulos acompanhados)")
        com_doutorado = sum(1 for c in casadas
                            if any("DOUTORADO" in g.upper() for g in saida[c]["por_grau"]))
        print(f"     {com_doutorado} das casadas oferecem doutorado")
    if ano:
        print(f"     ano-base: {ano}")


if __name__ == "__main__":
    main()
