"""
Ícones do aplicativo instalável, rasterizados a partir da marca.

    python site/icones_pwa.py

Gera em site/static/img/:
    app-192.png            ícone da tela inicial
    app-512.png            ícone grande (splash, lojas, atalhos)
    app-512-maskable.png   idem, com margem para recorte circular

Por que PNG, se todo o resto do site é SVG. O manifesto de aplicativo aceita
SVG na especificação, mas o Android — que é onde este site será instalado —
ainda trata PNG como o formato confiável. Um ícone que não aparece na tela
inicial derrota o propósito de instalar.

Por que rasterizado por navegador. Não há biblioteca de SVG para raster neste
projeto, e acrescentar uma só para isto seria peso permanente por um arquivo
que muda uma vez por década. O Playwright já é dependência de teste; aqui ele
abre a marca e fotografa. Os PNGs entram versionados, então nem o build nem o
CI precisam dele.

Por que a variante `maskable`. O Android recorta o ícone em círculo, quadrado
arredondado ou gota, conforme o aparelho. Sem margem, a lupa e o capelo perdem
as bordas no recorte; com 20% de folga em volta, o desenho sobrevive a
qualquer máscara.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
IMG = RAIZ / "site" / "static" / "img"

# (arquivo, lado em pixels, margem em % do lado)
SAIDAS = [
    ("app-192.png", 192, 0.0),
    ("app-512.png", 512, 0.0),
    ("app-512-maskable.png", 512, 0.20),
]


def pagina_com_marca(svg, margem):
    """Uma página só com a marca, sobre fundo opaco.

    Fundo opaco de propósito: ícone com transparência vira um borrão sobre
    papel de parede claro em vários lançadores do Android.
    """
    folga = f"{margem * 100:.0f}%"
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#FFFFFF}"
        f"body{{display:flex;align-items:center;justify-content:center;"
        f"box-sizing:border-box;padding:{folga}}}"
        "svg{width:100%;height:100%;display:block}</style>"
        f"<body>{svg}</body>"
    )


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("[ERRO] playwright ausente: pip install -r requirements-dev.txt "
                 "&& python -m playwright install chromium")

    origem = IMG / "icone.svg"
    if not origem.exists():
        sys.exit(f"[ERRO] {origem} não existe. Rode python site/build.py antes — "
                 f"a marca é gerada lá, a partir da malha do IBGE.")
    svg = origem.read_text(encoding="utf-8")

    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        for nome, lado, margem in SAIDAS:
            pagina = navegador.new_page(viewport={"width": lado, "height": lado})
            pagina.set_content(pagina_com_marca(svg, margem))
            pagina.wait_for_timeout(150)
            destino = IMG / nome
            pagina.screenshot(path=str(destino), omit_background=False)
            pagina.close()
            print(f"[OK] {destino.relative_to(RAIZ)} — {lado}x{lado}, "
                  f"{destino.stat().st_size / 1024:.0f} KB")
        navegador.close()


if __name__ == "__main__":
    main()
