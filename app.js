const DATA_URL = 'data/processed/radar-janja.json';
const GOV_URL = 'data/processed/government-context.json';
const DOSSIER_URL = 'data/processed/dossier-db.json';
const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
let payload = null;
let govPayload = null;
let dossierPayload = null;
let records = [];
let activeRanking = 'direct';

function money(value) { return BRL.format(Number(value || 0)); }
function shortMoney(value) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 1_000_000_000) return `R$ ${(n / 1_000_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} bi`;
  if (Math.abs(n) >= 1_000_000) return `R$ ${(n / 1_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`;
  if (Math.abs(n) >= 1_000) return `R$ ${(n / 1_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil`;
  return money(n);
}
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[ch])); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#096;'); }
function shortText(value, max = 130) { const s = String(value || '').trim(); return s.length > max ? `${s.slice(0, max - 1)}…` : s; }
function pct(value) { return `${Number(value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`; }

const categoryCopy = {
  gasto_direto_identificado: 'Direto identificado',
  gasto_direto_em_comitiva: 'Direto em comitiva',
  equipe_apoio_primeira_dama: 'Equipe / apoio',
  agenda_com_mencao: 'Agenda com menção',
  comitiva_presidencial_com_mencao: 'Comitiva presidencial',
  possivel_homonimo_ou_nao_confirmado: 'Possível homônimo',
  nao_confirmado: 'Não confirmado'
};
function categoryLabel(value) { return categoryCopy[value] || String(value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()); }
function confidenceClass(confidence) { if (confidence === 'alta') return 'high'; if (confidence === 'média' || confidence === 'media') return 'medium'; return 'low'; }

function animateNumber(el, end, { currency = false, compact = false } = {}) {
  if (!el) return;
  const val = Number(end || 0);
  el.textContent = compact ? shortMoney(val) : currency ? money(val) : String(Math.round(val));
}

function totals() {
  const summary = payload?.summary || {};
  const cpgf = govPayload?.cpgf_presidency?.total_2023_2026 || {};
  const travel = govPayload?.official_travel || {};
  const federalTravelTotal = Object.values(travel.by_year || {}).reduce((sum, y) => sum + Number(y.total?.total || 0), 0);
  const structure = Number(summary.structure_context?.total_structure_cost_2023_2024 || 0);
  const watchedGovernment = federalTravelTotal + Number(cpgf.total || 0) + structure;
  const secret = (govPayload?.cpgf_presidency?.top_favored || []).find(item => String(item.favored || '').toLowerCase().includes('sigiloso')) || {};
  return { summary, cpgf, travel, federalTravelTotal, structure, watchedGovernment, secret };
}

async function loadData() {
  const [res, govRes, dossierRes] = await Promise.all([
    fetch(DATA_URL, { cache: 'no-store' }),
    fetch(GOV_URL, { cache: 'no-store' }),
    fetch(DOSSIER_URL, { cache: 'no-store' })
  ]);
  if (!res.ok) throw new Error(`Falha ao carregar ${DATA_URL}: ${res.status}`);
  if (!govRes.ok) throw new Error(`Falha ao carregar ${GOV_URL}: ${govRes.status}`);
  if (!dossierRes.ok) throw new Error(`Falha ao carregar ${DOSSIER_URL}: ${dossierRes.status}`);
  payload = await res.json();
  govPayload = await govRes.json();
  dossierPayload = await dossierRes.json();
  records = payload.records || [];
  renderSummary();
  renderRecentSignals();
  renderCharts();
  renderTravelFood();
  renderLayers();
  renderInvestigationRoadmap();
  renderNewsContext();
  setupRankingToggle();
  renderTopExpenses();
  setupFilters();
  renderRecords();
  renderDraft();
  startSignalCanvas();
}

function renderSummary() {
  const { summary, cpgf, watchedGovernment, secret } = totals();
  const dbgg = govPayload?.debt?.dbgg_pct_pib || {};
  animateNumber(document.getElementById('governmentGrandTotal'), watchedGovernment, { compact: true, duration: 1300 });
  setText('governmentGrandNote', `Viagens federais + CPGF da Presidência + estrutura/equipe citada em fonte pública. É cobrança sobre dinheiro público — não acusação de gasto pessoal.`);
  setText('heroTravelTotal', shortMoney(totals().federalTravelTotal));
  setText('heroCpgfTotal', shortMoney(cpgf.total));
  setText('heroStructureTotal', shortMoney(totals().structure));
  setText('janjaDirectTotal', shortMoney(summary.direct_total));
  setText('truthDirect', shortMoney(summary.direct_total));
  setText('truthContext', shortMoney(Number(summary.support_and_mentions_total || 0) + Number(summary.structure_context?.total_structure_cost_2023_2024 || 0)));
  setText('truthGovernment', shortMoney(watchedGovernment));
  setText('structureTotal', shortMoney(summary.structure_context?.total_structure_cost_2023_2024));
  setText('cpgfPresidencyTotal', shortMoney(cpgf.total));
  setText('cpgfSecretTotal', shortMoney(secret.total));
  setText('debtTopValue', `${Number(dbgg.latest_value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`);
  setText('debtTopNote', `${dbgg.latest_date || '—'} • Banco Central. Contexto fiscal, não atribuição pessoal.`);
  setText('cpgfPresidencyNote', `${cpgf.count || 0} transações • despesa da Presidência; não é atribuição automática à Janja.`);
  setText('cpgfSecretNote', `${secret.count || 0} transações: o cidadão paga, mas a base pública não mostra quem recebeu.`);
  const years = summary.years?.length ? `${Math.min(...summary.years)}–${Math.max(...summary.years)}` : 'anos disponíveis';
  setText('statusPill', `Base oficial ${years}`);
  const generated = payload.generated_at ? new Date(payload.generated_at) : null;
  setText('lastUpdate', `Última varredura: ${generated ? generated.toLocaleString('pt-BR') : '—'}`);
}

function renderRecentSignals() {
  const box = document.getElementById('recentSignals');
  if (!box) return;
  const clean = (records || [])
    .filter(r => !['possivel_homonimo_ou_nao_confirmado', 'nao_confirmado'].includes(r.category))
    .sort((a, b) => String(b.date_start_iso || '').localeCompare(String(a.date_start_iso || '')) || Number(b.total || 0) - Number(a.total || 0));
  const direct = clean.filter(r => r.counted_in_direct_total).slice(0, 2);
  const context = clean.filter(r => !r.counted_in_direct_total).slice(0, 2);
  const recent = [...direct, ...context]
    .filter((r, idx, arr) => arr.findIndex(x => x.id === r.id) === idx)
    .slice(0, 4);
  box.innerHTML = recent.map(r => {
    const category = categoryLabel(r.category);
    const contextLabel = r.counted_in_direct_total ? 'direto Janja' : 'camada separada';
    const explanation = r.counted_in_direct_total
      ? 'Registro oficial em nome de Rosângela da Silva. É a prova mais forte do recorte — sem malabarismo.'
      : 'Menção, apoio ou comitiva: não entra como gasto pessoal direto, mas serve para apertar a blindagem.';
    const urgency = String(r.urgent || '').toUpperCase() === 'SIM' ? '<span class="urgent-chip">urgente</span>' : '';
    return `<article class="quick-log-card ${r.counted_in_direct_total ? 'direct-proof' : ''}">
      <div><strong>${money(r.total)}</strong><small>${escapeHtml(r.date_start || 'sem data')} • ${escapeHtml(r.destination || 'sem destino')}</small></div>
      <p>${escapeHtml(explanation)}</p>
      <footer><span>${escapeHtml(category)}</span><span>${escapeHtml(contextLabel)}</span>${urgency}<a href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener noreferrer">fonte oficial</a></footer>
    </article>`;
  }).join('') || '<p class="empty">Sem novos sinais relevantes nos filtros atuais.</p>';
}

function renderLayers() {
  const { summary, cpgf, secret } = totals();
  const dbgg = govPayload?.debt?.dbgg_pct_pib || {};
  const cpgfTotals = govPayload?.cpgf_presidency?.total_2023_2026 || {};
  const presidencyTravel = govPayload?.official_travel?.presidency_context_2023_2026 || {};
  const secretRatio = Number(cpgf.total) ? (Number(secret.total || 0) / Number(cpgf.total)) * 100 : 0;
  setText('directTotal', shortMoney(summary.direct_total));
  setText('structureTravel', shortMoney(summary.structure_context?.travel_cost_janja_plus_team_2023_2024));
  setText('cpgfSecretPercent', pct(secretRatio));
  setText('presidencyTravel', shortMoney(presidencyTravel.total));
  setText('cpgfFoodClue', shortMoney(cpgfTotals.food_like_total));
  setText('dbggValue', `${Number(dbgg.latest_value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`);
  setText('dbggNote', `${dbgg.latest_date || '—'} • Banco Central SGS`);
}

function renderInvestigationRoadmap() {
  const box = document.getElementById('stepLayerCards');
  const cpgfBox = document.getElementById('cpgfGranularSummary');
  const steps = dossierPayload?.investigation_roadmap || [];
  const staff = dossierPayload?.staff_structure || {};
  const cpgf = dossierPayload?.cpgf_granular || {};
  const cache = dossierPayload?.cache_status || {};
  if (box) {
    const enriched = steps.map(step => {
      if (step.step === '1') return { ...step, value: `${cache.cpgf_monthly_zips?.count || 0} meses CPGF`, small: cache.rule || step.public_copy };
      if (step.step === '2') return { ...step, value: shortMoney(staff.total_structure_cost_2023_2024), small: `${staff.known_team_size_estimate || '—'} pessoas citadas • equipe/estrutura separada do direto.` };
      if (step.step === '3') return { ...step, value: shortMoney(cpgf.total?.total), small: `${cpgf.total?.count || 0} transações • mês a mês + sigilo + pistas.` };
      return { ...step, value: step.status, small: step.public_copy };
    });
    box.innerHTML = enriched.map(step => `<article><span>${escapeHtml(step.step)}</span><b>${escapeHtml(step.title)}</b><strong>${escapeHtml(step.value)}</strong><small>${escapeHtml(step.small || step.public_copy || '')}</small></article>`).join('') || '<p class="empty">Mapa de investigação ainda não carregado.</p>';
  }
  if (cpgfBox) {
    const secret = cpgf.secret_summary || {};
    const latestMonth = Object.keys(cpgf.by_month || {}).sort().pop();
    cpgfBox.textContent = `CPGF granular: ${shortMoney(cpgf.total?.total)} em ${cpgf.total?.count || 0} transações da Presidência. Sigilo: ${shortMoney(secret.total)} (${Number(secret.ratio_of_cpgf_total_pct || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%). Último mês no cache: ${latestMonth || '—'}. Não é atribuição pessoal à Janja — é pressão contra a caixa-preta.`;
  }
}

function renderCharts() {
  renderGovYearChart();
  renderJanjaMonthChart();
  renderDebtChart();
}
function renderBarChart(id, rows, { moneyMode = true, valueFormatter = null } = {}) {
  const box = document.getElementById(id);
  if (!box) return;
  const max = Math.max(...rows.map(r => Number(r.value || 0)), 1);
  box.innerHTML = rows.map(row => {
    const width = Math.max(3, (Number(row.value || 0) / max) * 100);
    const formatted = valueFormatter ? valueFormatter(row) : moneyMode ? shortMoney(row.value) : escapeHtml(row.value);
    return `<div class="bar-row"><span>${escapeHtml(row.label)}</span><div class="bar-track"><i style="width:${width}%"></i></div><b>${formatted}</b></div>`;
  }).join('') || '<p class="empty">Sem dados para gráfico.</p>';
}
function renderGovYearChart() {
  const { travel } = totals();
  const cpgfByYear = govPayload?.cpgf_presidency?.by_year || {};
  const rows = Object.entries(travel.by_year || {}).sort(([a], [b]) => a.localeCompare(b)).map(([year, y]) => ({
    label: year,
    value: Number(y.total?.total || 0) + Number(cpgfByYear[year]?.total || 0)
  }));
  renderBarChart('govYearChart', rows);
}
function renderJanjaMonthChart() {
  const monthly = new Map();
  const direct = records.filter(r => r.counted_in_direct_total || r.category === 'gasto_direto_em_comitiva');
  for (const r of direct) {
    const key = (r.date_start_iso || r.date_start || '').slice(0, 7) || String(r.year || 's/data');
    monthly.set(key, (monthly.get(key) || 0) + Number(r.total || 0));
  }
  const rows = [...monthly.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([label, value]) => ({ label: label.replace('-', '/'), value }));
  renderBarChart('janjaMonthChart', rows.slice(-14));
}
function renderDebtChart() {
  const dbgg = govPayload?.debt?.dbgg_pct_pib || {};
  const rows = [
    { label: (dbgg.baseline_date || 'base').slice(3), value: Number(dbgg.baseline_value || 0) },
    { label: (dbgg.latest_date || 'agora').slice(3), value: Number(dbgg.latest_value || 0) }
  ];
  renderBarChart('debtChart', rows, {
    moneyMode: false,
    valueFormatter: row => `${Number(row.value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
  });
}


function renderTravelFood() {
  const tf = dossierPayload?.travel_food || {};
  const direct = tf.direct_travel || {};
  const support = tf.support_and_mentions || {};
  const food = tf.food_like_clues || {};
  const lodging = tf.lodging_daily_clues || {};
  setText('travelDirectTotal', shortMoney(direct.total));
  setText('travelTicketsTotal', shortMoney(direct.passagens));
  setText('travelDailyTotal', shortMoney(direct.diarias));
  setText('foodClueTotal', shortMoney(food.cpgf_presidency_food_like_total || 0));
  setText('travelFoodNote', tf.editorial_note || 'Comida e hospedagem só entram como pista quando a fonte permite.');
  setText('supportTravelTotal', shortMoney(support.total));
  setText('lodgingClueTotal', shortMoney(lodging.diarias || lodging.total));

  const directBox = document.getElementById('travelFoodList');
  if (directBox) {
    const rows = (direct.top_records || []).slice(0, 6);
    directBox.innerHTML = rows.map(r => `<article class="mini-expense"><div><b>${escapeHtml(r.date_start || 'sem data')}</b><span>${escapeHtml(r.destination || 'sem destino')}</span></div><strong>${money(r.total)}</strong><p>${escapeHtml(shortText(r.objective, 115))}</p><a href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener noreferrer">fonte oficial</a></article>`).join('') || '<p class="empty">Sem viagens diretas identificadas.</p>';
  }
  const foodBox = document.getElementById('foodClueList');
  if (foodBox) {
    const rows = (food.top_records || []).slice(0, 4);
    foodBox.innerHTML = rows.map(r => `<article class="mini-expense"><div><b>${escapeHtml(r.date_start || 'sem data')}</b><span>${escapeHtml(r.expense_label || 'pista de comida/almoço')}</span></div><strong>${money(r.total)}</strong><p>${escapeHtml(shortText(r.objective, 110))}</p><small>Ressalva: pista textual; não é compra pessoal comprovada.</small></article>`).join('') || '<p class="empty">Sem pista textual de comida/almoço na amostra.</p>';
  }
  const status = document.getElementById('databaseStatus');
  if (status) {
    const idx = dossierPayload?.records_index || {};
    const generated = dossierPayload?.generated_at ? new Date(dossierPayload.generated_at).toLocaleString('pt-BR') : '—';
    status.innerHTML = `<b>Base viva do dossiê</b><span>${idx.total_records || 0} registros indexados • ${idx.food_or_meal_clue_records || 0} pistas de comida/almoço • atualizada em ${escapeHtml(generated)}</span>`;
  }
}

function renderNewsContext() {
  const box = document.getElementById('newsContext');
  if (!box) return;
  const { summary, cpgf, secret } = totals();
  const dbgg = govPayload?.debt?.dbgg_pct_pib || {};
  const items = [
    { tag: 'Estrutura', stat: shortMoney(summary.structure_context?.average_annual_structure_cost_2023_2024), title: 'Poder360: estrutura ligada à Janja custa cerca de R$ 2 mi/ano', text: 'Não há gabinete próprio, mas há custo público na máquina. Trocar nome não faz a conta desaparecer.', url: 'https://www.poder360.com.br/poder-governo/gabinete-de-janja-no-planalto-custa-cerca-de-r-2-mi-por-ano/', source: 'Poder360' },
    { tag: 'Viagens', stat: shortMoney(summary.janja_direct_total_all_contexts ?? summary.direct_total), title: 'Portal da Transparência: viagens oficiais', text: 'Base primária usada para separar Janja, apoio e comitiva — para ninguém inflar nem esconder.', url: 'https://portaldatransparencia.gov.br/download-de-dados/viagens/2025', source: 'Portal da Transparência' },
    { tag: 'Cartão', stat: shortMoney(cpgf.total), title: 'CPGF Presidência: cartão público sob lupa', text: 'Camada da Presidência. Não é atribuição pessoal sem prova, mas é dinheiro público sob cobrança.', url: 'https://portaldatransparencia.gov.br/download-de-dados/cpgf/202604', source: 'Portal da Transparência' },
    { tag: 'Sigilo', stat: shortMoney(secret.total), title: 'Favorecido sigiloso no cartão da Presidência', text: 'O cidadão paga, mas a base pública esconde quem recebeu. Isso merece holofote.', url: 'https://www.poder360.com.br/poder-governo/tcu-mostra-99-de-sigilo-no-cartao-corporativo-da-presidencia/', source: 'Poder360/TCU' },
    { tag: 'Dívida', stat: `${Number(dbgg.latest_value || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}% PIB`, title: 'Banco Central: dívida bruta em patamar alto', text: 'Quando a conta pública explode, quem paga é o contribuinte — não o discurso.', url: 'https://www.bcb.gov.br/estatisticas/tabelasespeciais', source: 'BCB SGS' },
    { tag: 'Meta fiscal', stat: 'R$ 324 bi', title: 'Gasto fora da meta vira pergunta pública', text: 'Contexto macro: bilhões fora da regra não podem virar nota de rodapé.', url: 'https://www.poder360.com.br/poder-economia/lula-gasta-r-324-bilhoes-fora-da-meta-fiscal-em-3-anos/', source: 'Poder360' }
  ];
  box.innerHTML = items.map(item => `<article class="news-item"><div><span>${escapeHtml(item.tag)}</span><strong>${escapeHtml(item.stat)}</strong></div><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.text)}</p><em>Camada de contexto — não é atribuição pessoal sem prova direta. É cobrança pública com fonte.</em><a href="${escapeAttr(item.url)}" target="_blank" rel="noopener noreferrer">Abrir fonte: ${escapeHtml(item.source)}</a></div></article>`).join('');
}

function setupRankingToggle() {
  document.querySelectorAll('[data-ranking]').forEach(btn => {
    btn.addEventListener('click', () => {
      activeRanking = btn.dataset.ranking;
      document.querySelectorAll('[data-ranking]').forEach(b => b.classList.toggle('active', b === btn));
      renderTopExpenses();
    });
  });
}
function renderTopExpenses() {
  const box = document.getElementById('topExpenses');
  const summary = payload.summary || {};
  const list = activeRanking === 'direct' ? (summary.top_expenses_direct || []) : (summary.top_expenses_all || []);
  box.innerHTML = list.slice(0, 6).map((r, idx) => `<article class="top-card"><div class="rank">${idx + 1}</div><div><div class="top-money">${money(r.total)}</div><h3>${escapeHtml(r.expense_label || categoryLabel(r.category))}</h3><p>${escapeHtml(r.date_start || 'Sem data')} • ${escapeHtml(r.destination || 'Sem destino')}</p><small>${escapeHtml(shortText(r.objective || '', 115))}</small></div></article>`).join('') || '<p class="empty">Ainda não há registros.</p>';
}

function setupFilters() {
  const years = [...new Set(records.map(r => r.year))].sort((a, b) => b - a);
  const categories = [...new Set(records.map(r => r.category))].sort();
  const expenseTypes = [...new Set(records.map(r => r.expense_type))].sort();
  const yearFilter = document.getElementById('yearFilter');
  const categoryFilter = document.getElementById('categoryFilter');
  const expenseFilter = document.getElementById('expenseFilter');
  yearFilter.innerHTML = '<option value="all">Todos os anos</option>' + years.map(y => `<option value="${y}">${y}</option>`).join('');
  categoryFilter.innerHTML = '<option value="all">Toda evidência</option>' + categories.map(c => `<option value="${c}">${categoryLabel(c)}</option>`).join('');
  expenseFilter.innerHTML = '<option value="all">Todo tipo de gasto</option>' + expenseTypes.map(t => `<option value="${t}">${escapeHtml(records.find(r => r.expense_type === t)?.expense_label || t)}</option>`).join('');
  [yearFilter, categoryFilter, expenseFilter, document.getElementById('searchInput')].forEach(el => el.addEventListener('input', renderRecords));
}
function filteredRecords() {
  const year = document.getElementById('yearFilter').value;
  const category = document.getElementById('categoryFilter').value;
  const expense = document.getElementById('expenseFilter').value;
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  return records.filter(r => {
    const hay = `${r.beneficiary} ${r.orgao} ${r.orgao_pagador} ${r.destination} ${r.objective} ${r.pcdp} ${r.expense_label} ${r.waste_signal}`.toLowerCase();
    return (year === 'all' || String(r.year) === year) && (category === 'all' || r.category === category) && (expense === 'all' || r.expense_type === expense) && (!q || hay.includes(q));
  }).sort((a, b) => Number(b.total || 0) - Number(a.total || 0));
}
function renderRecords() {
  const list = document.getElementById('recordsList');
  const rows = filteredRecords().slice(0, 20);
  list.innerHTML = rows.map(r => `<article class="record"><div class="record-head"><div><b>${escapeHtml(r.expense_label || 'Registro oficial')}</b><span>${escapeHtml(r.date_start || 'Sem data')} • ${escapeHtml(r.destination || 'Sem destino')}</span></div><strong>${money(r.total)}</strong></div><p>${escapeHtml(shortText(r.objective || r.simple_explanation, 140))}</p><div class="tags"><span class="tag ${confidenceClass(r.confidence)}">${categoryLabel(r.category)}</span><span class="tag">${r.counted_in_direct_total ? 'entra no direto' : 'contexto'}</span></div><details><summary>Detalhes da prova</summary><small>Beneficiário: ${escapeHtml(r.beneficiary || '—')}<br>Órgão: ${escapeHtml(r.orgao_pagador || r.orgao || '—')}<br>Passagens: ${money(r.passagens)} • Diárias: ${money(r.diarias)} • Outros: ${money(r.outros)}</small></details><a href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener noreferrer">Abrir fonte oficial</a></article>`).join('') || '<p class="empty">Nenhum registro para os filtros atuais.</p>';
}

function renderDraft() {
  const { summary, cpgf, watchedGovernment, secret } = totals();
  const foodClue = govPayload?.cpgf_presidency?.total_2023_2026?.food_like_total || 0;
  const draft = `O dinheiro é público. A conta também. A blindagem acabou.\n\nColoquei sob lupa ${shortMoney(watchedGovernment)} da máquina do governo: viagens federais, cartão da Presidência e estrutura ligada ao poder.\n\nJanja aparece em ${money(summary.janja_direct_total_all_contexts ?? summary.direct_total)} em registros diretos/contexto de viagens.\nEstrutura/equipe: ${money(summary.structure_context?.total_structure_cost_2023_2024)}.\nCartão Presidência: ${money(cpgf.total)}.\nFavorecido sigiloso: ${money(secret.total)}.\nPista CPGF comida/alimentação: ${money(foodClue)} — pista, não acusação pessoal.\n\nSem fonte, não vira acusação. Mas sigilo, cartão e privilégio pago pelo povo não passam batido.\n\nhttps://fiscalizando-a-janja.vercel.app`;
  setText('xDraft', draft);
}

function startSignalCanvas() {
  const canvas = document.getElementById('signalCanvas');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx = canvas.getContext('2d');
  let w, h, dots;
  function resize() {
    w = canvas.width = window.innerWidth * devicePixelRatio;
    h = canvas.height = window.innerHeight * devicePixelRatio;
    dots = Array.from({ length: Math.min(70, Math.floor(window.innerWidth / 7)) }, () => ({ x: Math.random() * w, y: Math.random() * h, r: (Math.random() * 1.7 + .5) * devicePixelRatio, vx: (Math.random() - .5) * .18 * devicePixelRatio, vy: (Math.random() - .5) * .18 * devicePixelRatio, c: Math.random() > .5 ? 'rgba(255,221,45,.52)' : 'rgba(0,156,59,.52)' }));
  }
  function frame() {
    ctx.clearRect(0, 0, w, h);
    for (const d of dots) { d.x += d.vx; d.y += d.vy; if (d.x < 0 || d.x > w) d.vx *= -1; if (d.y < 0 || d.y > h) d.vy *= -1; ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fillStyle = d.c; ctx.fill(); }
    requestAnimationFrame(frame);
  }
  resize(); window.addEventListener('resize', resize); frame();
}

document.getElementById('copyDraft')?.addEventListener('click', async () => {
  const text = document.getElementById('xDraft').textContent;
  await navigator.clipboard.writeText(text);
  document.getElementById('copyDraft').textContent = 'Copiado';
  setTimeout(() => document.getElementById('copyDraft').textContent = 'Copiar', 1600);
});

loadData().catch(err => {
  console.error(err);
  setText('statusPill', 'Erro ao carregar');
  document.getElementById('recordsList').innerHTML = `<p class="empty">Erro ao carregar dados: ${escapeHtml(err.message)}</p>`;
});
