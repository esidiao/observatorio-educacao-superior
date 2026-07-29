"""
A marca do observatório, gerada em SVG a partir da malha real do IBGE.

    from marca import simbolo, marca_completa

Por que gerada, e não uma imagem. Um PNG de logotipo precisa de três ou quatro
tamanhos para não borrar, pesa mais que o resto do cabeçalho somado e não
acompanha o tema escuro. O SVG é nítido em qualquer escala, cabe em poucos
kilobytes e é texto — versionável, diffável, sem binário opaco no repositório.

E o mapa do símbolo não é um desenho de mapa: são os contornos das 27 unidades
federativas, os mesmos de `data/geo/ufs.json` que alimentam os coropléticos do
site, amostrados numa grade e reduzidos a pontos. A silhueta da marca e a
silhueta dos mapas das páginas vêm da mesma fonte — se o IBGE revisar a malha,
as duas mudam juntas.

Sobre a arte de referência. O logotipo enviado traz três erros de texto:
"FUTUPO" no lugar de "FUTURO", e "ANALISES" e "EDUCACAO" sem acento. Foram
corrigidos aqui. Reproduzir um erro tipográfico porque ele veio no arquivo
original seria publicá-lo em dez mil páginas.
"""
import json
import math
from pathlib import Path

REPO = Path(__file__).parent.parent

# Paleta da arte de referência. O mapa vai do azul-marinho no Norte ao amarelo
# no Sul, passando pelo verde — a mesma progressão do arquivo enviado. Não usa
# os tokens de tema: logotipo que muda de cor com o tema deixa de ser
# reconhecível, e reconhecimento é a única coisa que um logotipo faz.
GRADIENTE = ["#1E3A72", "#1B5FA8", "#1F8A3C", "#6FA82A", "#E9B824"]
NAVY = "#16305C"
VERDE = "#1F8A3C"
AZUL = "#1B6FC4"
OURO = "#E9B824"


def _aneis(geometria):
    if geometria["tipo"] == "Polygon":
        return geometria["coords"]
    return [anel for poligono in geometria["coords"] for anel in poligono]


def _dentro(x, y, anel):
    """Ponto em polígono por cruzamentos (ray casting)."""
    dentro = False
    n = len(anel)
    j = n - 1
    for i in range(n):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > y) != (yj > y):
            corte = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < corte:
                dentro = not dentro
        j = i
    return dentro


def _pontos_do_brasil(passo=1.3):
    """Grade sobre o país; sobra o que cai dentro de alguma UF.

    O passo é o compromisso entre reconhecer o contorno e não virar mancha:
    mais fino apaga o padrão de pontos que dá caráter à marca, mais grosso
    dissolve o Nordeste. Em 1,3 grau saem ~420 pontos — perto da densidade da
    arte de referência, e num arquivo de poucos kilobytes.
    """
    caminho = REPO / "data" / "geo" / "ufs.json"
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8") as f:
        ufs = json.load(f)["ufs"]

    aneis = []
    for geo in ufs.values():
        aneis.extend(_aneis(geo))

    lons = [p[0] for a in aneis for p in a]
    lats = [p[1] for a in aneis for p in a]
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)

    # Caixa de cada anel, para não testar o país inteiro a cada ponto.
    caixas = [(min(p[0] for p in a), min(p[1] for p in a),
               max(p[0] for p in a), max(p[1] for p in a), a) for a in aneis]

    pontos = []
    lat = lat_max
    while lat >= lat_min:
        lon = lon_min
        while lon <= lon_max:
            for x0, y0, x1, y1, anel in caixas:
                if x0 <= lon <= x1 and y0 <= lat <= y1 and _dentro(lon, lat, anel):
                    pontos.append((lon, lat))
                    break
            lon += passo
        lat -= passo
    return pontos, (lon_min, lat_min, lon_max, lat_max)


def _mapa_pontilhado(cx, cy, raio, passo=1.3, ponto=1.5):
    """Brasil em pontos, centrado em (cx, cy) e cabendo num círculo de `raio`."""
    resultado = _pontos_do_brasil(passo)
    if not resultado:
        return ""
    pontos, (lon_min, lat_min, lon_max, lat_max) = resultado

    cos_lat = math.cos(math.radians((lat_min + lat_max) / 2))
    span_x = (lon_max - lon_min) * cos_lat
    span_y = lat_max - lat_min
    # 1,62 deixa o mapa ocupando ~85% do diametro da lente: cheio o bastante
    # para a silhueta se reconhecer num favicon de 16px, com folga para as
    # barras no canto inferior esquerdo.
    escala = (raio * 1.62) / max(span_x, span_y)
    dx = cx - span_x * escala / 2
    dy = cy - span_y * escala / 2

    # Agrupados por cor: repetir fill="#3F9C5A" em quatrocentos círculos
    # custa mais bytes que os próprios círculos.
    por_cor = {}
    for lon, lat in pontos:
        x = dx + (lon - lon_min) * cos_lat * escala
        y = dy + (lat_max - lat) * escala
        # A cor varia com a latitude, como na arte de referência.
        faixa = (lat_max - lat) / span_y
        cor = GRADIENTE[min(int(faixa * len(GRADIENTE)), len(GRADIENTE) - 1)]
        por_cor.setdefault(cor, []).append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{ponto}"/>')
    return "".join(f'<g fill="{cor}">{"".join(cs)}</g>'
                   for cor, cs in por_cor.items())


def simbolo(tamanho=64, id_prefixo="marca", passo=1.3, ponto=1.5):
    """Só o símbolo: capelo, lupa, Brasil pontilhado e as barras.

    `passo` mais grosso serve ao ícone de aba: a 16 pixels, quatrocentos pontos
    viram uma mancha cinza e ainda custam 16 KB. Com uns setenta, a silhueta
    do país continua reconhecível e o arquivo cabe em 3 KB.
    """
    mapa = _mapa_pontilhado(cx=52, cy=52, raio=30, passo=passo, ponto=ponto)
    return (
        f'<svg class="brand-mark" width="{tamanho}" height="{tamanho}" '
        f'viewBox="0 0 100 100" role="img" '
        f'aria-label="Observatório Nacional da Educação Superior" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<title>Observatório Nacional da Educação Superior</title>'
        # Anel da lupa, bicolor como no original: navy no arco inferior
        # esquerdo, verde no superior direito. Dois semicírculos desenhados
        # como arcos, para a emenda cair onde o cabo entra.
        f'<path d="M52 21 A31 31 0 0 1 74 74" fill="none" stroke="{VERDE}" '
        f'stroke-width="5" stroke-linecap="round"/>'
        f'<path d="M52 21 A31 31 0 0 0 74 74" fill="none" stroke="{NAVY}" '
        f'stroke-width="5" stroke-linecap="round"/>'
        # Brasil pontilhado, recortado pelo anel
        f'<clipPath id="{id_prefixo}-lente">'
        f'<circle cx="52" cy="52" r="28.5"/></clipPath>'
        f'<g clip-path="url(#{id_prefixo}-lente)">{mapa}'
        # Barras: a leitura dos dados, dentro da lente
        # Barras em amarelo, verde e azul, na ordem do original.
        f'<rect x="28" y="66" width="6" height="12" fill="{OURO}"/>'
        f'<rect x="36" y="58" width="6" height="20" fill="{VERDE}"/>'
        f'<rect x="44" y="50" width="6" height="28" fill="{AZUL}"/>'
        f'</g>'
        # Cabo
        f'<line x1="74" y1="74" x2="90" y2="90" stroke="{NAVY}" '
        f'stroke-width="7" stroke-linecap="round"/>'
        # Capelo
        f'<path d="M8 22 L44 8 L80 22 L44 36 Z" fill="{NAVY}"/>'
        f'<path d="M16 26 L16 38" stroke="{OURO}" stroke-width="2.5" '
        f'stroke-linecap="round"/>'
        f'<circle cx="16" cy="41" r="3.4" fill="{OURO}"/>'
        f'</svg>'
    )


def marca_completa(largura=420):
    """Símbolo mais assinatura, para a capa e para o compartilhamento.

    A assinatura vai como texto de verdade, não como caminho: continua
    selecionável, encontrável por busca e legível por leitor de tela — e o
    arquivo fica em poucos kilobytes.
    """
    altura = round(largura * 0.30)
    return (
        f'<svg width="{largura}" height="{altura}" viewBox="0 0 420 126" '
        f'role="img" xmlns="http://www.w3.org/2000/svg" '
        f'aria-label="Observatório Nacional da Educação Superior — '
        f'dados, análises, conhecimento, futuro">'
        f'<title>Observatório Nacional da Educação Superior</title>'
        f'<g transform="translate(4,10) scale(1.06)">'
        + simbolo(tamanho=100, id_prefixo="assinatura").split(">", 1)[1].rsplit("</svg>", 1)[0]
        + f'</g>'
        f'<g font-family="Inter, Segoe UI, system-ui, Arial, sans-serif">'
        f'<text x="126" y="42" font-size="30" font-weight="800" fill="{NAVY}" '
        f'letter-spacing="0.5">OBSERVATÓRIO</text>'
        f'<text x="126" y="70" font-size="21" font-weight="700" fill="{VERDE}" '
        f'letter-spacing="4.5">NACIONAL</text>'
        f'<text x="126" y="93" font-size="15" font-weight="600" fill="#1B2530" '
        f'letter-spacing="1.6">DA EDUCAÇÃO SUPERIOR</text>'
        f'<line x1="126" y1="101" x2="414" y2="101" stroke="{NAVY}" '
        f'stroke-width="1"/>'
        f'<text x="126" y="117" font-size="11" font-weight="500" fill="#4A5568" '
        f'letter-spacing="1.1">DADOS · ANÁLISES · CONHECIMENTO · FUTURO</text>'
        f'</g></svg>'
    )
