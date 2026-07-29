"""
População residente por município, do IBGE.

    python etl/populacao_municipal.py

Produz data/populacao_municipios.json: código IBGE → habitantes, mais o ano da
estimativa e a fonte.

Por que uma fonte separada. O Censo da Educação Superior não informa população:
ele conta vagas, matrículas e cursos. Sem o denominador populacional não dá para
dizer se um município com dez mil matrículas é bem servido ou mal servido — e é
essa comparação que o mapa municipal precisa sustentar.

Uma advertência que precisa acompanhar o número em toda leitura: **a população é
de um ano e o Censo é de outro**. A estimativa do IBGE é anual e sai antes do
Censo do INEP ser consolidado; qualquer razão entre os dois mistura dois
momentos. A diferença é pequena para o uso pretendido — ordem de grandeza,
comparação entre municípios —, mas não é zero, e por isso o ano de cada fonte
viaja junto com o dado até a página.

O casamento é por código IBGE de sete dígitos, nunca por nome: existem 39
municípios brasileiros chamados Bom Jesus e variações, e nome é a forma mais
confiável de errar de cidade.
"""
import gzip
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Agregado 6579 = Estimativas de População; variável 9324 = população residente
# estimada; N6[all] = todos os municípios; periodos/-1 = a mais recente.
URL = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/"
       "variaveis/9324?localidades=N6[all]")


def baixar():
    req = urllib.request.Request(URL, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=300) as r:
        bruto = r.read()
    # O IBGE responde comprimido mesmo sem Accept-Encoding, e o urllib não
    # descomprime sozinho — mesmo tropeço já tratado em etl/malha.py.
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    return json.loads(bruto.decode("utf-8"))


def main():
    print(f"[GET] {URL}")
    try:
        dados = baixar()
    except Exception as e:                          # noqa: BLE001
        sys.exit(f"[ERRO] IBGE não respondeu: {type(e).__name__}: {e}")

    resultado = dados[0]["resultados"][0]["series"]
    ano = list(resultado[0]["serie"])[0]

    populacao, ignorados = {}, 0
    for item in resultado:
        codigo = item["localidade"]["id"]
        valor = item["serie"][ano]
        # O IBGE usa "-" e "..." para valor ausente. Guardar isso como zero
        # criaria um município despovoado; ausente tem de continuar ausente.
        try:
            populacao[codigo] = int(valor)
        except (TypeError, ValueError):
            ignorados += 1

    if len(populacao) < 5000:
        sys.exit(f"[ERRO] só {len(populacao)} municípios com população — "
                 f"esperados ~5.570. Resposta incompleta, não gravando.")

    saida = {
        "_fonte": "IBGE — Estimativas de População (agregado 6579, variável 9324)",
        "_nota": ("A população é de {ano} e o Censo da Educação Superior é de "
                  "outro ano. Toda razão entre os dois mistura dois momentos; a "
                  "diferença é pequena para comparação entre municípios, mas não "
                  "é zero.").format(ano=ano),
        "ano": ano,
        "municipios": populacao,
    }
    destino = DATA / "populacao_municipios.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
    print(f"[OK] {destino.relative_to(REPO)} — {len(populacao)} municípios, "
          f"estimativa {ano}"
          + (f" · {ignorados} sem valor" if ignorados else ""))


if __name__ == "__main__":
    main()
