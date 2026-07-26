"""
Coerência entre o catálogo de indicadores (glossario.js) e a tabela de
formatação (app.js).

    python tests/test_catalogo.py

Motivo: um indicador presente no GLOSSARIO mas ausente do INDICADOR_META cai no
fallback de 3 casas decimais — uma contagem como 19 é renderizada "19,000", que
em pt-BR se lê como dezenove mil. O bug é invisível no código e evidente na tela.
Este teste torna impossível publicá-lo.
"""
import re
import sys
from pathlib import Path

JS = Path(__file__).parent.parent / "site" / "static" / "js"

falhas = []


def chaves_glossario():
    texto = (JS / "glossario.js").read_text(encoding="utf-8")
    return set(re.findall(r"key\s*:\s*'([^']+)'", texto))


def chaves_meta():
    texto = (JS / "app.js").read_text(encoding="utf-8")
    bloco = re.search(r"const INDICADOR_META = \{(.*?)\n\};", texto, re.S)
    if not bloco:
        falhas.append("INDICADOR_META não localizado em app.js")
        return set(), {}
    corpo = bloco.group(1)
    chaves = set(re.findall(r"^\s*(\w+)\s*:", corpo, re.M))
    entradas = dict(re.findall(r"^\s*(\w+)\s*:\s*\{([^}]*)\}", corpo, re.M))
    return chaves, entradas


def main():
    gloss = chaves_glossario()
    meta, entradas = chaves_meta()

    sem_formato = sorted(gloss - meta)
    if sem_formato:
        falhas.append(
            "indicadores no GLOSSARIO sem entrada em INDICADOR_META "
            f"(cairiam no fallback de 3 decimais): {', '.join(sem_formato)}")

    orfaos = sorted(meta - gloss)
    if orfaos:
        falhas.append(
            "entradas em INDICADOR_META sem verbete no GLOSSARIO "
            f"(o usuário veria o indicador sem explicação): {', '.join(orfaos)}")

    for chave, corpo in entradas.items():
        if "dec:" not in corpo:
            falhas.append(f"{chave}: sem 'dec' — casas decimais indefinidas")
        if "label:" not in corpo:
            falhas.append(f"{chave}: sem 'label' — apareceria como chave crua na tela")

    if falhas:
        print(f"[FALHOU] {len(falhas)} problema(s) no catálogo de indicadores:\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)

    print(f"[PASSOU] Catálogo coerente: {len(gloss)} indicadores com verbete e formatação.")


if __name__ == "__main__":
    main()
