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
//  BACKTEST ENGINE (runs in browser)
// ============================================================

function backtestStable(dates, prices, slopes, entryTh, exitTh) {
    const capital0 = 1000;
    let capital = capital0;
    let inPosition = false;
    let entryPrice = 0, entryDate = '';
    const trades = [];
    const equity = [];
    let maxEquity = capital0;
    let maxDD = 0;

    for (let i = 0; i < dates.length; i++) {
        const price = prices[i];
        const slope = slopes[i];
        if (price == null || slope == null) {
            equity.push(equity.length ? equity[equity.length - 1] : 0);
            continue;
        }

        // ENTRY
        if (!inPosition && slope > entryTh) {
            inPosition = true;
            entryPrice = price;
            entryDate = dates[i];
        }
        // EXIT
        else if (inPosition && slope < exitTh) {
            const pnl = ((price - entryPrice) / entryPrice) * 100;
            capital *= (1 + pnl / 100);
            trades.push({
                entry_date: entryDate, exit_date: dates[i],
                direction: 'LONG', entry_price: +entryPrice.toFixed(2),
                exit_price: +price.toFixed(2), pnl_pct: +pnl.toFixed(2),
                capital_after: +capital.toFixed(2)
            });
            inPosition = false;
        }

        // Equity
        let tempCap = capital;
        if (inPosition) {
            tempCap *= (1 + ((price - entryPrice) / entryPrice));
        }
        const eqPct = ((tempCap - capital0) / capital0) * 100;
        equity.push(+eqPct.toFixed(2));

        // Drawdown
        if (tempCap > maxEquity) maxEquity = tempCap;
        const dd = ((maxEquity - tempCap) / maxEquity) * 100;
        if (dd > maxDD) maxDD = dd;
    }

    // Close open position
    if (inPosition) {
        const lastPrice = prices[prices.length - 1];
        const pnl = ((lastPrice - entryPrice) / entryPrice) * 100;
        trades.push({
            entry_date: entryDate, exit_date: 'OPEN',
            direction: 'LONG', entry_price: +entryPrice.toFixed(2),
            exit_price: +lastPrice.toFixed(2), pnl_pct: +pnl.toFixed(2),
            capital_after: +(capital * (1 + pnl / 100)).toFixed(2)
        });
    }

    // Stats
    const closed = trades.filter(t => t.exit_date !== 'OPEN');
    const wins = closed.filter(t => t.pnl_pct > 0).length;
    const losses = closed.filter(t => t.pnl_pct <= 0).length;
    const winPnl = closed.filter(t => t.pnl_pct > 0).reduce((s, t) => s + t.pnl_pct, 0);
    const lossPnl = Math.abs(closed.filter(t => t.pnl_pct <= 0).reduce((s, t) => s + t.pnl_pct, 0));
    const finalCap = trades.length ? trades[trades.length - 1].capital_after : capital;
    const totalReturn = ((finalCap - capital0) / capital0) * 100;

    return {
        trades,
        equity,
        stats: {
            total_return: +totalReturn.toFixed(2),
            final_capital: +finalCap.toFixed(2),
            total_trades: closed.length,
            win_rate: closed.length > 0 ? +(wins / closed.length * 100).toFixed(1) : 0,
            avg_trade: closed.length > 0 ? +(closed.reduce((s, t) => s + t.pnl_pct, 0) / closed.length).toFixed(2) : 0,
            max_drawdown: +maxDD.toFixed(2),
            profit_factor: lossPnl > 0 ? +(winPnl / lossPnl).toFixed(2) : (winPnl > 0 ? 999 : 0),
            wins, losses
        }
    };
}

// ============================================================
//  API FETCH (one ticker at a time)
// ============================================================

async function fetchTicker(ticker, alpha, startDate) {
    const body = {
        ticker: ticker,
        alpha: alpha,
        beta: 1.0,
        start_date: startDate,
        use_cache: false
    };
    const url = API_BASE + '/analyze';
    console.log(`[STABLE Lab] Fetching ${ticker} from ${url}`, body);
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        console.error(`[STABLE Lab] HTTP ${resp.status} for ${ticker}:`, errText.substring(0, 500));
        throw new Error(`HTTP ${resp.status}: ${errText.substring(0, 200)}`);
    }
    const data = await resp.json();
    console.log(`[STABLE Lab] ${ticker} OK — dates:${data.dates?.length}, slopes:${data.indicators?.stable_slope?.length}`);
    return data;
}

// ============================================================
//  MAIN ANALYSIS
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

    renderChips(tickers);

    // Clear previous
    for (const k of Object.keys(RESULTS)) delete RESULTS[k];

    let okCount = 0, errCount = 0;
    const startTime = Date.now();

    for (let i = 0; i < tickers.length; i++) {
        const t = tickers[i];
        const chip = document.getElementById('chip-' + t);
        const pct = ((i) / tickers.length * 100).toFixed(0);

        // ETA calculation
        let eta = '';
        if (i > 0) {
            const elapsed = (Date.now() - startTime) / 1000;
            const avgPerTicker = elapsed / i;
            const remaining = avgPerTicker * (tickers.length - i);
            const mins = Math.floor(remaining / 60);
            const secs = Math.floor(remaining % 60);
            eta = ` — ETA ${mins}m ${secs}s`;
        }

        setStatus(`${t} (${i + 1}/${tickers.length}) — ✅ ${okCount} ❌ ${errCount}${eta}`);
        setProgress(pct);

        try {
            const data = await fetchTicker(t, alpha, startDate);
            if (data.status !== 'ok') throw new Error(data.error || 'unknown');

            const dates = data.dates || [];
            const prices = data.prices || [];
            const slopes = (data.indicators && data.indicators.stable_slope) || [];

            const bt = backtestStable(dates, prices, slopes, entryTh, exitTh);

            RESULTS[t] = { dates, prices, slopes, backtest: bt };
            okCount++;
            if (chip) { chip.style.background = '#2a4030'; chip.style.borderColor = '#00ff88'; chip.style.color = '#00ff88'; }
        } catch (err) {
            errCount++;
            console.error(`[STABLE Lab] Error ${t}:`, err);
            if (chip) {
                chip.style.background = '#402a2a';
                chip.style.borderColor = '#ff4444';
                chip.style.color = '#ff4444';
                chip.title = err.message;
            }
        }
    }

    const totalTime = ((Date.now() - startTime) / 1000).toFixed(0);
    setProgress(100);
    setTimeout(() => setProgress(0), 800);

    btn.disabled = false;
    btn.textContent = '▶ Analizza';
    RUNNING = false;

    setStatus(`Completato in ${totalTime}s — ✅ ${okCount} OK, ❌ ${errCount} errori su ${tickers.length} tickers. Entry>${entryTh} Exit<${exitTh}`);
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

    let i = 0;
    for (const [ticker, r] of Object.entries(RESULTS)) {
        traces.push({
            x: r.dates,
            y: r.backtest.equity,
            name: `${ticker} (${r.backtest.stats.total_return > 0 ? '+' : ''}${r.backtest.stats.total_return}%)`,
            type: 'scatter',
            mode: 'lines',
            line: { color: colors[i % colors.length], width: 2 }
        });
        i++;
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
        title: { text: 'Equity Curves (STABLE Strategy)', font: { color: '#ccc', size: 14 } },
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

// --- SUMMARY CARDS ---
function renderSummaryCards() {
    const div = document.getElementById('summary-cards');
    const tickers = Object.keys(RESULTS);
    if (tickers.length === 0) { div.innerHTML = ''; return; }

    const stats = tickers.map(t => RESULTS[t].backtest.stats);
    const avgReturn = stats.reduce((s, st) => s + st.total_return, 0) / stats.length;
    const avgWR = stats.reduce((s, st) => s + st.win_rate, 0) / stats.length;
    const totalTrades = stats.reduce((s, st) => s + st.total_trades, 0);
    const avgDD = stats.reduce((s, st) => s + st.max_drawdown, 0) / stats.length;
    const positivi = stats.filter(st => st.total_return > 0).length;

    const c = (v) => v >= 0 ? 'pos' : 'neg';

    div.innerHTML = `
        <div class="card"><div class="label">Return Medio</div><div class="value ${c(avgReturn)}">${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Win Rate Medio</div><div class="value">${avgWR.toFixed(1)}%</div></div>
        <div class="card"><div class="label">Trades Totali</div><div class="value">${totalTrades}</div></div>
        <div class="card"><div class="label">Max DD Medio</div><div class="value neg">-${avgDD.toFixed(1)}%</div></div>
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
            <td>🟢 ${t.direction}</td>
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
    const rows = Object.entries(RESULTS).map(([ticker, r]) => {
        const s = r.backtest.stats;
        const retCls = s.total_return >= 0 ? 'pos' : 'neg';
        const retSign = s.total_return >= 0 ? '+' : '';
        return `<tr>
            <td style="font-weight:600;">${ticker}</td>
            <td style="text-align:right;" class="${retCls}">${retSign}${s.total_return}%</td>
            <td style="text-align:right;">${s.win_rate}%</td>
            <td style="text-align:right;">${s.total_trades}</td>
            <td style="text-align:right;">${s.avg_trade}%</td>
            <td style="text-align:right; color:#ff4444;">-${s.max_drawdown}%</td>
            <td style="text-align:right;">${s.profit_factor}</td>
            <td style="text-align:right;">$${s.final_capital}</td>
        </tr>`;
    });

    // Sort by return descending
    const sorted = Object.entries(RESULTS)
        .sort((a, b) => b[1].backtest.stats.total_return - a[1].backtest.stats.total_return);

    tbody.innerHTML = sorted.map(([ticker, r]) => {
        const s = r.backtest.stats;
        const retCls = s.total_return >= 0 ? 'pos' : 'neg';
        const retSign = s.total_return >= 0 ? '+' : '';
        return `<tr>
            <td style="font-weight:600;">${ticker}</td>
            <td style="text-align:right;" class="${retCls}">${retSign}${s.total_return}%</td>
            <td style="text-align:right;">${s.win_rate}%</td>
            <td style="text-align:right;">${s.total_trades}</td>
            <td style="text-align:right;">${s.avg_trade}%</td>
            <td style="text-align:right; color:#ff4444;">-${s.max_drawdown}%</td>
            <td style="text-align:right;">${s.profit_factor}</td>
            <td style="text-align:right;">$${s.final_capital}</td>
        </tr>`;
    }).join('');
}

// ============================================================
//  OPTIMIZER
// ============================================================

async function runOptimizer() {
    if (RUNNING) return;
    const tickers = getTickerList();
    if (tickers.length === 0) { setStatus('Inserisci almeno un ticker per ottimizzare.'); return; }

    RUNNING = true;
    const btn = document.getElementById('btn-opt');
    btn.disabled = true;
    btn.textContent = '⏳ Ottimizzazione...';

    const alpha = parseFloat(document.getElementById('param-alpha').value) || 200;
    const startDate = document.getElementById('param-start').value || '2023-01-01';

    setStatus('Fase 1: Caricamento dati per optimizer...');
    renderChips(tickers);

    // Fetch all data first (if not already cached)
    const tickerData = {};
    for (let i = 0; i < tickers.length; i++) {
        const t = tickers[i];
        setProgress(((i) / tickers.length) * 50);
        setStatus(`Caricamento ${t} (${i + 1}/${tickers.length})...`);
        const chip = document.getElementById('chip-' + t);

        if (RESULTS[t]) {
            tickerData[t] = { dates: RESULTS[t].dates, prices: RESULTS[t].prices, slopes: RESULTS[t].slopes };
            if (chip) { chip.style.background = '#2a4030'; chip.style.borderColor = '#00ff88'; chip.style.color = '#00ff88'; }
            continue;
        }
        try {
            const data = await fetchTicker(t, alpha, startDate);
            if (data.status !== 'ok') throw new Error(data.error || 'fail');
            tickerData[t] = {
                dates: data.dates || [],
                prices: data.prices || [],
                slopes: (data.indicators && data.indicators.stable_slope) || []
            };
            if (chip) { chip.style.background = '#2a4030'; chip.style.borderColor = '#00ff88'; chip.style.color = '#00ff88'; }
        } catch (err) {
            console.error(`Opt error ${t}:`, err);
            if (chip) { chip.style.background = '#402a2a'; chip.style.borderColor = '#ff4444'; chip.style.color = '#ff4444'; }
        }
    }

    // Parameter grid
    const entryRange = [];
    for (let e = -0.5; e <= 0.5; e += 0.1) entryRange.push(+e.toFixed(1));
    const exitRange = [];
    for (let x = -0.5; x <= 0.5; x += 0.1) exitRange.push(+x.toFixed(1));

    setStatus('Fase 2: Grid search in corso...');

    const gridResults = [];
    const totalCombos = entryRange.length * exitRange.length;
    let comboIdx = 0;

    // Build heatmap data
    const zData = [];
    const validTickers = Object.keys(tickerData);

    for (let ei = 0; ei < entryRange.length; ei++) {
        const row = [];
        for (let xi = 0; xi < exitRange.length; xi++) {
            const entry = entryRange[ei];
            const exit = exitRange[xi];
            comboIdx++;

            if (comboIdx % 20 === 0) {
                setProgress(50 + (comboIdx / totalCombos) * 50);
            }

            // Run backtest for all tickers
            let sumReturn = 0;
            let sumWR = 0;
            let sumTrades = 0;
            let nPositive = 0;
            let count = 0;

            for (const t of validTickers) {
                const d = tickerData[t];
                const bt = backtestStable(d.dates, d.prices, d.slopes, entry, exit);
                sumReturn += bt.stats.total_return;
                sumWR += bt.stats.win_rate;
                sumTrades += bt.stats.total_trades;
                if (bt.stats.total_return > 0) nPositive++;
                count++;
            }

            const avgRet = count > 0 ? sumReturn / count : 0;
            const avgWR = count > 0 ? sumWR / count : 0;
            const avgTrades = count > 0 ? sumTrades / count : 0;

            row.push(+avgRet.toFixed(2));
            gridResults.push({
                entry, exit,
                avgReturn: +avgRet.toFixed(2),
                avgWR: +avgWR.toFixed(1),
                avgTrades: +avgTrades.toFixed(0),
                nPositive,
                total: count
            });
        }
        zData.push(row);
    }

    setProgress(100);
    setTimeout(() => setProgress(0), 800);

    // Sort and find best
    gridResults.sort((a, b) => b.avgReturn - a.avgReturn);
    const best = gridResults[0];

    // Render heatmap
    renderHeatmap(entryRange, exitRange, zData, best);
    renderOptTable(gridResults.slice(0, 10));

    btn.disabled = false;
    btn.textContent = '🔍 Ottimizza';
    RUNNING = false;
    setStatus(`Ottimizzazione completa! Best: Entry>${best.entry} Exit<${best.exit} → Avg ${best.avgReturn}%`);

    // Switch to optimizer tab
    switchTab('optimizer');
}

function renderHeatmap(entryRange, exitRange, zData, best) {
    const info = document.getElementById('opt-info');
    info.innerHTML = `
        <span>Migliore combinazione:</span>
        <span class="best">Entry > ${best.entry} | Exit < ${best.exit} → Avg Return ${best.avgReturn >= 0 ? '+' : ''}${best.avgReturn}% | WR ${best.avgWR}% | ${best.nPositive}/${best.total} positivi</span>
    `;

    // Build text annotations for each cell
    const textData = zData.map(row => row.map(v => {
        if (v === 0) return '0';
        return (v >= 0 ? '+' : '') + v.toFixed(0) + '%';
    }));

    // Text color: white on dark cells, black on bright cells
    const textColorData = zData.map(row => row.map(v => {
        return (v > -20 && v < 20) ? '#888' : '#fff';
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
        title: { text: 'Heatmap: Avg Return % per combinazione Entry/Exit', font: { color: '#ccc', size: 14 } },
        paper_bgcolor: '#1a1d29',
        plot_bgcolor: '#1a1d29',
        font: { color: '#aaa', family: 'Inter' },
        xaxis: { title: 'Exit Threshold', side: 'bottom', tickfont: { size: 11 } },
        yaxis: { title: 'Entry Threshold', tickfont: { size: 11 } },
        margin: { t: 40, b: 60, l: 80, r: 20 }
    }, { responsive: true });
}

function renderOptTable(top10) {
    const tbody = document.getElementById('opt-body');
    tbody.innerHTML = top10.map((r, i) => {
        const cls = r.avgReturn >= 0 ? 'pos' : 'neg';
        const sign = r.avgReturn >= 0 ? '+' : '';
        const medal = i === 0 ? '🥇 ' : i === 1 ? '🥈 ' : i === 2 ? '🥉 ' : '';
        return `<tr>
            <td>${medal}${r.entry}</td>
            <td>${r.exit}</td>
            <td style="text-align:right;" class="${cls}">${sign}${r.avgReturn}%</td>
            <td style="text-align:right;">${r.avgWR}%</td>
            <td style="text-align:right;">${r.avgTrades}</td>
            <td style="text-align:right;">${r.nPositive}/${r.total}</td>
        </tr>`;
    }).join('');
}

// ============================================================
//  INIT
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Default: Mega Cap preset
    document.getElementById('preset-select').value = 'mega';
    applyPreset();
});
