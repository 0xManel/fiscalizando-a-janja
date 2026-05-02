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
function headlineMoney(value) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 1_000_000_000) return `R$ ${(n / 1_000_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} Bilhões`;
  return shortMoney(n);
}
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[ch])); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#096;'); }
function sourceText(url, label = 'Fonte') {
  const clean = String(url || '').trim();
  if (!clean) return `<span class="source-url empty-source">${escapeHtml(label)}: sem link público</span>`;
  return `<span class="source-url">${escapeHtml(label)}: ${escapeHtml(clean)}</span>`;
}
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
  renderUpdateStatus();
  renderRecentSignals();
  renderCharts();
  renderGovTopTrips();
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
  const secretRatio = Number(cpgf.total) ? (Number(secret.total || 0) / Number(cpgf.total)) * 100 : 0;
  const headline = dossierPayload?.headline || {};
  setText('governmentGrandTotal', headlineMoney(watchedGovernment));
  renderHero2025Spend();
  setText('heroTravelTotal', shortMoney(totals().federalTravelTotal));
  setText('heroCpgfTotal', shortMoney(cpgf.total));
  setText('heroStructureTotal', shortMoney(totals().structure));
  setText('heroRecordCount', `${Number(dossierPayload?.records_index?.total_records || records.length || 0).toLocaleString('pt-BR')}`);
  setText('heroDirectCount', `${Number(summary.direct_records_conservative || 0).toLocaleString('pt-BR')} regs.`);
  setText('heroSecretShare', pct(secretRatio));
  setText('janjaDirectTotal', shortMoney(summary.direct_total));
  setText('truthDirect', shortMoney(summary.direct_total));
  setText('truthContext', shortMoney(Number(summary.support_and_mentions_total || 0) + Number(summary.structure_context?.total_structure_cost_2023_2024 || 0)));
  setText('truthGovernment', shortMoney(watchedGovernment));
  setText('publicReading', `Leitura correta: ${shortMoney(watchedGovernment)} é governo sob lupa. Direto Janja: ${shortMoney(summary.direct_total)}. Equipe, Presidência, CPGF e dívida ficam em partes separadas — não é gasto pessoal sem prova direta.`);
  setText('structureTotal', shortMoney(summary.structure_context?.total_structure_cost_2023_2024));
  setText('cpgfPresidencyTotal', shortMoney(cpgf.total));
  setText('cpgfSecretTotal', shortMoney(secret.total));
  setText('debtTopValue', `${Number(dbgg.latest_value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`);
  setText('debtTopNote', `${dbgg.latest_date || '—'} • Banco Central. Contexto fiscal, não atribuição pessoal.`);
  setText('cpgfPresidencyNote', `${cpgf.count || 0} transações • despesa da Presidência; não é atribuição automática à Janja.`);
  setText('cpgfSecretNote', `${secret.count || 0} transações: o cidadão paga, mas a base pública não mostra quem recebeu.`);
  const allYears = [...(summary.years || []), ...Object.keys(govPayload?.official_travel?.by_year || {}).map(Number)].filter(Boolean);
  const years = allYears.length ? `${Math.min(...allYears)}–${Math.max(...allYears)}` : 'anos disponíveis';
  setText('statusPill', `Base oficial ${years}`);
  const generated = payload.generated_at ? new Date(payload.generated_at) : null;
  const recordCount = Number(dossierPayload?.records_index?.total_records || records.length || 0).toLocaleString('pt-BR');
  const headerStatus = document.getElementById('headerStatus');
  if (headerStatus) {
    headerStatus.innerHTML = `<span>Base oficial</span><strong>${recordCount} registros • ${generated ? generated.toLocaleDateString('pt-BR') : 'sem data'}</strong>`;
  }
  setText('lastUpdate', `Última varredura: ${generated ? generated.toLocaleString('pt-BR') : '—'}`);
}

function renderHero2025Spend() {
  const box = document.getElementById('hero2025Spend');
  if (!box) return;
  const travelYears = Object.keys(govPayload?.official_travel?.by_year || {}).map(Number).filter(Boolean);
  const cpgfYears = Object.keys(govPayload?.cpgf_presidency?.by_year || {}).map(Number).filter(Boolean);
  const recordYears = (records || []).map(r => Number(r.year || String(r.date_start_iso || '').slice(0, 4))).filter(Boolean);
  const latestYear = Math.max(...travelYears, ...cpgfYears, ...recordYears, new Date().getFullYear());
  const safeCategories = new Set([
    'gasto_direto_identificado',
    'gasto_direto_em_comitiva',
    'equipe_apoio_primeira_dama',
    'agenda_com_mencao',
    'comitiva_presidencial_com_mencao'
  ]);
  const yearRecords = (records || []).filter(r => Number(r.year || String(r.date_start_iso || '').slice(0, 4)) === latestYear && safeCategories.has(r.category));
  const janjaContextYear = yearRecords.reduce((sum, r) => sum + Number(r.total || 0), 0);
  const federalTravelYear = Number(govPayload?.official_travel?.by_year?.[String(latestYear)]?.total?.total || 0);
  const cpgfYear = Number(govPayload?.cpgf_presidency?.by_year?.[String(latestYear)]?.total || 0);
  const foodLikeYear = Number(govPayload?.cpgf_presidency?.by_year?.[String(latestYear)]?.food_like_total || 0);
  if (!yearRecords.length && !federalTravelYear && !cpgfYear) {
    box.innerHTML = `<span>${latestYear} sob lupa</span><strong>Sem base carregada</strong><small>A próxima varredura atualiza o recorte anual.</small>`;
    return;
  }
  box.innerHTML = `<span>${latestYear} sob lupa</span>
    <strong>${shortMoney(federalTravelYear + cpgfYear + janjaContextYear)}</strong>
    <small>Governo no ano: viagens federais + CPGF Presidência + registros Janja/contexto. Direto pessoal só quando a linha oficial prova.</small>
    <em>Janja/contexto ${latestYear}: ${shortMoney(janjaContextYear)} (${yearRecords.length} regs.) • Viagens federais: ${shortMoney(federalTravelYear)} • CPGF Presidência: ${shortMoney(cpgfYear)} • pistas comida: ${shortMoney(foodLikeYear)}</em>`;
}

function renderUpdateStatus() {
  const grid = document.getElementById('updateStatusGrid');
  const pill = document.querySelector('#updateStatus .update-mode-pill');
  const fileStrip = document.getElementById('updateFileStrip');
  if (!grid) return;
  const cache = dossierPayload?.cache_status || govPayload?.cache_status || {};
  const generated = cache.generated_at || dossierPayload?.generated_at || payload?.generated_at;
  const dt = generated ? new Date(generated) : null;
  const ageMin = dt ? Math.max(0, Math.round((Date.now() - dt.getTime()) / 60000)) : null;
  const freshClass = ageMin !== null && ageMin <= 180 ? 'ok' : 'stale';
  const travelCount = cache.travel_zips?.count ?? cache.travel_zips ?? '—';
  const budgetCount = cache.budget_zips?.count ?? cache.budget_zips ?? '—';
  const cpgfCount = cache.cpgf_monthly_zips?.count ?? cache.cpgf_monthly_zips ?? '—';
  if (pill) pill.innerHTML = `<span class="freshness-dot ${freshClass}"></span><b>Atualização por lote oficial</b><small>${dt ? dt.toLocaleString('pt-BR') : 'sem data'} • varredura por arquivos oficiais, não transmissão ao vivo</small>`;
  const items = [
    ['Última varredura', dt ? dt.toLocaleString('pt-BR') : '—', ageMin !== null ? `${ageMin} min desde a geração` : 'aguardando base'],
    ['Viagens oficiais', travelCount, 'arquivos ZIP/cache lidos'],
    ['CPGF Presidência', cpgfCount, 'meses monitorados'],
    ['Cache auditável', cache.public_status?.total_cached_files ?? budgetCount, cache.public_status?.public_summary || 'anos/arquivos de contexto']
  ];
  grid.innerHTML = items.map(([label, value, note]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong><small>${escapeHtml(note)}</small></article>`).join('');
  if (fileStrip) {
    const latest = cache.public_status?.latest_official_files || {};
    const files = [
      ['Viagens', latest.viagens || cache.travel_zips?.latest_file],
      ['Orçamento', latest.orcamento || cache.budget_zips?.latest_file],
      ['CPGF', latest.cpgf || cache.cpgf_monthly_zips?.latest_file]
    ].filter(([, value]) => value);
    fileStrip.innerHTML = files.length
      ? `<b>Arquivos oficiais mais recentes no cache:</b>${files.map(([label, value]) => `<span>${escapeHtml(label)}: ${escapeHtml(value)}</span>`).join('')}<em>Novos dados dependem da publicação nos portais oficiais; o painel não é transmissão ao vivo.</em>`
      : `<b>Arquivos oficiais:</b><em>Cache em leitura. O painel usa varredura por lote, não transmissão ao vivo.</em>`;
  }
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
    const contextLabel = r.counted_in_direct_total ? 'direto Janja' : 'parte separada';
    const explanation = r.counted_in_direct_total
      ? 'Registro oficial em nome de Rosângela da Silva. É a prova mais direta do recorte — sem enrolação.'
      : 'Menção, apoio ou comitiva: não entra como gasto pessoal direto, mas serve para cobrar transparência.';
    const urgency = String(r.urgent || '').toUpperCase() === 'SIM' ? '<span class="urgent-chip">urgente</span>' : '';
    return `<article class="quick-log-card ${r.counted_in_direct_total ? 'direct-proof' : ''}">
      <div><strong>${money(r.total)}</strong><small>${escapeHtml(r.date_start || 'sem data')} • ${escapeHtml(r.destination || 'sem destino')}</small></div>
      <p>${escapeHtml(explanation)}</p>
      <footer><span>${escapeHtml(category)}</span><span>${escapeHtml(contextLabel)}</span>${urgency}${sourceText(r.source_url, 'Fonte oficial')}</footer>
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
    cpgfBox.textContent = `CPGF granular: ${shortMoney(cpgf.total?.total)} em ${cpgf.total?.count || 0} transações da Presidência. Sigilo: ${shortMoney(secret.total)} (${Number(secret.ratio_of_cpgf_total_pct || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%). Último mês no cache: ${latestMonth || '—'}. Não é atribuição pessoal à Janja — é cobrança por transparência onde a base pública oculta favorecidos.`;
  }
}

function renderCharts() {
  renderGovYearChart();
  renderJanjaMonthChart();
  renderDebtChart();
  renderCpgfMonthChart();
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
  renderHeroYearPills(rows.slice(-4));
}
function renderHeroYearPills(rows) {
  const box = document.getElementById('heroGovYearChart');
  const insight = document.getElementById('heroChartInsight');
  if (!box) return;
  const max = Math.max(...rows.map(r => Number(r.value || 0)), 1);
  box.innerHTML = rows.map(row => {
    const value = Number(row.value || 0);
    const height = Math.max(18, (value / max) * 100);
    const topClass = value === max ? ' peak' : '';
    return `<article class="hero-year-pill${topClass}" aria-label="${escapeAttr(row.label)}: ${escapeAttr(shortMoney(value))}"><span>${escapeHtml(row.label)}</span><i style="height:${height}%"></i><b>${shortMoney(value)}</b></article>`;
  }).join('') || '<p class="empty">Sem dados para gráfico.</p>';
  if (insight) {
    const latest = rows.at(-1);
    const previous = rows.at(-2);
    const peak = rows.reduce((best, row) => Number(row.value || 0) > Number(best.value || 0) ? row : best, rows[0] || { label: '—', value: 0 });
    const latestValue = Number(latest?.value || 0);
    const previousValue = Number(previous?.value || 0);
    const delta = previousValue ? ((latestValue - previousValue) / previousValue) * 100 : 0;
    const deltaLabel = previous ? `${delta >= 0 ? '+' : '−'}${Math.abs(delta).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}% vs ${previous.label}` : 'sem comparação anterior';
    insight.innerHTML = `<span><b>${escapeHtml(latest?.label || '—')}</b>${escapeHtml(shortMoney(latestValue))}</span><span><b>Pico</b>${escapeHtml(peak.label)} • ${escapeHtml(shortMoney(peak.value))}</span><span><b>Variação</b>${escapeHtml(deltaLabel)}</span>`;
  }
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

function renderCpgfMonthChart() {
  const byMonth = govPayload?.cpgf_presidency?.by_month || dossierPayload?.cpgf_granular?.by_month || {};
  const rows = Object.entries(byMonth)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-8)
    .map(([key, value]) => {
      const total = Number(value.total || value?.total?.total || 0);
      return { label: `${key.slice(4, 6)}/${key.slice(2, 4)}`, value: total };
    });
  renderBarChart('cpgfMonthChart', rows);
}

function renderGovTopTrips() {
  const box = document.getElementById('govTopTrips');
  if (!box) return;
  const trips = govPayload?.official_travel?.top_travel_records_2023_2026 || [];
  box.innerHTML = trips.slice(0, 4).map(r => `<article class="mini-expense gov-trip-proof">
    <div><b>${escapeHtml(r.date_start || String(r.year || 'sem data'))}</b><span>${escapeHtml(shortText(r.org || r.paying_org || 'órgão federal', 34))}</span></div>
    <strong>${money(r.total)}</strong>
    <p>${escapeHtml(shortText(`${r.beneficiary || 'beneficiário'} • ${r.destination || 'sem destino'}`, 105))}</p>
    <small>${escapeHtml(r.caveat || 'Contexto federal; não é gasto pessoal automático.')}</small>
    ${sourceText(r.source_url, 'Fonte oficial')}
  </article>`).join('') || '<p class="empty">Sem ranking federal carregado.</p>';
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
    directBox.innerHTML = rows.map(r => `<article class="mini-expense"><div><b>${escapeHtml(r.date_start || 'sem data')}</b><span>${escapeHtml(r.destination || 'sem destino')}</span></div><strong>${money(r.total)}</strong><p>${escapeHtml(shortText(r.objective, 115))}</p>${sourceText(r.source_url, 'Fonte oficial')}</article>`).join('') || '<p class="empty">Sem viagens diretas identificadas.</p>';
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
    status.innerHTML = `<b>Base auditável</b><span>${idx.total_records || 0} registros indexados • ${idx.food_or_meal_clue_records || 0} pistas de comida/almoço • atualizada em ${escapeHtml(generated)}</span>`;
  }
}

function renderNewsContext() {
  const box = document.getElementById('newsContext');
  if (!box) return;
  const { summary, cpgf, secret } = totals();
  const dbgg = govPayload?.debt?.dbgg_pct_pib || {};
  const fallback = [
    { layer: 'Estrutura', visual_type: 'structure', stat: shortMoney(summary.structure_context?.average_annual_structure_cost_2023_2024), title: 'Poder360: estrutura ligada à Janja custa cerca de R$ 2 mi/ano', summary: 'Não há gabinete próprio, mas há custo público de equipe e apoio. Trocar o rótulo não faz a conta desaparecer.', url: 'https://www.poder360.com.br/poder-governo/gabinete-de-janja-no-planalto-custa-cerca-de-r-2-mi-por-ano/', source: 'Poder360' },
    { layer: 'Viagens', visual_type: 'travel', stat: shortMoney(summary.janja_direct_total_all_contexts ?? summary.direct_total), title: 'Portal da Transparência: viagens oficiais federais', summary: 'Base primária de todas as viagens federais do período. Não é total pessoal da Janja; o recorte dela fica separado.', url: 'https://portaldatransparencia.gov.br/download-de-dados/viagens/2025', source: 'Portal da Transparência' },
    { layer: 'Cartão', visual_type: 'card', stat: shortMoney(cpgf.total), title: 'CPGF Presidência: cartão público sob lupa', summary: 'Camada da Presidência. Não é atribuição pessoal sem prova, mas é dinheiro público sob cobrança.', url: 'https://portaldatransparencia.gov.br/download-de-dados/cpgf/202604', source: 'Portal da Transparência' },
    { layer: 'Sigilo', visual_type: 'secrecy', stat: shortMoney(secret.total), title: 'Favorecido sigiloso no cartão da Presidência', summary: 'O cidadão paga, mas a base pública esconde quem recebeu. Isso merece holofote.', url: 'https://www.poder360.com.br/poder-governo/tcu-mostra-99-de-sigilo-no-cartao-corporativo-da-presidencia/', source: 'Poder360/TCU' },
    { layer: 'Dívida', visual_type: 'debt', stat: `${Number(dbgg.latest_value || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}% PIB`, title: 'Banco Central: dívida bruta em patamar alto', summary: 'Quando a conta pública pesa, quem paga é o contribuinte — não o discurso.', url: 'https://www.bcb.gov.br/estatisticas/tabelasespeciais', source: 'BCB SGS' },
    { layer: 'Meta fiscal', visual_type: 'macro', stat: 'R$ 324 bi', title: 'Gasto fora da meta vira pergunta pública', summary: 'Contexto macro: bilhões fora da regra não podem virar nota de rodapé.', url: 'https://www.poder360.com.br/poder-economia/lula-gasta-r-324-bilhoes-fora-da-meta-fiscal-em-3-anos/', source: 'Poder360' }
  ];
  const jsonItems = Array.isArray(dossierPayload?.news_links) ? dossierPayload.news_links : [];
  const items = (jsonItems.length ? jsonItems : fallback).map((item, idx) => ({
    layer: item.layer || item.tag || fallback[idx % fallback.length].layer,
    visual_type: item.visual_type || fallback[idx % fallback.length].visual_type,
    stat: item.stat || fallback[idx % fallback.length].stat || item.source || 'Fonte',
    title: item.title,
    summary: item.summary || item.text || item.caveat || fallback[idx % fallback.length].summary,
    url: item.url,
    source: item.source || 'Fonte aberta',
    source_type: item.source_type || 'fonte/contexto aberto',
    credibility: item.credibility || 'contexto',
    claim_scope: item.claim_scope || item.layer || 'camada de contexto',
    official_basis: item.official_basis || 'Fonte aberta informada no card; confira a URL exibida como texto.',
    included_in_direct_janja_total: Boolean(item.included_in_direct_janja_total),
    image_policy: item.image_policy || 'visual gerado no dashboard; sem hotlink de foto',
    caveat: item.caveat || 'Contexto separado — não é atribuição pessoal sem prova direta.'
  }));
  box.innerHTML = items.map((item, idx) => {
    const safeType = String(item.visual_type || 'context').replace(/[^a-z0-9_-]/gi, '').toLowerCase() || 'context';
    const layerLabel = String(item.layer || 'Fonte').slice(0, 2).toUpperCase();
    const directBadge = item.included_in_direct_janja_total ? 'entra no direto' : 'contexto separado';
    return `<article class="news-card-premium">
      <div class="news-visual ${escapeAttr(safeType)}" aria-hidden="true">
        <span>${escapeHtml(layerLabel)}</span>
        <b>${escapeHtml(item.stat)}</b>
        <div class="news-visual-meta"><small>${escapeHtml(item.source)}</small><small>${escapeHtml(directBadge)}</small></div>
      </div>
      <div class="news-body">
        <div class="news-kicker"><span>${escapeHtml(item.layer)}</span><small>${escapeHtml(item.source)} • ${escapeHtml(item.credibility)}</small></div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.summary)}</p>
        <div class="news-proof-rail" aria-label="Resumo da evidência do link">
          <span><b>Número</b>${escapeHtml(item.stat)}</span>
          <span><b>Escopo</b>${escapeHtml(item.claim_scope)}</span>
          <span><b>Total direto</b>${item.included_in_direct_janja_total ? 'entra' : 'não entra'}</span>
          <span><b>Fonte</b>${escapeHtml(item.source)}</span>
        </div>
        <p class="basis-note"><b>Base:</b> ${escapeHtml(item.official_basis)}</p>
        <em>${escapeHtml(item.caveat)}</em>
        <small class="news-source-note">${escapeHtml(item.source_type)} • ${escapeHtml(item.image_policy)}</small>
        ${sourceText(item.url, `Fonte ${item.source}`)}
      </div>
    </article>`;
  }).join('');
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
function govTravelCard(r, idx, label) {
  return `<article class="top-card"><div class="rank">${idx + 1}</div><div><div class="top-money">${money(r.total)}</div><h3>${escapeHtml(label || r.org || r.paying_org || 'Viagem oficial federal')}</h3><p>${escapeHtml(r.date_start || r.year || 'Sem data')} • ${escapeHtml(r.destination || 'Sem destino')}</p><small>${escapeHtml(shortText(r.objective || 'Motivo não detalhado na linha pública.', 145))}</small><details><summary>Ver explicação e fonte</summary><small>Órgão: ${escapeHtml(r.org || r.paying_org || '—')}<br>Passagens: ${money(r.passagens)} • Diárias: ${money(r.diarias)} • Outros: ${money(r.outros)}<br>${escapeHtml(r.caveat || 'Contexto; não é gasto pessoal automático.')}</small></details>${sourceText(r.source_url || 'https://portaldatransparencia.gov.br/download-de-dados/viagens/2025', 'Fonte oficial')}</div></article>`;
}
function radarTravelCard(r, idx) {
  return `<article class="top-card"><div class="rank">${idx + 1}</div><div><div class="top-money">${money(r.total)}</div><h3>${escapeHtml(r.expense_label || categoryLabel(r.category))}</h3><p>${escapeHtml(r.date_start || 'Sem data')} • ${escapeHtml(r.destination || 'Sem destino')}</p><small>${escapeHtml(shortText(r.objective || '', 145))}</small><details><summary>Ver explicação e fonte</summary><small>Beneficiário: ${escapeHtml(r.beneficiary || '—')}<br>Órgão: ${escapeHtml(r.orgao_pagador || r.orgao || '—')}<br>Tipo: ${escapeHtml(categoryLabel(r.category))}<br>Passagens: ${money(r.passagens)} • Diárias: ${money(r.diarias)} • Outros: ${money(r.outros)}</small></details>${sourceText(r.source_url || 'https://portaldatransparencia.gov.br/download-de-dados/viagens/2025', 'Fonte oficial')}</div></article>`;
}
function cpgfCard(r, idx) {
  return `<article class="top-card"><div class="rank">${idx + 1}</div><div><div class="top-money">${money(r.total)}</div><h3>${escapeHtml(r.favored || 'Favorecido informado/sigiloso')}</h3><p>${escapeHtml(r.count || 0)} transações • CPGF Presidência</p><small>Camada de cartão da Presidência. Quando o favorecido é sigiloso, o dado cobra transparência — não identifica quem recebeu.</small></div></article>`;
}
function renderTopExpenses() {
  const box = document.getElementById('topExpenses');
  const note = document.getElementById('rankingNote');
  const summary = payload.summary || {};
  const govTravel = govPayload?.official_travel || {};
  const cpgf = govPayload?.cpgf_presidency || {};
  const configs = {
    direct: {
      note: 'Top 10 direto Janja: registros mais fortes, em nome dela ou CPF mascarado oficial. Não inclui governo, Presidência, equipe nem comitiva.',
      rows: (summary.top_expenses_direct || []).slice(0, 10),
      render: (r, i) => radarTravelCard(r, i)
    },
    context: {
      note: 'Top 10 comitiva/equipe/contexto: registros ligados por apoio, menção ou comitiva. Ficam separados do gasto pessoal direto.',
      rows: (summary.top_expenses_all || []).filter(r => !r.counted_in_direct_total).slice(0, 10),
      render: (r, i) => radarTravelCard(r, i)
    },
    federal: {
      note: 'Top 10 viagens federais oficiais: base ampla do Portal da Transparência. Não é gasto pessoal da Janja.',
      rows: (govTravel.top_travel_records_2023_2026 || []).slice(0, 10),
      render: (r, i) => govTravelCard(r, i, 'Viagem federal oficial')
    },
    presidency: {
      note: 'Top 10 viagens no recorte Presidência: contexto da Presidência, não atribuição automática à Janja.',
      rows: (govTravel.top_presidency_travel_records_2023_2026 || []).slice(0, 10),
      render: (r, i) => govTravelCard(r, i, 'Viagem oficial — Presidência')
    },
    cpgf: {
      note: 'Top 10 CPGF Presidência por favorecido: cartão corporativo sob lupa. Sigilo não mostra quem recebeu.',
      rows: (cpgf.top_favored || []).slice(0, 10),
      render: (r, i) => cpgfCard(r, i)
    }
  };
  const cfg = configs[activeRanking] || configs.direct;
  if (note) note.textContent = cfg.note;
  box.innerHTML = cfg.rows.map((r, idx) => cfg.render(r, idx)).join('') || '<p class="empty">Ainda não há registros nessa lista.</p>';
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
  const filtered = filteredRecords();
  const rows = filtered.slice(0, 20);
  const status = document.getElementById('recordsResultStatus');
  if (status) {
    status.textContent = `${filtered.length.toLocaleString('pt-BR')} registros encontrados; mostrando ${rows.length.toLocaleString('pt-BR')} primeiros por maior valor. Use filtros para auditar sem misturar evidências.`;
  }
  list.innerHTML = rows.map(r => `<article class="record"><div class="record-head"><div><b>${escapeHtml(r.expense_label || 'Registro oficial')}</b><span>${escapeHtml(r.date_start || 'Sem data')} • ${escapeHtml(r.destination || 'Sem destino')}</span></div><strong>${money(r.total)}</strong></div><p>${escapeHtml(shortText(r.objective || r.simple_explanation, 140))}</p><div class="tags"><span class="tag ${confidenceClass(r.confidence)}">${categoryLabel(r.category)}</span><span class="tag">${r.counted_in_direct_total ? 'entra no direto' : 'contexto'}</span></div><details><summary>Detalhes da prova</summary><small>Beneficiário: ${escapeHtml(r.beneficiary || '—')}<br>Órgão: ${escapeHtml(r.orgao_pagador || r.orgao || '—')}<br>Passagens: ${money(r.passagens)} • Diárias: ${money(r.diarias)} • Outros: ${money(r.outros)}</small></details>${sourceText(r.source_url, 'Fonte oficial')}</article>`).join('') || '<p class="empty">Nenhum registro para os filtros atuais.</p>';
}

function renderDraft() {
  const { summary, cpgf, watchedGovernment, secret } = totals();
  const headline = dossierPayload?.headline || {};
  const recordsCount = Number(dossierPayload?.records_index?.total_records || records.length || 0).toLocaleString('pt-BR');
  const url = 'https://janjometro.vercel.app';
  const directTotal = money(summary.direct_total);
  const contextTotal = money(summary.janja_direct_total_all_contexts ?? summary.direct_total);
  const cpgfTotal = money(cpgf.total);
  const secretTotal = money(secret.total);
  const travelTotal = money(headline.official_travel_federal_total || totals().federalTravelTotal);
  const draft = `Dossiê aberto no ar: Janjômetro. Registro direto fica separado de comitiva, equipe, Presidência e sigilo. Sem fonte, não vira acusação. ${url}`;
  const longPost = `🚨 Janjômetro está no ar.\n\nEu montei um painel público para qualquer pessoa conferir registros oficiais sem depender de manchete, torcida ou versão de governo.\n\nO que a página separa:\n• viagens federais oficiais: ${travelTotal}\n• gasto direto identificado em nome da Janja: ${directTotal}\n• contexto/comitiva/equipe: ${contextTotal}\n• cartão corporativo da Presidência: ${cpgfTotal}\n• favorecido sigiloso no CPGF: ${secretTotal}\n\nA regra é simples: direto é direto; equipe, comitiva, menção e Presidência ficam separados. Se não tem fonte, não vira acusação.\n\nO objetivo é fiscalização cidadã: número na tela, fonte aberta e cobrança pública contra desperdício, sigilo e favorecido oculto.\n\nAcesse: ${url}`;
  const thread = `1/ Estou abrindo o Janjômetro: um dossiê público com ${recordsCount} registros indexados.\n\n2/ O painel não mistura tudo para viralizar: separa direto Janja (${directTotal}), contexto/comitiva (${contextTotal}) e cartão da Presidência (${cpgfTotal}).\n\n3/ Onde há sigilo ou favorecido oculto, o painel cobra transparência. Onde só há menção/contexto, ele marca como contexto — não como gasto pessoal.\n\n4/ Sem fonte, não vira acusação. Com fonte, não fica escondido.\n${url}`;
  setText('xDraft', draft);
  setText('longPostDraft', longPost);
  setText('threadDraft', thread);
}

function startSignalCanvas() {
  const canvas = document.getElementById('signalCanvas');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.innerWidth < 760) return;
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

async function copyLaunchText(button) {
  const targetId = button?.dataset?.copyTarget;
  const target = targetId ? document.getElementById(targetId) : null;
  const status = document.getElementById('copyStatus');
  if (!target) return;
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(target.textContent.trim());
    button.textContent = 'Copiado';
    if (status) status.textContent = 'Rascunho copiado. Revise antes de publicar; nada é postado automaticamente.';
  } catch (err) {
    button.textContent = 'Selecione';
    if (status) status.textContent = 'Não consegui copiar automaticamente. Selecione o texto e copie manualmente.';
  }
  setTimeout(() => { button.textContent = original; }, 1800);
}

document.querySelectorAll('[data-copy-target]').forEach(button => {
  button.addEventListener('click', () => copyLaunchText(button));
});

loadData().catch(err => {
  console.error(err);
  setText('statusPill', 'Erro ao carregar');
  document.getElementById('recordsList').innerHTML = `<p class="empty">Erro ao carregar dados: ${escapeHtml(err.message)}</p>`;
});
