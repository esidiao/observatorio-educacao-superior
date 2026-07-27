"""
Indicadores de fluxo: evasão, conclusão, retenção e permanência por coorte.

Uso:
    python etl/fluxo.py --fluxo caminho/indicadores_fluxo_UF_2010_2024.zip

Baixe em:
    https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/indicadores_fluxo_UF_2010_2024.zip

Estes são os indicadores que o Censo sozinho NÃO produz. O Censo é um retrato
anual de estoque: a diferença de matrículas entre dois anos mistura quem entrou,
saiu, trancou e concluiu, e por isso o observatório se recusava a falar em evasão.
O INEP acompanha a mesma turma ao longo do tempo — coorte de ingressantes — e daí
saem taxas que significam o que o nome diz.

Definições, resumidas da metodologia do INEP:
  · evasão      — ingressantes que deixaram o curso e não retornaram até o fim
                  do acompanhamento;
  · conclusão   — ingressantes que concluíram;
  · retenção    — ainda matriculados além do prazo previsto de integralização;
  · permanência — ainda vinculados ao curso.

LIMITE DE AGREGAÇÃO, e é o que decide onde isso pode aparecer no site. A planilha
é por UNIDADE FEDERATIVA e coorte, não por curso nem por instituição. Logo estes
indicadores entram nos painéis estaduais e no panorama nacional, e NÃO nas páginas
de curso ou de IES. Ratear a evasão de um estado entre os cursos dele seria
exatamente a estimativa que este projeto recusa — cursos têm perfis de evasão
radicalmente diferentes, e a média estadual não descreve nenhum.
"""
import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependências: pip install -r requirements.txt")

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

sys.path.insert(0, str(Path(__file__).parent))
from referencias import NOME_UF  # noqa: E402

ABAS = {
    "TX_EVASAO": "evasao",
    "TX_CONCLUSAO": "conclusao",
    "TX_RETENCAO": "retencao",
    "TX_PERMANENCIA": "permanencia",
}
# Linha do cabeçalho de dados e primeira linha de dado, conferidas na planilha.
LINHA_DADOS = 8
COL_ANO, COL_UF, COL_TOTAL = 0, 1, 2
# Recortes na ordem em que a planilha os dispõe após a coluna Total.
RECORTES = ["feminino", "masculino", "ppi", "nao_ppi",
            "ate_19", "20_22", "23_24", "25_29", "30_39", "40_49", "50_mais"]


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


SIGLA_POR_NOME = {norm(nome): sigla for sigla, nome in NOME_UF.items()}


def numero(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip().replace(",", ".")
    if not texto or texto.lower() in {"nan", "-", "--", "x"}:
        return None
    try:
        return round(float(texto), 1)
    except ValueError:
        return None


def ler_aba(caminho, aba):
    """Uma aba → {sigla_uf: {coorte: {total, recortes...}}}."""
    df = pd.read_excel(caminho, sheet_name=aba, header=None, skiprows=LINHA_DADOS)
    saida, orfas = {}, set()
    coorte_atual = None

    for _, linha in df.iterrows():
        valores = linha.tolist()
        # "Ano Fluxo" vem em célula mesclada: só a primeira UF do bloco o traz.
        bruto_ano = valores[COL_ANO]
        if bruto_ano is not None and str(bruto_ano).strip().lower() != "nan":
            coorte_atual = str(bruto_ano).strip()
        nome_uf = valores[COL_UF]
        if not coorte_atual or nome_uf is None or str(nome_uf).strip().lower() == "nan":
            continue

        sigla = SIGLA_POR_NOME.get(norm(nome_uf))
        if not sigla:
            orfas.add(str(nome_uf).strip())
            continue

        registro = {"total": numero(valores[COL_TOTAL])}
        for i, chave in enumerate(RECORTES, start=COL_TOTAL + 1):
            registro[chave] = numero(valores[i]) if i < len(valores) else None
        saida.setdefault(sigla, {})[coorte_atual] = registro

    return saida, orfas


def main():
    parser = argparse.ArgumentParser(description="Ingestão dos indicadores de fluxo")
    parser.add_argument("--fluxo", required=True,
                        help="ZIP ou XLSX dos indicadores de fluxo por UF")
    parser.add_argument("--saida", default=str(DATA / "fluxo.json"))
    args = parser.parse_args()

    caminho = Path(args.fluxo)
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nome = next((n for n in z.namelist() if n.lower().endswith(".xlsx")), None)
            if not nome:
                raise SystemExit("[ERRO] nenhum .xlsx dentro do zip.")
            destino = caminho.parent / Path(nome).name
            with z.open(nome) as origem, open(destino, "wb") as saida_arq:
                saida_arq.write(origem.read())
            caminho = destino
            print(f"[INFO] extraído {caminho.name}")

    disponiveis = pd.ExcelFile(caminho).sheet_names
    print(f"[INFO] abas na planilha: {', '.join(disponiveis)}")

    indicadores, coortes, orfas = {}, set(), set()
    for aba, chave in ABAS.items():
        if aba not in disponiveis:
            print(f"[AVISO] aba {aba} ausente — {chave} ficará sem dados.")
            continue
        dados, sem_uf = ler_aba(caminho, aba)
        orfas |= sem_uf
        for sigla, por_coorte in dados.items():
            coortes.update(por_coorte)
            for coorte, registro in por_coorte.items():
                indicadores.setdefault(sigla, {}).setdefault(coorte, {})[chave] = registro
        print(f"[OK] {aba}: {len(dados)} UFs · {len(next(iter(dados.values()), {}))} coortes")

    if orfas:
        # Linhas de Brasil/região no arquivo de UF, ou nome fora da malha.
        print(f"[INFO] {len(orfas)} rótulo(s) fora das 27 UFs, ignorados: "
              f"{', '.join(sorted(orfas)[:6])}")

    faltando = sorted(set(NOME_UF) - set(indicadores))
    if faltando:
        print(f"[AVISO] sem dados de fluxo: {', '.join(faltando)}")

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("Taxas de coorte do INEP, por UNIDADE FEDERATIVA. Não existem "
                      "por curso nem por instituição nesta fonte, e ratear a taxa "
                      "estadual entre cursos seria estimativa — cursos têm perfis de "
                      "evasão radicalmente diferentes."),
            "_definicoes": {
                "evasao": "ingressantes que deixaram o curso e não retornaram",
                "conclusao": "ingressantes que concluíram o curso",
                "retencao": "ainda matriculados além do prazo de integralização",
                "permanencia": "ainda vinculados ao curso",
            },
            "coortes": sorted(coortes),
            "ufs": indicadores,
        }, f, ensure_ascii=False, indent=1)

    print(f"\n[OK] {len(indicadores)} UFs × {len(coortes)} coortes em {args.saida}")
    print(f"     coortes: {', '.join(sorted(coortes)[:4])} … {sorted(coortes)[-1]}")


if __name__ == "__main__":
    main()
