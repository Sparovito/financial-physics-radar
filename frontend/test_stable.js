// ============================================================
//  STABLE Strategy Lab — test_stable.js
//  Backtest della strategia STABLE (Stable Slope) su multi-ticker
//  con optimizer parametri entry/exit
// ============================================================

// --- GLOBALS ---
// Auto-detect API base: if opened as file://, try common backend URLs
let API_BASE = "";
if (window.location.protocol === 'file:') {
    // Running locally — need explicit backend URL
    // Try to read from localStorage or prompt user
    const saved = localStorage.getItem('STABLE_LAB_API');
    if (saved) {
        API_BASE = saved;
    } else {
        const url = prompt(
            'Stai aprendo il file localmente.\n' +
            'Inserisci l\'URL del backend (es. https://tuoserver.com oppure http://localhost:8000):',
            'http://localhost:8000'
        );
        if (url) {
            API_BASE = url.replace(/\/+$/, ''); // remove trailing slashes
            localStorage.setItem('STABLE_LAB_API', API_BASE);
        }
    }
    console.log('[STABLE Lab] File mode — API_BASE:', API_BASE);
}
const RESULTS = {};          // { ticker: { data, backtest, slopes, dates, prices } }
let RUNNING = false;

// --- PRESETS ---
// Build "ALL" preset dynamically from TICKERS_DATA (loaded from tickers.js)
function getAllTickers() {
    if (typeof TICKERS_DATA === 'undefined') return [];
    const seen = new Set();
    const all = [];
    for (const category of Object.values(TICKERS_DATA)) {
        for (const t of category) {
            if (!seen.has(t.symbol)) {
                seen.add(t.symbol);
                all.push(t.symbol);
            }
        }
    }
    return all;
}

const PRESETS = {
    all:    null, // computed lazily
    mega:   ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK-B'],
    tech:   ['AVGO','ORCL','ADBE','CRM','AMD','INTC','QCOM','NFLX'],
    us_all: null, // computed lazily
    eu:     ['ASML','SAP','LVMH.PA','MC.PA','SIE.DE','OR.PA','ABI.BR','ENEL.MI'],
    crypto: ['BTC-USD','ETH-USD','SOL-USD','ADA-USD','AVAX-USD','LINK-USD'],
    etf:    ['SPY','QQQ','IWM','VEA','VWO','GLD','TLT','XLF'],
};

// Build category-based presets from TICKERS_DATA
function buildDynamicPresets() {
    if (typeof TICKERS_DATA === 'undefined') return;
    PRESETS.all = getAllTickers();

    // US stocks only (no forex, crypto, commodities, indices)
    const usCategories = Object.keys(TICKERS_DATA).filter(k =>
        k.includes('US ') || k.includes('Mega') || k.includes('Highlights')
    );
    const usSet = new Set();
    usCategories.forEach(cat => TICKERS_DATA[cat].forEach(t => usSet.add(t.symbol)));
    PRESETS.us_all = [...usSet];
}

// ============================================================
//  UI HELPERS
// ============================================================

function setStatus(msg) {
    document.getElementById('status-bar').textContent = msg;
}

function setProgress(pct) {
    const bar = document.getElementById('progress-bar');
    const fill = document.getElementById('progress-fill');
    if (pct <= 0) { bar.style.display = 'none'; return; }
    bar.style.display = 'block';
    fill.style.width = pct + '%';
}

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel-section').forEach(p => p.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tab}"]`).classList.add('active');
    document.getElementById('panel-' + tab).classList.add('active');
}

function applyPreset() {
    const sel = document.getElementById('preset-select').value;
    if (!sel) return;
    buildDynamicPresets(); // ensure dynamic presets are built
    if (PRESETS[sel]) {
        document.getElementById('tickers-input').value = PRESETS[sel].join(',');
        const count = PRESETS[sel].length;
        setStatus(`Preset caricato: ${count} tickers. Premi Analizza o Ottimizza.`);
    }
}

function getTickerList() {
    const raw = document.getElementById('tickers-input').value.trim();
    if (!raw) return [];
    return raw.split(',').map(s => s.trim().toUpperCase()).filter(s => s.length > 0);
}

function renderChips(tickers) {
    const div = document.getElementById('ticker-chips');
    div.innerHTML = tickers.map(t =>
        `<span class="chip selected" id="chip-${t}">${t}</span>`
    ).join('');
}

// ============================================================
//  BACKTEST ENGINE
//  Il motore vive in stable_engine.js (replica SPECULARE di
//  backend/stable_strategy.py — parità garantita da
//  backend/tests/test_js_py_parity.py).
//  Semantica: esecuzione t+1, costi per lato, SHORT con soglie
//  speculari (entry slope < -entryTh), BOTH = leg paralleli,
//  win rate solo sui trade chiusi.
// ============================================================

function getCostPct() {
    const v = parseFloat(document.getElementById('param-cost')?.value);
    return Number.isFinite(v) ? v : 0.05;
}

function runStableBacktest(dates, prices, slopes, entryTh, exitTh, mode, opts) {
    opts = opts || {};
    return backtestStableCompat(dates, prices, slopes, {
        mode: mode || 'LONG',
        entryTh: entryTh,
        exitTh: exitTh,
        executionLag: 1,
        costPct: opts.costPct != null ? opts.costPct : getCostPct(),
        startDate: opts.startDate || null,
        endDate: opts.endDate || null,
    });
}

function getEndDate() {
    const v = document.getElementById('param-end')?.value?.trim();
    return v || null;
}

// Dispatch per strategia: STABLE (trend), ARANCIONE (scarico del potenziale),
// COMBO (trend OR arancione). ARANCIONE e COMBO sono LONG-only per evidenza
// (gli spike di potenziale con prezzo sopra F non hanno edge misurato).
function runLabBacktest(strategy, r, p) {
    const opts = {
        mode: p.mode || 'LONG',
        entryTh: p.entryTh, exitTh: p.exitTh,
        entryZ: p.entryZ, horizon: p.horizon,
        executionLag: 1, costPct: getCostPct(),
        startDate: null, endDate: p.endDate || null,
    };
    if (strategy === 'ARANCIONE' || strategy === 'COMBO') {
        if (!r.pot || r.pot.length === 0) {
            throw new Error('Serie "pot" mancante dal backend: riavvia il server aggiornato');
        }
        if (strategy === 'ARANCIONE') {
            return backtestPotentialDischarge(r.dates, r.prices, r.pot, r.fund, opts);
        }
        return backtestCombo(r.dates, r.prices, r.slopes, r.pot, r.fund, opts);
    }
    return backtestStableCompat(r.dates, r.prices, r.slopes, opts);
}

function updateStrategyControls() {
    const s = document.getElementById('param-strategy')?.value || 'STABLE';
    const isTrend = (s === 'STABLE');
    const modeEl = document.getElementById('param-mode');
    if (modeEl) {
        modeEl.disabled = !isTrend;
        if (!isTrend) modeEl.value = 'LONG';
    }
    const ez = document.getElementById('param-entryz');
    const hor = document.getElementById('param-horizon');
    if (ez) ez.disabled = isTrend;
    if (hor) hor.disabled = isTrend;
    const opt = document.getElementById('btn-opt');
    if (opt) {
        opt.disabled = !isTrend;
        opt.title = isTrend ? '' : 'L\'optimizer grid-search è disponibile solo per STABLE (per ARANCIONE/COMBO i parametri robusti sono Entry Z 1.5-2.5, Hold 10-42)';
    }
}

// UI helper: update labels when mode changes
function updateModeLabels() {
    const mode = document.getElementById('param-mode').value;
    const labelEntry = document.getElementById('label-entry');
    const labelExit = document.getElementById('label-exit');
    if (mode === 'SHORT') {
        labelEntry.textContent = 'Entry <';
        labelExit.textContent = 'Exit >';
    } else {
        labelEntry.textContent = 'Entry >';
        labelExit.textContent = 'Exit <';
    }
}

// ============================================================
//  API FETCH
// ============================================================

function getConcurrency() {
    return parseInt(document.getElementById('param-concurrency')?.value) || 8;
}

function getBatchSize() {
    return parseInt(document.getElementById('param-batchsize')?.value) || 20;
}

// Single ticker fetch (fallback)
async function fetchTicker(ticker, alpha, startDate) {
    const body = {
        ticker, alpha, beta: 1.0,
        start_date: startDate, use_cache: false
    };
    const resp = await fetch(API_BASE + '/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${errText.substring(0, 100)}`);
    }
    return await resp.json();
}

// Batch fetch: send N tickers per request, server processes them in parallel
async function fetchBatch(tickers, alpha, startDate, maxWorkers) {
    const body = {
        tickers,
        alpha,
        start_date: startDate,
        max_workers: maxWorkers
    };
    const resp = await fetch(API_BASE + '/analyze-batch-stable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${errText.substring(0, 100)}`);
    }
    return await resp.json();
}

// Main parallel fetch: splits tickers into batches, sends MULTIPLE batches concurrently
// Browser limit = 6 HTTP connections, but each batch = 20 tickers parallel server-side
// → 6 batches × 20 tickers = 120 tickers processing simultaneously!
async function fetchTickersParallel(tickers, alpha, startDate, onProgress) {
    const results = {};
    let okCount = 0, errCount = 0;
    const startTime = Date.now();
    const batchSize = getBatchSize();
    const maxWorkers = getConcurrency();
    const MAX_CONCURRENT_BATCHES = 6; // browser HTTP limit

    // Split into batches
    const batches = [];
    for (let i = 0; i < tickers.length; i += batchSize) {
        batches.push(tickers.slice(i, i + batchSize));
    }

    let doneTickers = 0;
    const batchQueue = [...batches];

    console.log(`[STABLE Lab] ${tickers.length} tickers → ${batches.length} batches (${batchSize}/batch, ${MAX_CONCURRENT_BATCHES} concurrent, ${maxWorkers} server threads)`);

    function updateProgress(label) {
        if (!onProgress) return;
        const elapsed = (Date.now() - startTime) / 1000;
        const avgPer = doneTickers > 0 ? elapsed / doneTickers : 2;
        const remaining = avgPer * (tickers.length - doneTickers);
        const mins = Math.floor(remaining / 60);
        const secs = Math.floor(remaining % 60);
        onProgress(label, doneTickers, tickers.length, okCount, errCount, `${mins}m ${secs}s`);
    }

    // Process a single batch and update results
    async function processBatch(batch) {
        const label = batch.length <= 3 ? batch.join(',') : `${batch[0]}..${batch[batch.length-1]}`;
        try {
            const data = await fetchBatch(batch, alpha, startDate, maxWorkers);

            if (data.results) {
                for (const [t, r] of Object.entries(data.results)) {
                    results[t] = {
                        dates: r.dates || [],
                        prices: r.prices || [],
                        slopes: r.stable_slope || [],
                        pot: r.pot || [],
                        fund: r.fundamental || []
                    };
                    okCount++;
                    const chip = document.getElementById('chip-' + t);
                    if (chip) { chip.style.background = '#2a4030'; chip.style.borderColor = '#00ff88'; chip.style.color = '#00ff88'; }
                }
            }
            if (data.errors) {
                for (const [t, err] of Object.entries(data.errors)) {
                    errCount++;
                    console.warn(`[STABLE Lab] Error ${t}: ${err}`);
                    const chip = document.getElementById('chip-' + t);
                    if (chip) {
                        chip.style.background = '#402a2a'; chip.style.borderColor = '#ff4444';
                        chip.style.color = '#ff4444'; chip.title = err;
                    }
                }
            }
        } catch (err) {
            console.error(`[STABLE Lab] Batch failed: ${label}`, err);
            for (const t of batch) {
                errCount++;
                const chip = document.getElementById('chip-' + t);
                if (chip) {
                    chip.style.background = '#402a2a'; chip.style.borderColor = '#ff4444';
                    chip.style.color = '#ff4444'; chip.title = 'Batch error: ' + err.message;
                }
            }
        }
        doneTickers += batch.length;
        updateProgress(label);
    }

    // Worker pool: run up to MAX_CONCURRENT_BATCHES in parallel
    async function batchWorker() {
        while (batchQueue.length > 0) {
            const batch = batchQueue.shift();
            await processBatch(batch);
        }
    }

    const nWorkers = Math.min(MAX_CONCURRENT_BATCHES, batches.length);
    const workers = [];
    for (let w = 0; w < nWorkers; w++) {
        workers.push(batchWorker());
    }
    await Promise.all(workers);

    const totalTime = ((Date.now() - startTime) / 1000).toFixed(0);
    console.log(`[STABLE Lab] Fetch complete: ${okCount} OK, ${errCount} errors in ${totalTime}s`);
    return { results, okCount, errCount, totalTime };
}

// ============================================================
//  MAIN ANALYSIS (parallel)
// ============================================================

async function runAnalysis() {
    if (RUNNING) return;
    const tickers = getTickerList();
    if (tickers.length === 0) { setStatus('Inserisci almeno un ticker.'); return; }

    RUNNING = true;
    const btn = document.getElementById('btn-run');
    btn.disabled = true;
    btn.textContent = '⏳ Loading...';

    const entryTh = parseFloat(document.getElementById('param-entry').value) || 0;
    const exitTh = parseFloat(document.getElementById('param-exit').value) || 0;
    const alpha = parseFloat(document.getElementById('param-alpha').value) || 200;
    const startDate = document.getElementById('param-start').value || '2023-01-01';
    const mode = document.getElementById('param-mode').value || 'LONG';
    const strategy = document.getElementById('param-strategy')?.value || 'STABLE';
    const entryZ = parseFloat(document.getElementById('param-entryz')?.value) || 2.0;
    const horizon = parseInt(document.getElementById('param-horizon')?.value) || 21;
    const endDate = getEndDate();

    renderChips(tickers);
    for (const k of Object.keys(RESULTS)) delete RESULTS[k];

    const { results, okCount, errCount, totalTime } = await fetchTickersParallel(
        tickers, alpha, startDate,
        (t, done, total, ok, err, eta) => {
            setStatus(`[${strategy}] Batch ${t} (${done}/${total}) — ✅ ${ok} ❌ ${err} — ETA ${eta} [${getBatchSize()}x batch, ${getConcurrency()} threads]`);
            setProgress((done / total * 100).toFixed(0));
        }
    );

    // Run backtest on all fetched data (motore unificato, t+1 + costi)
    let btErrors = 0, totalOnsets = 0;
    for (const [t, r] of Object.entries(results)) {
        try {
            const bt = runLabBacktest(strategy, r, { entryTh, exitTh, mode, entryZ, horizon, endDate });
            if (bt.n_onsets != null) totalOnsets += bt.n_onsets;
            RESULTS[t] = { ...r, backtest: bt };
        } catch (e) {
            btErrors++;
            console.warn(`[STABLE Lab] Backtest ${t} fallito:`, e.message);
        }
    }

    setProgress(100);
    setTimeout(() => setProgress(0), 800);
    btn.disabled = false;
    btn.textContent = '▶ Analizza';
    RUNNING = false;

    const onsetsLabel = (strategy !== 'STABLE') ? ` — 🟠 ${totalOnsets} onset potenziale` : '';
    const rangeLabel = endDate ? ` [${startDate} → ${endDate}]` : '';
    setStatus(`[${strategy}${strategy === 'STABLE' ? '/' + mode : ''}] Completato in ${totalTime}s — ✅ ${okCount} OK, ❌ ${errCount + btErrors} errori su ${tickers.length} tickers${onsetsLabel}${rangeLabel}`);
    renderAll(entryTh, exitTh);
}

// ============================================================
//  RENDER ALL
// ============================================================

function renderAll(entryTh, exitTh) {
    renderEquityChart();
    renderSlopesChart();
    renderSummaryCards();
    renderTradesTable();
    renderComparisonChart();
    renderComparisonTable();
    populateTradesFilter();
}

// --- EQUITY CHART ---
function renderEquityChart() {
    const traces = [];
    const colors = ['#aa44ff','#00ff88','#ff9900','#00e5ff','#ff4444','#3366ff','#ffff00','#ff66cc','#88ff00','#ff8800'];
    const nTickers = Object.keys(RESULTS).length;

    let i = 0;
    for (const [ticker, r] of Object.entries(RESULTS)) {
        traces.push({
            x: r.dates,
            y: r.backtest.equity,
            name: `${ticker} (${r.backtest.stats.total_return > 0 ? '+' : ''}${r.backtest.stats.total_return}%)`,
            type: 'scatter',
            mode: 'lines',
            line: { color: colors[i % colors.length], width: 1.5 },
            opacity: nTickers > 5 ? 0.3 : 0.8  // Fade individual lines when many tickers
        });
        i++;
    }

    // PORTAFOGLIO EQUIPONDERATO (media di tutte le equity curves)
    if (nTickers > 1) {
        const portfolio = computeEqualWeightPortfolio();
        traces.push({
            x: portfolio.dates,
            y: portfolio.equity,
            name: `📊 PORTAFOGLIO EW (${portfolio.finalReturn >= 0 ? '+' : ''}${portfolio.finalReturn.toFixed(1)}%)`,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#FFD700', width: 3.5 },
            opacity: 1
        });
    }

    // Zero line
    if (traces.length > 0) {
        traces.push({
            x: [traces[0].x[0], traces[0].x[traces[0].x.length - 1]],
            y: [0, 0],
            name: 'Zero',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#444', width: 1, dash: 'dash' },
            showlegend: false
        });
    }

    Plotly.newPlot('chart-equity', traces, {
        title: { text: 'Equity Curves + Portafoglio Equal-Weight', font: { color: '#ccc', size: 14 } },
        paper_bgcolor: '#1a1d29',
        plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { gridcolor: '#252836', showgrid: true },
        yaxis: { gridcolor: '#252836', showgrid: true, title: 'P/L %', zeroline: true, zerolinecolor: '#444' },
        legend: { orientation: 'h', y: -0.15, font: { size: 11 } },
        margin: { t: 40, b: 60, l: 50, r: 20 },
        hovermode: 'x unified'
    }, { responsive: true });
}

// --- SLOPES CHART ---
function renderSlopesChart() {
    const traces = [];
    const colors = ['#aa44ff','#00ff88','#ff9900','#00e5ff','#ff4444','#3366ff','#ffff00','#ff66cc'];

    let i = 0;
    for (const [ticker, r] of Object.entries(RESULTS)) {
        traces.push({
            x: r.dates,
            y: r.slopes,
            name: ticker,
            type: 'scatter',
            mode: 'lines',
            line: { color: colors[i % colors.length], width: 1.5 }
        });
        i++;
    }

    // Zero ref line
    if (traces.length > 0) {
        traces.push({
            x: [traces[0].x[0], traces[0].x[traces[0].x.length - 1]],
            y: [0, 0],
            name: 'Soglia 0',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#888', width: 1, dash: 'dot' },
            showlegend: false
        });
    }

    Plotly.newPlot('chart-slopes', traces, {
        title: { text: 'Stable Slope (segnale strategia)', font: { color: '#ccc', size: 13 } },
        paper_bgcolor: '#1a1d29',
        plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { gridcolor: '#252836' },
        yaxis: { gridcolor: '#252836', zeroline: true, zerolinecolor: '#666' },
        legend: { orientation: 'h', y: -0.2, font: { size: 10 } },
        margin: { t: 35, b: 50, l: 50, r: 20 },
        hovermode: 'x unified'
    }, { responsive: true });
}

// --- EQUAL-WEIGHT PORTFOLIO (media di tutte le equity curves) ---
// Ogni ticker pesa "1" come se costasse 100. Calcola la media giornaliera.
function computeEqualWeightPortfolio() {
    const tickers = Object.keys(RESULTS);
    if (tickers.length === 0) return { dates: [], equity: [], finalReturn: 0, maxDD: 0 };

    // Collect all dates across all tickers into a sorted union
    const dateSet = new Set();
    for (const t of tickers) {
        for (const d of RESULTS[t].dates) dateSet.add(d);
    }
    const allDates = [...dateSet].sort();

    // For each date, average the equity % of all tickers that have data for that date
    const avgEquity = [];
    let maxEq = 0, maxDD = 0;

    for (const date of allDates) {
        let sum = 0, count = 0;
        for (const t of tickers) {
            const r = RESULTS[t];
            const idx = r.dates.indexOf(date);
            if (idx >= 0 && idx < r.backtest.equity.length) {
                sum += r.backtest.equity[idx];
                count++;
            }
        }
        const avg = count > 0 ? sum / count : (avgEquity.length > 0 ? avgEquity[avgEquity.length - 1] : 0);
        avgEquity.push(+avg.toFixed(2));

        // Track max drawdown of the portfolio
        if (avg > maxEq) maxEq = avg;
        const dd = maxEq > 0 ? ((maxEq - avg) / (100 + maxEq)) * 100 : 0;
        if (dd > maxDD) maxDD = dd;
    }

    const finalReturn = avgEquity.length > 0 ? avgEquity[avgEquity.length - 1] : 0;
    return { dates: allDates, equity: avgEquity, finalReturn, maxDD };
}

// --- SUMMARY CARDS ---
function renderSummaryCards() {
    const div = document.getElementById('summary-cards');
    const tickers = Object.keys(RESULTS);
    if (tickers.length === 0) { div.innerHTML = ''; return; }

    // Portfolio equiponderato (media delle equity curves) per chart e Max DD
    const portfolio = computeEqualWeightPortfolio();

    // Media dei total_return per ticker (corrisponde alla media della colonna Return in Excel)
    const stats = tickers.map(t => RESULTS[t].backtest.stats);
    const avgReturn = stats.reduce((s, st) => s + st.total_return, 0) / stats.length;
    const avgWR = stats.reduce((s, st) => s + st.win_rate, 0) / stats.length;
    const totalTrades = stats.reduce((s, st) => s + st.total_trades, 0);
    const positivi = stats.filter(st => st.total_return > 0).length;
    // Benchmark: media buy & hold e differenza strategia - B&H
    const avgBH = stats.reduce((s, st) => s + (st.buy_hold_return || 0), 0) / stats.length;
    const vsBH = avgReturn - avgBH;

    const c = (v) => v >= 0 ? 'pos' : 'neg';

    div.innerHTML = `
        <div class="card"><div class="label">Return Medio</div><div class="value ${c(avgReturn)}">${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Buy&Hold Medio</div><div class="value ${c(avgBH)}">${avgBH >= 0 ? '+' : ''}${avgBH.toFixed(1)}%</div></div>
        <div class="card" title="Return strategia meno Buy&Hold: se negativo, comprare e tenere avrebbe reso di più"><div class="label">vs Buy&Hold</div><div class="value ${c(vsBH)}">${vsBH >= 0 ? '+' : ''}${vsBH.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Win Rate Medio</div><div class="value">${avgWR.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Trades Totali</div><div class="value">${totalTrades}</div></div>
        <div class="card"><div class="label">Max DD Portaf.</div><div class="value neg">-${portfolio.maxDD.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Tickers Positivi</div><div class="value ${positivi > tickers.length / 2 ? 'pos' : 'neg'}">${positivi}/${tickers.length}</div></div>
    `;
}

// --- TRADES TABLE ---
function populateTradesFilter() {
    const sel = document.getElementById('trades-filter');
    sel.innerHTML = '<option value="ALL">Tutti</option>';
    for (const t of Object.keys(RESULTS)) {
        sel.innerHTML += `<option value="${t}">${t}</option>`;
    }
}

function renderTradesTable() {
    const filter = document.getElementById('trades-filter').value;
    const tbody = document.getElementById('trades-body');
    let allTrades = [];

    for (const [ticker, r] of Object.entries(RESULTS)) {
        if (filter !== 'ALL' && filter !== ticker) continue;
        r.backtest.trades.forEach(t => allTrades.push({ ticker, ...t }));
    }

    // Reverse: newest first
    allTrades.reverse();

    tbody.innerHTML = allTrades.map(t => {
        const isOpen = t.exit_date === 'OPEN';
        const pnlCls = t.pnl_pct >= 0 ? 'pos' : 'neg';
        const sign = t.pnl_pct >= 0 ? '+' : '';
        return `<tr>
            <td style="font-weight:600;">${t.ticker}</td>
            <td>${t.entry_date}</td>
            <td>${isOpen ? '<span style="color:#ff9900;">⚠ OPEN</span>' : t.exit_date}</td>
            <td>${t.direction === 'SHORT' ? '🔴' : '🟢'} ${t.direction}</td>
            <td style="text-align:right;">${t.entry_price}</td>
            <td style="text-align:right;">${t.exit_price}</td>
            <td style="text-align:right;" class="${pnlCls}">${sign}${t.pnl_pct}%</td>
            <td style="text-align:right;">${t.capital_after}</td>
        </tr>`;
    }).join('');

    if (allTrades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#888; padding:30px;">Nessun trade</td></tr>';
    }
}

// --- COMPARISON CHART ---
function renderComparisonChart() {
    const tickers = Object.keys(RESULTS);
    const returns = tickers.map(t => RESULTS[t].backtest.stats.total_return);
    const colors = returns.map(r => r >= 0 ? '#00ff88' : '#ff4444');

    Plotly.newPlot('chart-comparison', [{
        x: tickers,
        y: returns,
        type: 'bar',
        marker: { color: colors, line: { color: '#fff', width: 0.5 } },
        text: returns.map(r => (r >= 0 ? '+' : '') + r.toFixed(1) + '%'),
        textposition: 'outside',
        textfont: { size: 12, color: '#ccc' }
    }], {
        title: { text: 'Return per Ticker', font: { color: '#ccc', size: 14 } },
        paper_bgcolor: '#1a1d29',
        plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { gridcolor: '#252836' },
        yaxis: { gridcolor: '#252836', title: 'Return %', zeroline: true, zerolinecolor: '#666' },
        margin: { t: 40, b: 40, l: 50, r: 20 }
    }, { responsive: true });
}

// --- COMPARISON TABLE ---
function renderComparisonTable() {
    const tbody = document.getElementById('comparison-body');

    // Sort by return descending
    const sorted = Object.entries(RESULTS)
        .sort((a, b) => b[1].backtest.stats.total_return - a[1].backtest.stats.total_return);

    tbody.innerHTML = sorted.map(([ticker, r]) => {
        const s = r.backtest.stats;
        const retCls = s.total_return >= 0 ? 'pos' : 'neg';
        const retSign = s.total_return >= 0 ? '+' : '';
        const bh = s.buy_hold_return != null ? s.buy_hold_return : 0;
        const vsBh = s.total_return - bh;
        const vsCls = vsBh >= 0 ? 'pos' : 'neg';
        const bhSign = bh >= 0 ? '+' : '';
        const vsSign = vsBh >= 0 ? '+' : '';
        return `<tr>
            <td style="font-weight:600;">${ticker}</td>
            <td style="text-align:right;" class="${retCls}">${retSign}${s.total_return}%</td>
            <td style="text-align:right;">${bhSign}${bh}%</td>
            <td style="text-align:right;" class="${vsCls}">${vsSign}${vsBh.toFixed(1)}%</td>
            <td style="text-align:right;">${s.win_rate}%</td>
            <td style="text-align:right;">${s.total_trades}</td>
            <td style="text-align:right;">${s.avg_trade}%</td>
            <td style="text-align:right; color:#ff4444;">-${s.max_drawdown}%</td>
            <td style="text-align:right;">${s.profit_factor}</td>
            <td style="text-align:right;">${s.sharpe != null ? s.sharpe : '-'}</td>
            <td style="text-align:right;">${s.exposure_pct != null ? s.exposure_pct : '-'}%</td>
            <td style="text-align:right;">$${s.final_capital}</td>
        </tr>`;
    }).join('');
}

// ============================================================
//  OPTIMIZER (with Alpha grid search)
// ============================================================

// Global: stores all optimizer results for browsing
let OPT_STORE = {}; // { alpha: { entryRange, exitRange, zData, gridResults, best } }
let OPT_GLOBAL_BEST = null;
let OPT_ALL_RESULTS = []; // flat list of all grid results across all alphas

// Train fraction for the optimizer OOS split (default 70%)
function getTrainFrac() {
    const v = parseFloat(document.getElementById('param-oos')?.value);
    if (!Number.isFinite(v)) return 0.7;
    return Math.min(0.95, Math.max(0.3, v / 100));
}

// Grid search for a single alpha's tickerData (synchronous, with async yield)
// VALIDAZIONE OUT-OF-SAMPLE: i parametri si scelgono sul segmento TRAIN
// (primi trainFrac% del periodo), ma il numero che conta è il ritorno OOS
// sul segmento successivo, MAI visto durante la scelta dei parametri.
async function runGridSearch(tickerData, entryRange, exitRange, mode, alphaLabel, progressBase, progressSpan, trainFrac) {
    const validTickers = Object.keys(tickerData).filter(t => {
        const d = tickerData[t];
        if (!d || !d.dates || !d.prices || !d.slopes) return false;
        if (d.slopes.length === 0 || d.dates.length === 0) return false;
        return true;
    });

    const nTickers = validTickers.length;
    if (nTickers === 0) return { gridResults: [], zData: [], nTickers: 0, splitDate: null };

    // Data di split globale: al trainFrac% del calendario unione
    const dateSet = new Set();
    for (const t of validTickers) for (const d of tickerData[t].dates) dateSet.add(d);
    const allDates = [...dateSet].sort();
    const splitIdx = Math.min(allDates.length - 1, Math.floor(allDates.length * (trainFrac != null ? trainFrac : 0.7)));
    const splitDate = allDates[splitIdx];
    const trainEnd = splitIdx > 0 ? allDates[splitIdx - 1] : allDates[0];

    const gridResults = [];
    const zData = [];

    await new Promise((resolve, reject) => {
        let ei = 0;
        function processRow() {
            try {
                const row = [];
                const entry = entryRange[ei];
                for (let xi = 0; xi < exitRange.length; xi++) {
                    const exit = exitRange[xi];
                    let sumReturn = 0, sumWR = 0, sumTrades = 0, nPositive = 0, count = 0;
                    let sumOOS = 0, oosPositive = 0, oosCount = 0;
                    for (const t of validTickers) {
                        try {
                            const d = tickerData[t];
                            // TRAIN: fino al giorno prima dello split
                            const btTrain = runStableBacktest(d.dates, d.prices, d.slopes, entry, exit, mode, { endDate: trainEnd });
                            sumReturn += btTrain.stats.total_return;
                            sumWR += btTrain.stats.win_rate;
                            sumTrades += btTrain.stats.total_trades;
                            if (btTrain.stats.total_return > 0) nPositive++;
                            count++;
                            // OOS: dallo split in poi (mai visto in ottimizzazione)
                            const btOOS = runStableBacktest(d.dates, d.prices, d.slopes, entry, exit, mode, { startDate: splitDate });
                            sumOOS += btOOS.stats.total_return;
                            if (btOOS.stats.total_return > 0) oosPositive++;
                            oosCount++;
                        } catch (e) { /* skip */ }
                    }
                    const avgRet = count > 0 ? sumReturn / count : 0;
                    const avgOOS = oosCount > 0 ? sumOOS / oosCount : 0;
                    row.push(+avgRet.toFixed(2));
                    gridResults.push({
                        alpha: alphaLabel, entry, exit,
                        avgReturn: +avgRet.toFixed(2),
                        oosReturn: +avgOOS.toFixed(2),
                        oosPositive,
                        avgWR: count > 0 ? +(sumWR / count).toFixed(1) : 0,
                        avgTrades: count > 0 ? +(sumTrades / count).toFixed(0) : 0,
                        nPositive, total: count
                    });
                }
                zData.push(row);
                ei++;
                const pct = progressBase + (ei / entryRange.length) * progressSpan;
                setProgress(pct.toFixed(0));
                setStatus(`[α=${alphaLabel}] Grid: riga ${ei}/${entryRange.length} (Entry=${entry}) — ${nTickers} tickers (train fino a ${trainEnd}, OOS da ${splitDate})`);
                if (ei < entryRange.length) {
                    setTimeout(processRow, 0);
                } else {
                    resolve();
                }
            } catch (err) {
                console.error(`[Optimizer] Row error α=${alphaLabel}:`, err);
                reject(err);
            }
        }
        processRow();
    });

    return { gridResults, zData, nTickers, splitDate };
}

async function runOptimizer() {
    if (RUNNING) return;
    const strategySel = document.getElementById('param-strategy')?.value || 'STABLE';
    if (strategySel !== 'STABLE') {
        setStatus('🔍 L\'optimizer grid-search è per la strategia STABLE. Per ARANCIONE/COMBO usa i parametri robusti (Entry Z 1.5-2.5, Hold 10-42) e valida con End Date (train) vs periodo successivo (OOS).');
        return;
    }
    const tickers = getTickerList();
    if (tickers.length === 0) { setStatus('Inserisci almeno un ticker per ottimizzare.'); return; }

    RUNNING = true;
    const btn = document.getElementById('btn-opt');
    btn.disabled = true;
    btn.textContent = '⏳ Ottimizzazione...';

    const startDate = document.getElementById('param-start').value || '2023-01-01';
    const mode = document.getElementById('param-mode').value || 'LONG';

    // Build Alpha range
    const alphaMin = parseFloat(document.getElementById('param-alpha-min').value) || 100;
    const alphaMax = parseFloat(document.getElementById('param-alpha-max').value) || 400;
    const alphaStep = parseFloat(document.getElementById('param-alpha-step').value) || 50;
    const alphaRange = [];
    for (let a = alphaMin; a <= alphaMax; a += alphaStep) alphaRange.push(+a.toFixed(0));
    if (alphaRange.length === 0) alphaRange.push(200); // fallback

    const entryRange = [];
    for (let e = -1.5; e <= 1.5; e += 0.1) entryRange.push(+e.toFixed(1));
    const exitRange = [];
    for (let x = -1.5; x <= 1.5; x += 0.1) exitRange.push(+x.toFixed(1));

    const totalCombos = entryRange.length * exitRange.length * alphaRange.length;
    console.log(`[Optimizer] ${alphaRange.length} alphas × ${entryRange.length * exitRange.length} combos × ${tickers.length} tickers`);

    renderChips(tickers);
    OPT_STORE = {};
    OPT_ALL_RESULTS = [];
    OPT_GLOBAL_BEST = null;

    const progressPerAlpha = 100 / alphaRange.length;

    for (let ai = 0; ai < alphaRange.length; ai++) {
        const alpha = alphaRange[ai];
        const pBase = ai * progressPerAlpha;

        // === FETCH PHASE for this Alpha ===
        setStatus(`[α=${alpha}] Fase 1: Scaricamento dati (${ai + 1}/${alphaRange.length} alpha)...`);

        const { results, okCount, errCount } = await fetchTickersParallel(
            tickers, alpha, startDate,
            (t, done, total, ok, err, eta) => {
                setStatus(`[α=${alpha}] Fetch: ${t} (${done}/${total}) — ✅ ${ok} ❌ ${err} — ETA ${eta}`);
                setProgress((pBase + (done / total) * progressPerAlpha * 0.5).toFixed(0));
            }
        );

        if (okCount === 0) {
            console.warn(`[Optimizer] α=${alpha}: no valid tickers, skipping`);
            continue;
        }

        // === GRID SEARCH for this Alpha ===
        const gridBase = pBase + progressPerAlpha * 0.5;
        const gridSpan = progressPerAlpha * 0.5;

        try {
            const { gridResults, zData, nTickers, splitDate } = await runGridSearch(
                results, entryRange, exitRange, mode, alpha, gridBase, gridSpan, getTrainFrac()
            );

            if (gridResults.length === 0) continue;

            // La scelta dei parametri avviene sul TRAIN (avgReturn);
            // oosReturn è la verifica onesta sul periodo mai visto.
            const sorted = [...gridResults].sort((a, b) => b.avgReturn - a.avgReturn);
            const best = sorted[0];

            OPT_STORE[alpha] = { entryRange, exitRange, zData, gridResults: sorted, best, nTickers, splitDate };
            OPT_ALL_RESULTS.push(...gridResults);

            if (!OPT_GLOBAL_BEST || best.avgReturn > OPT_GLOBAL_BEST.avgReturn) {
                OPT_GLOBAL_BEST = best;
            }

            console.log(`[Optimizer] α=${alpha}: Best Entry>${best.entry} Exit<${best.exit} → Train ${best.avgReturn}% | OOS ${best.oosReturn}% (${nTickers} tickers, split ${splitDate})`);
        } catch (err) {
            console.error(`[Optimizer] Grid search failed for α=${alpha}:`, err);
        }
    }

    setProgress(100);
    setTimeout(() => setProgress(0), 800);

    if (!OPT_GLOBAL_BEST) {
        setStatus('❌ Nessun risultato dall\'ottimizzazione.');
        btn.disabled = false;
        btn.textContent = '🔍 Ottimizza';
        RUNNING = false;
        return;
    }

    // Render Alpha selector buttons
    renderAlphaSelector(alphaRange);

    // Show best alpha's heatmap
    showAlphaHeatmap(OPT_GLOBAL_BEST.alpha);

    // Render global top 10 (across all alphas)
    OPT_ALL_RESULTS.sort((a, b) => b.avgReturn - a.avgReturn);
    renderOptTable(OPT_ALL_RESULTS.slice(0, 15));

    btn.disabled = false;
    btn.textContent = '🔍 Ottimizza';
    RUNNING = false;

    const gb = OPT_GLOBAL_BEST;
    setStatus(`[${mode}] Ottimizzazione completa! BEST (su train): α=${gb.alpha} Entry>${gb.entry} Exit<${gb.exit} → Train ${gb.avgReturn}% | ✅ OOS ${gb.oosReturn}% | WR ${gb.avgWR}%`);
    switchTab('optimizer');
}

// Render Alpha selector buttons
function renderAlphaSelector(alphaRange) {
    const container = document.getElementById('alpha-selector');
    const btnDiv = document.getElementById('alpha-buttons');
    container.style.display = 'flex';

    btnDiv.innerHTML = alphaRange.map(a => {
        const hasData = !!OPT_STORE[a];
        const isBest = OPT_GLOBAL_BEST && OPT_GLOBAL_BEST.alpha === a;
        const bestRet = hasData ? OPT_STORE[a].best.avgReturn : 0;
        const color = isBest ? 'var(--green)' : (hasData ? 'var(--purple)' : '#555');
        const border = isBest ? 'var(--green)' : 'var(--border)';
        return `<button onclick="showAlphaHeatmap(${a})" style="
            padding:6px 14px; border-radius:6px; border:1px solid ${border};
            background:${isBest ? 'rgba(0,255,136,0.15)' : '#252836'};
            color:${color}; cursor:pointer; font-family:inherit; font-weight:600; font-size:0.85rem;
        " title="Avg Return: ${bestRet}%">
            α=${a}${isBest ? ' ★' : ''}
        </button>`;
    }).join('');
}

// Show heatmap for a specific alpha
function showAlphaHeatmap(alpha) {
    const data = OPT_STORE[alpha];
    if (!data) {
        console.warn(`[Optimizer] No data for α=${alpha}`);
        return;
    }

    // Update button styles
    document.querySelectorAll('#alpha-buttons button').forEach(btn => {
        const isActive = btn.textContent.includes(`α=${alpha}`);
        btn.style.borderColor = isActive ? 'var(--cyan)' : 'var(--border)';
        btn.style.background = isActive ? 'rgba(0,229,255,0.15)' : '#252836';
    });

    renderHeatmap(data.entryRange, data.exitRange, data.zData, data.best, alpha);
}

function renderHeatmap(entryRange, exitRange, zData, best, alpha) {
    const info = document.getElementById('opt-info');
    const alphaLabel = alpha != null ? `α=${alpha} | ` : '';
    const splitDate = OPT_STORE[alpha]?.splitDate;
    const oosCls = (best.oosReturn != null && best.oosReturn >= 0) ? 'pos' : 'neg';
    info.innerHTML = `
        <span>Migliore per questo Alpha (scelto sul train):</span>
        <span class="best">${alphaLabel}Entry > ${best.entry} | Exit < ${best.exit} → Train ${best.avgReturn >= 0 ? '+' : ''}${best.avgReturn}% | WR ${best.avgWR}% | ${best.nPositive}/${best.total} positivi</span>
        <span style="font-weight:700;" class="${oosCls}">OOS${splitDate ? ' (da ' + splitDate + ')' : ''}: ${best.oosReturn >= 0 ? '+' : ''}${best.oosReturn != null ? best.oosReturn : '?'}% — questo è il numero che conta</span>
    `;

    const textData = zData.map(row => row.map(v => {
        if (v === 0) return '0';
        return (v >= 0 ? '+' : '') + v.toFixed(0) + '%';
    }));

    Plotly.newPlot('chart-heatmap', [{
        z: zData,
        x: exitRange.map(v => 'Exit ' + v),
        y: entryRange.map(v => 'Entry ' + v),
        type: 'heatmap',
        text: textData,
        texttemplate: '%{text}',
        textfont: { size: 10 },
        hovertemplate: 'Entry > %{y}<br>Exit < %{x}<br>Avg Return: %{z:.1f}%<extra></extra>',
        colorscale: [
            [0,    '#8B0000'],
            [0.15, '#CC3333'],
            [0.3,  '#DD6633'],
            [0.42, '#DDAA33'],
            [0.48, '#666655'],
            [0.52, '#556655'],
            [0.58, '#33AA66'],
            [0.7,  '#228855'],
            [0.85, '#1166AA'],
            [1,    '#0044DD']
        ],
        zmid: 0,
        colorbar: {
            title: { text: 'Avg Return %', font: { color: '#aaa' } },
            tickfont: { color: '#aaa' },
            outlinecolor: '#333',
            bordercolor: '#333'
        }
    }], {
        title: { text: `Heatmap: Avg Return % (α=${alpha || '?'})`, font: { color: '#ccc', size: 14 } },
        paper_bgcolor: '#1a1d29',
        plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { title: 'Exit Threshold', side: 'bottom', tickfont: { size: 11 } },
        yaxis: { title: 'Entry Threshold', tickfont: { size: 11 } },
        margin: { t: 40, b: 60, l: 80, r: 20 }
    }, { responsive: true });
}

function renderOptTable(topN) {
    const tbody = document.getElementById('opt-body');
    tbody.innerHTML = topN.map((r, i) => {
        const cls = r.avgReturn >= 0 ? 'pos' : 'neg';
        const sign = r.avgReturn >= 0 ? '+' : '';
        const oos = r.oosReturn != null ? r.oosReturn : 0;
        const oosCls = oos >= 0 ? 'pos' : 'neg';
        const oosSign = oos >= 0 ? '+' : '';
        const medal = i === 0 ? '🥇 ' : i === 1 ? '🥈 ' : i === 2 ? '🥉 ' : '';
        const isBest = OPT_GLOBAL_BEST && r.alpha === OPT_GLOBAL_BEST.alpha && r.entry === OPT_GLOBAL_BEST.entry && r.exit === OPT_GLOBAL_BEST.exit;
        const rowStyle = isBest ? 'background:rgba(0,255,136,0.08);' : '';
        return `<tr style="${rowStyle}">
            <td style="font-weight:600; color:var(--cyan);">${medal}${r.alpha}</td>
            <td>${r.entry}</td>
            <td>${r.exit}</td>
            <td style="text-align:right;" class="${cls}">${sign}${r.avgReturn}%</td>
            <td style="text-align:right; font-weight:700;" class="${oosCls}">${oosSign}${oos}%</td>
            <td style="text-align:right;">${r.oosPositive != null ? r.oosPositive : '-'}/${r.total}</td>
            <td style="text-align:right;">${r.avgWR}%</td>
            <td style="text-align:right;">${r.avgTrades}</td>
            <td style="text-align:right;">${r.nPositive}/${r.total}</td>
        </tr>`;
    }).join('');
}

// ============================================================
//  INIT
// ============================================================

// ============================================================
//  FORWARD TEST (monitor journal) + SIMULATORE DI INVESTIMENTO
// ============================================================

let FWD_JOURNAL = null;

async function loadForwardStatus() {
    try {
        setStatus('Caricamento forward test...');
        const resp = await fetch(`${API_BASE}/forward-test/status`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        FWD_JOURNAL = await resp.json();
        renderForward();
        setStatus('✅ Forward test aggiornato.');
    } catch (e) {
        console.error('forward status:', e);
        document.getElementById('fwd-info').textContent = `❌ Errore: ${e.message} (backend attivo?)`;
        setStatus(`❌ Forward test: ${e.message}`);
    }
}

async function resetForwardJournal() {
    if (!confirm('Archiviare il journal corrente e ripartire da zero?\n(Il file attuale viene rinominato, non cancellato)')) return;
    try {
        const resp = await fetch(`${API_BASE}/forward-test/reset`, { method: 'POST' });
        const data = await resp.json();
        setStatus(`🗑 Journal archiviato${data.archived ? ': ' + data.archived : ''}. Riparte col prossimo scan.`);
        loadForwardStatus();
    } catch (e) {
        setStatus(`❌ Reset fallito: ${e.message}`);
    }
}

function renderForward() {
    const stats = FWD_JOURNAL?.stats || {};
    const trades = FWD_JOURNAL?.trades || [];
    const info = document.getElementById('fwd-info');
    info.textContent = trades.length === 0
        ? 'Journal vuoto: si popola automaticamente a ogni scan email (22:30). Nessun dato retroattivo, solo segnali reali da oggi in poi.'
        : `Journal dal ${stats.created} — ${trades.length} segnali registrati.`;

    const c = (v) => v >= 0 ? 'pos' : 'neg';
    document.getElementById('fwd-cards').innerHTML = `
        <div class="card"><div class="label">Inizio</div><div class="value" style="font-size:1rem;">${stats.created || '-'}</div></div>
        <div class="card"><div class="label">In ingresso</div><div class="value">${stats.pending ?? 0}</div></div>
        <div class="card"><div class="label">Aperti</div><div class="value">${stats.open ?? 0}</div></div>
        <div class="card"><div class="label">Chiusi</div><div class="value">${stats.closed ?? 0}</div></div>
        <div class="card"><div class="label">Somma P/L (quota fissa)</div><div class="value ${c(stats.sum_pnl_pct || 0)}">${(stats.sum_pnl_pct ?? 0) >= 0 ? '+' : ''}${stats.sum_pnl_pct ?? 0}%</div></div>
        <div class="card"><div class="label">Media / Trade</div><div class="value ${c(stats.avg_pnl_pct || 0)}">${(stats.avg_pnl_pct ?? 0) >= 0 ? '+' : ''}${stats.avg_pnl_pct ?? 0}%</div></div>
        <div class="card"><div class="label">Win Rate</div><div class="value">${stats.win_rate ?? 0}%</div></div>
        <div class="card"><div class="label">Aperti: P/L medio</div><div class="value ${c(stats.open_avg_pnl_pct || 0)}">${(stats.open_avg_pnl_pct ?? 0) >= 0 ? '+' : ''}${stats.open_avg_pnl_pct ?? 0}%</div></div>
    `;

    // tabella (più recenti in alto)
    const tbody = document.getElementById('fwd-body');
    const stCls = { pending: 'color:#ff9900;', open: 'color:var(--cyan);', closed: 'color:var(--text2);' };
    const stLbl = { pending: '⏳ ingresso t+1', open: '🔵 aperto', closed: '✔ chiuso' };
    tbody.innerHTML = [...trades].reverse().map(t => {
        const pnl = t.status === 'closed' ? t.pnl_pct : t.current_pnl_pct;
        const pnlCls = (pnl ?? 0) >= 0 ? 'pos' : 'neg';
        return `<tr>
            <td style="font-weight:600;">${t.ticker}</td>
            <td>${t.strategy || '-'}</td>
            <td>${t.direction === 'SHORT' ? '🔴' : '🟢'} ${t.direction}</td>
            <td>${t.signal_date}</td>
            <td>${t.entry_date || '-'}</td>
            <td style="text-align:right;">${t.entry_price != null ? t.entry_price.toFixed(2) : '-'}</td>
            <td style="text-align:right;">${t.bars_held ?? 0}/${t.horizon}</td>
            <td>${t.exit_date || '-'}</td>
            <td style="text-align:right;">${t.exit_price != null ? t.exit_price.toFixed(2) : '-'}</td>
            <td style="text-align:right;" class="${pnlCls}">${pnl != null ? (pnl >= 0 ? '+' : '') + pnl + '%' : '-'}</td>
            <td style="${stCls[t.status] || ''}">${stLbl[t.status] || t.status}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="11" style="text-align:center; color:#888; padding:24px;">Nessun trade ancora: il journal parte col primo segnale reale.</td></tr>';

    // curva P/L realizzata (quota fissa: cumsum dei pnl% per data di uscita)
    const closed = trades.filter(t => t.status === 'closed' && t.pnl_pct != null)
        .sort((a, b) => a.exit_date < b.exit_date ? -1 : 1);
    let cum = 0;
    const xs = [], ys = [];
    for (const t of closed) { cum += t.pnl_pct; xs.push(t.exit_date); ys.push(+cum.toFixed(2)); }
    const traces = [{
        x: xs, y: ys, type: 'scatter', mode: 'lines+markers',
        name: 'P/L realizzato cum. (quota fissa)', line: { color: '#00e5ff', width: 2 }
    }];
    const openSum = trades.filter(t => t.status === 'open' && t.current_pnl_pct != null)
        .reduce((s, t) => s + t.current_pnl_pct, 0);
    if (trades.some(t => t.status === 'open')) {
        traces.push({
            x: [xs.length ? xs[xs.length - 1] : (trades[0]?.signal_date), new Date().toISOString().slice(0, 10)],
            y: [ys.length ? ys[ys.length - 1] : 0, +(cum + openSum).toFixed(2)],
            type: 'scatter', mode: 'lines', name: 'con aperti (MTM)',
            line: { color: '#ff9900', width: 2, dash: 'dot' }
        });
    }
    Plotly.newPlot('chart-fwd-equity', traces, {
        title: { text: 'Forward test — P/L cumulato (ogni trade pesa 1)', font: { color: '#ccc', size: 13 } },
        paper_bgcolor: '#1a1d29', plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { gridcolor: '#252836' }, yaxis: { gridcolor: '#252836', title: 'P/L % cum.', zeroline: true, zerolinecolor: '#444' },
        legend: { orientation: 'h', y: -0.2, font: { size: 10 } },
        margin: { t: 35, b: 45, l: 55, r: 15 },
    }, { responsive: true });
}

// --- Simulatore di sizing ---
function collectSimTrades(source) {
    if (source === 'journal') {
        return (FWD_JOURNAL?.trades || [])
            .filter(t => t.status === 'closed' && t.pnl_pct != null)
            .map(t => ({ entry_date: t.entry_date, exit_date: t.exit_date, pnl_pct: t.pnl_pct }));
    }
    // backtest corrente: tutti i trade chiusi dei ticker analizzati
    const out = [];
    for (const r of Object.values(RESULTS)) {
        for (const t of (r.backtest?.trades || [])) {
            if (t.exit_date !== 'OPEN' && t.pnl_pct != null) {
                out.push({ entry_date: t.entry_date, exit_date: t.exit_date, pnl_pct: t.pnl_pct });
            }
        }
    }
    return out;
}

function runSizingSim() {
    const source = document.getElementById('sim-source').value;
    const capital = parseFloat(document.getElementById('sim-capital').value) || 10000;
    const stakePct = parseFloat(document.getElementById('sim-stake').value) || 10;
    const cap = parseInt(document.getElementById('sim-cap').value) || 10;

    const trades = collectSimTrades(source);
    if (trades.length === 0) {
        setStatus(source === 'journal'
            ? '🧪 Il journal non ha ancora trade chiusi: usa la fonte "Backtest corrente" (lancia prima un\'analisi).'
            : '📊 Nessun trade: lancia prima un\'analisi nel tab Analizza.');
        return;
    }

    const schemes = [
        { key: 'fixed_unlimited', label: `Quota fissa ${stakePct}% — SENZA tetto (riferimento, può servire leva)`, color: '#888888' },
        { key: 'fixed', label: `Quota fissa ${stakePct}% — max ${cap} posizioni`, color: '#00e5ff' },
        { key: 'compound', label: `Reinvestimento ${stakePct}% equity — max ${cap} posizioni`, color: '#00ff88' },
    ];

    const rows = [];
    const eqTraces = [], cashTraces = [];
    for (const s of schemes) {
        const r = simulateSizing(trades, { scheme: s.key, capital, stakePct, cap });
        rows.push(`<tr>
            <td style="color:${s.color}; font-weight:600;">${s.label}</td>
            <td style="text-align:right;">${r.finalCapital.toFixed(0)}</td>
            <td style="text-align:right;" class="${r.returnPct >= 0 ? 'pos' : 'neg'}">${r.returnPct >= 0 ? '+' : ''}${r.returnPct}%</td>
            <td style="text-align:right; color:var(--red);">-${r.maxDD}%</td>
            <td style="text-align:right;">${r.maxConcurrent}</td>
            <td style="text-align:right;">${r.skipped}</td>
        </tr>`);
        eqTraces.push({
            x: r.curve.map(p => p.date), y: r.curve.map(p => p.equity),
            name: s.label, type: 'scatter', mode: 'lines',
            line: { color: s.color, width: s.key === 'fixed_unlimited' ? 1 : 2, dash: s.key === 'fixed_unlimited' ? 'dot' : 'solid' },
        });
        cashTraces.push({
            x: r.curve.map(p => p.date), y: r.curve.map(p => p.invested),
            name: s.label, type: 'scatter', mode: 'lines', fill: s.key === 'fixed' ? 'tozeroy' : 'none',
            line: { color: s.color, width: 1.5, dash: s.key === 'fixed_unlimited' ? 'dot' : 'solid' },
        });
    }
    document.getElementById('sizing-body').innerHTML = rows.join('');

    const layout = (title, ytitle) => ({
        title: { text: title, font: { color: '#ccc', size: 13 } },
        paper_bgcolor: '#1a1d29', plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { gridcolor: '#252836' },
        yaxis: { gridcolor: '#252836', title: ytitle },
        legend: { orientation: 'h', y: -0.22, font: { size: 10 } },
        margin: { t: 35, b: 55, l: 60, r: 15 },
        hovermode: 'x unified',
    });
    Plotly.newPlot('chart-sizing-equity', eqTraces,
        layout(`Equity nel tempo — ${trades.length} trade (${source === 'journal' ? 'forward journal' : 'backtest corrente'})`, 'Capitale'),
        { responsive: true });
    Plotly.newPlot('chart-sizing-cash', cashTraces,
        layout('Flusso di cassa — capitale IMPEGNATO nel tempo (il resto è liquidità)', 'Capitale impegnato'),
        { responsive: true });

    setStatus(`💰 Simulazione su ${trades.length} trade chiusi (${source}).`);
}

// ============================================================
//  EMAIL ALERT CONFIG
// ============================================================

function updateAlertToggle() {
    const cb = document.getElementById('alert-enabled');
    const track = document.getElementById('alert-toggle-track');
    const knob = document.getElementById('alert-toggle-knob');
    const label = document.getElementById('alert-status-label');
    if (cb.checked) {
        track.style.background = 'var(--green)';
        knob.style.left = '27px';
        label.textContent = 'ON';
        label.style.color = 'var(--green)';
    } else {
        track.style.background = '#555';
        knob.style.left = '3px';
        label.textContent = 'OFF';
        label.style.color = '#888';
    }
}

function applyAlertPreset() {
    const sel = document.getElementById('alert-preset').value;
    const tickersInput = document.getElementById('alert-tickers');
    const countEl = document.getElementById('alert-ticker-count');

    if (sel === 'custom') {
        tickersInput.style.display = 'block';
        countEl.textContent = 'Inserisci i ticker separati da virgola';
        return;
    }

    buildDynamicPresets();
    const tickers = PRESETS[sel];
    if (tickers) {
        tickersInput.value = ''; // clear custom — will use preset
        countEl.textContent = `Preset "${sel}": ${tickers.length} tickers`;
    } else {
        countEl.textContent = `Preset "${sel}" — tutti i tickers da tickers.js`;
    }
}

async function loadAlertConfig() {
    try {
        setStatus('Caricamento configurazione alert...');
        const resp = await fetch(`${API_BASE}/stable-alert/config`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const cfg = data.config;

        // Populate form
        document.getElementById('alert-enabled').checked = cfg.enabled !== false;
        updateAlertToggle();
        document.getElementById('alert-hour').value = cfg.trigger_hour || 18;
        document.getElementById('alert-minute').value = cfg.trigger_minute || 0;
        document.getElementById('alert-mode').value = cfg.mode || 'LONG';
        document.getElementById('alert-entry').value = cfg.entry_threshold || 0;
        document.getElementById('alert-exit').value = cfg.exit_threshold || 0;
        document.getElementById('alert-alpha').value = cfg.alpha || 200;
        if (document.getElementById('alert-strategy')) {
            document.getElementById('alert-strategy').value = cfg.strategy || 'STABLE';
            document.getElementById('alert-entryz').value = cfg.entry_z != null ? cfg.entry_z : 2.0;
            document.getElementById('alert-horizon').value = cfg.horizon != null ? cfg.horizon : 21;
        }
        document.getElementById('alert-start').value = cfg.start_date || '2023-01-01';
        document.getElementById('alert-recipient').value = cfg.recipient || '';

        // Tickers
        if (cfg.tickers && cfg.tickers.length > 0) {
            document.getElementById('alert-preset').value = 'custom';
            document.getElementById('alert-tickers').value = cfg.tickers.join(',');
            document.getElementById('alert-ticker-count').textContent = `Custom: ${cfg.tickers.length} tickers`;
        } else {
            const preset = cfg.preset || 'all';
            document.getElementById('alert-preset').value = preset;
            applyAlertPreset();
        }

        // Scheduler info
        const infoEl = document.getElementById('alert-scheduler-info');
        if (data.scheduler) {
            infoEl.innerHTML = `<b style="color:var(--green);">⏰ Prossimo invio:</b> ${data.scheduler.next_run_time}<br>` +
                               `<b>Trigger:</b> ${data.scheduler.trigger}`;
        } else {
            infoEl.innerHTML = `<span style="color:var(--orange);">⚠️ Nessun job schedulato (alert disabilitato o errore)</span>`;
        }

        setStatus('✅ Configurazione alert caricata.');
    } catch (e) {
        console.error('Errore caricamento config alert:', e);
        setStatus(`❌ Errore caricamento config: ${e.message}`);
        document.getElementById('alert-scheduler-info').innerHTML =
            `<span style="color:var(--red);">❌ Errore connessione al server: ${e.message}</span>`;
    }
}

async function saveAlertConfig() {
    try {
        setStatus('Salvataggio configurazione alert...');
        const btn = document.getElementById('btn-save-alert');
        btn.disabled = true;

        const preset = document.getElementById('alert-preset').value;
        const customTickers = document.getElementById('alert-tickers').value.trim();

        // Build tickers array
        let tickers = [];
        if (preset === 'custom' && customTickers) {
            tickers = customTickers.split(',').map(t => t.trim()).filter(t => t);
        }
        // If preset != custom, leave tickers empty (server will load from tickers.js or use preset)

        const config = {
            enabled: document.getElementById('alert-enabled').checked,
            trigger_hour: parseInt(document.getElementById('alert-hour').value) || 22,
            trigger_minute: parseInt(document.getElementById('alert-minute').value) || 30,
            mode: document.getElementById('alert-mode').value,
            entry_threshold: parseFloat(document.getElementById('alert-entry').value) || 0,
            exit_threshold: parseFloat(document.getElementById('alert-exit').value) || 0,
            alpha: parseInt(document.getElementById('alert-alpha').value) || 200,
            start_date: document.getElementById('alert-start').value || '2023-01-01',
            tickers: tickers,
            preset: preset,
            recipient: document.getElementById('alert-recipient').value.trim(),
            strategy: document.getElementById('alert-strategy')?.value || 'STABLE',
            entry_z: parseFloat(document.getElementById('alert-entryz')?.value) || 2.0,
            horizon: parseInt(document.getElementById('alert-horizon')?.value) || 21,
        };

        const resp = await fetch(`${API_BASE}/stable-alert/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (data.status === 'ok') {
            setStatus('✅ Configurazione salvata! Scheduler aggiornato.');
            // Reload to show updated scheduler info
            setTimeout(() => loadAlertConfig(), 500);
        } else {
            setStatus('❌ Errore salvataggio configurazione.');
        }

        btn.disabled = false;
    } catch (e) {
        console.error('Errore salvataggio config:', e);
        setStatus(`❌ Errore: ${e.message}`);
        document.getElementById('btn-save-alert').disabled = false;
    }
}

async function triggerAlertNow() {
    try {
        // Single call: scans + sends email + returns results
        setStatus('🔬 Scansione STABLE + invio email in corso... (2-5 min per ~700 tickers)');

        const testResp = await fetch(`${API_BASE}/stable-alert/trigger-with-result`, {
            method: 'POST',
        });
        if (!testResp.ok) throw new Error(`HTTP ${testResp.status}`);
        const testData = await testResp.json();

        // Show result preview
        const resultDiv = document.getElementById('alert-last-result');
        const contentDiv = document.getElementById('alert-result-content');
        resultDiv.style.display = 'block';

        if (testData.result) {
            const r = testData.result;
            const entriesToday = r.entries_today || [];
            const entriesRecent = r.entries_recent || [];
            const active = r.active || [];
            const errors = r.errors || [];

            let html = '<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">';
            html += `<div class="alert-stat"><div class="num" style="color:var(--green);">${entriesToday.length}</div><div class="lbl">Entry Oggi</div></div>`;
            html += `<div class="alert-stat"><div class="num" style="color:var(--orange);">${entriesRecent.length}</div><div class="lbl">Recenti</div></div>`;
            html += `<div class="alert-stat"><div class="num">${active.length}</div><div class="lbl">Attivi</div></div>`;
            html += `<div class="alert-stat"><div class="num" style="color:${errors.length > 0 ? 'var(--red)' : 'var(--text2)'};">${errors.length}</div><div class="lbl">Errori</div></div>`;
            html += '</div>';

            // Sezione 1: ENTRY OGGI
            if (entriesToday.length > 0) {
                html += '<h4 style="color:var(--green); margin:10px 0 6px;">🟢 ENTRY OGGI — Trigger scattato oggi</h4>';
                html += '<table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Prezzo Entry</th><th>Slope</th></tr></thead><tbody>';
                for (const e of entriesToday) {
                    const dir = e.direction === 'LONG' ? '<span style="color:var(--green);">LONG</span>' : '<span style="color:var(--red);">SHORT</span>';
                    html += `<tr><td><b>${e.ticker}</b></td><td>${dir}</td><td>$${e.price.toFixed(2)}</td><td style="color:var(--purple);">${e.slope.toFixed(4)}</td></tr>`;
                }
                html += '</tbody></table>';
            } else {
                html += '<h4 style="color:var(--green); margin:10px 0 6px;">🟢 ENTRY OGGI</h4>';
                html += '<p style="color:var(--text2); padding:6px;">Nessun segnale oggi.</p>';
            }

            // Sezione 2: ENTRY RECENTI (< 5gg)
            if (entriesRecent.length > 0) {
                html += '<h4 style="color:var(--orange); margin:14px 0 6px;">🟡 INGRESSI RECENTI — Ultimi 5 giorni</h4>';
                html += '<table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Prezzo Entry</th><th>Prezzo Att.</th><th>Var %</th><th>Quando</th></tr></thead><tbody>';
                for (const e of entriesRecent) {
                    const dir = e.direction === 'LONG' ? '<span style="color:var(--green);">LONG</span>' : '<span style="color:var(--red);">SHORT</span>';
                    const varPct = e.price_change_since || 0;
                    const varCls = varPct >= 0 ? 'pos' : 'neg';
                    const days = e.days_ago;
                    const daysLabel = days === 1 ? 'IERI' : `${days}gg fa`;
                    html += `<tr><td><b>${e.ticker}</b></td><td>${dir}</td><td>$${e.price.toFixed(2)}</td><td>$${(e.current_price||0).toFixed(2)}</td><td class="${varCls}">${varPct >= 0 ? '+' : ''}${varPct.toFixed(2)}%</td><td><span style="background:var(--orange);color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;">${daysLabel}</span> <small>(${e.date})</small></td></tr>`;
                }
                html += '</tbody></table>';
            }

            // Sezione 3: Posizioni attive
            if (active.length > 0) {
                html += '<h4 style="color:var(--purple); margin:14px 0 6px;">🟣 Posizioni Attive</h4>';
                html += '<table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Entry</th><th>Current</th><th>P/L %</th></tr></thead><tbody>';
                for (const p of active) {
                    const pnlCls = p.pnl_pct >= 0 ? 'pos' : 'neg';
                    html += `<tr><td><b>${p.ticker}</b></td><td>${p.direction}</td><td>${p.entry_date} @ $${p.entry_price.toFixed(2)}</td><td>$${p.current_price.toFixed(2)}</td><td class="${pnlCls}">${p.pnl_pct.toFixed(2)}%</td></tr>`;
                }
                html += '</tbody></table>';
            }

            if (entriesToday.length === 0 && entriesRecent.length === 0 && active.length === 0) {
                html += '<p style="color:var(--text2); text-align:center; padding:20px;">Nessun segnale rilevato.</p>';
            }

            contentDiv.innerHTML = html;
        }

        setStatus(`✅ Test completato. ${testData.entries_today || 0} entry oggi, ${testData.entries_recent || 0} recenti, ${testData.active || 0} attivi.`);
    } catch (e) {
        console.error('Errore trigger alert:', e);
        setStatus(`❌ Errore: ${e.message}`);
    }
}

// ============================================================
//  INIT
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Default: Mega Cap preset
    document.getElementById('preset-select').value = 'mega';
    applyPreset();
    updateStrategyControls();

    // Load alert config when tab is available
    // Delay slightly to allow API_BASE to be set
    setTimeout(() => {
        loadAlertConfig();
    }, 1000);
});
