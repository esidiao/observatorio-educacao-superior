"""
Portão de segurança, acessibilidade e privacidade dos templates.

    python tests/test_seguranca.py

Cada checagem aqui nasceu de um problema real encontrado em auditoria. São
invariantes fáceis de quebrar sem perceber — um `onclick=` conveniente, um
recurso externo "só para testar", um `select_autoescape` que parece proteger e
não protege. O teste existe para que a regressão apareça no build, não em
produção.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
TEMPLATES = REPO / "site" / "templates"
STATIC = REPO / "site" / "static"
BUILD = REPO / "site" / "build.py"

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def test_autoescape():
    """select_autoescape casa pelo SUFIXO do arquivo.

    Todo template aqui termina em ".j2". Uma lista como ("html", "xml") deixa o
    escape DESLIGADO em 100% das páginas, e o build parece protegido sem estar.
    """
    codigo = BUILD.read_text(encoding="utf-8")
    bloco = re.search(r"select_autoescape\((.*?)\)\)", codigo, re.S)
    checar(bloco is not None, "select_autoescape não localizado em site/build.py")
    if bloco:
        checar('"j2"' in bloco.group(1) or "'j2'" in bloco.group(1),
               "select_autoescape não inclui 'j2' — o escape fica desligado em "
               "todos os templates, que terminam em .j2")


def test_sem_handlers_inline():
    """Handler no markup exigiria 'unsafe-inline' em script-src."""
    padrao = re.compile(r"\son(click|input|change|submit|focus|blur|keydown|keyup|"
                        r"load|error|mouseover)\s*=", re.I)
    for arq in sorted(TEMPLATES.glob("*.j2")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                falhas.append(f"{arq.name}:{n}: handler inline — use addEventListener "
                              f"em site/static/js/")
    for arq in sorted(STATIC.glob("js/*.js")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                falhas.append(f"static/js/{arq.name}:{n}: handler inline gerado em "
                              f"string HTML — a CSP bloqueia")


def test_csp():
    base = (TEMPLATES / "base.html.j2").read_text(encoding="utf-8")
    csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', base)
    checar(csp is not None, "base.html.j2 sem Content-Security-Policy")
    if not csp:
        return
    politica = csp.group(1)
    diretivas = {}
    for parte in politica.split(";"):
        parte = parte.strip()
        if parte:
            nome, _, valor = parte.partition(" ")
            diretivas[nome] = valor

    checar("'unsafe-inline'" not in diretivas.get("script-src", ""),
           "script-src permite 'unsafe-inline' — todo JS deve viver em arquivo")
    checar("'unsafe-eval'" not in diretivas.get("script-src", ""),
           "script-src permite 'unsafe-eval'")
    for obrigatoria in ("default-src", "object-src", "base-uri", "frame-ancestors",
                        "form-action"):
        checar(obrigatoria in diretivas, f"CSP sem a diretiva {obrigatoria}")
    checar(diretivas.get("frame-ancestors") == "'none'",
           "frame-ancestors deveria ser 'none' (proteção contra clickjacking)")


def test_sem_recursos_externos():
    """Nenhuma requisição sai do domínio — é o que a página de privacidade promete."""
    padrao = re.compile(r'(?:src|href)\s*=\s*["\'](https?:)?//', re.I)
    for arq in sorted(TEMPLATES.glob("*.j2")) + sorted(STATIC.glob("**/*.js")) \
            + sorted(STATIC.glob("**/*.css")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                falhas.append(f"{arq.name}:{n}: recurso externo — a promessa de "
                              f"privacidade e a CSP proíbem")
    for arq in sorted(STATIC.glob("**/*.css")):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"@import\s+url\(\s*['\"]?https?:", linha, re.I):
                falhas.append(f"{arq.name}:{n}: @import externo no CSS")


def test_sem_rastreamento():
    """Sem cookies, sem storage, sem analytics — a base da declaração de LGPD."""
    proibidos = {
        "document.cookie": "cookie",
        "localStorage": "armazenamento local",
        "sessionStorage": "armazenamento de sessão",
        "indexedDB": "IndexedDB",
        "gtag(": "Google Analytics",
        "dataLayer": "tag manager",
        "sendBeacon": "beacon de telemetria",
    }
    alvos = sorted(STATIC.glob("**/*.js")) + sorted(TEMPLATES.glob("*.j2"))
    for arq in alvos:
        texto = arq.read_text(encoding="utf-8")
        for agulha, nome in proibidos.items():
            # A página de privacidade cita os termos justamente para negá-los.
            if agulha in texto and arq.name != "privacidade.html.j2":
                falhas.append(f"{arq.name}: usa {nome} ({agulha}) — contradiz "
                              f"privacidade.html")


def test_sem_credencial_versionada():
    """Chave de API não pode entrar no repositório.

    Este repositório é público: uma chave commitada fica no histórico para
    sempre, e removê-la do HEAD não a apaga de lá — o remédio seria reescrever
    o histórico e rotacionar a chave. Melhor nunca deixar entrar.
    """
    padroes = [
        (re.compile(r"DADOS_GOV_API_KEY\s*=\s*['\"][^'\"]{8,}"), "chave do dados.gov.br"),
        (re.compile(r"chave-api-dados-abertos['\"]?\s*[:=]\s*['\"][^'\"]{8,}"), "header com chave"),
        (re.compile(r"(?i)(api[_-]?key|secret|token|senha|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}"),
         "credencial literal"),
    ]
    alvos = list((REPO / "etl").glob("*.py")) + list((REPO / "site").glob("*.py"))         + list((REPO / "tests").glob("*.py")) + list(STATIC.glob("**/*.js"))         + list(TEMPLATES.glob("*.j2")) + list((REPO / ".github").glob("**/*.yml"))
    # Exemplos de uso na documentação usam valor obviamente fictício. Ignorar
    # esses casos mantém o teste útil: um teste que grita em falso é desligado,
    # e aí deixa de proteger de verdade.
    marcadores = ("sua-chave", "sua_chave", "your-key", "your_key", "exemplo",
                  "coloque", "xxxx", "<", "trocar", "changeme")
    for arq in alvos:
        texto = arq.read_text(encoding="utf-8")
        for padrao, rotulo in padroes:
            for achado in padrao.finditer(texto):
                trecho = achado.group(0).lower()
                if any(m in trecho for m in marcadores):
                    continue
                falhas.append(f"{arq.name}: {rotulo} aparentemente literal no código "
                              f"— use variável de ambiente")
                break


def test_acessibilidade_base():
    base = (TEMPLATES / "base.html.j2").read_text(encoding="utf-8")
    checar('lang="pt-BR"' in base, "sem lang=\"pt-BR\" no <html>")
    checar("pular-para-conteudo" in base, "sem link de pular para o conteúdo")
    checar('id="conteudo"' in base, "sem alvo #conteudo para o link de pular")
    checar("aria-live" in base, "sem região aria-live para anunciar resultados")


def test_contraste_tokens():
    """Cor de texto precisa de 4,5:1 (WCAG AA). Tokens de traço não servem de texto."""
    css = (STATIC / "css" / "style.css").read_text(encoding="utf-8")

    def luminancia(hexa):
        canais = []
        for i in (1, 3, 5):
            v = int(hexa[i:i + 2], 16) / 255
            canais.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]

    def razao(a, b):
        la, lb = luminancia(a), luminancia(b)
        maior, menor = max(la, lb), min(la, lb)
        return (maior + 0.05) / (menor + 0.05)

    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", css))
    fundo = tokens.get("--bg", "#FFFFFF")
    for nome in ("--text", "--text-muted", "--gold-texto", "--nodata-texto",
                 "--navy", "--blue"):
        cor = tokens.get(nome)
        if not cor:
            falhas.append(f"token {nome} ausente em style.css")
            continue
        r = razao(cor, fundo)
        checar(r >= 4.5, f"{nome} ({cor}) tem contraste {r:.2f}:1 sobre {fundo} — "
                         f"WCAG AA exige 4,5:1 para texto")

    # Os tokens de traço não podem voltar a ser usados como cor de texto.
    for bruto in ("var(--gold)", "var(--nodata)"):
        for n, linha in enumerate(css.splitlines(), 1):
            if re.search(r"color:\s*" + re.escape(bruto), linha):
                falhas.append(f"style.css:{n}: {bruto} usado como cor de texto — "
                              f"use a variante -texto, que passa no AA")


def main():
    test_autoescape()
    test_sem_handlers_inline()
    test_csp()
    test_sem_recursos_externos()
    test_sem_rastreamento()
    test_sem_credencial_versionada()
    test_acessibilidade_base()
    test_contraste_tokens()

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) de segurança/acessibilidade:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    print("[PASSOU] CSP sem unsafe-inline, zero handler inline, zero recurso "
          "externo, zero rastreamento, contraste AA nos tokens de texto.")


if __name__ == "__main__":
    main()
