"""
Verifica se o INEP publicou uma edição do Censo mais nova que a usada aqui.

Uso:
    python etl/verificar_novo_censo.py            # relatório legível
    python etl/verificar_novo_censo.py --json     # para consumo em automação

Códigos de saída:
    0  nada novo — a edição em uso é a mais recente publicada
    1  erro ao consultar o servidor do INEP
    2  existe edição mais nova (não é falha: é o achado que se procurava)

Por que isto existe. Um observatório desatualizado não avisa que está
desatualizado: as páginas continuam no ar, os números continuam plausíveis, e
nada quebra. O risco não é o erro visível, é a defasagem silenciosa — alguém
citar em 2027 um número de 2024 acreditando que é o mais recente.

Por que só verifica e não ingere. Uma edição nova reescreve todos os números do
site, e essa é uma decisão de quem assina a obra, não de um agendador. O Censo
também costuma sair primeiro como prévia e depois consolidado, e ingerir a
primeira versão que aparece trocaria dado estável por dado provisório sem que
ninguém tivesse decidido isso.

O servidor do INEP derruba conexão com frequência — ver a nota em
etl/baixar_censo.py. Por isso cada ano é consultado com retentativa, e uma queda
não é lida como ausência: dizer "não há edição nova" quando na verdade não se
conseguiu perguntar seria pior que não verificar.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from rede import abrir

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
URL = "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"
# Duas tentativas, não três, e vinte segundos, não cento e vinte. Uma pergunta
# HEAD que não volta em vinte segundos não vai voltar, e cada segundo aqui é
# multiplicado por tentativas e por anos: com os valores antigos o pior caso
# passava de uma hora, e passou — a execução de 10/08/2026 ficou 1h20 presa.
TENTATIVAS = 2
ESPERA_RESPOSTA = 20
ANOS_ADIANTE = 3          # quanto olhar além da edição em uso


def edicao_em_uso():
    """Ano do Censo que alimenta o site hoje.

    Lido de um arquivo de curso, e não de uma constante: constante se atualiza
    à mão e mente quando alguém esquece. O dado sabe de que ano ele é.
    """
    for caminho in sorted((DATA / "cursos").glob("*/nacional.json")):
        with open(caminho, encoding="utf-8") as f:
            versao = json.load(f).get("metadados", {}).get("versao_censo")
        if versao:
            return int(versao)
    raise SystemExit("[ERRO] Nenhum data/cursos/*/nacional.json com versao_censo. "
                     "Rode o pipeline do ETL antes.")


def existe(ano):
    """(publicado?, tamanho em MB). Levanta se não conseguiu perguntar."""
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with abrir(URL.format(ano=ano), timeout=ESPERA_RESPOSTA, metodo="HEAD") as r:
                return True, int(r.headers.get("Content-Length", 0)) / 1048576
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, 0.0       # resposta clara: ainda não saiu
            ultimo_erro = e
        except Exception as e:          # noqa: BLE001
            ultimo_erro = e
        if tentativa < TENTATIVAS:
            time.sleep(5 * tentativa)
    raise RuntimeError(f"{ano}: {type(ultimo_erro).__name__}: {ultimo_erro}")


def main():
    parser = argparse.ArgumentParser(
        description="Procura edição do Censo mais nova que a usada no site")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    atual = edicao_em_uso()
    novas, indisponiveis = [], []
    for ano in range(atual + 1, atual + 1 + ANOS_ADIANTE):
        try:
            publicado, mb = existe(ano)
        except RuntimeError as e:
            indisponiveis.append(str(e))
            continue
        if publicado:
            novas.append({"ano": ano, "mb": round(mb)})

    relatorio = {"edicao_em_uso": atual, "novas": novas,
                 "nao_consultados": indisponiveis}

    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False))
    else:
        print(f"Edição em uso no site: Censo {atual}")
        for n in novas:
            print(f"  [NOVA] Censo {n['ano']} publicado ({n['mb']} MB)")
        for e in indisponiveis:
            print(f"  [?] não foi possível consultar — {e}")
        if not novas and not indisponiveis:
            print("  Nada novo: a edição em uso é a mais recente publicada.")

    if indisponiveis and not novas:
        # Não se conseguiu perguntar. Silêncio aqui viraria "não há nada novo",
        # que é uma afirmação que ninguém verificou.
        return 1
    return 2 if novas else 0


if __name__ == "__main__":
    sys.exit(main())
