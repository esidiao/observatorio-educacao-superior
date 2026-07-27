"""
Índice Geral de Cursos (IGC) e conceitos médios por instituição.

Uso:
    python etl/igc.py --igc caminho/IGC_2023.xlsx

Baixe em:
    https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/IGC_2023.xlsx

Produz data/igc.json, indexado pelo código da IES — a mesma chave do Censo, então
o casamento com data/instituicoes.json é exato, sem heurística sobre nome.

Arquivo separado de propósito. O IGC vem de outra fonte, com outro calendário e
outro ciclo (é trienal, calculado sobre os CPC dos três últimos anos). Misturá-lo
ao instituicoes.json faria uma reingestão do Censo apagar dado de avaliação, e
obrigaria a rodar os dois na ordem certa. Assim cada etapa é independente e
idempotente, e o build junta na hora de renderizar.

O QUE ESTE ARQUIVO NÃO RESOLVE. O IGC é um índice calculado a partir dos CPC e da
pós-graduação; ele NÃO é o Conceito Institucional (CI), que vem de avaliação in
loco por comissão, nem informa situação de credenciamento ou data da última
visita. Esses três continuam ausentes do observatório, porque estão no e-MEC e
não em base aberta com download estável. Continuam declarados como ausentes nas
páginas, e não preenchidos por aproximação: IGC alto não implica CI alto.

Cuidado de leitura embutido nos dados: o IGC cobre só instituições com cursos
avaliados no triênio. Instituição nova, ou cuja área não entrou no rodízio do
ENADE, fica sem IGC — o que é ausência de avaliação, não avaliação ruim.
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

# Campo interno → trechos que identificam a coluna na planilha do INEP.
# Casar por trecho, e não por nome exato, porque o INEP muda pontuação, acento e
# espaçamento dos cabeçalhos entre edições.
CAMPOS = {
    "igc_continuo":        ("IGC", "CONTINUO"),
    "igc_faixa":           ("IGC", "FAIXA"),
    "cursos_com_cpc":      ("CURSOS", "CPC"),
    "conceito_graduacao":  ("CONCEITO", "GRADUACAO"),
    "conceito_mestrado":   ("CONCEITO", "MESTRADO"),
    "conceito_doutorado":  ("CONCEITO", "DOUTORADO"),
}
FAIXA_MAXIMA = 5


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def achar(colunas, *trechos):
    for c in colunas:
        n = norm(c)
        if all(t in n for t in trechos):
            return c
    return None


def numero(valor):
    """Converte para float aceitando vírgula decimal; None quando não é número."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip().replace(",", ".")
    if not texto or texto.upper() in {"NA", "N/A", "-", "SC", "SEM CONCEITO"}:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Ingestão do IGC por instituição")
    parser.add_argument("--igc", required=True, help="Planilha IGC_AAAA.xlsx do INEP")
    parser.add_argument("--aba", default="IGC")
    parser.add_argument("--saida", default=str(DATA / "igc.json"))
    args = parser.parse_args()

    print(f"[INFO] Lendo {args.igc} (aba {args.aba}) ...")
    df = pd.read_excel(args.igc, sheet_name=args.aba, dtype=str)
    cols = list(df.columns)

    c_ies = achar(cols, "CODIGO", "IES")
    c_ano = achar(cols, "ANO")
    if not c_ies:
        raise SystemExit("[ERRO] coluna de código da IES não localizada na planilha.")

    mapa = {campo: achar(cols, *trechos) for campo, trechos in CAMPOS.items()}
    faltando = [k for k, v in mapa.items() if v is None]
    if faltando:
        print(f"[AVISO] colunas não encontradas (ficarão nulas): {', '.join(faltando)}")

    saida = {}
    anos = set()
    for _, linha in df.iterrows():
        codigo = str(linha[c_ies]).strip()
        if not codigo or codigo.lower() == "nan":
            continue
        codigo = codigo.split(".")[0]           # o Excel entrega "123.0"

        registro = {}
        for campo, coluna in mapa.items():
            registro[campo] = numero(linha[coluna]) if coluna else None

        # Faixa é nota inteira de 1 a 5; contínuo é decimal de 0 a 5.
        if registro.get("igc_faixa") is not None:
            faixa = int(registro["igc_faixa"])
            registro["igc_faixa"] = faixa if 1 <= faixa <= FAIXA_MAXIMA else None
        if registro.get("cursos_com_cpc") is not None:
            registro["cursos_com_cpc"] = int(registro["cursos_com_cpc"])

        # Sem IGC não há registro: linha vazia aqui viraria "avaliada com nada",
        # quando o caso é "não avaliada".
        if registro.get("igc_continuo") is None and registro.get("igc_faixa") is None:
            continue

        if c_ano:
            ano = numero(linha[c_ano])
            if ano:
                registro["ano"] = int(ano)
                anos.add(int(ano))
        saida[codigo] = registro

    caminho = Path(args.saida)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("IGC é índice calculado a partir dos CPC e da pós-graduação. "
                      "NÃO é o Conceito Institucional (CI), que vem de avaliação in "
                      "loco, nem informa credenciamento. Ausência de IGC significa "
                      "instituição sem cursos avaliados no triênio — ausência de "
                      "avaliação, não avaliação ruim."),
            "anos": sorted(anos),
            "instituicoes": saida,
        }, f, ensure_ascii=False, indent=1)

    # Quanto do observatório fica coberto — informação necessária para decidir se
    # vale exibir o indicador ou se ele seria uma exceção disfarçada de regra.
    caminho_ies = DATA / "instituicoes.json"
    if caminho_ies.exists():
        with open(caminho_ies, encoding="utf-8") as f:
            nossas = json.load(f)["instituicoes"]
        casadas = sum(1 for co in nossas if co in saida)
        print(f"\n[OK] {len(saida)} instituições com IGC em {caminho.name}")
        print(f"     {casadas} de {len(nossas)} do observatório têm IGC "
              f"({100 * casadas / len(nossas):.0f}%) · "
              f"{len(nossas) - casadas} sem cursos avaliados no triênio")
    else:
        print(f"\n[OK] {len(saida)} instituições com IGC em {caminho.name}")
    print(f"     anos na planilha: {', '.join(str(a) for a in sorted(anos)) or 'não declarado'}")


if __name__ == "__main__":
    main()
