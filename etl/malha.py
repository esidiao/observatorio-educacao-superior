"""
Malha geográfica oficial: fronteiras das UFs e centroides municipais.

Uso (raro — só quando a malha do IBGE mudar):
    python etl/malha.py

Baixa da API de malhas do IBGE e grava dois arquivos versionados:

    data/geo/ufs.json         polígonos das 27 UFs, já simplificados
    data/geo/municipios.json  um ponto (centroide) por município

Por que centroide e não polígono para município: a malha municipal completa passa
de vários MB e o mapa municipal deste observatório responde "onde existe oferta",
não "qual a área do município". Ponto responde isso com uma fração do peso.

O download acontece AQUI, no ETL, e o resultado é versionado. Em tempo de execução
o site não busca nada de fora — a Content-Security-Policy proíbe, e a página de
privacidade promete. Malha é dado de origem, como o Censo: entra pelo pipeline.

Fonte: IBGE, API de malhas territoriais (mesma malha das divulgações oficiais).
"""
import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
GEO = REPO / "data" / "geo"

API = "https://servicodados.ibge.gov.br/api/v3/malhas"
FORMATO = "formato=application/vnd.geo+json&qualidade=minima"

UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

# Casas decimais das coordenadas. 3 casas ≈ 100 m no equador: mais que suficiente
# para um mapa de 900 px de largura, e corta o arquivo pela metade.
PRECISAO = 3


def baixar(url):
    print(f"[GET] {url}")
    # A API responde gzip mesmo sem ser pedido, e urllib não descomprime sozinha.
    req = urllib.request.Request(url, headers={
        "User-Agent": "observatorio-educacao",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        bruto = resp.read()
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    return json.loads(bruto.decode("utf-8"))


def arredondar(coords):
    """Reduz a precisão recursivamente, preservando a estrutura aninhada."""
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], PRECISAO), round(coords[1], PRECISAO)]
    return [arredondar(c) for c in coords]


def anexar_pontos(geometria, pontos):
    tipo = geometria["type"]
    coords = geometria["coordinates"]
    if tipo == "Polygon":
        for anel in coords:
            pontos.extend(anel)
    elif tipo == "MultiPolygon":
        for poligono in coords:
            for anel in poligono:
                pontos.extend(anel)


def centroide(geometria):
    """Média dos vértices. Não é o centro de massa exato, e não precisa ser:
    serve para pousar um ponto dentro do município num mapa nacional."""
    pontos = []
    anexar_pontos(geometria, pontos)
    if not pontos:
        return None
    return [round(sum(p[0] for p in pontos) / len(pontos), PRECISAO),
            round(sum(p[1] for p in pontos) / len(pontos), PRECISAO)]


def malha_ufs():
    dados = baixar(f"{API}/paises/BR?{FORMATO}&intrarregiao=UF")
    ufs = {}
    for feicao in dados["features"]:
        codigo = str(feicao.get("properties", {}).get("codarea", "")).strip()
        sigla = UF_POR_CODIGO.get(codigo)
        if not sigla:
            print(f"  [AVISO] código de UF desconhecido: {codigo!r} — ignorado")
            continue
        ufs[sigla] = {
            "tipo": feicao["geometry"]["type"],
            "coords": arredondar(feicao["geometry"]["coordinates"]),
        }
    faltando = sorted(set(UF_POR_CODIGO.values()) - set(ufs))
    if faltando:
        raise SystemExit(f"[ERRO] malha sem as UFs {faltando} — não publicar mapa "
                         f"incompleto, que se lê como ausência de dado")
    return ufs


def centroides_municipais():
    """Percorre UF a UF: a malha municipal do país inteiro numa tacada estoura
    o tempo limite da API."""
    pontos = {}
    for codigo, sigla in sorted(UF_POR_CODIGO.items()):
        dados = baixar(f"{API}/estados/{codigo}?{FORMATO}&intrarregiao=municipio")
        n = 0
        for feicao in dados["features"]:
            cod_mun = str(feicao.get("properties", {}).get("codarea", "")).strip()
            ponto = centroide(feicao["geometry"])
            if cod_mun and ponto:
                pontos[cod_mun] = ponto
                n += 1
        print(f"  {sigla}: {n} municípios")
    return pontos


def main():
    parser = argparse.ArgumentParser(description="Baixa a malha do IBGE (raro)")
    parser.add_argument("--so-ufs", action="store_true",
                        help="Pula os centroides municipais (27 requisições)")
    args = parser.parse_args()

    GEO.mkdir(parents=True, exist_ok=True)

    print("== Fronteiras das UFs ==")
    ufs = malha_ufs()
    destino = GEO / "ufs.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"_fonte": "IBGE — API de malhas territoriais, qualidade mínima",
                   "_precisao_graus": 10 ** -PRECISAO,
                   "ufs": ufs}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {destino.name}: {len(ufs)} UFs · "
          f"{destino.stat().st_size / 1024:.0f} KB")

    if args.so_ufs:
        return

    print("\n== Centroides municipais ==")
    pontos = centroides_municipais()
    destino = GEO / "municipios.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"_fonte": "IBGE — centroides derivados da malha municipal",
                   "_nota": "média dos vértices, para posicionar o ponto no mapa",
                   "pontos": pontos}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {destino.name}: {len(pontos)} municípios · "
          f"{destino.stat().st_size / 1024:.0f} KB")
    if len(pontos) != 5570:
        print(f"[AVISO] esperados 5.570 municípios, obtidos {len(pontos)}")


if __name__ == "__main__":
    main()
