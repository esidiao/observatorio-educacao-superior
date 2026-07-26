---
description: Retoma o trabalho no Observatório Nacional da Educação Superior — carrega estado, decisões de modelagem e próximos passos.
argument-hint: [o que fazer nesta sessão, opcional]
---

# Continuar: Observatório Nacional da Educação Superior

Retomada do projeto multi-curso em `C:\Users\User\dev\observatorio-educacao-superior`.

Se `$ARGUMENTS` trouxer uma tarefa específica, faça-a. Se vier vazio, leia o estado
abaixo, rode a verificação da seção 6 e proponha os próximos passos antes de agir.

## 1. Estado ao final da sessão de 2026-07-26

- Commit inicial `2850f0b`, árvore limpa.
- **Sem remote no GitHub. Sem deploy.** Nada publicado ainda — decisão pendente do usuário.
- 4 cursos com dados reais do Censo 2024 (720.349 linhas) + CPC/ENADE 2023:
  Farmácia, Medicina, Direito, Engenharia Civil.
- Site com 115 páginas, verificado no navegador, sem erros de console.
- Portão de qualidade, integridade e catálogo: todos passando.

## 2. Pipeline

Microdados não versionados (>450 MB), em
`G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/`:

```bash
python etl/ingestao.py \
  --censo "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/microdados_censo_da_educacao_superior_2024/dados/MICRODADOS_CADASTRO_CURSOS_2024.CSV" \
  --ies   "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/microdados_censo_da_educacao_superior_2024/dados/MICRODADOS_ED_SUP_IES_2024.CSV"
python etl/qualidade.py --cpc "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/CPC_2023.xlsx"
python etl/consolidar.py
python site/build.py
```

A ingestão lê o CSV inteiro uma vez (~2 min). Só reprocessar quando mudar o catálogo
de cursos ou sair Censo novo — os JSONs consolidados já estão versionados.

## 3. Decisões de modelagem — NÃO reverter achando que é bug

Estas divergem de propósito do observatório de Farmácia
(`C:\Users\User\dev\observatorio-nacional`), que é referência arquitetural, não dependência:

- **Match EXATO no rótulo CINE**, nunca substring. `NO_CINE_ROTULO == "Medicina"` —
  substring capturaria "Biomedicina" (7.193 linhas) e "Medicina veterinária" (841);
  "Direito" capturaria "Programas interdisciplinares abrangendo negócios, administração
  e direito".
- **EaD tem duas camadas no Censo**: linhas de *sede* têm `SG_UF` nulo e carregam as
  VAGAS; linhas de *polo* têm UF preenchida e carregam as MATRÍCULAS, com zero vagas.
  Somar ingenuamente zera as vagas EaD. As vagas vão para a UF-sede da mantenedora via
  `MICRODADOS_ED_SUP_IES_2024.CSV` (`CO_IES` → `SG_UF_IES`).
- **`municipios_oferta` conta só presencial.** O repo de Farmácia funde campus presencial
  com polo EaD num número só (GO: reporta 75, que é a contagem de polos; o presencial é
  19). Aqui são campos separados: `municipios_oferta`, `ead_polos_municipios`,
  `mun_ead_only`. Os dois observatórios reportam números territoriais diferentes para
  Farmácia — intencional, documentado em `metodologia.html`.
- **Denominador do IAF é `vagas_total`**, não `vagas_presencial`. `vagas_avaliadas` cobre
  cursos presenciais E EaD; dividir só pelo presencial produzia V > 1 e IAF até 185 numa
  escala 0–100.
- **ICON virou "cobertura correlata"** opcional, declarada por curso em
  `data/cursos.json`. Sem fonte oficial para a área, o indicador não aparece — nenhuma
  proxy é inventada.
- **MT tem 141 municípios**, não 142 (o repo de Farmácia tem 142, fechando 5.571).

## 4. Âncoras de validação — usar para detectar regressão

- Farmácia: 417.010 vagas = 130.150 presencial + 286.860 EaD (idêntico ao cross-check
  publicado no observatório de Farmácia).
- Medicina: 0 vagas EaD (vedação legal da modalidade) — bom sinal de que o split
  sede/polo está correto.
- Soma municipal exatamente 5.570 por curso; por UF,
  `municipios_oferta + municipios_deserto == municipios_total`.
- Direito sem ENADE em todas as 27 UFs → IAF nulo. **É comportamento correto**, não bug:
  o ciclo da área não está no CPC 2023.

## 5. Guardrails automatizados

- `etl/indices.py --autoteste` — valida as fórmulas contra casos sintéticos (incluindo
  "fonte ausente deve virar null"), então segue válido conforme novos cursos entram.
- `tests/test_catalogo.py` — falha o build se um indicador existir no `GLOSSARIO`
  (`site/static/js/glossario.js`) sem entrada em `INDICADOR_META`
  (`site/static/js/app.js`), ou vice-versa. É a proteção contra o bug de formatação em
  que uma contagem de 19 renderiza `19,000`, lido em pt-BR como dezenove mil.
- `tests/test_validacao.py` — faixas dos índices, fechamento territorial e a regra de que
  IAF nunca é calculado sem conceito ENADE (pega estimativa silenciosa).

## 6. Verificação rápida ao retomar

```bash
python etl/indices.py --autoteste && python tests/test_validacao.py && python tests/test_catalogo.py && python site/build.py
```

Para conferir no navegador: sirva `site/dist/` e abra `comparar-cursos.html`
(a página que é o diferencial do projeto — testar o recorte Brasil e ao menos uma UF).
Use `preview_start` com `{url}` apontando para o localhost; a config em
`.claude/launch.json` usa a porta 7474.

## 7. Próximos passos em aberto

**Decisão pendente do usuário (publica conteúdo — confirmar antes):**
1. Criar repositório no GitHub — público ou privado? Nome sugerido:
   `observatorio-educacao-superior`.
2. Deploy: GitHub Pages, Vercel, ou ambos (o projeto de Farmácia usa os dois).
   Se for Pages, o `ci.yml` precisa ganhar os jobs de `upload-pages-artifact` e
   `deploy-pages` mais as permissions `pages: write` / `id-token: write`.

**Melhorias identificadas, não implementadas:**
- Mapa coroplético por UF (o repo de Farmácia usa Leaflet + malhas do IBGE via
  `servicodados.ibge.gov.br`); exigiria ajustar a CSP, hoje restrita a `'self'`.
- Páginas por município (o repo de Farmácia gera ~2.009; aqui os dados municipais já
  estão em `data/cursos/<slug>/municipios/<UF>.json`, só falta a rota).
- Série histórica (Censo 2023 disponível em
  `G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2023.zip`).
- Ampliar o catálogo de cursos — é só acrescentar entrada em `data/cursos.json` com o
  rótulo CINE exato e rodar o pipeline.
- Processo de auditoria semanal no mesmo formato de 7 seções do projeto de Farmácia,
  quando este estiver publicado.

## 8. Princípio inegociável

Nenhum indicador é estimado. Sem fonte oficial para um recorte, o valor é `null` e
aparece como "sem dados" — nunca zero, nunca média plausível. Isso vale em dobro aqui:
cursos diferentes têm cobertura de dados muito desigual no Censo/ENADE, e a tentação de
preencher lacuna por analogia é constante. Não ceda a ela.
