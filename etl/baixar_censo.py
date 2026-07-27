"""
Baixa edições do Censo do INEP e alimenta a série histórica.

Uso:
    python etl/baixar_censo.py --anos 2015 2016 2017 2018 2019 2020 2021
    python etl/baixar_censo.py --anos 2021 --manter   # não apaga o CSV depois

Um ano por vez: baixa o zip, extrai só os dois CSVs necessários, chama
etl/serie.py e apaga. Sem o descarte, sete edições ocupariam mais de um giga de
disco para produzir alguns megabytes de série.

Por que dá para voltar até 2015 com o mesmo código: o INEP reclassificou as
edições antigas na CINE e republicou. `NO_CINE_ROTULO` existe em todas, então o
match exato de rótulo — a regra do projeto inteiro — vale para trás sem gambiarra.

Duas diferenças de nomenclatura entre edições, tratadas aqui:
  · o cadastro de IES se chamou MICRODADOS_CADASTRO_IES_AAAA.CSV até 2021 e
    MICRODADOS_ED_SUP_IES_AAAA.CSV depois;
  · o diretório dentro do zip muda de nome e de acentuação a cada ano, então os
    arquivos são localizados por padrão, nunca por caminho fixo.

O que este script NÃO faz: reingerir os indicadores completos de anos anteriores.
A série guarda poucos campos comparáveis de propósito — ver etl/serie.py.
"""
import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).parent.parent
URL = "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"


def baixar(ano, destino):
    url = URL.format(ano=ano)
    print(f"[GET] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "observatorio-educacao"})
    with urllib.request.urlopen(req, timeout=900) as resp, open(destino, "wb") as saida:
        baixado = 0
        while True:
            bloco = resp.read(1 << 20)
            if not bloco:
                break
            saida.write(bloco)
            baixado += len(bloco)
            print(f"\r      {baixado / 1048576:.0f} MB", end="", flush=True)
    print()


def extrair(zip_path, ano, pasta):
    """Extrai o cadastro de cursos e o de IES, achando-os por padrão no nome."""
    with zipfile.ZipFile(zip_path) as z:
        csvs = [n for n in z.namelist() if n.upper().endswith(".CSV")]
        cursos = next((n for n in csvs if "CURSOS" in n.upper()), None)
        ies = next((n for n in csvs if "IES" in n.upper() and "CURSOS" not in n.upper()),
                   None)
        if not cursos or not ies:
            raise SystemExit(f"[ERRO] {ano}: CSVs esperados não encontrados no zip. "
                             f"Encontrados: {csvs}")
        saidas = {}
        for rotulo, nome in (("censo", cursos), ("ies", ies)):
            alvo = pasta / f"{rotulo}_{ano}.csv"
            with z.open(nome) as origem, open(alvo, "wb") as destino:
                shutil.copyfileobj(origem, destino)
            saidas[rotulo] = alvo
            print(f"      {alvo.name}: {alvo.stat().st_size / 1048576:.0f} MB")
        return saidas


def main():
    parser = argparse.ArgumentParser(description="Baixa edições do Censo e monta a série")
    parser.add_argument("--anos", nargs="+", type=int, required=True)
    parser.add_argument("--manter", action="store_true",
                        help="Não apagar os CSVs extraídos ao terminar")
    parser.add_argument("--trabalho", default=None,
                        help="Diretório de trabalho (padrão: temporário no repo)")
    args = parser.parse_args()

    pasta = Path(args.trabalho) if args.trabalho else REPO / ".censo-tmp"
    pasta.mkdir(parents=True, exist_ok=True)

    falhas = []
    for ano in sorted(args.anos):
        print(f"\n{'=' * 60}\n== Censo {ano}\n{'=' * 60}")
        zip_path = pasta / f"censo_{ano}.zip"
        try:
            if not zip_path.exists():
                baixar(ano, zip_path)
            else:
                print(f"[INFO] {zip_path.name} já baixado, reaproveitando.")
            arquivos = extrair(zip_path, ano, pasta)

            print(f"[RUN] etl/serie.py para {ano} ...")
            resultado = subprocess.run(
                [sys.executable, str(REPO / "etl" / "serie.py"),
                 "--censo", str(arquivos["censo"]), "--ies", str(arquivos["ies"])],
                cwd=str(REPO / "etl"))
            if resultado.returncode != 0:
                falhas.append(f"{ano}: serie.py retornou {resultado.returncode}")
                continue
        except Exception as e:                       # noqa: BLE001
            falhas.append(f"{ano}: {type(e).__name__}: {e}")
            continue
        finally:
            if not args.manter:
                # Descarta cedo: sete edições somam mais de um giga em disco.
                for p in pasta.glob(f"*_{ano}.*"):
                    p.unlink(missing_ok=True)

    if not args.manter and pasta.exists() and not any(pasta.iterdir()):
        pasta.rmdir()

    if falhas:
        print(f"\n[ATENÇÃO] {len(falhas)} edição(ões) não entraram na série:")
        for f in falhas:
            print(f"  · {f}")
        print("  A série segue válida com os anos que entraram — ponto ausente "
              "não vira zero.")
        sys.exit(1)
    print("\n[OK] Série atualizada.")


if __name__ == "__main__":
    main()
