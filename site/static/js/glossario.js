/**
 * Catálogo de indicadores — fonte única para o glossário e para o seletor de KPIs.
 * Todo `key` daqui precisa ter entrada correspondente em INDICADOR_META (app.js);
 * tests/test_catalogo.py falha o build se algum ficar sem.
 */
const GLOSSARIO = [
  // ── Território ────────────────────────────────────────────────────────────
  { key:'ICT', sigla:'ICT', nome:'Índice de Concentração Territorial', cat:'Território',
    oque:'Mede o quanto a oferta presencial se concentra em poucos municípios. Combina a fatia de vagas na capital com a proporção de municípios sem oferta. Perto de 1 = formação concentrada, interior descoberto.',
    escala:'0 a 1', dir:'menor', fonte:'Censo INEP' },
  { key:'E', sigla:'Equidade', nome:'Equidade Territorial', cat:'Território',
    oque:'Complemento do ICT (E = 1 − ICT). Quanto maior, mais distribuída pelo território é a oferta presencial.',
    escala:'0 a 1', dir:'maior', fonte:'Calculado' },
  { key:'municipios_oferta', sigla:'Municípios c/ oferta', nome:'Municípios com oferta presencial', cat:'Território',
    oque:'Municípios com ao menos um curso PRESENCIAL em funcionamento. Polos EaD são contados à parte, pois não equivalem a um campus.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP' },
  { key:'municipios_deserto', sigla:'Desertos', nome:'Desertos formativos', cat:'Território',
    oque:'Municípios sem nenhum curso presencial deste curso. Quanto maior, menor o acesso local à formação.',
    escala:'municípios', dir:'menor', fonte:'Censo INEP' },
  { key:'ead_polos_municipios', sigla:'Municípios c/ polo EaD', nome:'Alcance territorial da EaD', cat:'Território',
    oque:'Municípios da UF que recebem oferta a distância via polo. Mostra a penetração real no território, que a contagem de vagas na sede da mantenedora esconde.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP' },
  { key:'mun_ead_only', sigla:'Municípios só EaD', nome:'Municípios atendidos apenas por EaD', cat:'Território',
    oque:'Municípios com polo EaD e nenhum curso presencial. Onde a formação existe somente a distância.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP' },
  { key:'ead_polos_registros', sigla:'Polos EaD (registros)', nome:'Total de registros de polo EaD', cat:'Território',
    oque:'Registros de polo no estado. Um mesmo município pode ter polos de várias instituições, por isso este número supera o de municípios com polo.',
    escala:'registros', dir:'contextual', fonte:'Censo INEP' },
  { key:'cobertura', sigla:'Cobertura correlata', nome:'Cobertura do serviço correlato ao curso', cat:'Território',
    oque:'Razão entre municípios com o serviço público correlato à profissão e municípios com oferta formativa. Só existe para cursos com fonte oficial declarada; nos demais aparece como "sem dados", nunca estimado.',
    escala:'razão', dir:'maior', fonte:'Varia por curso' },

  // ── Qualidade ─────────────────────────────────────────────────────────────
  { key:'IAF', sigla:'IAF', nome:'Índice de Adequação Formativa', cat:'Qualidade',
    oque:'Combina qualidade dos conceitos (ENADE/IDD), cobertura avaliativa e equidade territorial num único índice de 0 a 100. Exige ciclo ENADE publicado para o curso.',
    escala:'0 a 100', dir:'maior', fonte:'ENADE + Censo INEP' },
  { key:'ENADE', sigla:'ENADE', nome:'Conceito ENADE (contínuo)', cat:'Qualidade',
    oque:'Desempenho dos concluintes no Exame Nacional de Desempenho dos Estudantes, em escala contínua. Média ponderada pelos concluintes participantes de cada curso da UF.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / ENADE' },
  { key:'CC', sigla:'CC', nome:'Conceito de Curso', cat:'Qualidade',
    oque:'Conceito médio dos cursos avaliados na UF, derivado do desempenho no ENADE.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / ENADE' },
  { key:'IDD', sigla:'IDD', nome:'Indicador de Diferença de Desempenho', cat:'Qualidade',
    oque:'Mede o VALOR AGREGADO pelo curso: compara o desempenho final com o esperado pelo perfil de ingresso, isolando o efeito do curso da qualidade de quem entrou.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / CPC' },
  { key:'CPC_cont', sigla:'CPC', nome:'Conceito Preliminar de Curso', cat:'Qualidade',
    oque:'Índice composto que reúne ENADE, IDD, corpo docente e infraestrutura numa visão geral da qualidade do curso.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / CPC' },
  { key:'pct_doc_doutores', sigla:'% Doutores', nome:'Docentes com doutorado', cat:'Qualidade',
    oque:'Proporção de professores com título de doutor nos cursos avaliados, ponderada por concluintes.',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC' },
  { key:'pct_doc_mestres', sigla:'% Mestres+', nome:'Docentes com mestrado ou mais', cat:'Qualidade',
    oque:'Proporção de professores com titulação mínima de mestre (inclui doutores).',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC' },
  { key:'pct_doc_regime', sigla:'% Regime integral/parcial', nome:'Docentes em regime integral ou parcial', cat:'Qualidade',
    oque:'Proporção de professores não horistas, o que favorece dedicação à pesquisa, orientação e permanência.',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC' },
  { key:'cpc_org_didatico', sigla:'Org. didático-pedagógica', nome:'Organização didático-pedagógica', cat:'Qualidade',
    oque:'Nota atribuída pelos próprios estudantes ao currículo, didática e formas de avaliação, no Questionário do Estudante.',
    escala:'1 a 6', dir:'maior', fonte:'INEP / CPC' },
  { key:'cpc_infraestrutura', sigla:'Infraestrutura', nome:'Infraestrutura e instalações físicas', cat:'Qualidade',
    oque:'Nota dada pelos estudantes a laboratórios, biblioteca, salas e equipamentos.',
    escala:'1 a 6', dir:'maior', fonte:'INEP / CPC' },
  { key:'cpc_oportunidade', sigla:'Oport. de ampliação', nome:'Oportunidade de ampliação da formação', cat:'Qualidade',
    oque:'Nota dada pelos estudantes às oportunidades além da sala de aula — pesquisa, extensão, monitoria, estágios.',
    escala:'1 a 6', dir:'maior', fonte:'INEP / CPC' },
  { key:'vagas_avaliadas', sigla:'Vagas avaliadas', nome:'Vagas em cursos avaliados', cat:'Qualidade',
    oque:'Vagas em cursos que participaram do ENADE — a base sobre a qual os conceitos de qualidade se aplicam.',
    escala:'vagas', dir:'contextual', fonte:'INEP / CPC' },
  { key:'n_cursos_avaliados', sigla:'Cursos avaliados', nome:'Cursos avaliados no ciclo', cat:'Qualidade',
    oque:'Quantidade de cursos da UF que participaram do ciclo ENADE vigente para esta área.',
    escala:'cursos', dir:'contextual', fonte:'INEP / CPC' },
  { key:'concluintes_avaliados', sigla:'Concluintes avaliados', nome:'Concluintes participantes do ENADE', cat:'Qualidade',
    oque:'Concluintes que participaram do exame — peso usado nas médias ponderadas de qualidade da UF.',
    escala:'estudantes', dir:'contextual', fonte:'INEP / CPC' },

  // ── Capacidade ────────────────────────────────────────────────────────────
  { key:'vagas_total', sigla:'Vagas totais', nome:'Capacidade total (presencial + EaD)', cat:'Capacidade',
    oque:'Soma das vagas anuais presenciais e a distância. As vagas EaD são atribuídas à UF-sede da mantenedora, conforme registro do Censo.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP' },
  { key:'vagas_presencial', sigla:'Vagas presenciais', nome:'Vagas presenciais', cat:'Capacidade',
    oque:'Vagas anuais em cursos presenciais em funcionamento na UF.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP' },
  { key:'vagas_ead', sigla:'Vagas EaD', nome:'Vagas a distância', cat:'Capacidade',
    oque:'Vagas anuais em cursos EaD, registradas na sede da mantenedora. Um único curso EaD pode atender dezenas de municípios via polos.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP' },
  { key:'vagas_capital', sigla:'Vagas na capital', nome:'Vagas presenciais na capital', cat:'Capacidade',
    oque:'Vagas presenciais ofertadas no município da capital — componente do cálculo de concentração territorial.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP' },
  { key:'pct_ead', sigla:'% EaD', nome:'Participação da EaD na capacidade', cat:'Capacidade',
    oque:'Percentual das vagas que são a distância. Em cursos com forte componente prático, valores muito altos acendem alerta sobre a oferta de atividades presenciais.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },
  { key:'vagas_por_100k', sigla:'Vagas / 100 mil hab.', nome:'Densidade de vagas por habitante', cat:'Capacidade',
    oque:'Vagas totais por 100 mil habitantes. Normaliza a capacidade pela população, revelando excesso ou escassez relativa que o número absoluto esconde.',
    escala:'vagas/100k', dir:'contextual', fonte:'Censo INEP + IBGE' },
  { key:'populacao', sigla:'População', nome:'População residente estimada', cat:'Capacidade',
    oque:'Estimativa populacional do IBGE para a UF, base dos indicadores per capita.',
    escala:'habitantes', dir:'contextual', fonte:'IBGE' },
  { key:'matriculas', sigla:'Matrículas', nome:'Matrículas presenciais', cat:'Capacidade',
    oque:'Estudantes matriculados em cursos presenciais no ano de referência.',
    escala:'estudantes', dir:'contextual', fonte:'Censo INEP' },
  { key:'matriculas_ead', sigla:'Matrículas EaD', nome:'Matrículas em polos EaD', cat:'Capacidade',
    oque:'Estudantes matriculados via polos EaD instalados na UF. Diferente das vagas EaD, que ficam na sede da mantenedora.',
    escala:'estudantes', dir:'contextual', fonte:'Censo INEP' },
  { key:'ingressos', sigla:'Ingressantes', nome:'Ingressantes presenciais', cat:'Capacidade',
    oque:'Estudantes que ingressaram em cursos presenciais no ano.',
    escala:'estudantes', dir:'contextual', fonte:'Censo INEP' },
  { key:'concluintes', sigla:'Concluintes', nome:'Concluintes presenciais', cat:'Capacidade',
    oque:'Estudantes que concluíram cursos presenciais no ano.',
    escala:'estudantes', dir:'contextual', fonte:'Censo INEP' },
  { key:'taxa_conclusao', sigla:'Taxa de conclusão', nome:'Conclusão (concluintes / matrículas)', cat:'Capacidade',
    oque:'Razão entre concluintes e matriculados no ano. É um retrato pontual, não o acompanhamento de uma coorte ao longo do tempo.',
    escala:'0 a 100%', dir:'maior', fonte:'Censo INEP' },
  { key:'n_cursos_presencial', sigla:'Cursos presenciais', nome:'Cursos presenciais em funcionamento', cat:'Capacidade',
    oque:'Quantidade de cursos presenciais registrados na UF.',
    escala:'cursos', dir:'contextual', fonte:'Censo INEP' },
  { key:'n_cursos_ead', sigla:'Cursos EaD', nome:'Cursos EaD sediados na UF', cat:'Capacidade',
    oque:'Cursos a distância cuja mantenedora é sediada na UF.',
    escala:'cursos', dir:'contextual', fonte:'Censo INEP' },
  { key:'municipios_total', sigla:'Municípios na UF', nome:'Total de municípios da UF', cat:'Capacidade',
    oque:'Total de municípios do estado, conforme a malha do IBGE. Denominador dos indicadores territoriais.',
    escala:'municípios', dir:'contextual', fonte:'IBGE' },

  // ── Acesso & equidade ─────────────────────────────────────────────────────
  { key:'pct_mulheres', sigla:'% Mulheres', nome:'Mulheres entre ingressantes', cat:'Acesso & equidade',
    oque:'Percentual de mulheres entre os ingressantes. Indicador descritivo do perfil de gênero, que varia muito entre as áreas.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },
  { key:'pct_ppi', sigla:'% Pretos/pardos/indígenas', nome:'Pretos, pardos e indígenas (PPI)', cat:'Acesso & equidade',
    oque:'Percentual de pretos, pardos e indígenas entre os ingressantes que declararam cor/raça. Acompanha a demografia regional.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },
  { key:'pct_financiamento', sigla:'% FIES/PROUNI', nome:'Ingressantes com FIES ou PROUNI', cat:'Acesso & equidade',
    oque:'Percentual de ingressantes com financiamento estudantil ou bolsa. Indica o peso das políticas públicas de acesso ao ensino privado.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },
  { key:'pct_noturno', sigla:'% Vagas noturnas', nome:'Vagas no turno noturno', cat:'Acesso & equidade',
    oque:'Percentual das vagas presenciais ofertadas à noite. Quanto maior, maior o acesso para quem trabalha durante o dia.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },
  { key:'pct_rede_publica', sigla:'% Rede pública', nome:'Vagas em rede pública', cat:'Acesso & equidade',
    oque:'Percentual das vagas em instituições públicas. Varia enormemente entre cursos e é decisivo para a leitura de acesso.',
    escala:'0 a 100%', dir:'contextual', fonte:'Censo INEP' },

  // ── Mercado ───────────────────────────────────────────────────────────────
  { key:'n_ies', sigla:'IES', nome:'Instituições de Ensino Superior', cat:'Mercado',
    oque:'Instituições com oferta do curso na UF (presencial ou sede de EaD).',
    escala:'instituições', dir:'contextual', fonte:'Censo INEP' },
  { key:'HHI', sigla:'HHI', nome:'Índice Herfindahl-Hirschman', cat:'Mercado',
    oque:'Concentração do mercado entre instituições. 0 = muitas IES pequenas; 1 = uma só domina. Acima de 0,25 indica mercado concentrado.',
    escala:'0 a 1', dir:'menor', fonte:'Censo INEP' },
  { key:'CR2', sigla:'CR2', nome:'Razão de Concentração — 2 maiores', cat:'Mercado',
    oque:'Fatia das vagas detida pelas 2 maiores instituições da UF.',
    escala:'0 a 100%', dir:'menor', fonte:'Censo INEP' },
  { key:'CR10', sigla:'CR10', nome:'Razão de Concentração — 10 maiores', cat:'Mercado',
    oque:'Fatia das vagas detida pelas 10 maiores instituições da UF.',
    escala:'0 a 100%', dir:'menor', fonte:'Censo INEP' },
];

const ORDEM_CATEGORIAS = ['Território', 'Qualidade', 'Capacidade', 'Acesso & equidade', 'Mercado'];

const DIR_ROTULO = {
  maior: '▲ Maior é melhor',
  menor: '▼ Menor é melhor',
  contextual: '◆ Leitura contextual',
};

function renderGlossario() {
  const raiz = document.getElementById('glossario-lista');
  if (!raiz) return;
  let html = '';
  ORDEM_CATEGORIAS.forEach(cat => {
    const itens = GLOSSARIO.filter(g => g.cat === cat);
    if (!itens.length) return;
    html += `<div class="glossario-cat"><div class="glossario-cat-titulo">${cat}</div><div class="glossario-cards">`;
    itens.forEach(g => {
      // <button> em vez de div[tabindex]: o verbete abre e fecha, então precisa
      // do papel e do estado que o leitor de tela já sabe anunciar.
      html += `<button type="button" class="gloss-card" id="gloss-${g.key}" aria-expanded="false">
        <span class="gloss-head">
          <span class="gloss-sigla">${g.sigla}</span>
          <span class="gloss-nome">${g.nome}</span>
          <span class="gloss-toggle" aria-hidden="true">+</span>
        </span>
        <span class="gloss-body">
          <span class="gloss-oque">${g.oque}</span>
          <span class="gloss-meta">
            <span>${g.escala}</span>
            <span>${DIR_ROTULO[g.dir] || ''}</span>
            <span>${g.fonte}</span>
          </span>
        </span>
      </button>`;
    });
    html += '</div></div>';
  });
  raiz.innerHTML = html;

  // Delegação em vez de onclick no markup — sem isso a CSP precisaria liberar
  // 'unsafe-inline' em script-src, que é justamente o que queremos evitar.
  raiz.addEventListener('click', function (e) {
    const card = e.target.closest('.gloss-card');
    if (!card) return;
    const aberto = card.getAttribute('aria-expanded') === 'true';
    card.setAttribute('aria-expanded', aberto ? 'false' : 'true');
    card.classList.toggle('aberto', !aberto);
  });
}

function filtrarGlossario(termo) {
  const t = (termo || '').trim().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  let visiveisTotal = 0;
  document.querySelectorAll('.gloss-card').forEach(card => {
    const texto = card.textContent.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const bate = !t || texto.includes(t);
    card.hidden = !bate;
    if (bate) visiveisTotal++;
  });
  document.querySelectorAll('.glossario-cat').forEach(bloco => {
    bloco.hidden = ![...bloco.querySelectorAll('.gloss-card')].some(c => !c.hidden);
  });
  const aviso = document.getElementById('glossario-resultado');
  if (aviso) {
    aviso.textContent = visiveisTotal === 1
      ? '1 indicador encontrado'
      : visiveisTotal + ' indicadores encontrados';
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const filtro = document.getElementById('glossario-filtro');
  if (filtro) {
    filtro.addEventListener('input', function () { filtrarGlossario(this.value); });
  }
});

document.addEventListener('DOMContentLoaded', renderGlossario);
