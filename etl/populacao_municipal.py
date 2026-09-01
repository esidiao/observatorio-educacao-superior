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
import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# Agregado 6579 = Estimativas de População; variável 9324 = população residente
# estimada; N6[all] = todos os municípios.
URL = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/{periodos}/"
       "variaveis/9324?localidades=N6[all]")


def edicao_do_censo():
    """Ano do Censo que alimenta o site, lido do próprio dado."""
    for caminho in sorted((DATA / "cursos").glob("*/nacional.json")):
        with open(caminho, encoding="utf-8") as f:
            versao = json.load(f).get("metadados", {}).get("versao_censo")
        if versao:
            return int(versao)
    return None


def anos_disponiveis():
    """Quais anos a série do IBGE oferece.

    A série tem buracos — não há estimativa para 2022, o ano do Censo
    Demográfico, nem para alguns anos anteriores. Pedir um ano inexistente
    devolve resposta vazia, e uma resposta vazia viraria um site sem população
    nenhuma. Melhor perguntar antes.
    """
    dados = baixar("all", "N3[52]")     # uma UF basta para listar os períodos
    serie = dados[0]["resultados"][0]["series"][0]["serie"]
    return sorted(serie)


def baixar(periodos="-1", localidades="N6[all]"):
    url = URL.format(periodos=periodos).replace("N6[all]", localidades)
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=300) as r:
        bruto = r.read()
    # O IBGE responde comprimido mesmo sem Accept-Encoding, e o urllib não
    # descomprime sozinho — mesmo tropeço já tratado em etl/malha.py.
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    return json.loads(bruto.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Baixa a população municipal do IBGE")
    parser.add_argument("--ano", type=int, default=None,
                        help="Ano da estimativa (padrão: o do Censo em uso)")
    args = parser.parse_args()

    censo = edicao_do_censo()
    alvo = args.ano or censo
    try:
        anos = anos_disponiveis()
    except Exception as e:                          # noqa: BLE001
        sys.exit(f"[ERRO] IBGE não respondeu: {type(e).__name__}: {e}")

    # Casar o ano da população com o do Censo é o que torna a razão legível:
    # matrículas de 2024 por habitante de 2024. A série tem buracos — não há
    # estimativa para 2022, por exemplo — e nesse caso usa-se o ano mais
    # próximo, com a distância registrada no arquivo para a página poder dizer.
    if alvo and str(alvo) in anos:
        periodo = str(alvo)
    else:
        periodo = min(anos, key=lambda a: abs(int(a) - alvo)) if alvo else anos[-1]
        if alvo:
            print(f"[INFO] Sem estimativa para {alvo}; usando {periodo}, "
                  f"a mais próxima disponível.")

    print(f"[GET] população municipal de {periodo}")
    try:
        dados = baixar(periodo)
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

    defasagem = abs(int(ano) - censo) if censo else None
    if defasagem == 0:
        nota = (f"População e Censo são do mesmo ano ({ano}): a razão entre "
                f"matrículas e habitantes compara dois retratos do mesmo "
                f"momento.")
    else:
        nota = (f"A população é de {ano} e o Censo da Educação Superior é de "
                f"{censo}. Toda razão entre os dois mistura dois momentos; a "
                f"diferença é pequena para comparação entre municípios, mas "
                f"não é zero.")

    saida = {
        "_fonte": "IBGE — Estimativas de População (agregado 6579, variável 9324)",
        "_nota": nota,
        "ano": ano,
        "ano_censo_alvo": censo,
        "defasagem_anos": defasagem,
        "municipios": populacao,
    }
    destino = DATA / "populacao_municipios.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
    print(f"[OK] {destino.relative_to(REPO)} — {len(populacao)} municípios, "
          f"estimativa {ano}"
          + (f" (mesmo ano do Censo)" if defasagem == 0
             else f" · {defasagem} ano(s) do Censo {censo}")
          + (f" · {ignorados} sem valor" if ignorados else ""))


if __name__ == "__main__":
    main()
