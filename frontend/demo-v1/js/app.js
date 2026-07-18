import { loadInitialConfig, saveRuntimeConfig, resetRuntimeConfig, configToFormObject, formObjectToConfig } from './config.js';
import { state, loadState, saveState, clearAllData, clearWorksData, addAuthor, removeAuthor, addLog } from './store.js';
import { testConnection, searchAuthors, fetchWorksForAuthor, enrichSources, hydrateMissingProceedingsMetrics, identifyCoauthorNationalities } from './openalex-api.js';
import { CATEGORY_META, consolidateWorks, computeMetrics, buildCollaborationGraph, summarizeTopics, getTopicForLevel } from './metrics.js';
import { renderBarChart, renderLineChart, renderHistogram, renderDonutChart, renderGroupedBarChart, renderWorldHeatmap } from './charts.js';
import { renderCollaborationGraph } from './graph.js';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
let selectedAuthorIds = new Set();

const COUNTRY_NAMES = {
  BR: 'Brasil', US: 'Estados Unidos', CA: 'Canadá', MX: 'México', AR: 'Argentina', CL: 'Chile', CO: 'Colômbia', PE: 'Peru', UY: 'Uruguai',
  GB: 'Reino Unido', UK: 'Reino Unido', IE: 'Irlanda', PT: 'Portugal', ES: 'Espanha', FR: 'França', DE: 'Alemanha', NL: 'Países Baixos', BE: 'Bélgica', CH: 'Suíça', IT: 'Itália', AT: 'Áustria', SE: 'Suécia', NO: 'Noruega', DK: 'Dinamarca', FI: 'Finlândia', PL: 'Polônia', CZ: 'Tchéquia', HU: 'Hungria', GR: 'Grécia', TR: 'Turquia', RU: 'Rússia', UA: 'Ucrânia',
  CN: 'China', JP: 'Japão', KR: 'Coreia do Sul', IN: 'Índia', SG: 'Singapura', MY: 'Malásia', TH: 'Tailândia', ID: 'Indonésia', PH: 'Filipinas', VN: 'Vietnã', TW: 'Taiwan', HK: 'Hong Kong',
  AU: 'Austrália', NZ: 'Nova Zelândia', ZA: 'África do Sul', EG: 'Egito', MA: 'Marrocos', NG: 'Nigéria', KE: 'Quênia', IL: 'Israel', SA: 'Arábia Saudita', AE: 'Emirados Árabes Unidos'
};

function html(text) {
  return String(text ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function fmt(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 's/d';
  return Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });
}

function pct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 's/d';
  return `${(Number(value) * 100).toLocaleString('pt-BR', { maximumFractionDigits: digits })}%`;
}

function setText(selector, text) {
  const el = $(selector);
  if (el) el.textContent = text;
}

function showTab(name) {
  $$('.nav-tab').forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === name));
  $$('.tab-panel').forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${name}`));
  if (name === 'network') renderNetwork();
  if (name === 'topics') renderTopicsPanel();
  if (name === 'international') renderInternational();
}

function setApiStatus(kind, title, text) {
  const dot = $('#api-status-dot');
  dot.className = `status-dot ${kind || ''}`;
  setText('#api-status-title', title);
  setText('#api-status-text', text);
}

function updateBrand() {
  $('#system-logo').src = state.config.logoUrl;
  const displayName = String(state.config.systemName || 'Science Metrics').replace(/^WebSensors\s+/i, '');
  $('#system-name').textContent = displayName || 'Science Metrics';
  document.title = state.config.systemName || 'Science Metrics';
}

function fillConfigForm() {
  const data = configToFormObject(state.config);
  const form = $('#config-form');
  for (const [key, value] of Object.entries(data)) {
    const input = form.elements[key];
    if (input) input.value = value ?? '';
  }
}

function readForm(form) {
  const data = {};
  for (const el of Array.from(form.elements)) if (el.name) data[el.name] = el.value;
  return data;
}

function bindEvents() {
  $$('.nav-tab').forEach((btn) => btn.addEventListener('click', () => showTab(btn.dataset.tab)));
  $('#config-form').addEventListener('submit', (event) => {
    event.preventDefault();
    state.config = saveRuntimeConfig(formObjectToConfig(readForm(event.currentTarget), state.config));
    updateBrand();
    fillConfigForm();
    addLog('Configuração da sessão atualizada.');
    renderAll();
    setApiStatus('ok', 'Configuração salva', 'Parâmetros ativos nesta sessão.');
  });
  $('#btn-reset-config').addEventListener('click', () => {
    state.config = resetRuntimeConfig();
    updateBrand();
    fillConfigForm();
    addLog('Configuração restaurada para o padrão.');
    renderAll();
  });
  $('#btn-test-api').addEventListener('click', onTestApi);
  $('#btn-search-authors').addEventListener('click', onSearchAuthors);
  $('#author-query').addEventListener('keydown', (event) => { if (event.key === 'Enter') onSearchAuthors(); });
  $('#btn-merge-authors').addEventListener('click', openMergeDialog);
  $('#btn-clear-group').addEventListener('click', () => {
    clearAllData();
    selectedAuthorIds.clear();
    addLog('Grupo e dados da sessão foram limpos.');
    renderAll();
  });
  $('#btn-load-works').addEventListener('click', onLoadWorks);
  $('#btn-refresh-sources').addEventListener('click', onRefreshSources);
  ['#works-filter-text', '#works-filter-category', '#works-filter-type', '#works-filter-source-type', '#works-filter-oa', '#works-sort'].forEach((sel) => {
    $(sel).addEventListener(sel.includes('text') ? 'input' : 'change', renderWorksTable);
  });
  ['#dashboard-filter-type', '#dashboard-filter-topic', '#dashboard-filter-oa'].forEach((sel) => $(sel).addEventListener('change', renderDashboard));
  ['#topic-level-filter', '#topic-type-filter', '#topic-oa-filter'].forEach((sel) => $(sel).addEventListener('change', renderTopicsPanel));
  $('#topic-text-filter').addEventListener('input', renderTopicsPanel);
  $('#institution-filter').addEventListener('change', renderInstitutionTable);
  $('#btn-export-json').addEventListener('click', exportJSON);
  $('#btn-export-csv').addEventListener('click', exportCSV);
  $('#btn-export-csv-top').addEventListener('click', exportCSV);
  $('#btn-redraw-network').addEventListener('click', renderNetwork);
  $('#modal-close').addEventListener('click', () => $('#details-modal').close());
}

async function onTestApi() {
  try {
    setApiStatus('', 'Testando API', 'Enviando requisição de teste...');
    const meta = await testConnection();
    setApiStatus('ok', 'API conectada', `${fmt(meta.count || 0, 0)} resultados possíveis na busca de teste.`);
    addLog('Conexão testada com sucesso.');
  } catch (error) {
    setApiStatus('error', 'Falha na API', error.message.slice(0, 95));
    addLog(`Erro no teste da API: ${error.message}`);
  }
  renderLogs();
}

async function onSearchAuthors() {
  const query = $('#author-query').value.trim();
  if (query.length < 3) {
    $('#author-search-status').textContent = 'Digite pelo menos 3 caracteres para buscar autores.';
    return;
  }
  $('#author-search-status').textContent = 'Buscando autores...';
  $('#btn-search-authors').disabled = true;
  try {
    state.authorResults = await searchAuthors(query);
    selectedAuthorIds.clear();
    $('#author-search-status').textContent = `${state.authorResults.length} autores encontrados para "${query}".`;
    addLog(`Busca de autores concluída para: ${query}`);
    renderAuthors();
  } catch (error) {
    $('#author-search-status').textContent = `Erro na busca: ${error.message}`;
    addLog(`Erro na busca de autores: ${error.message}`);
  } finally {
    $('#btn-search-authors').disabled = false;
    renderLogs();
  }
}

async function onLoadWorks() {
  if (!state.groupAuthors.length) {
    showTab('authors');
    $('#author-search-status').textContent = 'Adicione pelo menos um autor ao grupo antes de carregar publicações.';
    return;
  }
  const startYear = Number($('#start-year').value);
  const endYear = Number($('#end-year').value);
  if (!Number.isFinite(startYear) || !Number.isFinite(endYear) || startYear > endYear) {
    alert('Confira o período da análise. O ano inicial deve ser menor ou igual ao ano final.');
    return;
  }

  showTab('works');
  clearWorksData();
  showProgress(true, 'Iniciando coleta...', 2);
  $('#btn-load-works').disabled = true;
  try {
    const totalUnits = state.groupAuthors.reduce((acc, a) => acc + authorQueryIds(a).length, 0);
    let doneUnits = 0;
    for (const author of state.groupAuthors) {
      const allWorks = [];
      for (const sourceId of authorQueryIds(author)) {
        const queryAuthor = { ...author, id: sourceId, display_name: author.display_name };
        const works = await fetchWorksForAuthor(queryAuthor, startYear, endYear, ({ page, total }) => {
          const progress = ((doneUnits / Math.max(totalUnits, 1)) * 40) + Math.min(8, page * 1.5);
          showProgress(true, `${author.display_name}: perfil ${doneUnits + 1}/${totalUnits}, página ${page}, ${total} registros`, progress);
        });
        allWorks.push(...works);
        doneUnits += 1;
      }
      state.worksByAuthor[author.id] = allWorks;
    }

    state.works = consolidateWorks(
      state.worksByAuthor,
      state.groupAuthors,
      state.sourceCache,
      state.config.defaults.countryBrazil,
      state.authorCountryProfiles
    );

    const groupProfileIds = new Set(state.groupAuthors.flatMap((author) => [...(author.queryIds || []), author.id]).filter(Boolean));
    const externalCoauthorCount = new Set(state.works.flatMap((work) => (work.authors || [])
      .filter((author) => author?.id && !groupProfileIds.has(author.id))
      .map((author) => author.id))).size;
    showProgress(true, `Etapa 3: identificando nacionalidade de ${externalCoauthorCount} coautores externos pelas produções recentes...`, 50);
    await identifyCoauthorNationalities(
      state.works,
      state.groupAuthors,
      state.config.defaults.countryBrazil,
      ({ loaded, total, author }) => {
        const progress = 50 + (total ? (loaded / total) * 22 : 22);
        const who = author?.name ? ` · ${author.name}` : '';
        showProgress(true, `Etapa 3: nacionalidade dos coautores ${loaded}/${total}${who}`, progress);
      }
    );
    state.works = consolidateWorks(
      state.worksByAuthor,
      state.groupAuthors,
      state.sourceCache,
      state.config.defaults.countryBrazil,
      state.authorCountryProfiles
    );

    const missingProceedingsFwci = state.works.filter((w) => w.fwci === null && /proceedings|conference/i.test(String(w.rawType || w.type || ''))).length;
    if (missingProceedingsFwci > 0) {
      showProgress(true, `${state.works.length} publicações únicas. Verificando FWCI de conferências...`, 73);
      await hydrateMissingProceedingsMetrics(state.worksByAuthor, state.works, ({ loaded, total }) => {
        const progress = 73 + (total ? (loaded / total) * 5 : 5);
        showProgress(true, `Verificando métricas completas de conferências: ${loaded}/${total}`, progress);
      });
      state.works = consolidateWorks(state.worksByAuthor, state.groupAuthors, state.sourceCache, state.config.defaults.countryBrazil, state.authorCountryProfiles);
    }

    showProgress(true, `${state.works.length} publicações únicas. Enriquecendo veículos...`, 79);
    if (state.config.openAlex.maxSourcesToEnrich > 0) {
      await enrichSources(state.works, ({ loaded, total }) => {
        const progress = 79 + (total ? (loaded / total) * 18 : 18);
        showProgress(true, `Veículos enriquecidos: ${loaded}/${total}`, progress);
      });
    }

    state.works = consolidateWorks(state.worksByAuthor, state.groupAuthors, state.sourceCache, state.config.defaults.countryBrazil, state.authorCountryProfiles);
    state.metrics = computeMetrics(state.works);
    saveState();
    addLog(`Coleta concluída: ${state.works.length} publicações únicas consolidadas.`);
    showProgress(true, 'Concluído.', 100);
    populateDynamicFilters();
    renderAll();
    showTab('international');
  } catch (error) {
    addLog(`Erro ao carregar publicações: ${error.message}`);
    alert(`Erro ao carregar publicações: ${error.message}`);
  } finally {
    $('#btn-load-works').disabled = false;
    setTimeout(() => showProgress(false), 800);
    renderLogs();
  }
}

async function onRefreshSources() {
  if (!state.works.length) return;
  if (!Object.keys(state.worksByAuthor || {}).length) {
    alert('Para atualizar o impacto dos veículos depois de recarregar a página, carregue novamente as publicações do grupo.');
    return;
  }
  showProgress(true, 'Atualizando impacto dos veículos...', 8);
  try {
    await enrichSources(state.works, ({ loaded, total }) => showProgress(true, `Veículos atualizados: ${loaded}/${total}`, 8 + (loaded / Math.max(total, 1)) * 88));
    state.works = consolidateWorks(state.worksByAuthor, state.groupAuthors, state.sourceCache, state.config.defaults.countryBrazil, state.authorCountryProfiles);
    state.metrics = computeMetrics(state.works);
    saveState();
    addLog('Impacto dos veículos atualizado.');
    renderAll();
  } catch (error) {
    addLog(`Erro ao atualizar veículos: ${error.message}`);
    alert(`Erro ao atualizar veículos: ${error.message}`);
  } finally {
    setTimeout(() => showProgress(false), 800);
  }
}

function showProgress(visible, text = '', percent = 0) {
  const panel = $('#load-progress');
  panel.classList.toggle('hidden', !visible);
  $('#progress-text').textContent = text;
  $('#progress-bar-fill').style.width = `${Math.max(0, Math.min(100, percent))}%`;
}

function renderAll() {
  populateDynamicFilters();
  renderAuthors();
  renderWorksSummary();
  renderWorksTable();
  renderDashboard();
  renderInternational();
  renderTopicsPanel();
  renderDataSummary();
  renderLogs();
}

function renderAuthors() {
  $('#author-results-count').textContent = `${state.authorResults.length} autores`;
  $('#group-count').textContent = `${state.groupAuthors.length} autores`;
  $('#btn-merge-authors').disabled = selectedAuthorIds.size < 2;

  const results = $('#author-results');
  if (!state.authorResults.length) {
    results.className = 'list empty-state';
    results.textContent = 'Busque autores para adicioná-los ao grupo.';
  } else {
    results.className = 'list';
    results.innerHTML = state.authorResults.map((a) => authorCard(a, 'add')).join('');
  }

  const group = $('#group-list');
  if (!state.groupAuthors.length) {
    group.className = 'list empty-state';
    group.textContent = 'Nenhum autor adicionado ainda.';
  } else {
    group.className = 'list';
    group.innerHTML = state.groupAuthors.map((a) => authorCard(a, 'remove')).join('');
  }

  $$('#author-results [data-select-author]').forEach((box) => {
    box.checked = selectedAuthorIds.has(box.dataset.selectAuthor);
    box.addEventListener('change', () => {
      if (box.checked) selectedAuthorIds.add(box.dataset.selectAuthor);
      else selectedAuthorIds.delete(box.dataset.selectAuthor);
      $('#btn-merge-authors').disabled = selectedAuthorIds.size < 2;
    });
  });
  $$('#author-results [data-add-author]').forEach((btn) => btn.addEventListener('click', () => {
    const author = state.authorResults.find((a) => a.id === btn.dataset.addAuthor);
    if (addAuthor(author)) {
      addLog(`Autor adicionado ao grupo: ${author.display_name}`);
      renderAll();
    }
  }));
  $$('#group-list [data-remove-author]').forEach((btn) => btn.addEventListener('click', () => {
    const author = state.groupAuthors.find((a) => a.id === btn.dataset.removeAuthor);
    removeAuthor(btn.dataset.removeAuthor);
    addLog(`Autor removido do grupo: ${author?.display_name || btn.dataset.removeAuthor}`);
    renderAll();
  }));
  $$('#author-results [data-author-details], #group-list [data-author-details]').forEach((btn) => btn.addEventListener('click', () => {
    const author = [...state.authorResults, ...state.groupAuthors].find((a) => a.id === btn.dataset.authorDetails);
    showAuthorDetails(author);
  }));
}

function authorCard(author, mode) {
  const inGroup = state.groupAuthors.some((a) => a.id === author.id || authorQueryIds(a).includes(author.id));
  const mergeBadge = author.merged ? `<span class="badge merged">Merge de ${author.queryIds.length} perfis</span>` : '';
  const selector = mode === 'add' ? `<label class="select-line"><input type="checkbox" data-select-author="${html(author.id)}" /> selecionar para merge</label>` : '';
  const action = mode === 'add'
    ? `<button class="btn btn-primary" data-add-author="${html(author.id)}" ${inGroup ? 'disabled' : ''}>${inGroup ? 'Já no grupo' : 'Adicionar ao grupo'}</button>`
    : `<button class="btn btn-danger" data-remove-author="${html(author.id)}">Remover</button>`;
  const aliasText = author.merged ? `<p class="rank-meta">Perfis integrados: ${html(author.queryIds.map(shortId).join(', '))}</p>` : '';
  return `
    <article class="item-card">
      <div class="item-topline">${selector}${mergeBadge}</div>
      <h4>${html(author.display_name)}</h4>
      <p>${html(author.institution_name)} ${author.institution_country ? `(${flag(author.institution_country)} ${html(author.institution_country)})` : ''}</p>
      <p>${fmt(author.works_count, 0)} trabalhos · ${fmt(author.cited_by_count, 0)} citações · h-index ${fmt(author.h_index, 0)}</p>
      ${aliasText}
      <div class="item-actions">${action}<button class="btn btn-ghost" data-author-details="${html(author.id)}">Detalhes</button></div>
    </article>`;
}

function openMergeDialog() {
  const authors = state.authorResults.filter((a) => selectedAuthorIds.has(a.id));
  if (authors.length < 2) return;
  const institutions = uniqueBy(authors.flatMap((a) => a.institutions || []), (i) => i.id || `${i.display_name}-${i.country_code}`);
  const defaultName = longestName(authors.map((a) => a.display_name));
  $('#modal-title').textContent = 'Mesclar entradas do mesmo autor';
  $('#modal-body').innerHTML = `
    <p>Confirme o nome que será usado no grupo e escolha a instituição principal para representar o perfil mesclado.</p>
    <form id="merge-form" class="merge-form">
      <label>Nome consolidado <input name="mergedName" type="text" value="${html(defaultName)}" /></label>
      <fieldset>
        <legend>Instituição principal</legend>
        ${institutions.map((inst, i) => `<label class="radio-card"><input type="radio" name="institution" value="${html(inst.id)}" ${i === 0 ? 'checked' : ''} /> ${flag(inst.country_code)} ${html(inst.display_name)} ${inst.country_code ? `(${html(inst.country_code)})` : ''}</label>`).join('') || '<p>Nenhuma instituição foi identificada. O sistema usará “Instituição não identificada”.</p>'}
      </fieldset>
      <div class="merge-list">
        ${authors.map((a) => `<div>${html(a.display_name)} · ${html(a.institution_name)} · ${fmt(a.works_count, 0)} trabalhos</div>`).join('')}
      </div>
      <div class="form-actions"><button type="submit" class="btn btn-primary">Adicionar autor mesclado ao grupo</button></div>
    </form>`;
  $('#details-modal').showModal();
  $('#merge-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const instId = form.get('institution');
    const inst = institutions.find((i) => i.id === instId) || {};
    const merged = {
      id: `merge:${authors.map((a) => shortId(a.id)).join('+')}`,
      shortId: `merge:${authors.length}`,
      queryIds: unique(authors.flatMap((a) => authorQueryIds(a))),
      display_name: String(form.get('mergedName') || defaultName).trim() || defaultName,
      orcid: authors.find((a) => a.orcid)?.orcid || '',
      works_count: authors.reduce((acc, a) => acc + (Number(a.works_count) || 0), 0),
      cited_by_count: authors.reduce((acc, a) => acc + (Number(a.cited_by_count) || 0), 0),
      h_index: Math.max(...authors.map((a) => Number(a.h_index) || 0)),
      i10_index: Math.max(...authors.map((a) => Number(a.i10_index) || 0)),
      institution_name: inst.display_name || 'Instituição não identificada',
      institution_country: inst.country_code || '',
      institutions,
      merged: true,
      mergedAuthors: authors
    };
    addAuthor(merged);
    selectedAuthorIds.clear();
    addLog(`Autor mesclado adicionado ao grupo: ${merged.display_name}`);
    $('#details-modal').close();
    renderAll();
  }, { once: true });
}

function renderWorksSummary() {
  const el = $('#works-summary');
  if (!state.works.length) { el.innerHTML = ''; return; }
  const rows = filteredWorks();
  const m = computeMetrics(rows);
  el.innerHTML = [
    kpi('Publicações', fmt(m.total, 0), 'Após filtros e deduplicação'),
    kpi('Citações', fmt(m.citations, 0), 'Soma das citações'),
    kpi('FWCI médio', fmt(m.avgFwci, 2), 'Impacto normalizado'),
    kpi('Impacto médio do veículo', fmt(m.avgSourceImpact, 2), '2-year mean citedness'),
    kpi('h-index médio dos veículos', fmt(m.avgSourceHIndex, 1), 'Veículos com métrica disponível'),
    kpi('Acesso aberto', pct(m.openAccessShare, 1), 'Percentual após os filtros'),
    kpi('Tipos', fmt(m.topTypes.length, 0), 'Tipos de publicação')
  ].join('');
}

function renderWorksTable() {
  renderWorksSummary();
  const wrap = $('#works-table');
  if (!state.works.length) {
    wrap.className = 'table-wrap empty-state';
    wrap.textContent = 'Carregue publicações para visualizar a tabela.';
    return;
  }
  wrap.className = 'table-wrap';
  const rows = filteredWorks().slice(0, 500);
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Ano</th><th>Título</th><th>Veículo</th><th>Tipo</th><th>Acesso</th><th>Internacionalização</th><th>FWCI</th><th>Citações</th><th>Impacto veículo</th><th>h-index veículo</th><th>Ação</th></tr></thead>
      <tbody>
      ${rows.map((w) => `
        <tr>
          <td>${html(w.year || 's/d')}</td>
          <td>${workTitleLink(w, 'strong')}<br><span class="rank-meta">${topicPath(w)}</span></td>
          <td>${html(w.sourceName)}<br><span class="rank-meta">${html(w.sourceType)}</span></td>
          <td>${html(w.type)}</td>
          <td>${oaBadge(w)}</td>
          <td>${categoryBadge(w.internationalCategory)}</td>
          <td>${fmt(w.fwci, 2)}</td>
          <td>${fmt(w.citedByCount, 0)}</td>
          <td>${fmt(w.sourceImpact, 2)}</td>
          <td>${fmt(w.sourceHIndex, 0)}</td>
          <td><button class="btn btn-ghost" data-work-details="${html(w.id)}">Ver</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  $$('[data-work-details]', wrap).forEach((btn) => btn.addEventListener('click', () => showWorkDetails(state.works.find((w) => w.id === btn.dataset.workDetails))));
}

function filteredWorks() {
  const text = $('#works-filter-text')?.value?.trim().toLowerCase() || '';
  const category = $('#works-filter-category')?.value || 'all';
  const type = $('#works-filter-type')?.value || 'all';
  const sourceType = $('#works-filter-source-type')?.value || 'all';
  const oa = $('#works-filter-oa')?.value || 'all';
  const sort = $('#works-sort')?.value || 'year_desc';
  let rows = [...state.works];
  if (text) rows = rows.filter((w) => `${w.title} ${w.sourceName} ${w.authors.map((a) => a.name).join(' ')} ${topicPath(w)}`.toLowerCase().includes(text));
  if (category !== 'all') rows = rows.filter((w) => w.internationalCategory === category);
  if (type !== 'all') rows = rows.filter((w) => w.type === type);
  if (sourceType !== 'all') rows = rows.filter((w) => w.sourceType === sourceType);
  if (oa === 'open') rows = rows.filter((w) => w.isOpenAccess === true);
  if (oa === 'closed') rows = rows.filter((w) => w.isOpenAccess !== true);
  rows.sort((a, b) => {
    if (sort === 'fwci_desc') return (b.fwci ?? -1) - (a.fwci ?? -1);
    if (sort === 'citations_desc') return (b.citedByCount ?? -1) - (a.citedByCount ?? -1);
    if (sort === 'source_impact_desc') return (b.sourceImpact ?? -1) - (a.sourceImpact ?? -1);
    return (b.year ?? 0) - (a.year ?? 0);
  });
  return rows;
}

function dashboardWorks() {
  const type = $('#dashboard-filter-type')?.value || 'all';
  const topicId = $('#dashboard-filter-topic')?.value || 'all';
  const oa = $('#dashboard-filter-oa')?.value || 'all';
  let rows = [...state.works];
  if (type !== 'all') rows = rows.filter((w) => w.type === type);
  if (topicId !== 'all') rows = rows.filter((w) => [w.primaryTopic?.id, w.subfield?.id, w.field?.id, w.domain?.id].includes(topicId));
  if (oa === 'open') rows = rows.filter((w) => w.isOpenAccess === true);
  if (oa === 'closed') rows = rows.filter((w) => w.isOpenAccess !== true);
  return rows;
}

function renderDashboard() {
  const empty = $('#dashboard-empty');
  const content = $('#dashboard-content');
  if (!state.works.length) { empty.classList.remove('hidden'); content.classList.add('hidden'); return; }
  empty.classList.add('hidden');
  content.classList.remove('hidden');
  const rows = dashboardWorks();
  const m = computeMetrics(rows);
  $('#dashboard-kpis').innerHTML = [
    kpi('Publicações', fmt(m.total, 0), 'Total consolidado nos filtros'),
    kpi('Citações por paper', fmt(m.avgCitations, 1), 'Média simples'),
    kpi('FWCI médio', fmt(m.avgFwci, 2), '1,0 equivale à média mundial esperada'),
    kpi('h-index do conjunto', fmt(m.hIndex, 0), 'Calculado dentro da sessão'),
    kpi('Top 10%', pct(m.top10Share), 'Impacto de citação normalizado'),
    kpi('Impacto médio do veículo', fmt(m.avgSourceImpact, 2), '2-year mean citedness'),
    kpi('h-index médio dos veículos', fmt(m.avgSourceHIndex, 1), 'Média entre os veículos com métrica disponível'),
    kpi('Acesso aberto', pct(m.openAccessShare), 'Percentual de publicações em acesso aberto'),
    kpi('Veículos distintos', fmt(m.uniqueSources, 0), 'Fontes distintas'),
    kpi('Mediana FWCI', fmt(m.medianFwci, 2), 'Robusta a outliers')
  ].join('');
  renderBarChart($('#chart-pubs-year'), m.yearSeries.map((d) => ({ label: d.year, value: d.publications })));
  renderLineChart($('#chart-fwci-year'), m.yearSeries.map((d) => ({ label: d.year, value: d.avgFwci })));
  renderBarChart($('#chart-citations-year'), m.yearSeries.map((d) => ({ label: d.year, value: d.citations })));
  renderHistogram($('#chart-fwci-hist'), rows.map((w) => w.fwci));
  $('#top-sources').innerHTML = sourceMetricsTable(m.topSourceMetrics);
  $('#top-types').innerHTML = rankList(m.topTypes, 'publicações');
  $('#top-works').innerHTML = workRankList(m.topWorksByFwci, 'FWCI');
  $('#top-source-types').innerHTML = rankList(m.topSourceTypes, 'publicações');
}

function renderInternational() {
  const empty = $('#international-empty');
  const content = $('#international-content');
  if (!state.works.length) { empty.classList.remove('hidden'); content.classList.add('hidden'); return; }
  empty.classList.add('hidden');
  content.classList.remove('hidden');
  const m = state.metrics || computeMetrics(state.works);
  state.metrics = m;
  const intl = m.categories.international;
  const national = m.categories.national_only;

  $('#international-share').innerHTML = `
    <section class="hero-card national"><div class="hero-label">Apenas nacional</div><div class="hero-value">${pct(national.share, 1)}</div><div class="hero-hint">${fmt(national.total, 0)} de ${fmt(m.total, 0)} publicações sem coautor de país principal estrangeiro.</div></section>
    <section class="hero-card main"><div class="hero-label">Internacional</div><div class="hero-value">${pct(intl.share, 1)}</div><div class="hero-hint">${fmt(intl.total, 0)} de ${fmt(m.total, 0)} publicações com ao menos um coautor de país principal estrangeiro.</div></section>`;

  const catRows = [
    { label: 'Apenas nacional', value: national.total },
    { label: 'Internacional', value: intl.total }
  ];
  renderDonutChart($('#chart-international-donut'), catRows, { height: 390 });

  const years = Array.from(new Set(state.works.map((w) => w.year).filter(Boolean))).sort((a, b) => a - b);
  const yearRows = years.map((year) => ({
    label: year,
    a: state.works.filter((w) => w.year === year && w.internationalCategory === 'national_only').length,
    b: state.works.filter((w) => w.year === year && w.internationalCategory === 'international').length
  }));
  renderGroupedBarChart($('#chart-international-year'), yearRows, { height: 390, labelA: 'Apenas nacional', labelB: 'Internacional' });

  $('#international-category-cards').innerHTML = Object.entries(CATEGORY_META).map(([key, meta]) => {
    const c = m.categories[key];
    return `<section class="category-card ${key}">
      <h4>${meta.icon} ${meta.label}</h4>
      <div class="big">${pct(c.share, 1)}</div>
      <p class="rank-meta">${meta.description}</p>
      <dl>
        <div class="row"><span>Publicações</span><strong>${fmt(c.total, 0)}</strong></div>
        <div class="row"><span>FWCI médio</span><strong>${fmt(c.avgFwci, 2)}</strong></div>
        <div class="row"><span>h-index</span><strong>${fmt(c.hIndex, 0)}</strong></div>
        <div class="row"><span>Citações médias</span><strong>${fmt(c.avgCitations, 1)}</strong></div>
        <div class="row"><span>Top 10%</span><strong>${pct(c.top10Share, 1)}</strong></div>
        <div class="row"><span>Impacto veículo</span><strong>${fmt(c.avgSourceImpact, 2)}</strong></div>
        <div class="row"><span>h-index médio dos veículos</span><strong>${fmt(c.avgSourceHIndex, 1)}</strong></div>
        <div class="row"><span>Acesso aberto</span><strong>${pct(c.openAccessShare, 1)}</strong></div>
      </dl>
    </section>`;
  }).join('');

  $('#top-countries').innerHTML = countryRankList(m.topCountries, 'publicações');
  try {
    renderWorldHeatmap($('#chart-country-map'), m.allCountries || m.topCountries, { height: 430 });
  } catch (error) {
    console.error('Falha ao renderizar mapa de internacionalização:', error);
    $('#chart-country-map').innerHTML = '<div class="empty-state">Não foi possível renderizar o mapa, mas a lista de países permanece disponível.</div>';
  }
  renderInstitutionTable();
  renderInternationalTable();
}

function renderInstitutionTable() {
  const wrap = $('#top-institutions');
  if (!state.works.length) { wrap.innerHTML = ''; return; }
  const m = state.metrics || computeMetrics(state.works);
  const scope = $('#institution-filter input[name="institutionScope"]:checked')?.value || 'all';
  let rows = m.topInstitutions || [];
  if (scope === 'national') rows = rows.filter((r) => r.scope === 'national');
  if (scope === 'international') rows = rows.filter((r) => r.scope === 'international');
  if (!rows.length) { wrap.className = 'table-wrap empty-state'; wrap.textContent = 'Sem instituições para o filtro selecionado.'; return; }
  wrap.className = 'table-wrap';
  wrap.innerHTML = `<table class="data-table compact-table">
    <thead><tr><th>País</th><th>Instituição</th><th>Escopo</th><th>Publicações</th></tr></thead>
    <tbody>${rows.slice(0, 40).map((r) => `<tr><td>${flag(r.country)} ${html(r.country || 's/pais')}</td><td>${html(r.label)}</td><td>${r.scope === 'national' ? 'Nacional' : 'Internacional'}</td><td><strong>${fmt(r.value, 0)}</strong></td></tr>`).join('')}</tbody>
  </table>`;
}

function renderInternationalTable() {
  const rows = state.works.filter((w) => w.internationalCategory === 'international').sort((a, b) => (b.fwci ?? 0) - (a.fwci ?? 0)).slice(0, 100);
  const wrap = $('#international-table');
  if (!rows.length) { wrap.className = 'table-wrap empty-state'; wrap.textContent = 'Nenhuma publicação internacional foi identificada no período.'; return; }
  wrap.className = 'table-wrap';
  wrap.innerHTML = `<table class="data-table">
    <thead><tr><th>Ano</th><th>Título</th><th>Países principais dos autores</th><th>Instituições BR</th><th>Instituições estrangeiras</th><th>FWCI</th><th>Citações</th><th>Ação</th></tr></thead>
    <tbody>${rows.map((w) => `<tr>
      <td>${html(w.year || 's/d')}</td>
      <td>${workTitleLink(w, 'strong')}<br><span class="rank-meta">${html(w.sourceName)}</span></td>
      <td>${w.countries.map((c) => `${flag(c)} ${html(c)}`).join(', ')}</td>
      <td>${fmt(w.brazilInstitutionCount, 0)}</td>
      <td>${fmt(w.foreignInstitutionCount, 0)}</td>
      <td>${fmt(w.fwci, 2)}</td>
      <td>${fmt(w.citedByCount, 0)}</td>
      <td><button class="btn btn-ghost" data-work-details="${html(w.id)}">Ver</button></td>
    </tr>`).join('')}</tbody>
  </table>`;
  $$('[data-work-details]', wrap).forEach((btn) => btn.addEventListener('click', () => showWorkDetails(state.works.find((w) => w.id === btn.dataset.workDetails))));
}

function renderTopicsPanel() {
  const empty = $('#topics-empty');
  const content = $('#topics-content');
  if (!state.works.length) { empty.classList.remove('hidden'); content.classList.add('hidden'); return; }
  empty.classList.add('hidden');
  content.classList.remove('hidden');
  const level = $('#topic-level-filter')?.value || 'topic';
  const type = $('#topic-type-filter')?.value || 'all';
  const oa = $('#topic-oa-filter')?.value || 'all';
  const text = $('#topic-text-filter')?.value?.trim().toLowerCase() || '';
  let rows = [...state.works];
  if (type !== 'all') rows = rows.filter((w) => w.type === type);
  if (oa === 'open') rows = rows.filter((w) => w.isOpenAccess === true);
  if (oa === 'closed') rows = rows.filter((w) => w.isOpenAccess !== true);
  let topics = summarizeTopics(rows, level);
  if (text) topics = topics.filter((t) => t.label.toLowerCase().includes(text));
  const top = topics.slice(0, 14);
  const totalWorks = rows.length;
  $('#topic-kpis').innerHTML = [
    kpi('Publicações analisadas', fmt(totalWorks, 0), 'Após filtro de tipo'),
    kpi('Agrupamentos', fmt(topics.length, 0), labelForLevel(level)),
    kpi('FWCI médio geral', fmt(computeMetrics(rows).avgFwci, 2), 'Nos filtros atuais'),
    kpi('h-index geral', fmt(computeMetrics(rows).hIndex, 0), 'Nos filtros atuais'),
    kpi('Acesso aberto', pct(computeMetrics(rows).openAccessShare, 1), 'Nos filtros atuais')
  ].join('');
  renderBarChart($('#chart-topic-pubs'), top.map((t) => ({ label: truncate(t.label, 16), value: t.total })), { height: 420, rotateLabels: true });
  renderBarChart($('#chart-topic-fwci'), top.map((t) => ({ label: truncate(t.label, 16), value: t.avgFwci || 0 })), { height: 420, rotateLabels: true });
  $('#topics-table').innerHTML = topicTable(topics.slice(0, 100));
}

function topicTable(rows) {
  if (!rows.length) return '<div class="empty-state">Sem tópicos para os filtros selecionados.</div>';
  return `<table class="data-table">
    <thead><tr><th>Tópico/área</th><th>Publicações</th><th>%</th><th>FWCI médio</th><th>h-index</th><th>h-index veículo</th><th>Acesso aberto</th><th>Citações médias</th><th>Top 10%</th><th>Tipos mais comuns</th></tr></thead>
    <tbody>${rows.map((r) => `<tr>
      <td><strong>${html(r.label)}</strong></td>
      <td>${fmt(r.total, 0)}</td>
      <td>${pct(r.total / Math.max(state.works.length, 1), 1)}</td>
      <td>${fmt(r.avgFwci, 2)}</td>
      <td>${fmt(r.hIndex, 0)}</td>
      <td>${fmt(r.avgSourceHIndex, 1)}</td>
      <td>${pct(r.openAccessShare, 1)}</td>
      <td>${fmt(r.avgCitations, 1)}</td>
      <td>${pct(r.top10Share, 1)}</td>
      <td>${html(r.typeBreakdown.map((x) => `${x.label} (${x.value})`).join(', '))}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

function renderNetwork() {
  const empty = $('#network-empty');
  const content = $('#network-content');
  if (!state.works.length) { empty.classList.remove('hidden'); content.classList.add('hidden'); return; }
  empty.classList.add('hidden');
  content.classList.remove('hidden');
  const graph = buildCollaborationGraph(state.works, state.groupAuthors, state.config.openAlex.maxExternalCoauthors);
  renderCollaborationGraph($('#network-chart'), $('#network-details'), graph);
}

function renderDataSummary() {
  $('#data-session-summary').innerHTML = [
    kv('Autores no grupo', fmt(state.groupAuthors.length, 0)),
    kv('Publicações únicas', fmt(state.works.length, 0)),
    kv('Veículos em cache', fmt(Object.keys(state.sourceCache).length, 0)),
    kv('Endpoint', state.config.openAlex.baseUrl),
    kv('API key', state.config.openAlex.apiKey ? 'preenchida' : 'não preenchida'),
    kv('Persistência', 'sessionStorage do navegador')
  ].join('');
}

function renderLogs() {
  $('#app-log').innerHTML = state.logs.map((l) => `<div>${html(l)}</div>`).join('') || '<div>Nenhum log nesta sessão.</div>';
}

function populateDynamicFilters() {
  if (!state.works.length) return;
  const types = unique(state.works.map((w) => w.type).filter(Boolean)).sort();
  const sourceTypes = unique(state.works.map((w) => w.sourceType).filter(Boolean)).sort();
  fillSelect('#works-filter-type', types, 'Todos');
  fillSelect('#works-filter-source-type', sourceTypes, 'Todos');
  fillSelect('#dashboard-filter-type', types, 'Todos');
  fillSelect('#topic-type-filter', types, 'Todos');
  const topicOptions = uniqueTopicOptions(state.works);
  fillSelect('#dashboard-filter-topic', topicOptions, 'Todos', true);
}

function fillSelect(selector, values, allLabel, valuesAreObjects = false) {
  const select = $(selector);
  if (!select) return;
  const current = select.value || 'all';
  select.innerHTML = `<option value="all">${html(allLabel)}</option>` + values.map((v) => {
    const value = valuesAreObjects ? v.id : v;
    const label = valuesAreObjects ? v.label : v;
    return `<option value="${html(value)}">${html(label)}</option>`;
  }).join('');
  select.value = Array.from(select.options).some((o) => o.value === current) ? current : 'all';
}

function uniqueTopicOptions(works) {
  const map = new Map();
  for (const w of works) {
    for (const node of [w.domain, w.field, w.subfield, w.primaryTopic]) {
      if (node?.id && !map.has(node.id)) map.set(node.id, { id: node.id, label: `${levelName(node.level)}: ${node.name}` });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label)).slice(0, 400);
}

function kpi(label, value, hint = '') {
  return `<section class="kpi-card"><div class="label">${html(label)}</div><div class="value">${html(value)}</div><div class="hint">${html(hint)}</div></section>`;
}

function kv(label, value) {
  return `<div class="kv-row"><span>${html(label)}</span><strong>${html(value)}</strong></div>`;
}

function categoryBadge(key) {
  const meta = CATEGORY_META[key] || CATEGORY_META.national_only;
  return `<span class="badge ${html(key)}">${meta.icon} ${html(meta.label)}</span>`;
}

function oaBadge(work) {
  return work?.isOpenAccess === true
    ? '<span class="badge open-access">🔓 Aberto</span>'
    : '<span class="badge closed-access">🔒 Fechado</span>';
}

function rankList(rows, unit) {
  if (!rows?.length) return '<div class="empty-state">Sem dados.</div>';
  return rows.map((r, i) => `<div class="rank-item"><div class="rank-number">${i + 1}</div><div><div class="rank-title">${html(r.label)}</div><div class="rank-meta">${html(unit)}</div></div><div class="rank-value">${fmt(r.value, 0)}</div></div>`).join('');
}

function sourceMetricsTable(rows) {
  if (!rows?.length) return '<div class="empty-state">Sem dados de veículos.</div>';
  return `<table class="data-table compact-table">
    <thead><tr><th>Veículo</th><th>Tipo</th><th>Publicações</th><th>Impacto</th><th>h-index</th></tr></thead>
    <tbody>${rows.slice(0, 15).map((r) => `<tr>
      <td><strong>${html(r.label)}</strong></td>
      <td>${html(r.sourceType)}</td>
      <td>${fmt(r.works, 0)}</td>
      <td>${fmt(r.sourceImpact, 2)}</td>
      <td>${fmt(r.sourceHIndex, 0)}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

function countryRankList(rows, unit) {
  if (!rows?.length) return '<div class="empty-state">Sem dados.</div>';
  return rows.map((r, i) => `<div class="rank-item"><div class="rank-number">${i + 1}</div><div><div class="rank-title">${flag(r.label)} ${html(countryLabel(r.label))}</div><div class="rank-meta">${html(r.label)} · ${html(unit)}</div></div><div class="rank-value">${fmt(r.value, 0)}</div></div>`).join('');
}

function workRankList(works, metricLabel) {
  if (!works?.length) return '<div class="empty-state">Sem dados.</div>';
  return works.map((w, i) => `<div class="rank-item"><div class="rank-number">${i + 1}</div><div><div class="rank-title">${workTitleLink(w)}</div><div class="rank-meta">${html(w.year || 's/d')} · ${html(w.sourceName)}</div></div><div class="rank-value">${metricLabel === 'FWCI' ? fmt(w.fwci, 2) : fmt(w.citedByCount, 0)}</div></div>`).join('');
}

function showAuthorDetails(author) {
  if (!author) return;
  $('#modal-title').textContent = author.display_name;
  $('#modal-body').innerHTML = `
    <div class="kv-list">
      ${kv('Instituição principal', author.institution_name)}
      ${kv('País da instituição', author.institution_country || 's/d')}
      ${kv('Trabalhos', fmt(author.works_count, 0))}
      ${kv('Citações', fmt(author.cited_by_count, 0))}
      ${kv('h-index', fmt(author.h_index, 0))}
      ${kv('i10-index', fmt(author.i10_index, 0))}
      ${kv('ORCID', author.orcid || 's/d')}
      ${kv('ID bibliográfico', author.id)}
      ${author.merged ? kv('Perfis integrados', author.queryIds.map(shortId).join(', ')) : ''}
    </div>
    <p class="copy-line">${html(author.id)}</p>`;
  $('#details-modal').showModal();
}

function showWorkDetails(work) {
  if (!work) return;
  $('#modal-title').textContent = work.title;
  const countries = work.countries.length ? work.countries.map((c) => `${flag(c)} ${c}`).join(', ') : 'Não identificados';
  $('#modal-body').innerHTML = `
    <div class="kv-list">
      ${kv('Ano', work.year || 's/d')}
      ${kv('Veículo', work.sourceName)}
      ${kv('Tipo de publicação', work.type)}
      ${kv('Tipo de veículo', work.sourceType)}
      ${kv('Acesso aberto', work.isOpenAccess ? `Sim${work.openAccessStatus ? ` (${work.openAccessStatus})` : ''}` : 'Não')}
      ${kv('Internacionalização', CATEGORY_META[work.internationalCategory]?.label || 'Apenas nacional')}
      ${kv('Países principais dos autores', countries)}
      ${kv('Tópico principal', work.primaryTopic?.name || 's/d')}
      ${kv('Área', work.field?.name || 's/d')}
      ${kv('Domínio', work.domain?.name || 's/d')}
      ${kv('FWCI', fmt(work.fwci, 2))}
      ${kv('Citações', fmt(work.citedByCount, 0))}
      ${kv('Impacto do veículo', fmt(work.sourceImpact, 2))}
      ${kv('h-index do veículo', fmt(work.sourceHIndex, 0))}
      ${kv('Autores do grupo no paper', work.groupAuthorsInWork.map((a) => a.name).join(', ') || 's/d')}
    </div>
    <h4>Autores</h4>
    <p>${html(work.authors.slice(0, 40).map((a) => a.name).join('; '))}${work.authors.length > 40 ? '...' : ''}</p>
    <h4>Endereços externos</h4>
    <p>Quando houver DOI, o link abre em uma nova janela.</p>
    <div class="copy-line">Registro: ${html(work.externalUrl || 's/d')}</div>
    <div class="copy-line">DOI: ${doiUrl(work) ? `<a class="external-doi" href="${html(doiUrl(work))}" target="_blank" rel="noopener noreferrer">${html(work.doi)}</a>` : 's/d'}</div>
    <h4>Instituições identificadas</h4>
    <p>${html(work.institutions.map((i) => `${flag(i.country)} ${i.name} (${i.country || 's/pais'})`).join('; ') || 's/d')}</p>`;
  $('#details-modal').showModal();
}

function exportJSON() {
  downloadBlob(JSON.stringify({ config: state.config, groupAuthors: state.groupAuthors, works: state.works, metrics: state.metrics }, null, 2), 'websensors-science-metrics.json', 'application/json');
}

function exportCSV() {
  const rows = state.works.map((w) => ({
    ano: w.year || '', titulo: w.title, veiculo: w.sourceName, tipo_publicacao: w.type, tipo_veiculo: w.sourceType,
    acesso_aberto: w.isOpenAccess ? 'sim' : 'nao', status_acesso_aberto: w.openAccessStatus || '', internacionalizacao: w.internationalLabel, paises: w.countries.join('|'), fwci: w.fwci ?? '', citacoes: w.citedByCount ?? '', impacto_veiculo: w.sourceImpact ?? '', h_index_veiculo: w.sourceHIndex ?? '',
    topico: w.primaryTopic?.name || '', area: w.field?.name || '', dominio: w.domain?.name || '', doi: w.doi || '', registro: w.externalUrl || ''
  }));
  const headers = Object.keys(rows[0] || { ano: '', titulo: '' });
  const csv = [headers.join(';'), ...rows.map((r) => headers.map((h) => csvCell(r[h])).join(';'))].join('\n');
  downloadBlob(csv, 'websensors-science-metrics.csv', 'text/csv;charset=utf-8');
}

function csvCell(value) {
  const text = String(value ?? '').replace(/"/g, '""');
  return `"${text}"`;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function authorQueryIds(author) {
  return Array.isArray(author?.queryIds) && author.queryIds.length ? author.queryIds : [author?.id].filter(Boolean);
}


function doiUrl(work) {
  const raw = String(work?.doi || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw)) return raw;
  return `https://doi.org/${raw.replace(/^doi:/i, '')}`;
}

function workTitleLink(work, wrapper = '') {
  const title = html(work?.title || 'Título não informado');
  const url = doiUrl(work);
  const label = wrapper === 'strong' ? `<strong>${title}</strong>` : title;
  if (!url) return label;
  return `<a class="work-title-link" href="${html(url)}" target="_blank" rel="noopener noreferrer" title="Abrir DOI em nova janela">${label}</a>`;
}

function shortId(id) { return String(id || '').split('/').pop(); }
function truncate(text, n) { return String(text || '').length > n ? `${String(text).slice(0, n - 1)}…` : String(text || ''); }
function topicPath(w) { return [w.domain?.name, w.field?.name, w.primaryTopic?.name].filter(Boolean).join(' › ') || 'Sem tópico'; }
function levelName(level) { return ({ topic: 'Tópico', subfield: 'Subárea', field: 'Área', domain: 'Domínio' })[level] || 'Tema'; }
function labelForLevel(level) { return ({ topic: 'tópicos', subfield: 'subáreas', field: 'áreas', domain: 'domínios' })[level] || 'temas'; }
function countryLabel(cc) { return COUNTRY_NAMES[cc] || cc || 'Sem país'; }
function flag(cc) {
  const code = String(cc || '').toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return '🏳️';
  return [...code].map((c) => String.fromCodePoint(127397 + c.charCodeAt(0))).join('');
}
function unique(values) { return Array.from(new Set(values.filter(Boolean))); }
function uniqueBy(values, keyFn) {
  const map = new Map();
  for (const value of values) {
    const key = keyFn(value);
    if (key && !map.has(key)) map.set(key, value);
  }
  return Array.from(map.values());
}
function longestName(names) { return names.sort((a, b) => String(b).length - String(a).length)[0] || 'Autor mesclado'; }

async function init() {
  state.config = await loadInitialConfig();
  loadState();
  state.metrics = state.works.length ? computeMetrics(state.works) : null;
  $('#start-year').value = state.config.defaults.startYear;
  $('#end-year').value = state.config.defaults.endYear;
  updateBrand();
  fillConfigForm();
  bindEvents();
  renderAll();
}

init();
