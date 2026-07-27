"""
e-MEC: Conceito Institucional, credenciamento e cadastro de IES.

Precisa de chave da API do Portal Brasileiro de Dados Abertos. A chave é pessoal,
vinculada a um cadastro — obtenha em https://dados.gov.br, área "Minha Conta".

    # Windows PowerShell
    $env:DADOS_GOV_API_KEY = "sua-chave"
    # bash
    export DADOS_GOV_API_KEY="sua-chave"

    python etl/emec.py --listar          # inspeciona o conjunto e as colunas
    python etl/emec.py                   # ingere para data/emec.json

A CHAVE NUNCA VAI PARA O REPOSITÓRIO. É lida só de variável de ambiente, jamais de
arquivo versionado, e `tests/test_seguranca.py` reprova o build se algo com cara de
credencial aparecer no código. O repositório é público: uma chave commitada fica
no histórico para sempre, e apagá-la do HEAD não a remove de lá.

POR QUE O MODO --listar EXISTE. Não foi possível conferir o esquema deste conjunto
antes de escrever o ETL — a API exige chave. Então o script primeiro mostra o que
veio (recursos, formatos, colunas) em vez de assumir nomes de campo e falhar
silenciosamente ou, pior, casar a coluna errada. Rode `--listar` uma vez, confira
os nomes contra o mapa CAMPOS abaixo, ajuste se preciso, e só então ingira.

O QUE SE ESPERA DAQUI, e o que continua fora. O e-MEC traz Conceito Institucional
(CI), Conceito de Curso (CC), situação de credenciamento e data da última
avaliação — as quatro ausências que os painéis institucionais declaram hoje. O CI
NÃO é o IGC: um é nota de comissão que visitou a instituição, o outro é índice
calculado sobre CPC e pós-graduação. Continuarão lado a lado, nunca fundidos.
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

BASE = "https://dados.gov.br/dados/api/publico"
CABECALHO_CHAVE = "chave-api-dados-abertos"
VARIAVEL = "DADOS_GOV_API_KEY"
BUSCA_PADRAO = "e-MEC"

# Campo interno → possíveis nomes de coluna, em ordem de preferência. Vale por
# trecho e sem caixa: o e-MEC muda pontuação e acentuação entre publicações.
CAMPOS = {
    "co_ies": ("CODIGO_DA_IES", "CO_IES", "CODIGO_IES", "COD_IES"),
    "nome": ("NOME_DA_IES", "NO_IES", "NOME_IES"),
    "ci": ("CI", "CONCEITO_INSTITUCIONAL"),
    "ci_ano": ("ANO_CI", "CI_ANO", "ANO_DO_CI"),
    "igc_emec": ("IGC", "INDICE_GERAL_DE_CURSOS"),
    "situacao": ("SITUACAO", "SITUACAO_DA_IES", "STATUS"),
    "credenciamento": ("CREDENCIAMENTO", "ATO_REGULATORIO", "DATA_CREDENCIAMENTO"),
    "organizacao": ("ORGANIZACAO_ACADEMICA", "TP_ORGANIZACAO_ACADEMICA"),
    "categoria": ("CATEGORIA_ADMINISTRATIVA", "TP_CATEGORIA_ADMINISTRATIVA"),
}


def chave():
    valor = os.environ.get(VARIAVEL, "").strip()
    if not valor:
        sys.exit(
            f"[ERRO] Variável {VARIAVEL} não definida.\n"
            f"       A chave é pessoal e não pode ser versionada. Obtenha em\n"
            f"       https://dados.gov.br (Minha Conta) e exporte na sessão:\n"
            f'         PowerShell:  $env:{VARIAVEL} = "sua-chave"\n'
            f'         bash:        export {VARIAVEL}="sua-chave"')
    return valor


def pedir(caminho, params=None):
    url = f"{BASE}{caminho}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        CABECALHO_CHAVE: chave(),
        "Accept": "application/json",
        "User-Agent": "observatorio-educacao",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("[ERRO] 401: chave recusada. Confira se copiou a chave inteira "
                     "e se o perfil tem permissão de consulta.")
        sys.exit(f"[ERRO] HTTP {e.code} em {url}")


def normalizar(nome):
    return "".join(c if c.isalnum() else "_" for c in str(nome).upper()).strip("_")


def achar_coluna(colunas, candidatos):
    normalizadas = {normalizar(c): c for c in colunas}
    for alvo in candidatos:
        if alvo in normalizadas:
            return normalizadas[alvo]
    # Segunda passada, por trecho — cobre sufixos e prefixos inesperados.
    for alvo in candidatos:
        for norm, original in normalizadas.items():
            if alvo in norm:
                return original
    return None


def baixar_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        bruto = resp.read()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(enc)
        except UnicodeDecodeError:
            continue
        amostra = texto[:4000]
        delim = ";" if amostra.count(";") > amostra.count(",") else ","
        return list(csv.DictReader(io.StringIO(texto), delimiter=delim))
    sys.exit("[ERRO] não foi possível decodificar o CSV.")


def main():
    parser = argparse.ArgumentParser(description="Ingestão do cadastro e-MEC")
    parser.add_argument("--busca", default=BUSCA_PADRAO)
    parser.add_argument("--listar", action="store_true",
                        help="Só mostra conjuntos, recursos e colunas — não ingere")
    parser.add_argument("--recurso", help="URL de um recurso CSV específico")
    parser.add_argument("--saida", default=str(DATA / "emec.json"))
    args = parser.parse_args()

    if args.recurso:
        linhas = baixar_csv(args.recurso)
    else:
        print(f"[INFO] Buscando conjuntos com '{args.busca}' ...")
        resultado = pedir("/conjuntos-dados", {"nomeConjuntoDados": args.busca})
        conjuntos = resultado if isinstance(resultado, list) else resultado.get("value", [])
        if not conjuntos:
            sys.exit(f"[ERRO] nenhum conjunto encontrado para '{args.busca}'.")

        print(f"[INFO] {len(conjuntos)} conjunto(s):")
        for c in conjuntos[:10]:
            print(f"   id={c.get('id')}  {c.get('title') or c.get('nome')}")

        detalhe = pedir(f"/conjuntos-dados/{conjuntos[0].get('id')}")
        recursos = detalhe.get("recursos") or detalhe.get("resources") or []
        print(f"\n[INFO] {len(recursos)} recurso(s) no primeiro conjunto:")
        csvs = []
        for r in recursos:
            formato = (r.get("formato") or r.get("format") or "").upper()
            link = r.get("link") or r.get("url")
            print(f"   [{formato}] {r.get('titulo') or r.get('name')}\n        {link}")
            if formato == "CSV" and link:
                csvs.append(link)
        if not csvs:
            sys.exit("[ERRO] nenhum recurso CSV. Rode com --recurso <url> se souber "
                     "o endereço, ou confira a saída acima.")
        linhas = baixar_csv(csvs[0])

    if not linhas:
        sys.exit("[ERRO] recurso vazio.")
    colunas = list(linhas[0].keys())
    print(f"\n[INFO] {len(linhas)} linhas · {len(colunas)} colunas")

    mapa = {campo: achar_coluna(colunas, candidatos)
            for campo, candidatos in CAMPOS.items()}
    print("\n[INFO] mapeamento de colunas:")
    for campo, coluna in mapa.items():
        print(f"   {campo:<16} → {coluna or '(NÃO ENCONTRADA)'}")

    if args.listar:
        print("\n[INFO] Colunas disponíveis:")
        for c in colunas:
            print("   ", c)
        print("\nConfira o mapeamento acima contra CAMPOS em etl/emec.py e rode "
              "sem --listar para ingerir.")
        return

    if not mapa["co_ies"]:
        sys.exit("[ERRO] coluna de código da IES não localizada. Sem ela não há "
                 "junção exata com o Censo, e casar por nome seria heurística — "
                 "o que este projeto recusa. Rode --listar e ajuste CAMPOS.")

    saida = {}
    for linha in linhas:
        codigo = str(linha.get(mapa["co_ies"]) or "").strip().split(".")[0]
        if not codigo or not codigo.isdigit():
            continue
        registro = {}
        for campo, coluna in mapa.items():
            if campo == "co_ies" or not coluna:
                continue
            valor = str(linha.get(coluna) or "").strip()
            registro[campo] = valor or None
        saida[codigo] = registro

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump({
            "_nota": ("Conceito Institucional (CI) vem de avaliação in loco por "
                      "comissão e NÃO é o IGC, que é índice calculado sobre CPC e "
                      "pós-graduação. Os dois convivem, nunca se substituem."),
            "_fonte": "Portal Brasileiro de Dados Abertos — cadastro e-MEC",
            "instituicoes": saida,
        }, f, ensure_ascii=False, indent=1)

    caminho_ies = DATA / "instituicoes.json"
    print(f"\n[OK] {len(saida)} instituições em {args.saida}")
    if caminho_ies.exists():
        with open(caminho_ies, encoding="utf-8") as f:
            nossas = json.load(f)["instituicoes"]
        casadas = sum(1 for co in nossas if co in saida)
        print(f"     {casadas} de {len(nossas)} do observatório casaram por código "
              f"({100 * casadas / len(nossas):.0f}%)")
        if casadas < len(nossas) * 0.5:
            print("     [ATENÇÃO] casamento baixo. O código do e-MEC pode não ser o "
                  "mesmo do Censo neste recurso — confira antes de publicar.")


if __name__ == "__main__":
    main()
