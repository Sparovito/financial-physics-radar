const API_URL = ""; // Relative path for production (same origin)

async function runAnalysis() {
    const btn = document.querySelector('.btn-analyze');
    const status = document.getElementById('status-bar');
    const statusText = document.getElementById('status-text');

    // 1. Leggi Input
    const ticker = document.getElementById('ticker').value;
    const alpha = parseFloat(document.getElementById('alpha').value);
    const beta = parseFloat(document.getElementById('beta').value);
    const forecast = parseInt(document.getElementById('forecast').value);
    const lookbackYears = parseInt(document.getElementById('lookback-years').value) || 3;
    const endDate = document.getElementById('end-date').value || null; // null if empty
    const useCache = document.getElementById('use-cache').checked;

    // Calculate Start Date
    const d = new Date();
    d.setFullYear(d.getFullYear() - lookbackYears);
    const startDate = d.toISOString().split('T')[0];

    if (!ticker) {
        alert("Inserisci un Ticker!");
        return;
    }

    // UI Loading State
    btn.disabled = true;
    status.style.display = 'flex';
    statusText.innerText = endDate
        ? `Analisi storica (fino a ${endDate}) per ${ticker}...`
        : `Scaricando ${lookbackYears} anni di dati per ${ticker}...`;

    try {
        // 2. Chiama API Backend
        const response = await fetch(`${API_URL}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                alpha: alpha,
                beta: beta,
                forecast_days: forecast,
                start_date: startDate,
                end_date: endDate,
                use_cache: useCache
            })
        });

        if (!response.ok) {
            let errorMsg = response.statusText;
            try {
                const errData = await response.json();
                if (errData.detail) errorMsg = errData.detail;
            } catch (e) { }
            throw new Error(`Errore Server: ${errorMsg}`);
        }

        const data = await response.json();

        // 3. Disegna Grafici
        renderCharts(data);
        renderStats(data.fourier_components);

        statusText.innerText = "Analisi Completata.";
        setTimeout(() => { status.style.display = 'none'; }, 2000);

    } catch (err) {
        console.error(err);
        statusText.innerText = `Errore: ${err.message}`;
        alert(`Si è verificato un errore:\n${err.message}\n\nAssicurati che il server Python sia avviato!`);
    } finally {
        btn.disabled = false;
    }
}

// Shift date by N days and re-run analysis
// Keyboard Listener for Navigation
document.addEventListener('keydown', (e) => {
    // Ignore if typing in text inputs (except end-date)
    const active = document.activeElement;
    const isInput = (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA') && active.id !== 'end-date';
    if (isInput) return;

    if (e.key === 'ArrowLeft') shiftDate(-1);
    if (e.key === 'ArrowRight') shiftDate(1);
});

let isThrottled = false;
const THROTTLE_DELAY = 50; // Fast updates (20fps cap)

// Shift date by N days and re-run analysis (Throttled)
function shiftDate(days) {
    const dateInput = document.getElementById('end-date');
    if (!dateInput.value) {
        // Init to today if empty
        dateInput.value = new Date().toISOString().split('T')[0];
    }

    let currentDate = new Date(dateInput.value);
    currentDate.setDate(currentDate.getDate() + days);

    // Update Input Immediately (Visual Feedback)
    const year = currentDate.getFullYear();
    const month = String(currentDate.getMonth() + 1).padStart(2, '0');
    const day = String(currentDate.getDate()).padStart(2, '0');
    dateInput.value = `${year}-${month}-${day}`;

    // Throttle calls to runAnalysis
    if (!isThrottled) {
        runAnalysis();
        isThrottled = true;
        setTimeout(() => { isThrottled = false; }, THROTTLE_DELAY);
    }
}

function renderCharts(data) {
    // Cache data for toggle re-renders
    window.LAST_ANALYSIS_DATA = data;

    // Safety Check for updated backend
    if (!data.indicators) {
        console.warn("Backend missing 'indicators' field. Using empty arrays.");
        data.indicators = { slope: [], z_residuo: [] };
        // Mostra avviso visibile
        const statusText = document.getElementById('status-text');
        if (statusText) statusText.innerText += " (⚠️ Dati indicatori mancanti, riavvia server)";
    }
    // --- TRACCE GRAFICO PRINCIPALE (Prezzo) ---
    const tracePrice = {
        x: data.dates,
        y: data.prices,
        name: 'Prezzo Reale',
        type: 'scatter',
        line: { color: '#e0e0e0', width: 2 },
        xaxis: 'x',
        yaxis: 'y'
    };

    const tracePath = {
        x: data.dates,
        y: data.min_action,
        name: 'Percorso Minima Azione',
        type: 'scatter',
        line: { color: '#00cc96', width: 2, dash: 'dash' },
        xaxis: 'x',
        yaxis: 'y'
    };

    const traceFund = {
        x: data.dates,
        y: data.fundamentals,
        name: 'Fondamentali',
        type: 'scatter',
        line: { color: '#4444ff', width: 1, dash: 'dot' },
        visible: 'legendonly',
        xaxis: 'x',
        yaxis: 'y'
    };

    const traceForecast = {
        x: data.forecast.dates,
        y: data.forecast.values,
        name: 'Proiezione Fourier',
        type: 'scatter',
        line: { color: '#ab63fa', width: 2, dash: 'dot' },
        xaxis: 'x',
        yaxis: 'y'
    };

    // Calculate Volume Colors (Green if Close >= PrevClose, Red if Lower)
    const volumeColors = (data.volume || []).map((v, i) => {
        if (i === 0) return 'rgba(100, 150, 255, 0.4)'; // Neutral first
        const priceChange = (data.prices[i] || 0) - (data.prices[i - 1] || 0);
        return priceChange >= 0
            ? 'rgba(0, 255, 136, 0.4)'  // Green (Up)
            : 'rgba(255, 68, 68, 0.4)'; // Red (Down)
    });

    // --- TRACE: VOLUME (Overlay) ---
    const traceVolume = {
        x: data.dates,
        y: data.volume || [],
        type: 'bar',
        name: 'Volume',
        marker: { color: volumeColors },
        yaxis: 'y8',
        xaxis: 'x',
        showlegend: false, // Don't clutter legend
        hoverinfo: 'y+name'
    };

    // --- TRACCE GRAFICO ENERGIA (Centro) ---
    const traceKinetic = {
        x: data.dates,
        y: data.energy.kinetic,
        name: 'Densità Cinetica (Volatilità)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#00bfff', width: 1 }, // Blue
        xaxis: 'x',
        yaxis: 'y2'
    };

    const tracePotential = {
        x: data.dates,
        y: data.energy.potential,
        name: 'Densità Potenziale (Tensione)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#ff4444', width: 1 }, // Red
        xaxis: 'x',
        yaxis: 'y2'
    };

    // --- FROZEN Z-SCORES (Point-in-Time - No Look-Ahead Bias) ---
    const traceFrozenKin = {
        x: data.frozen?.dates || [],
        y: data.frozen?.z_kinetic || [],
        name: '❄️ Kin Density (Frozen)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#00e5ff', width: 2 }, // Cyan
        xaxis: 'x',
        yaxis: 'y6' // DEDICATED PANEL
    };

    const traceFrozenPot = {
        x: data.frozen?.dates || [],
        y: data.frozen?.z_potential || [],
        name: '❄️ Pot Density (Frozen)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#ff6600', width: 2 }, // Orange
        xaxis: 'x',
        yaxis: 'y6'
    };

    // --- KINETIC Z TRACE (New Request) ---
    const traceKineticZ = {
        x: data.dates,
        y: data.energy.z_kinetic || [],
        name: 'Kinetic Z (Normalized)',
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy', // Optional: fill to zero like others, or just line
        line: { color: '#bf00ff', width: 2 }, // Neon Purple
        xaxis: 'x',
        yaxis: 'y9'
    };

    // --- FROZEN SUM TRACE (Cyan) ---
    const traceFrozenSum = {
        x: data.frozen?.dates || [],
        y: data.frozen?.z_sum || [],
        name: 'Frozen Sum Z',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#00e5ff', width: 2, dash: 'solid' }, // Cyan
        xaxis: 'x',
        yaxis: 'y9'
    };

    // --- TRACCE INDICATORI (Sotto - Dual Axis) ---
    const traceSlope = {
        x: data.dates,
        y: data.indicators.slope,
        name: 'Slope (Velocità)',
        type: 'scatter',
        line: { color: '#eba834', width: 1.5 }, // Orange/Yellow
        xaxis: 'x',
        yaxis: 'y3'
    };

    const traceZ = {
        x: data.dates,
        y: data.indicators.z_residuo,
        name: 'Z-Residuo (Div.)',
        type: 'scatter',
        line: { color: '#ff88ff', width: 1.5 }, // Pink
        xaxis: 'x',
        yaxis: 'y4' // Asse destro
    };

    // Z-ROC TRACE (Rate of Change) - NO LOOK-AHEAD BIAS
    const traceZRoc = {
        x: data.dates,
        y: data.indicators.z_roc || [],
        name: 'Z-ROC (Istantaneo)',
        type: 'scatter',
        line: { color: '#00ffff', width: 2, dash: 'dot' }, // Cyan dashed
        xaxis: 'x',
        yaxis: 'y4' // Same axis as Z-residuo for comparison
    };

    // --- BACKTEST TRACE (Equity Curve) ---
    const showBacktest = document.getElementById('show-backtest')?.checked ?? false;
    let traceBacktest = null;
    let traceFrozenStrat = null;
    let traceFrozenSumStrat = null;
    let backtestStats = null;
    let frozenStats = null;
    let frozenSumStats = null;

    if (showBacktest) {
        // 1. Live Strategy (Green)
        if (data.backtest && data.backtest.trade_pnl_curve) {
            traceBacktest = {
                x: data.dates,
                y: data.backtest.trade_pnl_curve,
                name: `LIVE Strat (Avg: ${data.backtest.stats.avg_trade}%)`,
                type: 'scatter',
                fill: 'tozeroy',
                line: { color: '#00ff88', width: 2 },
                fillcolor: 'rgba(0, 255, 136, 0.2)',
                xaxis: 'x',
                yaxis: 'y5'
            };
            backtestStats = data.backtest.stats;
        }

        // 2. Frozen Strategy (Orange)
        if (data.frozen_strategy && data.frozen_strategy.trade_pnl_curve) {
            traceFrozenStrat = {
                x: data.dates,
                y: data.frozen_strategy.trade_pnl_curve,
                name: `❄️ FROZEN Strat (Avg: ${data.frozen_strategy.stats.avg_trade}%)`,
                type: 'scatter',
                line: { color: '#ff9900', width: 2, dash: 'solid' }, // Orange
                xaxis: 'x',
                yaxis: 'y5'
            };
            frozenStats = data.frozen_strategy.stats;
        }

        // 3. Frozen Sum Strategy (Yellow/Gold)
        if (data.frozen_sum_strategy && data.frozen_sum_strategy.trade_pnl_curve) {
            traceFrozenSumStrat = {
                x: data.dates,
                y: data.frozen_sum_strategy.trade_pnl_curve,
                name: `📊 SUM Strat (Avg: ${data.frozen_sum_strategy.stats.avg_trade}%)`,
                type: 'scatter',
                line: { color: '#ffcc00', width: 2, dash: 'solid' }, // Gold
                xaxis: 'x',
                yaxis: 'y5'
            };
            frozenSumStats = data.frozen_sum_strategy.stats;
        }
    }

    // --- DETECT MOBILE ---
    // Increased threshold to ensure it catches high-res phones/tablets
    const isMobile = window.innerWidth < 1024;

    // Get extended name from TICKERS_DATA for title
    let extendedName = '';
    for (const cat of Object.values(TICKERS_DATA)) {
        const found = cat.find(t => t.symbol === data.ticker);
        if (found) { extendedName = found.name; break; }
    }
    const titleText = extendedName
        ? `Analisi: ${data.ticker} (${extendedName})`
        : `Analisi: ${data.ticker}`;

    // --- READ VISIBILITY TOGGLES ---
    const showPrice = document.getElementById('show-price')?.checked ?? true;
    const showEnergy = document.getElementById('show-energy')?.checked ?? true;
    const showFrozen = document.getElementById('show-frozen')?.checked ?? true;
    const showIndicators = document.getElementById('show-indicators')?.checked ?? true;
    const showZigZag = document.getElementById('show-zigzag')?.checked ?? true;
    const showVolume = document.getElementById('show-volume')?.checked ?? false;
    const showKineticZ = document.getElementById('show-kinetic-z')?.checked ?? false;
    // showBacktest is already defined above

    // --- DYNAMIC DOMAIN CALCULATION ---
    // Calculate visible panels and redistribute space
    const visiblePanels = [];
    if (showPrice) visiblePanels.push('price');
    if (showEnergy) visiblePanels.push('energy');
    if (showFrozen) visiblePanels.push('frozen');
    if (showZigZag && data.indicators?.zigzag) visiblePanels.push('zigzag');
    if (showIndicators) visiblePanels.push('indicators');
    if (showKineticZ) visiblePanels.push('kineticz');
    if (showBacktest) visiblePanels.push('backtest');

    const panelCount = visiblePanels.length;
    const gap = 0.02; // Gap between panels
    const totalGap = gap * (panelCount - 1);
    const availableSpace = 1 - totalGap;

    // Price gets 40% of available space, others share the rest
    const priceWeight = showPrice ? 0.4 : 0;
    const otherWeight = (1 - priceWeight) / (panelCount - (showPrice ? 1 : 0) || 1);

    // Calculate domains
    const domains = {};
    let currentTop = 1;

    visiblePanels.forEach((panel, i) => {
        const weight = panel === 'price' ? priceWeight : otherWeight;
        const height = availableSpace * weight;
        const bottom = currentTop - height;
        domains[panel] = [Math.max(0, bottom), currentTop];
        currentTop = bottom - gap;
    });

    // Default domains if panel not visible (still needed for axis definition)
    const defaultDomain = [0, 0]; // Hidden

    // --- LAYOUT COMBINATO ---
    const layout = {
        // --- Asse X Condiviso ---
        xaxis: {
            anchor: 'y',
            domain: [0, 1],
            gridcolor: '#333',
            hoverformat: '%d/%m/%Y' // [NEW] Numeric date format (DD/MM/YYYY)
        },

        // --- Configurazione Assi Y (Dynamic Domains) ---
        yaxis: {
            domain: domains.price || defaultDomain,
            gridcolor: '#333',
            title: showPrice ? 'Prezzo (€)' : '',
            tickfont: { color: '#e0e0e0' },
            visible: showPrice
        },
        yaxis2: {
            domain: domains.energy || defaultDomain,
            gridcolor: '#333333',
            title: showEnergy ? 'Energy' : '',
            tickfont: { color: '#9966ff' },
            visible: showEnergy
        },
        yaxis6: { // FROZEN PANEL
            domain: domains.frozen || defaultDomain,
            gridcolor: '#333333',
            title: showFrozen ? 'Frozen' : '',
            tickfont: { color: '#00e5ff' },
            visible: showFrozen
        },
        yaxis7: { // ZIGZAG PANEL
            domain: domains.zigzag || defaultDomain,
            gridcolor: '#333333',
            title: showZigZag ? 'ZigZag' : '',
            tickfont: { color: '#ffcc00' },
            visible: showZigZag
        },
        yaxis3: {
            domain: domains.indicators || defaultDomain,
            gridcolor: '#333333',
            title: showIndicators ? 'Ind.' : '',
            tickfont: { color: '#ff9966' },
            visible: showIndicators
        },
        yaxis4: {
            // Z-Score Axis (Right side of Indicators panel)
            overlaying: 'y3',
            side: 'right',
            gridcolor: 'rgba(0,0,0,0)',
            tickfont: { color: '#00ffff' },
            showgrid: false,
            visible: showIndicators
        },
        yaxis5: {
            domain: domains.backtest || defaultDomain,
            gridcolor: '#333333',
            title: showBacktest ? 'P/L %' : '',
            tickfont: { color: '#00ff88' },
            visible: showBacktest
        },
        yaxis9: { // KINETIC Z PANEL
            domain: domains.kineticz || defaultDomain,
            gridcolor: '#333333',
            title: showKineticZ ? 'Kinetic Z' : '',
            tickfont: { color: '#bf00ff' },
            visible: showKineticZ
        },
        yaxis8: {
            // Volume Axis (Overlay on Price)
            overlaying: 'y',
            side: 'left',
            showgrid: false,
            zeroline: false,
            visible: showVolume,
            showticklabels: false,
            range: [0, (data.volume && data.volume.length ? Math.max(...data.volume) : 100) * 5]
        },

        title: { text: titleText, font: { color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#aaa', size: isMobile ? 10 : 12 },
        showlegend: !isMobile,
        legend: isMobile ? {
            orientation: 'h',
            x: 0,
            y: -0.15,
            xanchor: 'left',
            font: { size: 10 },
            bgcolor: 'rgba(0,0,0,0)'
        } : {
            orientation: 'h',
            x: 0.5,
            y: 1.05,
            xanchor: 'center',
            bgcolor: 'rgba(0,0,0,0)'
        },
        margin: isMobile ?
            { t: 40, r: 10, l: 35, b: 30 } :
            { t: 60, r: 50, l: 50, b: 40 },
        hovermode: 'x unified'
    };

    // Add yaxis5 for backtest if visible

    layout.autosize = true;

    const config = {
        responsive: true,
        displayModeBar: !isMobile
    };

    // Build traces array based on toggles
    const traces = [];

    // Price group
    if (showPrice) {
        // Volume first so it's behind candles
        if (showVolume) traces.push(traceVolume);
        traces.push(tracePrice, tracePath, traceFund, traceForecast);
    }

    // Energy group
    if (showEnergy) {
        traces.push(traceKinetic, tracePotential);
    }

    // Frozen group
    if (showFrozen) {
        traces.push(traceFrozenKin, traceFrozenPot);
    }

    // Indicators group
    if (showIndicators) {
        traces.push(traceSlope, traceZ, traceZRoc);
    }

    // Backtest / Strategy traces
    if (traceBacktest) traces.push(traceBacktest);
    if (traceFrozenStrat) traces.push(traceFrozenStrat);
    if (traceFrozenSumStrat) traces.push(traceFrozenSumStrat);

    // Kinetic Z Trace
    if (showKineticZ) {
        traces.push(traceKineticZ, traceFrozenSum);
    }

    // ZigZag Indicator Trace
    if (showZigZag && data.indicators && data.indicators.zigzag) {
        const traceZigZag = {
            x: data.dates,
            y: data.indicators.zigzag,
            name: '⚡ ZigZag Cumulativo',
            type: 'scatter',
            line: { color: '#ffcc00', width: 2 },
            xaxis: 'x',
            yaxis: 'y7'
        };
        traces.push(traceZigZag);
    }

    // Add saved annotation shapes to layout
    loadAnnotations();
    layout.shapes = getAnnotationShapes();

    Plotly.newPlot('chart-combined', traces, layout, config);

    // Setup click handler for annotations
    setupChartClickHandler();

    // Display backtest stats if available
    const statsDiv = document.getElementById('backtest-stats');
    if (statsDiv) {
        let html = '';

        if (backtestStats) {
            html += `
                <div style="color: #00ff88; margin-bottom: 4px;">
                    <strong>🟢 LIVE Strat:</strong> 
                    Trades: ${backtestStats.total_trades} | 
                    Win: ${backtestStats.win_rate}% | 
                    Return: ${backtestStats.total_return}%
                </div>`;
        }

        if (frozenStats) {
            html += `
                <div style="color: #ff9900;">
                    <strong>🟠 FROZEN Strat:</strong> 
                    Trades: ${frozenStats.total_trades} | 
                    Win: ${frozenStats.win_rate}% | 
                    Return: ${frozenStats.total_return}%
                </div>`;
        }

        if (frozenSumStats) {
            html += `
                <div style="color: #ff4444;">
                    <strong>🔴 SUM Strat:</strong> 
                    Trades: ${frozenSumStats.total_trades} | 
                    Win: ${frozenSumStats.win_rate}% | 
                    Return: ${frozenSumStats.total_return}%
                </div>`;
        }

        statsDiv.innerHTML = html || 'No Stats Available';
    }

    // Store trades globally and show button
    window.TRADES_LIVE = (data.backtest && data.backtest.trades) ? data.backtest.trades : [];
    window.TRADES_FROZEN = (data.frozen_strategy && data.frozen_strategy.trades) ? data.frozen_strategy.trades : [];
    window.TRADES_SUM = (data.frozen_sum_strategy && data.frozen_sum_strategy.trades) ? data.frozen_sum_strategy.trades : [];

    if (window.TRADES_LIVE.length > 0 || window.TRADES_FROZEN.length > 0 || window.TRADES_SUM.length > 0) {
        const btnTrades = document.getElementById('btn-view-trades');
        if (btnTrades) btnTrades.style.display = 'block';
    } else {
        const btnTrades = document.getElementById('btn-view-trades');
        if (btnTrades) btnTrades.style.display = 'none';
    }

    // Refresh Trades Modal if open (Live Update while scrolling)
    const tradesModal = document.getElementById('trades-modal');
    if (tradesModal && tradesModal.style.display !== 'none') {
        renderTradesList();
    }
}

// --- TRADES MODAL FUNCTIONS ---
// --- TRADES MODAL FUNCTIONS ---
window.CURRENT_TRADES_VIEW = 'LIVE';

function switchTradesView(mode) {
    window.CURRENT_TRADES_VIEW = mode;

    // Update Buttons UI
    const btnLive = document.getElementById('btn-trades-live');
    const btnFrozen = document.getElementById('btn-trades-frozen');

    if (btnLive && btnFrozen) {
        // Reset all to inactive
        btnLive.style.background = 'transparent'; btnLive.style.color = '#888'; btnLive.style.border = 'none';
        btnFrozen.style.background = 'transparent'; btnFrozen.style.color = '#888'; btnFrozen.style.border = 'none';
        const btnSum = document.getElementById('btn-trades-sum');
        if (btnSum) { btnSum.style.background = 'transparent'; btnSum.style.color = '#888'; btnSum.style.border = 'none'; }

        // Activate selected
        if (mode === 'LIVE') {
            btnLive.style.background = '#00ff88'; btnLive.style.color = '#000';
        } else if (mode === 'FROZEN') {
            btnFrozen.style.background = '#ff9900'; btnFrozen.style.color = '#000';
        } else if (mode === 'SUM' && btnSum) {
            btnSum.style.background = '#ff4444'; btnSum.style.color = '#fff';
        }
    }

    renderTradesList();
}

function openTradesModal() {
    // Force Default to Live on open unless we want persistence
    if (!window.CURRENT_TRADES_VIEW) window.CURRENT_TRADES_VIEW = 'LIVE';

    switchTradesView(window.CURRENT_TRADES_VIEW);
    document.getElementById('trades-modal').style.display = 'flex';
}

// Global storage for ORIGINAL trades (baseline - saved once, never overwritten)
window.ORIGINAL_TRADES = window.ORIGINAL_TRADES || { LIVE: null, FROZEN: null, SUM: null };

function renderTradesList() {
    const listDiv = document.getElementById('trades-list');
    const viewMode = window.CURRENT_TRADES_VIEW;
    let trades;
    if (viewMode === 'LIVE') {
        trades = window.TRADES_LIVE;
    } else if (viewMode === 'FROZEN') {
        trades = window.TRADES_FROZEN;
    } else {
        trades = window.TRADES_SUM;
    }

    if (!trades || trades.length === 0) {
        listDiv.innerHTML = '<p style="color: #888; text-align: center; margin-top: 20px;">Nessuna operazione disponibile per questa strategia.</p>';
        return;
    }

    // Save ORIGINAL trades only once (baseline for all future comparisons)
    if (window.ORIGINAL_TRADES[viewMode] === null) {
        window.ORIGINAL_TRADES[viewMode] = JSON.parse(JSON.stringify(trades));
        console.log(`📌 Baseline ${viewMode} salvato:`, trades.length, 'trades');
    }

    // Get original trades for comparison (baseline)
    const originalTrades = window.ORIGINAL_TRADES[viewMode] || [];

    // Build lookup map by entry_date for fast comparison
    const originalTradesMap = {};
    originalTrades.forEach((t, idx) => {
        if (t && t.entry_date) {
            originalTradesMap[t.entry_date] = t;
        }
    });

    let html = '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">';
    html += `<tr style="color: #888; border-bottom: 1px solid #333;">
        <th style="text-align: left; padding: 8px;">Data</th>
        <th style="text-align: center; padding: 8px;">Tipo</th>
        <th style="text-align: right; padding: 8px;">Entry</th>
        <th style="text-align: right; padding: 8px;">Exit</th>
        <th style="text-align: right; padding: 8px;">P/L %</th>
    </tr>`;

    // Sort by recent first? usually sequential is better. We keep array order.
    // Trades are typically oldest to newest. Reverse for newest first?
    const tradesReversed = [...trades].reverse();

    tradesReversed.forEach((t, idx) => {
        const isOpen = t.exit_date === 'OPEN';

        // Custom styling for OPEN trades
        const rowStyle = isOpen
            ? 'border-bottom: 1px solid #444; background: rgba(255, 153, 0, 0.15); box-shadow: 0 0 5px rgba(255,153,0,0.2) inset;'
            : 'border-bottom: 1px solid #222;';

        const exitDateDisplay = isOpen
            ? '<span style="color: #ff9900; font-weight: bold; border: 1px solid #ff9900; padding: 2px 6px; border-radius: 4px; font-size: 0.8em;">⚠️ IN CORSO</span>'
            : `${t.exit_date}`;

        const exitPriceDisplay = isOpen
            ? `<span style="color: #fff;">${t.exit_price}</span> <small>(att)</small>`
            : t.exit_price;

        const pnlColor = t.pnl_pct >= 0 ? '#00ff88' : '#ff4444';
        const pnlSign = t.pnl_pct >= 0 ? '+' : '';
        const typeEmoji = t.direction === 'LONG' ? '🟢' : '🔴';

        // === COMPLETE CHANGE DETECTION (DISABLED BY USER REQUEST) ===
        // Logic commented out to remove red highlights in the main list
        let warningMessages = [];
        let rowWarningStyle = '';
        let snapshotWarning = ''; // Defined here to avoid ReferenceError

        /*
        // Compare with ORIGINAL version of this trade (by matching entry_date)
        const originalTrade = originalTradesMap[t.entry_date];
        if (originalTrade) {
            // Direction changed from original
            if (originalTrade.direction !== t.direction) {
                warningMessages.push(`Dir: ${originalTrade.direction}→${t.direction}`);
            }
            // Exit date changed from original (ignore OPEN→date, that's normal closure)
            if (originalTrade.exit_date !== t.exit_date && originalTrade.exit_date !== 'OPEN') {
                warningMessages.push(`Exit: ${originalTrade.exit_date}→${t.exit_date}`);
            }
            // Entry price changed significantly from original
            if (Math.abs(originalTrade.entry_price - t.entry_price) > 0.01) {
                warningMessages.push(`Entry$: ${originalTrade.entry_price}→${t.entry_price}`);
            }
        }

        // 3. Build warning display
        let snapshotWarning = '';
        if (warningMessages.length > 0) {
            snapshotWarning = '<span style="color:#ff4444; font-size:0.7em; display:block;">⚠️ ' + warningMessages.join(' | ') + '</span>';
            rowWarningStyle = 'background: rgba(255,68,68,0.2); border-left: 3px solid #ff4444;';
        }
        */

        const finalRowStyle = isOpen ? rowStyle : (rowWarningStyle || rowStyle);

        html += `<tr style="${finalRowStyle}">
            <td style="padding: 8px; color: #aaa;">${t.entry_date}${snapshotWarning}<br><small>→ ${exitDateDisplay}</small></td>
            <td style="padding: 8px; text-align: center;">${typeEmoji} ${t.direction}</td>
            <td style="padding: 8px; text-align: right; color: #ccc;">${t.entry_price}</td>
            <td style="padding: 8px; text-align: right; color: #ccc;">${exitPriceDisplay}</td>
            <td style="padding: 8px; text-align: right; color: ${pnlColor}; font-weight: bold;">
                ${pnlSign}${t.pnl_pct}%
                ${isOpen ? '<br><small style="font-weight:normal; opacity:0.8;">(open)</small>' : ''}
            </td>
        </tr>`;
    });

    html += '</table>';
    listDiv.innerHTML = html;
}

// Verify trade integrity by running time simulation
// Verify trade integrity by running time simulation
async function verifyTradeIntegrity() {
    console.log("👆 Button verifyTradeIntegrity clicked!");

    const listDiv = document.getElementById('trades-list');
    // FIX: IDs are 'ticker', 'alpha', 'beta', NOT 'ticker-input' etc.
    const tickerEl = document.getElementById('ticker');
    const alphaEl = document.getElementById('alpha');
    const betaEl = document.getElementById('beta');

    if (!tickerEl) {
        alert("Errore: Impossibile trovare l'input ticker!");
        return;
    }

    const ticker = tickerEl.value.toUpperCase();
    const strategy = window.CURRENT_TRADES_VIEW || 'FROZEN';
    const alpha = parseFloat(alphaEl ? alphaEl.value : 200);
    const beta = parseFloat(betaEl ? betaEl.value : 1.0);

    // Show loading
    listDiv.innerHTML = `
        <div style="text-align: center; padding: 40px; color: #888;">
            <div style="font-size: 2rem; margin-bottom: 10px;">🔍</div>
            <div>Verifica integrità in corso per ${ticker} (${strategy})...</div>
            <div style="font-size: 0.8em; margin-top: 10px;">Simulazione dal passato al presente...</div>
        </div>
    `;

    try {
        const response = await fetch('/verify-integrity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, strategy, alpha, beta })
        });

        const data = await response.json();

        if (data.status === 'error') {
            listDiv.innerHTML = `<div style="color: #ff4444; padding: 20px;">Errore: ${data.detail}</div>`;
            return;
        }

        // Display results
        let html = `
            <div style="background: #1a1d2e; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                <h3 style="margin: 0 0 10px 0; color: #fff;">📊 Risultato Verifica Integrità</h3>
                <div style="display: flex; gap: 20px; color: #888;">
                    <span><b>Ticker:</b> ${data.ticker}</span>
                    <span><b>Strategia:</b> ${data.strategy}</span>
                    <span><b>Trade Totali:</b> ${data.total_trades}</span>
                    <span style="color: ${data.corrupted_count > 0 ? '#ff4444' : '#00ff88'};">
                        <b>Trade Corrotti:</b> ${data.corrupted_count}
                    </span>
                </div>
            </div>
        `;

        if (data.corrupted_count === 0) {
            html += `
                <div style="text-align: center; padding: 30px; color: #00ff88;">
                    <div style="font-size: 3rem;">✅</div>
                    <div style="font-size: 1.2rem; margin-top: 10px;">Nessuna anomalia rilevata!</div>
                    <div style="color: #888; font-size: 0.9em; margin-top: 5px;">
                        I trade sono coerenti nel tempo (nessun look-ahead bias)
                    </div>
                </div>
            `;
        } else {
            html += `
                <div style="background: rgba(255,68,68,0.1); padding: 10px; border-radius: 6px; margin-bottom: 15px; color: #ff4444;">
                    ⚠️ <b>${data.corrupted_count} trade</b> hanno cambiato retroattivamente (look-ahead bias)
                </div>
            `;

            html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">';
            html += `<tr style="color: #888; border-bottom: 1px solid #333;">
                <th style="text-align: left; padding: 8px;">Entry Date</th>
                <th style="text-align: left; padding: 8px;">Direzione Orig.</th>
                <th style="text-align: left; padding: 8px;">Cambiamenti</th>
            </tr>`;

            data.corrupted_trades.forEach(trade => {
                html += `<tr style="border-bottom: 1px solid #222; background: rgba(255,68,68,0.1);">
                    <td style="padding: 8px; color: #fff;">${trade.entry_date}</td>
                    <td style="padding: 8px; color: #aaa;">${trade.original.direction}</td>
                    <td style="padding: 8px; color: #ff4444; font-size: 0.8em;">${trade.changes.join(' | ')}</td>
                </tr>`;
            });

            html += '</table>';
        }

        listDiv.innerHTML = html;

    } catch (error) {
        listDiv.innerHTML = `<div style="color: #ff4444; padding: 20px;">Errore di connessione: ${error.message}</div>`;
    }
}

function closeTradesModal() {
    document.getElementById('trades-modal').style.display = 'none';
}

function renderStats(components) {
    const container = document.getElementById('fourier-stats');
    if (!components || components.length === 0) {
        container.innerHTML = "Nessun ciclo rilevato.";
        return;
    }

    let html = "<strong>Cicli Dominanti (Barre):</strong><br>";
    components.slice(0, 5).forEach(c => {
        html += `• ${c.period}gg (Amp: ${c.amplitude.toFixed(4)})<br>`;
    });

    container.innerHTML = html;
}

// --- LOGICA MODALE SELEZIONE TICKER ---

// Cache DOM elements
const modal = document.getElementById("ticker-modal");
const btnOpen = document.getElementById("btn-open-modal");
const btnClose = document.querySelector(".close-modal"); // Questo prende solo il primo! Correggiamo.
// Le funzioni openRadar/closeRadar gestiscono la loro modale.
// Qui gestiamo la modale Ticker.

function closeTickerModal() {
    modal.style.display = "none";
}

// 1. Apri/Chiudi Modale Ticker
btnOpen.onclick = () => {
    modal.style.display = "flex";
    renderCategories();
    renderTickers(currentCategory);
    searchInput.focus();
}

// window.onclick gestisce chiusura cliccando fuori
window.onclick = (event) => {
    if (event.target == modal) closeTickerModal();
    if (event.target == document.getElementById('radar-modal')) closeRadar();
}

// ... (Resto funzioni Render Categories/Tickers invariate) ...

// --- LOGICA RADAR SCANNER ---
const radarModal = document.getElementById('radar-modal');
// Removed global const radarSlider = ... to invoke explicitly
// const radarDateLabel = ...
// const radarTrailsCheck = ...

// Global Cache per Timeline
let RADAR_RESULTS_CACHE = null;
let FOCUSED_TICKER = null; // Ticker in focus mode (null = show all)

function openRadar() {
    radarModal.style.display = 'flex';
    // Se è vuoto o c'è "Scansione Temporale" (loading), avvia
    const chartDiv = document.getElementById('radar-chart');
    if (chartDiv.innerHTML === "" || chartDiv.innerHTML.includes("Scansione")) {
        document.getElementById('radar-category').value = "Tech";
        runRadarScan();
    }
}

function closeRadar() {
    radarModal.style.display = 'none';
}

async function runRadarScan() {
    const category = document.getElementById('radar-category').value;
    const chartDiv = document.getElementById('radar-chart');

    // 1. Raccogli Tickers based on category
    let tickersToScan = [];

    // Category mapping to tickers.js keys
    const categoryMap = {
        "ALL": null, // Special: all tickers
        "HIGHLIGHTS": "⭐ Highlights",
        "US_MEGA": "🏛️ US Mega Cap",
        "US_TECH": "💻 US Tech",
        "US_FINANCE": "🏦 US Finance",
        "US_HEALTH": "🏥 US Healthcare",
        "US_INDUSTRIAL": "🏭 US Industrials",
        "US_CONSUMER": "🛒 US Consumer",
        "US_ENERGY": "⚡ US Energy",
        "US_MIDCAP": ["📈 US Mid Cap A-L", "📉 US Mid Cap M-Z"],
        "UK": "🇬🇧 UK (FTSE)",
        "DE": "🇩🇪 Germany (DAX)",
        "FR": "🇫🇷 France (CAC 40)",
        "IT": "🇮🇹 Italy (MIB)",
        "EU_ALL": ["🇬🇧 UK (FTSE)", "🇩🇪 Germany (DAX)", "🇫🇷 France (CAC 40)", "🇮🇹 Italy (MIB)", "🇳🇱 Netherlands", "🇪🇸 Spain", "🇨🇭 Switzerland"],
        "JP": "🇯🇵 Japan",
        "CN": "🇨🇳 China / HK",
        "KR": "🇰🇷 Korea",
        "TW": "🇹🇼 Taiwan",
        "IN": "🇮🇳 India",
        "ETF": "📊 Major ETFs",
        "CRYPTO": "🪙 Crypto",
        "COMMODITIES": "🛢️ Commodities"
    };

    if (category === "ALL") {
        tickersToScan = Object.values(TICKERS_DATA).flat().map(t => t.symbol);
    } else {
        const catKeys = categoryMap[category];
        if (Array.isArray(catKeys)) {
            // Multiple categories
            catKeys.forEach(key => {
                if (TICKERS_DATA[key]) tickersToScan.push(...TICKERS_DATA[key].map(t => t.symbol));
            });
        } else if (catKeys && TICKERS_DATA[catKeys]) {
            tickersToScan = TICKERS_DATA[catKeys].map(t => t.symbol);
        } else {
            // Fallback to Highlights
            tickersToScan = TICKERS_DATA["⭐ Highlights"]?.map(t => t.symbol) || [];
        }
    }

    tickersToScan = [...new Set(tickersToScan)];
    const totalTickers = tickersToScan.length;

    // 2. CHECK DAILY CACHE
    const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
    const cacheKey = `radar_cache_${category}_${today}`;

    try {
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
            console.log("📦 Using cached radar data from today");
            RADAR_RESULTS_CACHE = JSON.parse(cached);
            setupRadarAfterLoad();
            return;
        }
    } catch (e) {
        console.warn("Cache read failed:", e);
    }

    // 3. Show Progress Bar
    chartDiv.innerHTML = `
        <div style="display:flex; flex-direction:column; height:100%; align-items:center; justify-content:center; color:#eba834; gap: 15px;">
            <h3>📡 Scansione di ${totalTickers} titoli...</h3>
            <div style="width: 80%; max-width: 400px; background: #1a1d2a; border-radius: 10px; overflow: hidden; height: 20px;">
                <div id="radar-progress-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #eba834, #ffd700); transition: width 0.3s;"></div>
            </div>
            <span id="radar-progress-text" style="font-size: 0.9rem; color: #888;">Avvio scansione...</span>
        </div>`;

    // Simulate progress while waiting (real progress would require server-sent events)
    let fakeProgress = 0;
    const progressBar = document.getElementById('radar-progress-bar');
    const progressText = document.getElementById('radar-progress-text');

    const progressInterval = setInterval(() => {
        if (fakeProgress < 90) {
            fakeProgress += Math.random() * 10;
            if (progressBar) progressBar.style.width = `${Math.min(fakeProgress, 90)}%`;
            if (progressText) progressText.innerText = `Analisi in corso... ${Math.floor(fakeProgress)}%`;
        }
    }, 500);

    try {
        const response = await fetch(`${API_URL}/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tickers: tickersToScan })
        });

        clearInterval(progressInterval);
        if (progressBar) progressBar.style.width = '100%';
        if (progressText) progressText.innerText = 'Elaborazione completata!';

        const data = await response.json();
        if (data.status !== "ok") throw new Error(data.detail);

        // SALVA CACHE
        RADAR_RESULTS_CACHE = data.results;

        // Save to localStorage for today
        try {
            localStorage.setItem(cacheKey, JSON.stringify(RADAR_RESULTS_CACHE));
            console.log("💾 Radar data cached for today");
        } catch (e) {
            console.warn("Cache write failed (maybe too large):", e);
        }

        if (!RADAR_RESULTS_CACHE || RADAR_RESULTS_CACHE.length === 0) {
            chartDiv.innerHTML = `<div style="display:flex; justify-content:center; align-items:center; height:100%; color:orange;"><h3>Nessun dato trovato per questa categoria.</h3></div>`;
            return;
        }

        setupRadarAfterLoad();

    } catch (e) {
        clearInterval(progressInterval);
        chartDiv.innerHTML = `<h3 style="color:red">Errore: ${e.message}</h3>`;
        console.error(e);
    }
}

// Helper function to setup radar after data is loaded (either from cache or API)
function setupRadarAfterLoad() {
    const chartDiv = document.getElementById('radar-chart');
    const slider = document.getElementById('radar-slider');
    const trailsCheck = document.getElementById('radar-trails');

    // Trova una history valida per settare il max
    let maxIdx = 0;
    for (let r of RADAR_RESULTS_CACHE) {
        if (r.history && r.history.dates) {
            maxIdx = r.history.dates.length - 1;
            break;
        }
    }

    slider.max = maxIdx;
    slider.value = maxIdx;

    // Attiva Listener (uses toggle mode so frozen view also updates)
    slider.oninput = toggleRadarMode;
    trailsCheck.onchange = toggleRadarMode;

    // CRITICAL: Clear loading message
    chartDiv.innerHTML = "";

    // Reset focus when loading new data
    FOCUSED_TICKER = null;
    updateAnalyzeButton();

    // Render Iniziale (rispetta lo stato del toggle)
    toggleRadarMode();
}

// Funzione Core per il "Time Travel"
function updateRadarFrame() {
    if (!RADAR_RESULTS_CACHE || RADAR_RESULTS_CACHE.length === 0) return;

    const slider = document.getElementById('radar-slider');
    const trailsCheck = document.getElementById('radar-trails');
    const dateLabel = document.getElementById('radar-date');

    const dayIdx = parseInt(slider.value);
    const showTrails = trailsCheck.checked;

    // Recupera data corrente (Cerca la prima valida)
    let currentDate = "N/A";
    for (let r of RADAR_RESULTS_CACHE) {
        if (r.history && r.history.dates && r.history.dates[dayIdx]) {
            currentDate = r.history.dates[dayIdx];
            break;
        }
    }
    dateLabel.innerText = currentDate;

    // --- DETECT MOBILE ---
    const isMobile = window.innerWidth < 768;

    // 1. Dati Punti (Teste)
    const xHead = [];
    const yHead = [];
    const texts = [];
    const colors = [];
    const textColors = []; // Text color per point (green/red/white based on P/L)
    const tickers = [];
    const opacities = []; // Per-point opacity for focus mode

    RADAR_RESULTS_CACHE.forEach(r => {
        // Safety check index (some histories might be shorter/padded differently if bugged, but logic used padding)
        if (r.history && r.history.z_kin && dayIdx < r.history.z_kin.length) {
            const valX = r.history.z_kin[dayIdx];
            const valY = r.history.z_pot[dayIdx];

            // Only plot if values are not null (padding)
            if (valX !== null && valY !== null) {
                xHead.push(valX);
                yHead.push(valY);

                // Focus Mode: Only show label for focused ticker
                if (FOCUSED_TICKER === null || r.ticker === FOCUSED_TICKER) {
                    const price = r.history.prices && r.history.prices[dayIdx];
                    const zKin = r.history.z_kin[dayIdx];
                    const zSlopeVal = r.history.z_slope && r.history.z_slope[dayIdx];

                    if (FOCUSED_TICKER && price) {
                        let label = `${r.ticker} [${price.toFixed(2)}]`;

                        // Calculate Trade P/L % using EXACT same logic as backend backtest_strategy
                        // Simulate forward from day 0 to dayIdx tracking position state
                        let tradePnl = 0;
                        let inPosition = false;
                        let entryPrice = null;
                        let positionDirection = null;

                        for (let j = 0; j <= dayIdx; j++) {
                            const jPrice = r.history.prices[j];
                            const jZKin = r.history.z_kin[j];
                            const jZSlope = r.history.z_slope ? r.history.z_slope[j] : 0;

                            if (jPrice === null || jZKin === null) continue;

                            if (!inPosition) {
                                // Check for entry signal
                                if (jZKin > 0) {
                                    inPosition = true;
                                    entryPrice = jPrice;
                                    positionDirection = (jZSlope || 0) >= 0 ? 'LONG' : 'SHORT';
                                    tradePnl = 0; // Just entered
                                } else {
                                    tradePnl = 0; // Not invested
                                }
                            } else {
                                // In position - calculate current P/L
                                if (positionDirection === 'LONG') {
                                    tradePnl = ((jPrice - entryPrice) / entryPrice) * 100;
                                } else {
                                    tradePnl = ((entryPrice - jPrice) / entryPrice) * 100;
                                }

                                // Check for exit signal
                                if (jZKin < 0) {
                                    // Trade closed
                                    inPosition = false;
                                    entryPrice = null;
                                    positionDirection = null;
                                    tradePnl = 0; // Back to 0
                                }
                            }
                        }

                        const sign = tradePnl >= 0 ? '+' : '';
                        label += ` ${sign}${tradePnl.toFixed(1)}%`;

                        // Color based on P/L: green if positive, red if negative, white if 0
                        const textColor = tradePnl > 0 ? '#00ff88' : (tradePnl < 0 ? '#ff4444' : '#ffffff');
                        texts.push(label);
                        textColors.push(textColor);
                    } else {
                        texts.push(r.ticker);
                        textColors.push('#ffffff'); // Default white
                    }
                } else {
                    texts.push(''); // Hide label
                    textColors.push('#ffffff');
                }

                // SLOPE COLOR: Use backend-calculated Z-Slope (dX of minima azione path)
                // z_slope is the Z-Score of the path velocity, already in history
                const zSlope = r.history.z_slope && r.history.z_slope[dayIdx] !== null
                    ? r.history.z_slope[dayIdx]
                    : 0;
                colors.push(zSlope); // Positive = accelerating up, Negative = decelerating/falling


                tickers.push(r.ticker);

                // Focus Mode: Set opacity per point
                if (FOCUSED_TICKER === null) {
                    opacities.push(0.9); // All visible
                } else if (r.ticker === FOCUSED_TICKER) {
                    opacities.push(1.0); // Focused = full opacity
                } else {
                    opacities.push(0.15); // Others = faded
                }
            }
        }
    });

    // 2. Dati Scie (Trails) - Solo se attive
    // Focus Mode: Se c'è un ticker focalizzato, mostra solo la sua scia
    const xTail = [];
    const yTail = [];

    if (showTrails || FOCUSED_TICKER !== null) { // Also show trail if focused
        const TAIL_LEN = 50;
        const startIdx = Math.max(0, dayIdx - TAIL_LEN);

        RADAR_RESULTS_CACHE.forEach(r => {
            // Focus Mode: Skip trails for non-focused tickers
            if (FOCUSED_TICKER !== null && r.ticker !== FOCUSED_TICKER) return;

            if (r.history && r.history.z_kin) {
                if (dayIdx < r.history.z_kin.length) {
                    for (let i = startIdx; i <= dayIdx; i++) {
                        if (i < r.history.z_kin.length) {
                            const tX = r.history.z_kin[i];
                            const tY = r.history.z_pot[i];
                            if (tX !== null && tY !== null) {
                                xTail.push(tX);
                                yTail.push(tY);
                            }
                        }
                    }
                    xTail.push(null);
                    yTail.push(null);
                }
            }
        });
    }

    // Costruisci Tracce
    const traceMain = {
        x: xHead,
        y: yHead,
        text: texts,
        mode: 'markers+text',
        textposition: 'top center',
        texttemplate: '%{text}',
        textfont: {
            color: textColors,
            size: 14
        },
        marker: {
            size: FOCUSED_TICKER ?
                texts.map(t => t === FOCUSED_TICKER ? 20 : 12) : 15, // Bigger if focused
            color: colors,
            colorscale: 'RdYlGn', // Red (bearish) - Yellow (neutral) - Green (bullish)
            reversescale: false, // Green = positive momentum
            showscale: true,
            cmin: -2, // Z-Score range
            cmax: 2,
            colorbar: isMobile ? {
                title: 'Z-Slope',
                orientation: 'h',
                y: -0.25,
                thickness: 10,
                len: 0.9
            } : {
                title: 'Z-Slope (dX)'
            },
            line: { color: 'white', width: 0.5 },
            opacity: opacities // Use per-point opacity array
        },
        type: 'scatter',
        name: 'Asset'
    };

    const traceTrails = {
        x: xTail,
        y: yTail,
        mode: 'lines',
        line: {
            color: '#ffffff',
            width: 1,
            opacity: 0.3 // Scia trasparente
        },
        hoverinfo: 'skip',
        type: 'scatter',
        showlegend: false
    };

    const dataToPlot = showTrails ? [traceTrails, traceMain] : [traceMain];

    // Layout (Statico)
    const layout = {
        title: {
            text: `Market Radar (${currentDate})`,
            font: { color: 'white', size: isMobile ? 14 : 18 }
        },
        xaxis: {
            title: 'Volatilità (Kinetic Z)',
            gridcolor: '#333',
            range: [-3, 5],
            titlefont: { size: isMobile ? 12 : 14 }
        },
        yaxis: {
            title: 'Tensione (Potential Z)',
            gridcolor: '#333',
            range: [-3, 5],
            titlefont: { size: isMobile ? 12 : 14 }
        },
        paper_bgcolor: '#0f111a',
        plot_bgcolor: '#0f111a',
        font: { color: '#aaa', size: isMobile ? 10 : 12 },
        shapes: [
            // Quadrante 1 (Alto Dx): SURRISCALDAMENTO -> Rosso
            { type: 'rect', x0: 0, y0: 0, x1: 10, y1: 10, fillcolor: '#ff0000', opacity: 0.1, line: { width: 0 }, layer: 'below' },
            // Quadrante 2 (Alto Sx): TENSIONE -> Arancione
            { type: 'rect', x0: -10, y0: 0, x1: 0, y1: 10, fillcolor: '#ffa500', opacity: 0.1, line: { width: 0 }, layer: 'below' },
            // Quadrante 3 (Basso Sx): QUIETE -> Verde
            { type: 'rect', x0: -10, y0: -10, x1: 0, y1: 0, fillcolor: '#00ff00', opacity: 0.05, line: { width: 0 }, layer: 'below' },
            // Quadrante 4 (Basso Dx): VOLATILITÀ -> Blu
            { type: 'rect', x0: 0, y0: -10, x1: 10, y1: 0, fillcolor: '#0000ff', opacity: 0.1, line: { width: 0 }, layer: 'below' }
        ],
        hovermode: 'closest',
        margin: isMobile ?
            { t: 40, l: 30, r: 10, b: 40 } :  // Reduced bottom margin (no legend)
            { t: 50, l: 50, r: 50, b: 50 },
        showlegend: !isMobile, // HIDE LEGEND ON MOBILE
        legend: {
            orientation: 'v',
            x: 1.02,
            y: 1,
            xanchor: 'left',
            bgcolor: 'rgba(0,0,0,0)'
        },
        transition: { duration: 0 } // Disabilita animazione nativa plotly per performance
    };

    // Usa newPlot se l'elemento è vuoto (prima volta), altrimenti react
    const chartDiv = document.getElementById('radar-chart');
    // Poiché abbiamo pulito innerHTML in runRadarScan, newPlot è più sicuro per il primo frame.
    // Ma updateRadarFrame sarà chiamata ripetutamente.
    // Plotly.react gestisce entrambi    // Debug visuale se non ci sono punti
    if (xHead.length === 0) {
        layout.title.text += " [NESSUN DATO VISIBILE]";
    }

    const config = {
        responsive: true,
        displayModeBar: !isMobile // HIDE MODE BAR ON MOBILE
    };

    // Usa newPlot per garantire il rendering corretto anche la prima volta
    Plotly.newPlot('radar-chart', dataToPlot, layout, config);

    // Re-bind Click - FOCUS MODE + Double-click for Analysis
    document.getElementById('radar-chart').on('plotly_click', function (data) {
        const point = data.points[0];
        if (point.data.mode === 'lines') return; // Ignore trail click

        const tickerClicked = point.text;
        if (!tickerClicked) return;

        // Toggle Focus Mode
        if (FOCUSED_TICKER === tickerClicked) {
            // Click same ticker again = unfocus
            FOCUSED_TICKER = null;
        } else {
            // Focus on this ticker
            FOCUSED_TICKER = tickerClicked;
        }

        // Re-render radar with new focus state
        updateRadarFrame();

        // Update Analyze Button visibility
        updateAnalyzeButton();
    });

    // Double-click to run analysis
    document.getElementById('radar-chart').on('plotly_doubleclick', function () {
        if (FOCUSED_TICKER) {
            analyzeFocusedTicker();
        }
    });
}

// Toggle between Live Radar (2D) and Frozen Line (1D)
function toggleRadarMode() {
    const isFrozen = document.getElementById('radar-frozen-toggle').checked;

    if (isFrozen) {
        renderFrozenLine();
    } else {
        // Restore normal 2D radar
        updateRadarFrame();
    }
}

// Render 1D Frozen Z-Score Line Chart
function renderFrozenLine() {
    if (!RADAR_RESULTS_CACHE || RADAR_RESULTS_CACHE.length === 0) {
        console.warn("No radar data loaded for Frozen view");
        return;
    }

    // Get current slider position
    const sliderIdx = parseInt(document.getElementById('radar-slider').value);
    const dateLabel = document.getElementById('radar-date');

    // Update date label
    let currentDate = "N/A";
    for (let r of RADAR_RESULTS_CACHE) {
        if (r.history && r.history.dates && sliderIdx < r.history.dates.length) {
            currentDate = r.history.dates[sliderIdx];
            break;
        }
    }
    dateLabel.innerText = currentDate;

    // Extract frozen Z-scores for each ticker
    const points = [];
    RADAR_RESULTS_CACHE.forEach(r => {
        if (!r.history || !r.history.z_kin_frozen) return;
        if (sliderIdx >= r.history.z_kin_frozen.length) return;

        const frozenZ = r.history.z_kin_frozen[sliderIdx];
        if (frozenZ === null || frozenZ === undefined) return;

        // --- USE REAL BACKEND STRATEGY P/L (Yellow Line) ---
        // logic.py now computes this curve using backtest_strategy
        let tradePnl = 0;
        let inPosition = false;
        let currentPrice = 0;

        if (r.history.strategy_pnl && sliderIdx < r.history.strategy_pnl.length) {
            tradePnl = r.history.strategy_pnl[sliderIdx];
            // If P/L is exactly 0, it likely means NO POSITION (based on backend logic).
            // But entry steps are also 0. 
            // However, typically the Strategy returns 0 when out of market.
            // Let's assume non-zero means active or result.
            // The backend returns 0 when out of market.
            inPosition = tradePnl !== 0;
        }

        if (r.history.prices && sliderIdx < r.history.prices.length) {
            currentPrice = r.history.prices[sliderIdx];
        }

        // [NEW] Get SUM Strategy P/L (Red Line)
        let sumPnl = 0;
        if (r.history.sum_pnl && sliderIdx < r.history.sum_pnl.length) {
            sumPnl = r.history.sum_pnl[sliderIdx];
        }

        points.push({
            ticker: r.ticker,
            z: frozenZ,
            pnl: tradePnl,       // Orange
            sumPnl: sumPnl,     // Red
            active: inPosition || sumPnl !== 0,
            price: currentPrice
        });
    });

    if (points.length === 0) {
        console.warn("No frozen data points found");
        return;
    }

    // Sort by Z-score for cleaner display
    points.sort((a, b) => a.z - b.z);

    // Focus Mode Logic
    const opacities = points.map(p => {
        if (!FOCUSED_TICKER) return 1;
        return p.ticker === FOCUSED_TICKER ? 1 : 0.2; // Dim others
    });

    const sizes = points.map(p => {
        if (!FOCUSED_TICKER) return 18;
        return p.ticker === FOCUSED_TICKER ? 25 : 15; // Enlarge focused
    });

    const borderColors = points.map(p => {
        if (p.ticker === FOCUSED_TICKER) return '#eba834'; // Gold border for focused
        return '#333';
    });

    const borderWidths = points.map(p => {
        if (p.ticker === FOCUSED_TICKER) return 3;
        return 1;
    });

    // Create chart label (with P/L and Price for focused ticker)
    const labelText = points.map(p => {
        // Only show P/L info if this specific ticker is focused and in position
        if (FOCUSED_TICKER && p.ticker === FOCUSED_TICKER && p.active) {
            const sign = p.pnl > 0 ? '+' : '';
            return `${p.ticker} [$${p.price}] [${sign}${p.pnl.toFixed(1)}%]`;
        } else if (FOCUSED_TICKER && p.ticker === FOCUSED_TICKER) {
            // Focused but not in position - show 0%
            return `${p.ticker} [$${p.price}] [0%]`;
        } else {
            return p.ticker;
        }
    });

    // Color labels based on P/L (or Focus)
    const labelColors = points.map(p => {
        // Focus Logic overrides color or not? 
        // Let's mix: if focused, show P/L color. If unfocused, dim.
        if (FOCUSED_TICKER && p.ticker !== FOCUSED_TICKER) return 'rgba(255,255,255,0.2)';

        if (!p.active) return '#fff';
        return p.pnl > 0 ? '#00ff88' : '#ff4444';
    });

    // Create scatter plot (1D line with dots)
    const trace = {
        x: points.map(p => p.z),
        y: points.map(() => 0), // All on same horizontal line
        mode: 'markers+text',
        type: 'scatter',
        text: labelText,
        textposition: 'top center',
        textfont: {
            size: 10,
            color: labelColors
        },
        marker: {
            size: sizes,
            color: points.map(p => p.z),
            opacity: opacities,
            colorscale: [
                [0, '#ff4444'],     // Negative = Red
                [0.5, '#888888'],   // Zero = Gray
                [1, '#00ff88']      // Positive = Green
            ],
            cmin: -3,
            cmax: 3,
            line: {
                width: borderWidths,
                color: borderColors
            }
        },
        hoverinfo: 'text',
        hovertext: points.map(p => {
            const orangeSign = p.pnl > 0 ? '+' : '';
            const redSign = p.sumPnl > 0 ? '+' : '';
            return `${p.ticker}: Z=${p.z.toFixed(2)}\n🟠 ${orangeSign}${p.pnl?.toFixed(1) || 0}%  🔴 ${redSign}${p.sumPnl?.toFixed(1) || 0}%`;
        })
    };

    // Zero line reference
    const zeroLine = {
        x: [-4, 4],
        y: [0, 0],
        mode: 'lines',
        type: 'scatter',
        line: { color: '#444', width: 2, dash: 'dash' },
        hoverinfo: 'none',
        showlegend: false
    };

    const layout = {
        title: { text: '❄️ Frozen Z-Score Line', font: { color: '#00aaff', size: 16 } },
        paper_bgcolor: '#0f111a',
        plot_bgcolor: '#0f111a',
        xaxis: {
            title: 'Frozen Z-Score',
            color: '#888',
            gridcolor: '#333',
            zeroline: true,
            zerolinecolor: '#666',
            range: [-4, 4]
        },
        yaxis: {
            visible: false,
            range: [-1, 1.5]
        },
        margin: { l: 50, r: 50, t: 60, b: 50 },
        showlegend: false
    };

    const config = {
        responsive: true,
        displayModeBar: false
    };

    Plotly.newPlot('radar-chart', [zeroLine, trace], layout, config);

    // Click handler for frozen view
    document.getElementById('radar-chart').on('plotly_click', function (eventData) {
        const point = eventData.points.find(p => p.data.mode === 'markers+text');
        if (point) {
            const ticker = point.text;

            // Toggle Focus
            if (FOCUSED_TICKER === ticker) {
                FOCUSED_TICKER = null; // Deselect if already selected
            } else {
                FOCUSED_TICKER = ticker;
            }

            updateAnalyzeButton();
            renderFrozenLine(); // Re-render to apply opacity/size changes
        }
    });
}
// Update Analyze Button visibility and label
function updateAnalyzeButton() {
    const btn = document.getElementById('btn-analyze-focused');
    const label = document.getElementById('focused-ticker-label');

    if (FOCUSED_TICKER && btn) {
        btn.style.display = 'block';
        if (label) label.innerText = FOCUSED_TICKER;
    } else if (btn) {
        btn.style.display = 'none';
    }
}

// Analyze the currently focused ticker
function analyzeFocusedTicker() {
    if (!FOCUSED_TICKER) return;

    closeRadar();
    document.getElementById('ticker').value = FOCUSED_TICKER;
    FOCUSED_TICKER = null;
    updateAnalyzeButton(); // Hide button
    runAnalysis();
}


// 2. Render Categorie
function renderCategories() {
    categoriesContainer.innerHTML = "";
    Object.keys(TICKERS_DATA).forEach(cat => {
        const div = document.createElement("div");
        div.className = `category-item ${cat === currentCategory ? 'active' : ''}`;
        div.innerText = cat;
        div.onclick = () => {
            currentCategory = cat;
            renderCategories(); // Redraw to update active class
            renderTickers(cat);
        };
        categoriesContainer.appendChild(div);
    });
}

// 3. Render Tickers (filtrati per categoria e ricerca)
function renderTickers(category = null, filterText = "") {
    tickersContainer.innerHTML = "";

    let items = [];

    // Se c'è testo di ricerca, cerca in TUTTE le categorie
    if (filterText.length > 0) {
        const lowerFilter = filterText.toLowerCase();
        Object.values(TICKERS_DATA).flat().forEach(t => {
            if (t.symbol.toLowerCase().includes(lowerFilter) || t.name.toLowerCase().includes(lowerFilter)) {
                items.push(t);
            }
        });
    } else {
        // Altrimenti mostra solo la categoria selezionata
        items = TICKERS_DATA[category] || [];
    }

    // De-duplica (se serve) e Renderizza
    // (Set di simboli per evitare duplicati se la ricerca pesca la stessa cosa)
    const uniqueItems = [...new Map(items.map(item => [item['symbol'], item])).values()];

    if (uniqueItems.length === 0) {
        tickersContainer.innerHTML = "<div style='grid-column: 1/-1; text-align: center; color: #666; padding: 20px;'>Nessun risultato trovato</div>";
        return;
    }

    uniqueItems.forEach(ticker => {
        const card = document.createElement("div");
        card.className = "ticker-card";
        card.innerHTML = `
            <div class="ticker-symbol">${ticker.symbol}</div>
            <div class="ticker-name">${ticker.name}</div>
        `;
        card.onclick = () => selectTicker(ticker.symbol);
        tickersContainer.appendChild(card);
    });
}

// 4. Gestione Ricerca
const searchInput = document.getElementById('modal-search-input');
const mainInput = document.getElementById('ticker');
const categoriesContainer = document.getElementById('categories-list');
const tickersContainer = document.getElementById('tickers-grid');
let currentCategory = "⭐ Highlights"; // Default matching tickers.js key

searchInput.oninput = (e) => {
    const text = e.target.value;
    if (text) {
        // Disattiva selezione categoria visiva se cerco globalmente
        Array.from(document.querySelectorAll('.category-item')).forEach(el => el.classList.remove('active'));
    } else {
        // Ripristina categoria attiva visualmente
        renderCategories();
    }
    renderTickers(currentCategory, text);
}

// 5. Selezione
function selectTicker(symbol) {
    mainInput.value = symbol;
    modal.style.display = "none";
    // Opzionale: Auto-run analysis?
    // runAnalysis(); 
}

// --- FULLSCREEN UTILITY (iOS Fallback) ---
function toggleFullScreen(elementId) {
    const elem = document.getElementById(elementId);
    if (!elem) return;

    // Detect iOS (iPhone/iPad) or generic lack of API support
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    // Check if API exists
    const hasApi = elem.requestFullscreen || elem.webkitRequestFullscreen || elem.msRequestFullscreen;

    if (isIOS || !hasApi) {
        // Fallback: Toggle CSS class
        const parent = elem.parentElement; // Usually chart-container
        // Toggle on parent to handle position relative
        parent.classList.toggle('pseudo-fullscreen');

        // Force Resize Plotly
        if (typeof Plotly !== 'undefined') {
            setTimeout(() => { Plotly.Plots.resize(elem); }, 100);
        }
        return;
    }

    // Standard API
    if (!document.fullscreenElement) {
        if (elem.requestFullscreen) {
            elem.requestFullscreen();
        } else if (elem.webkitRequestFullscreen) { /* Safari */
            elem.webkitRequestFullscreen();
        } else if (elem.msRequestFullscreen) { /* IE11 */
            elem.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) { /* Safari */
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) { /* IE11 */
            document.msExitFullscreen();
        }
    }
}

// --- SCANNER MODAL FUNCTIONS ---
let SCAN_STOP_SIGNAL = false;

function openScannerModal() {
    const select = document.getElementById('scanner-category');
    select.innerHTML = ''; // Reset

    // Check if TICKERS_DATA exists
    if (typeof TICKERS_DATA !== 'undefined') {
        Object.keys(TICKERS_DATA).forEach(cat => {
            select.innerHTML += `<option value="${cat}">${cat}</option>`;
        });
        select.innerHTML += '<option value="ALL">🚨 TUTTI I TITOLI (Lento)</option>';
    }
    document.getElementById('scanner-modal').style.display = 'flex';
}

function closeScannerModal() {
    document.getElementById('scanner-modal').style.display = 'none';
    stopBulkScan();
}

async function startBulkScan() {
    const cat = document.getElementById('scanner-category').value;
    const tableBody = document.getElementById('scanner-results');
    const progressBar = document.getElementById('scan-progress');
    const statusLabel = document.getElementById('scan-status');
    const btnStart = document.getElementById('btn-start-scan');
    const btnStop = document.getElementById('btn-stop-scan');

    // UI Reset
    tableBody.innerHTML = '';
    progressBar.style.display = 'block';
    progressBar.value = 0;
    btnStart.style.display = 'none';
    btnStop.style.display = 'inline-block';
    SCAN_STOP_SIGNAL = false;

    // Build Ticker List
    let tickersToScan = [];
    if (cat === 'ALL') {
        Object.values(TICKERS_DATA).forEach(list => {
            tickersToScan = tickersToScan.concat(list.map(t => t.symbol));
        });
        // Deduplicate
        tickersToScan = [...new Set(tickersToScan)];
    } else {
        tickersToScan = TICKERS_DATA[cat].map(t => t.symbol);
    }

    progressBar.max = tickersToScan.length;

    // --- ACCUMULATORS FOR AVERAGE ---
    let totalLiveRet = 0;
    let totalFrozenRet = 0;
    let totalSumRet = 0;
    let totalWinLive = 0;
    let totalWinFrozen = 0;
    let totalWinSum = 0;
    let countStats = 0;

    // Global Trade Accumulator for Portfolio Simulator
    // Global Trade Accumulator for Portfolio Simulator
    window.ALL_SCAN_TRADES_LIVE = [];
    window.ALL_SCAN_TRADES_FROZEN = [];
    window.ALL_SCAN_TRADES = []; // Fallback/Reference

    // Get Parallelism Level
    const parallelism = parseInt(document.getElementById('scan-parallel').value) || 4;

    // Helper: Analyze a single ticker and return result
    async function analyzeTicker(ticker) {
        if (SCAN_STOP_SIGNAL) return null;

        try {
            const alpha = parseFloat(document.getElementById('alpha').value) || 200;
            const beta = parseFloat(document.getElementById('beta').value) || 1.0;
            const startDate = document.getElementById('scanner-start').value || "2023-01-01";
            let endDate = document.getElementById('scanner-end').value;
            if (endDate === "") endDate = null;

            const response = await fetch(`${API_URL}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: ticker,
                    alpha: alpha,
                    beta: beta,
                    top_k: 5,
                    forecast_days: 60,
                    start_date: startDate,
                    end_date: endDate,
                    use_cache: true
                })
            });

            if (!response.ok) return null;
            const data = await response.json();
            return { ticker, data };
        } catch (e) {
            console.error(`Error analyzing ${ticker}:`, e);
            return null;
        }
    }

    // Process in batches
    let processed = 0;
    for (let i = 0; i < tickersToScan.length; i += parallelism) {
        if (SCAN_STOP_SIGNAL) {
            statusLabel.innerHTML = '🛑 Scan Interrotto.';
            break;
        }

        // Create batch
        const batch = tickersToScan.slice(i, i + parallelism);
        statusLabel.innerHTML = `⚡ Analisi batch ${Math.floor(i / parallelism) + 1}/${Math.ceil(tickersToScan.length / parallelism)} (${batch.join(', ')})...`;

        // Execute batch in parallel
        const results = await Promise.all(batch.map(t => analyzeTicker(t)));

        // Process results
        for (const result of results) {
            if (!result) continue;

            const { ticker, data } = result;
            processed++;
            progressBar.value = processed;

            // Capture trades
            if (data.backtest?.trades) {
                data.backtest.trades.forEach(t => {
                    window.ALL_SCAN_TRADES_LIVE.push({ ...t, ticker: ticker });
                });
            }
            if (data.frozen_strategy?.trades) {
                data.frozen_strategy.trades.forEach(t => {
                    window.ALL_SCAN_TRADES_FROZEN.push({ ...t, ticker: ticker });
                });
            }
            window.ALL_SCAN_TRADES = window.ALL_SCAN_TRADES_LIVE;

            const liveStats = data.backtest?.stats;
            const frozenStats = data.frozen_strategy?.stats;
            const sumStats = data.frozen_sum_strategy?.stats;

            if (liveStats && frozenStats) {
                totalLiveRet += liveStats.total_return;
                totalFrozenRet += frozenStats.total_return;
                totalWinLive += liveStats.win_rate;
                totalWinFrozen += frozenStats.win_rate;
                if (sumStats) {
                    totalSumRet += sumStats.total_return;
                    totalWinSum += sumStats.win_rate;
                }
                countStats++;

                const liveRet = liveStats.total_return;
                const frozenRet = frozenStats.total_return;
                const sumRet = sumStats ? sumStats.total_return : 0;
                const sumWin = sumStats ? sumStats.win_rate : 0;
                const delta = (liveRet - frozenRet).toFixed(2);
                const deltaColor = parseFloat(delta) > 20 ? '#ff4444' : (parseFloat(delta) < -5 ? '#00ff88' : '#888');

                const row = `
                    <tr class="scan-row" data-kin="${data.avg_abs_kin || 0}" data-cap="${data.market_cap || 0}" style="border-bottom:1px solid #333;">
                        <td style="padding:10px; text-align:center;">
                            <input type="checkbox" class="scan-ticker-checkbox" data-ticker="${ticker}" checked>
                        </td>
                        <td style="padding:10px; font-weight:bold;">${ticker}</td>
                        <td style="padding:10px; color:#ccc;">${data.avg_abs_kin || '-'}</td>
                        <td style="padding:10px; color:#ccc;">${formatMarketCap(data.market_cap)}</td>
                        <td style="padding:10px; color:#ccc;">${data.backtest?.trades?.length || 0}</td>
                        <td style="color:${liveStats.win_rate >= 50 ? '#00ff88' : '#888'}">${liveStats.win_rate}%</td>
                        <td style="color:${liveRet > 0 ? '#00ff88' : '#ff4444'}">${liveRet}%</td>
                        <td style="color:${frozenStats.win_rate >= 50 ? '#ff9900' : '#888'}">${frozenStats.win_rate}%</td>
                        <td style="color:${frozenRet > 0 ? '#ff9900' : '#ff4444'}">${frozenRet}%</td>
                        <td style="color:${sumWin >= 50 ? '#ff4444' : '#888'}">${sumWin}%</td>
                        <td style="color:${sumRet > 0 ? '#ff4444' : '#888'}">${sumRet}%</td>
                        <td style="color:${deltaColor}; font-weight:bold;">${delta}%</td>
                        <td>
                            <button onclick="loadTickerFromScan('${ticker}')" style="background:#333; color:#fff; border:none; padding:4px 8px; cursor:pointer; font-size:0.8em; border-radius:4px;">🔍 Vedi</button>
                        </td>
                    </tr>
                `;
                tableBody.innerHTML += row;
            }
        }

        // Small delay between batches
        await new Promise(r => setTimeout(r, 50));
    }

    // --- APPEND AVERAGE ROW & SIMULATOR BUTTON ---
    if (countStats > 0) {
        const avgLiveRet = (totalLiveRet / countStats).toFixed(2);
        const avgFrozenRet = (totalFrozenRet / countStats).toFixed(2);
        const avgSumRet = (totalSumRet / countStats).toFixed(2);
        const avgWinLive = (totalWinLive / countStats).toFixed(1);
        const avgWinFrozen = (totalWinFrozen / countStats).toFixed(1);
        const avgWinSum = (totalWinSum / countStats).toFixed(1);
        const avgDelta = (avgLiveRet - avgFrozenRet).toFixed(2);

        const statsRow = `
            <tr style="border-top: 3px solid #eba834; background: rgba(235, 168, 52, 0.15); font-weight: bold; font-size: 1.05em;">
                <td></td>
                <td colspan="4" style="padding:15px; color:#eba834; text-align:center;">📊 MEDIA (${countStats})</td>
                <td style="color:${avgWinLive >= 50 ? '#00ff88' : '#bbb'}">${avgWinLive}%</td>
                <td style="color:${avgLiveRet > 0 ? '#00ff88' : '#ff4444'}">${avgLiveRet}%</td>
                <td style="color:${avgWinFrozen >= 50 ? '#ff9900' : '#bbb'}">${avgWinFrozen}%</td>
                <td style="color:${avgFrozenRet > 0 ? '#ff9900' : '#ff4444'}">${avgFrozenRet}%</td>
                <td style="color:${avgWinSum >= 50 ? '#ff4444' : '#bbb'}">${avgWinSum}%</td>
                <td style="color:${avgSumRet > 0 ? '#ff4444' : '#888'}">${avgSumRet}%</td>
                <td style="color:#eba834;">${avgDelta}%</td>
                <td>
                    <button onclick="openSimulatorModal()" style="background:#00ff88; color:#000; font-weight:bold; border:none; padding:6px 10px; cursor:pointer; border-radius:4px; box-shadow:0 2px 5px rgba(0,0,0,0.5);">
                        💰 SIMULA
                    </button>
                </td>
            </tr>
        `;
        tableBody.innerHTML += statsRow;

        // Auto scroll to bottom
        tableBody.parentElement.parentElement.scrollTop = tableBody.parentElement.parentElement.scrollHeight;
    }

    if (!SCAN_STOP_SIGNAL) {
        statusLabel.innerHTML = '✅ Scan Completato!';
    }

    // Reset Buttons
    document.getElementById('btn-stop-scan').style.display = 'none';
    document.getElementById('btn-start-scan').style.display = 'inline-block';
}

// --- PORTFOLIO SIMULATOR FUNCTIONS ---

function openSimulatorModal() {
    const modal = document.getElementById('simulator-modal');
    // Check if we have trades
    if (!window.ALL_SCAN_TRADES || window.ALL_SCAN_TRADES.length === 0) {
        alert("Esegui prima una scansione per raccogliere i dati!");
        return;
    }

    document.getElementById('sim-total-trades').textContent = window.ALL_SCAN_TRADES.length;
    modal.style.display = 'flex';

    // Auto-run with default capital if trades exist
    if (window.ALL_SCAN_TRADES.length > 0) {
        runPortfolioSimulation();
    }
}

function closeSimulatorModal() {
    document.getElementById('simulator-modal').style.display = 'none';
}

function runPortfolioSimulation() {
    const capitalPerTrade = parseFloat(document.getElementById('sim-capital').value) || 100;
    const mode = document.getElementById('sim-mode').value; // LIVE or FROZEN

    // Select Source Data
    let sourceTrades = window.ALL_SCAN_TRADES_LIVE;
    const content = document.getElementById('sim-modal-content');

    if (mode === 'FROZEN') {
        sourceTrades = window.ALL_SCAN_TRADES_FROZEN;
        if (content) content.style.background = '#1a1d2a'; // Reset
    } else {
        // LIVE/IDEAL -> Warning Background
        if (content) content.style.background = 'linear-gradient(180deg, rgba(60, 20, 20, 1) 0%, #1a1d2a 100%)';
    }

    // Filter tickers based on checkboxes AND visibility
    const checkedTickers = Array.from(document.querySelectorAll('.scan-ticker-checkbox:checked'))
        .filter(cb => cb.closest('tr').style.display !== 'none')
        .map(cb => cb.dataset.ticker);

    const trades = sourceTrades.filter(t => checkedTickers.includes(t.ticker));

    // Update Trade Count UI
    if (document.getElementById('sim-total-trades')) {
        document.getElementById('sim-total-trades').innerText = trades.length;
    }

    if (!trades || trades.length === 0) return;

    // Get the selected date range from scanner for chart limits
    const chartStartDate = document.getElementById('scanner-start').value || null;
    const chartEndDate = document.getElementById('scanner-end').value || new Date().toISOString().split('T')[0];

    // 1. Determine Timeline
    // Filter out invalid dates
    const validTrades = trades.filter(t => t.entry_date);

    // Sort by Entry Date
    validTrades.sort((a, b) => new Date(a.entry_date) - new Date(b.entry_date));

    if (validTrades.length === 0) return;

    const minDate = new Date(validTrades[0].entry_date);
    const maxDate = new Date(); // Today

    // Generate Date Range Array
    const dateRange = [];
    let curr = new Date(minDate);
    while (curr <= maxDate) {
        dateRange.push(curr.toISOString().split('T')[0]);
        curr.setDate(curr.getDate() + 1);
    }

    // 2. Simulation Loop
    const equityCurve = [];        // Realized only
    const totalEquityCurve = [];   // Realized + Unrealized
    const exposureCurve = [];
    let cumulativeRealizedProfit = 0;

    // Track open trades for unrealized calc
    const openTrades = new Map(); // trade -> { entryDate, pnl_pct }

    // Pre-process trades for faster lookup
    const events = {};

    validTrades.forEach(t => {
        const entry = t.entry_date;
        let exit = t.exit_date;
        const isOpen = !exit || exit === 'OPEN';
        if (isOpen) exit = chartEndDate || new Date().toISOString().split('T')[0];

        if (!events[entry]) events[entry] = [];
        events[entry].push({ type: 'OPEN', trade: t });

        if (!events[exit]) events[exit] = [];
        events[exit].push({ type: 'CLOSE', trade: t, isForced: isOpen });
    });

    let activeTrades = 0;

    dateRange.forEach(date => {
        // Process Daily Events
        if (events[date]) {
            events[date].forEach(e => {
                if (e.type === 'OPEN') {
                    activeTrades++;
                    openTrades.set(e.trade, { pnl_pct: e.trade.pnl_pct || 0 });
                } else if (e.type === 'CLOSE') {
                    const ret = e.trade.pnl_pct || 0;
                    const profit = capitalPerTrade * (ret / 100);
                    cumulativeRealizedProfit += profit;
                    openTrades.delete(e.trade);
                    activeTrades--;
                }
            });
        }

        // Ensure non-negative active trades (safety)
        if (activeTrades < 0) activeTrades = 0;

        // Calculate unrealized profit from open trades
        let unrealizedProfit = 0;
        openTrades.forEach((info) => {
            unrealizedProfit += capitalPerTrade * (info.pnl_pct / 100);
        });

        const currentExposure = activeTrades * capitalPerTrade;

        equityCurve.push({ date: date, value: cumulativeRealizedProfit });
        totalEquityCurve.push({ date: date, value: cumulativeRealizedProfit + unrealizedProfit });
        exposureCurve.push({ date: date, value: currentExposure });
    });

    // 3. Calculate Metrics
    const maxExposure = Math.max(...exposureCurve.map(d => d.value));
    const totalProfit = cumulativeRealizedProfit;
    const roiOnMax = maxExposure > 0 ? (totalProfit / maxExposure) * 100 : 0;

    // 4. Update UI
    document.getElementById('sim-max-exposure').textContent = `€ ${maxExposure.toLocaleString()}`;
    document.getElementById('sim-net-profit').textContent = `€ ${totalProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById('sim-roi').textContent = `${roiOnMax.toFixed(2)}%`;

    document.getElementById('sim-net-profit').style.color = totalProfit >= 0 ? '#00ff88' : '#ff4444';
    document.getElementById('sim-roi').style.color = roiOnMax >= 0 ? '#00ff88' : '#ff4444';

    // 5. Render Charts

    // Equity Chart (Area/Line)
    const traceEquityRealized = {
        x: equityCurve.map(d => d.date),
        y: equityCurve.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        name: 'Realizzato',
        line: { color: '#00ff88', width: 2 }
    };

    // Final Jump (Unrealized) - Only the last segment
    const lastRealizedPoint = equityCurve[equityCurve.length - 1];
    const lastTotalPoint = totalEquityCurve[totalEquityCurve.length - 1];
    const unrealizedDiff = lastTotalPoint.value - lastRealizedPoint.value;

    const traceUnrealizedJump = {
        x: [lastRealizedPoint.date, lastRealizedPoint.date],
        y: [lastRealizedPoint.value, lastTotalPoint.value],
        type: 'scatter',
        mode: 'lines+markers',
        name: `Unrealized (${unrealizedDiff >= 0 ? '+' : ''}€${unrealizedDiff.toFixed(0)})`,
        line: { color: '#ffaa00', width: 5, dash: 'dot' },
        marker: { size: 14, color: '#ffaa00', symbol: 'diamond' }
    };

    Plotly.newPlot('chart-sim-equity', [traceEquityRealized, traceUnrealizedJump], {
        title: { text: '📈 Curva dei Profitti', font: { color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { color: '#888', gridcolor: '#333', range: chartStartDate ? [chartStartDate, chartEndDate] : null },
        yaxis: { color: '#888', gridcolor: '#333', tickprefix: '€' },
        margin: { l: 50, r: 20, t: 40, b: 40 },
        legend: { font: { color: '#ccc' }, x: 0.02, y: 0.98 }
    });

    // Exposure Chart (Step/Bar)
    const traceExposure = {
        x: exposureCurve.map(d => d.date),
        y: exposureCurve.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        name: 'Capitale Investito',
        line: { color: '#eba834', width: 2, shape: 'hv' } // Step-shape for capital
    };

    Plotly.newPlot('chart-sim-exposure', [traceExposure], {
        title: { text: '🏦 Capitale Esposto nel Tempo (Max Drawdown Risk)', font: { color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { color: '#888', gridcolor: '#333', range: chartStartDate ? [chartStartDate, chartEndDate] : null },
        yaxis: { color: '#888', gridcolor: '#333', tickprefix: '€' },
        margin: { l: 50, r: 20, t: 40, b: 40 }
    });

    // 6. Populate Trades List
    const listBody = document.getElementById('sim-trades-body');
    listBody.innerHTML = '';

    validTrades.forEach(t => {
        // Assume close Today if OPEN
        let exitDate = t.exit_date;
        let pnlPct = t.pnl_pct;

        // If trade is effectively "OPEN" (no exit date or specifically marked)
        // logic.py returns "OPEN" as string for open trades.
        const isOpen = (exitDate === 'OPEN' || !exitDate);

        if (isOpen) {
            exitDate = "IN CORSO";
            // Unrealized PnL logic was handled in logic.py which populates 'pnl_pct' for OPEN trades too
        }

        const profitVal = capitalPerTrade * ((pnlPct || 0) / 100);
        const color = (pnlPct || 0) >= 0 ? '#00ff88' : '#ff4444';
        const directionIcon = t.direction === 'LONG' ? '🟢' : '🔴';

        const tr = `
            <tr style="border-bottom:1px solid #333;">
                <td style="padding:10px; font-weight:bold;">${t.ticker}</td>
                <td style="padding:10px;">${t.entry_date}</td>
                <td style="padding:10px;">${exitDate}</td>
                <td style="padding:10px;">${directionIcon} ${t.direction || 'N/A'}</td>
                <td style="padding:10px; color:${color}; font-weight:bold;">${(pnlPct || 0).toFixed(2)}%</td>
                <td style="padding:10px; color:${color}; font-weight:bold;">€ ${profitVal.toFixed(2)}</td>
            </tr>
        `;
        listBody.innerHTML += tr;
    });
}


function stopBulkScan() {
    SCAN_STOP_SIGNAL = true;
}

function loadTickerFromScan(ticker) {
    closeScannerModal();
    document.getElementById('ticker').value = ticker;
    runAnalysis();
}

// Toggle All Checkboxes
function toggleAllScanRows(source) {
    const checkboxes = document.querySelectorAll('.scan-ticker-checkbox');
    checkboxes.forEach(cb => {
        // Only toggle visible rows if we want to be smart? Or all?
        // Standard behavior: Toggle All (even hidden). But mostly user wants visible.
        if (cb.closest('tr').style.display !== 'none') {
            cb.checked = source.checked;
        }
    });
}

// FORMAT MARKET CAP
function formatMarketCap(value) {
    if (!value) return '-';
    if (value >= 1e12) return (value / 1e12).toFixed(2) + 'T';
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    return parseInt(value).toLocaleString();
}

// APPLY FILTERS
function applyScanFilters() {
    const minKin = parseFloat(document.getElementById('filter-kin-min').value) || 0;
    const minCapB = parseFloat(document.getElementById('filter-cap-min').value) || 0;
    const minCapVal = minCapB * 1e9; // Convert Billions

    const rows = document.querySelectorAll('.scan-row');
    rows.forEach(row => {
        const kin = parseFloat(row.dataset.kin);
        const cap = parseFloat(row.dataset.cap);

        let visible = true;
        if (kin < minKin) visible = false;
        if (cap < minCapVal) visible = false;

        row.style.display = visible ? '' : 'none';
    });
}

// --- CHART VISIBILITY TOGGLE LISTENERS ---
// Re-render chart when toggles change (uses cached data)
['show-price', 'show-energy', 'show-frozen', 'show-indicators', 'show-zigzag', 'show-backtest', 'show-volume', 'show-kinetic-z'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener('change', (e) => {
            // Update icon opacity
            const icon = el.parentElement.querySelector('.toggle-icon');
            if (icon) {
                icon.style.opacity = el.checked ? '1' : '0.3';
            }

            // If we have cached data, re-render without API call
            if (window.LAST_ANALYSIS_DATA) {
                renderCharts(window.LAST_ANALYSIS_DATA);
            }
        });
    }
});


// --- SIDEBAR TOGGLE ---
// --- SIDEBAR TOGGLE ---
function toggleSidebar() {
    const toggles = document.getElementById('chart-toggles');
    const arrow = document.getElementById('collapse-arrow');

    if (!toggles || !arrow) return;

    // Check current state
    const isCollapsed = toggles.style.display === 'none';

    if (isCollapsed) {
        // EXPAND
        toggles.style.display = 'flex';
        arrow.innerText = '‹'; // Left to collapse
    } else {
        // COLLAPSE
        toggles.style.display = 'none';
        arrow.innerText = '›'; // Right to expand
    }

    // Trigger resize for chart (Plotly needs to know container changed)
    setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
    }, 320);
}

// ============================================
// VERTICAL ANNOTATION SYSTEM (Clickable Lines)
// ============================================

// Global state for annotation mode
window.ANNOTATION_MODE = null; // 'green', 'red', or null
window.CHART_ANNOTATIONS = []; // [{x: date, color: 'green'|'red'}, ...]

// Load annotations from localStorage
function loadAnnotations() {
    try {
        const ticker = document.getElementById('ticker')?.value || 'DEFAULT';
        const saved = localStorage.getItem(`annotations_${ticker}`);
        window.CHART_ANNOTATIONS = saved ? JSON.parse(saved) : [];
    } catch (e) {
        window.CHART_ANNOTATIONS = [];
    }
}

// Save annotations to localStorage
function saveAnnotations() {
    try {
        const ticker = document.getElementById('ticker')?.value || 'DEFAULT';
        localStorage.setItem(`annotations_${ticker}`, JSON.stringify(window.CHART_ANNOTATIONS));
    } catch (e) {
        console.warn('Could not save annotations');
    }
}

// Set annotation mode (called by buttons)
function setAnnotationMode(mode) {
    const btnGreen = document.getElementById('btn-anno-green');
    const btnRed = document.getElementById('btn-anno-red');
    const btnBlue = document.getElementById('btn-anno-blue');
    const btnPurple = document.getElementById('btn-anno-purple');
    const btnClear = document.getElementById('btn-anno-clear');

    // Reset all button styles
    [btnGreen, btnRed, btnBlue, btnPurple, btnClear].forEach(btn => {
        if (btn) btn.style.background = 'transparent';
    });

    if (mode === 'clear') {
        // Clear all annotations for current ticker
        window.CHART_ANNOTATIONS = [];
        saveAnnotations();
        window.ANNOTATION_MODE = null;

        // Re-render chart to remove shapes
        if (window.LAST_ANALYSIS_DATA) {
            renderCharts(window.LAST_ANALYSIS_DATA);
        }
        return;
    }

    // Toggle mode
    if (window.ANNOTATION_MODE === mode) {
        window.ANNOTATION_MODE = null; // Deactivate
    } else {
        window.ANNOTATION_MODE = mode;
        // Highlight active button
        let activeBtn = null;
        if (mode === 'green') activeBtn = btnGreen;
        if (mode === 'red') activeBtn = btnRed;
        if (mode === 'blue') activeBtn = btnBlue;
        if (mode === 'purple') activeBtn = btnPurple;

        if (activeBtn) activeBtn.style.background = 'rgba(255,255,255,0.15)';
    }

    console.log('Annotation mode:', window.ANNOTATION_MODE);
}

// Convert annotations to Plotly shapes
function getAnnotationShapes() {
    return window.CHART_ANNOTATIONS.map(anno => {
        let color = '#ffffff';
        if (anno.color === 'green') color = '#00ff88';
        if (anno.color === 'red') color = '#ff4444';
        if (anno.color === 'blue') color = '#3366ff';
        if (anno.color === 'purple') color = '#aa33ff';

        return {
            type: 'line',
            x0: anno.x,
            x1: anno.x,
            y0: 0,
            y1: 1,
            yref: 'paper', // Full height
            line: {
                color: color,
                width: 2,
                dash: 'solid'
            },
            layer: 'below'
        };
    });
}

// Setup click handler for the chart (called after Plotly.newPlot)
function setupChartClickHandler() {
    const chartDiv = document.getElementById('chart-combined');
    if (!chartDiv) return;

    // Remove existing handler to avoid duplicates
    chartDiv.removeAllListeners?.('plotly_click');

    chartDiv.on('plotly_click', function (data) {
        if (!window.ANNOTATION_MODE) return;

        // Get X coordinate (date)
        const clickX = data.points[0]?.x;
        if (!clickX) return;

        // Check if annotation already exists at this X (remove if so)
        const existingIndex = window.CHART_ANNOTATIONS.findIndex(a => a.x === clickX);
        if (existingIndex >= 0) {
            // Remove existing annotation
            window.CHART_ANNOTATIONS.splice(existingIndex, 1);
        } else {
            // Add new annotation
            window.CHART_ANNOTATIONS.push({
                x: clickX,
                color: window.ANNOTATION_MODE
            });
        }

        saveAnnotations();

        // Update chart shapes without full re-render
        const currentLayout = chartDiv.layout || {};
        currentLayout.shapes = getAnnotationShapes();
        Plotly.relayout(chartDiv, { shapes: currentLayout.shapes });
    });
}

// Initialize annotations when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadAnnotations();

    // Add listener for new Kinetic Z toggle
    document.getElementById('show-kinetic-z')?.addEventListener('change', () => {
        if (currentAnalysisData) renderCharts(currentAnalysisData);
    });
});
// Helper to get tickers (Shared)
// Helper to get tickers (Shared)
function getTickersForCategory(category) {
    if (!window.TICKERS_DATA) return [];

    // Mapping from HTML values to TICKERS_DATA keys
    const CATEGORY_MAP = {
        'ALL': 'ALL',
        'HIGHLIGHTS': '⭐ Highlights',
        'US_MEGA': '🏛️ US Mega Cap',
        'US_TECH': '💻 US Tech',
        'US_FINANCE': '🏦 US Finance',
        'US_HEALTH': '🏥 US Healthcare',
        'US_INDUSTRIAL': '🏭 US Industrials',
        'US_CONSUMER': '🛒 US Consumer',
        'US_ENERGY': '⚡ US Energy',
        'US_MIDCAP': '📈 US Mid Cap A-L',
        'UK': '🇬🇧 UK (FTSE)',
        'DE': '🇩🇪 Germany (DAX)',
        'FR': '🇫🇷 France (CAC 40)',
        'IT': '🇮🇹 Italy (MIB)',
        'EU_ALL': 'EU_ALL',
        'JP': '🇯🇵 Japan',
        'CN': '🇨🇳 China / HK',
        'KR': '🇰🇷 Korea',
        'TW': '🇹🇼 Taiwan',
        'IN': '🇮🇳 India',
        'ETF': '📊 Major ETFs',
        'CRYPTO': '🪙 Crypto',
        'COMMODITIES': '🛢️ Commodities'
    };

    // Special Merging Logic
    if (category === 'US_MIDCAP') {
        const list1 = window.TICKERS_DATA['📈 US Mid Cap A-L'] || [];
        const list2 = window.TICKERS_DATA['📉 US Mid Cap M-Z'] || [];
        return [...list1, ...list2].map(t => t.symbol);
    }

    if (category === 'ALL') {
        let all = [];
        Object.values(window.TICKERS_DATA).forEach(list => {
            all = all.concat(list.map(t => t.symbol));
        });
        return [...new Set(all)];
    }

    if (category === 'EU_ALL') {
        const euKeys = ['🇬🇧 UK (FTSE)', '🇩🇪 Germany (DAX)', '🇫🇷 France (CAC 40)', '🇮🇹 Italy (MIB)', '🇳🇱 Netherlands', '🇪🇸 Spain', '🇨🇭 Switzerland'];
        let allEu = [];
        euKeys.forEach(k => {
            if (window.TICKERS_DATA[k]) allEu = allEu.concat(window.TICKERS_DATA[k].map(t => t.symbol));
        });
        return [...new Set(allEu)];
    }

    const dataKey = CATEGORY_MAP[category];
    if (dataKey && window.TICKERS_DATA[dataKey]) {
        return window.TICKERS_DATA[dataKey].map(t => t.symbol);
    }

    return [];
}

// Ensure functions are global
window.openDailyScanModal = openDailyScanModal;
window.closeDailyScanModal = closeDailyScanModal;
window.runDailyScan = runDailyScan;

// --- DAILY SCANNER LOGIC ---

function openDailyScanModal() {
    document.getElementById('daily-scan-modal').style.display = 'flex';
}

function closeDailyScanModal() {
    document.getElementById('daily-scan-modal').style.display = 'none';
}

// Time Navigation: Shift date by N days and re-run scan
function shiftScanDate(days) {
    const dateInput = document.getElementById('daily-scan-date');
    let currentDate = dateInput.value ? new Date(dateInput.value) : new Date();

    // Shift by N days
    currentDate.setDate(currentDate.getDate() + days);

    // Format as YYYY-MM-DD
    const year = currentDate.getFullYear();
    const month = String(currentDate.getMonth() + 1).padStart(2, '0');
    const day = String(currentDate.getDate()).padStart(2, '0');
    dateInput.value = `${year}-${month}-${day}`;

    // Auto-run scan
    runDailyScan();
}

// Export to window
window.shiftScanDate = shiftScanDate;

async function runDailyScan() {
    const category = document.getElementById('daily-scan-category').value;
    const tickers = getTickersForCategory(category);
    const asOfDate = document.getElementById('daily-scan-date').value || null; // Time travel date

    if (tickers.length === 0) {
        alert("Nessun ticker trovato per questa categoria.");
        return;
    }

    const progress = document.getElementById('daily-scan-progress');
    const status = document.getElementById('daily-scan-status');
    const tbody = document.getElementById('daily-scan-results');

    // Reset UI
    progress.style.display = 'block';
    progress.value = 10; // Started
    status.style.display = 'block';
    const dateLabel = asOfDate ? ` (data: ${asOfDate})` : ' (oggi)';
    status.innerText = `Analisi in corso su ${tickers.length} titoli${dateLabel}...`;
    tbody.innerHTML = ''; // Clear previous results

    try {
        // Call API
        const response = await fetch(`${API_URL}/scan-daily`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tickers: tickers, as_of_date: asOfDate })
        });

        if (!response.ok) throw new Error("Errore scansione backend");

        const results = await response.json();

        progress.value = 100;
        status.innerText = `Scansione completata: ${results.length} risultati.`;

        renderDailyScanResults(results);

    } catch (err) {
        console.error(err);
        status.innerText = "Errore durante la scansione.";
        progress.style.display = 'none';
    }
}

function renderDailyScanResults(results) {
    const tbody = document.getElementById('daily-scan-results');
    let html = '';

    if (!results || results.length === 0) {
        html = '<tr><td colspan="6" style="padding:20px; text-align:center; color:#888;">Nessun segnale rilevato o errore di connessione.</td></tr>';
        tbody.innerHTML = html;
        return;
    }

    // Sort logic: Actionable first (BUY/SELL), then others
    // Sorting happens in backend by Market Cap, but let's prioritize ACTION here
    const actionable = [];
    const others = [];

    results.forEach(r => {
        const hasAction = (r.frozen && (r.frozen.action === 'BUY' || r.frozen.action === 'SELL')) ||
            (r.sum && (r.sum.action === 'BUY' || r.sum.action === 'SELL'));
        if (hasAction) actionable.push(r);
        else others.push(r);
    });

    // Combine: Actionable first
    const sortedResults = [...actionable, ...others];

    sortedResults.forEach(r => {
        // Resolve Action & Date Logic
        const scanDateInput = document.getElementById('daily-scan-date').value;
        const todayStr = new Date().toISOString().split('T')[0];
        const refDate = scanDateInput || todayStr;

        const resolveStat = (resObj) => {
            if (!resObj || !resObj.action) return { action: '-', date: '-', isRecent: false };

            let act = resObj.action;
            let date = '-';
            let isRecent = false;

            if (resObj.trade) {
                date = resObj.trade.entry_date;
                // Calc Diff
                const d1 = new Date(refDate);
                const d2 = new Date(date);
                const diffTime = d1 - d2;
                const diffDays = diffTime / (1000 * 60 * 60 * 24);

                // Highlight if recent (<= 5 days) & not future
                if (diffDays >= 0 && diffDays <= 5) isRecent = true;

                // Override BUY -> HOLD if strictly past
                if (act === 'BUY' && date < refDate) {
                    act = 'HOLD';
                }

                // Append Direction (LONG/SHORT)
                if (resObj.trade.direction) {
                    act += ` ${resObj.trade.direction}`;
                }
            }
            return { action: act, date: date, isRecent: isRecent };
        };

        const fInfo = resolveStat(r.frozen);
        const sInfo = resolveStat(r.sum);

        const frozenAction = fInfo.action;
        const sumAction = sInfo.action;

        // Date Styles
        let fDateStyle = "color:#888;";
        if (fInfo.isRecent) fDateStyle = "color:#00ff88; font-weight:bold;";

        let sDateStyle = "color:#888;";
        if (sInfo.isRecent) sDateStyle = "color:#00ff88; font-weight:bold;";

        const getActionStyle = (action) => {
            if (action.includes('BUY')) return 'color:#00ff88; font-weight:bold;';
            if (action.includes('SELL')) return 'color:#ff4444; font-weight:bold;';
            return 'color:#888;';
        };

        const frozenStyle = getActionStyle(frozenAction);
        const sumStyle = getActionStyle(sumAction);

        // Final Action Logic (Combined recommendation)
        let finalAction = "-";
        let finalStyle = "color:#666;";

        const isBuy = (a) => a.includes('BUY');
        const isHold = (a) => a.includes('HOLD');
        const isSell = (a) => a.includes('SELL');

        if (isBuy(frozenAction) && isBuy(sumAction)) {
            finalAction = "🚀 STRONG BUY";
            finalStyle = "color:#00ff88; font-weight:900; background:rgba(0,255,136,0.2); padding:4px 8px; border-radius:4px;";
        } else if (isBuy(frozenAction)) {
            finalAction = "🟢 BUY (Trend)";
            finalStyle = "color:#00ff88; font-weight:bold;";
        } else if (isBuy(sumAction)) {
            finalAction = "🟡 BUY (Speculative)";
            finalStyle = "color:#ffcc00; font-weight:bold;";
        } else if (isSell(frozenAction) || isSell(sumAction)) {
            finalAction = "🔴 SELL / EXIT";
            finalStyle = "color:#ff4444; font-weight:bold;";
        }

        const tradeDir = (frozenAction.includes('SHORT') || sumAction.includes('SHORT')) ? 'SHORT' : 'LONG';

        html += `<tr style="border-bottom:1px solid #333;">
            <td style="padding:12px; font-weight:bold; color:#fff;">${r.ticker}</td>
            <td style="padding:12px; color:#ccc;">${r.frozen ? r.frozen.value : '-'} (Z)</td>
            
            <td style="padding:12px; ${fDateStyle}">${fInfo.date}</td>
            <td style="padding:12px; ${frozenStyle}">${frozenAction}</td>
            
            <td style="padding:12px; ${sDateStyle}">${sInfo.date}</td>
            <td style="padding:12px; ${sumStyle}">${sumAction}</td>
            
            <td style="padding:12px; ${finalStyle}">${finalAction}</td>
            <td style="padding:12px;">
                <div style="display:flex; justify-content:center; gap:8px;">
                    <button onclick="pfQuickOpen('${r.ticker}', '${tradeDir}')" 
                        style="background:#2d3342; border:1px solid #7d4bf0; color:#d9ccff; border-radius:4px; padding:4px 8px; cursor:pointer;" title="Apri in Portafoglio Reale">
                        💼
                    </button>
                    <button onclick="loadTickerFromScanner('${r.ticker}')" 
                        style="background:#333; border:1px solid #555; color:#fff; border-radius:4px; padding:4px 8px; cursor:pointer;" title="Carica nel Grafico">
                        ⚡
                    </button>
                </div>
            </td>
        </tr>`;
    });

    tbody.innerHTML = html;
}

function loadTickerFromScanner(ticker) {
    // 1. Sync Date (Time Travel)
    const scanDate = document.getElementById('daily-scan-date').value;
    if (scanDate) {
        document.getElementById('end-date').value = scanDate;
    }

    // 2. Sync Ticker
    document.getElementById('ticker').value = ticker;

    // 3. UI
    closeDailyScanModal();
    runAnalysis(); // Trigger main analysis
}

/* =========================================
   PORTFOLIO REAL SIMULATION
   ========================================= */

function openPortfolioModal() {
    const m = document.getElementById('portfolio-modal');
    if (m) {
        m.style.display = 'flex';
        pfLoadData();

        // Setup Close
        const closeBtn = m.querySelector('.close-modal');
        if (closeBtn) closeBtn.onclick = () => m.style.display = 'none';

        // Double check global close listener
        m.onclick = (e) => {
            if (e.target === m) m.style.display = 'none';
        }
    }
}

async function pfLoadData() {
    const openList = document.getElementById('pf-open-list');
    const closedList = document.getElementById('pf-closed-list');

    // Clear (9 cols)
    openList.innerHTML = '<tr><td colspan="9">Caricamento...</td></tr>';

    try {
        const res = await fetch(`${API_URL}/portfolio`);
        const data = await res.json();

        openList.innerHTML = '';
        closedList.innerHTML = '';

        const positions = data.positions || [];

        // Split Open vs Closed
        const openPos = positions.filter(p => p.status === 'OPEN').reverse(); // Newest first
        const closedPos = positions.filter(p => p.status === 'CLOSED').reverse();

        // Render OPEN
        if (openPos.length === 0) {
            openList.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:#555;">Nessuna posizione aperta</td></tr>';
        }

        openPos.forEach(p => {
            const color = p.pnl_pct >= 0 ? '#00ff88' : '#ff4444';
            const sign = p.pnl_pct >= 0 ? '+' : '';
            const dirIcon = p.direction === 'LONG' ? '🟢' : '🔴';
            const safeStrat = (p.strategy || 'Manuale').replace(/'/g, "\\'");
            const safeNotes = (p.notes || '').replace(/'/g, "\\'");

            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #333';
            tr.innerHTML = `
                <td style="padding:10px; font-weight:bold; color:#fff;">${p.ticker}</td>
                <td style="padding:10px;">${dirIcon} ${p.direction}</td>
                <td onclick="pfEditStrategy(this, '${p.id}', '${safeStrat}')" title="Clicca per modificare" style="padding:10px; color:#aaa; font-size:0.9em; cursor:pointer; border-bottom:1px dashed #444;">${p.strategy || 'Manuale'} ✏️</td>
                <td onclick="pfUpdateField('${p.id}', 'notes', '${safeNotes}')" title="Clicca per modificare" style="padding:10px; color:#aaa; font-style:italic; font-size:0.9em; cursor:pointer; border-bottom:1px dashed #444;">${p.notes || '-'} ✏️</td>
                <td style="padding:10px; color:#888;">${p.entry_date}</td>
                <td style="padding:10px;">${p.entry_price}</td>
                <td style="padding:10px; font-weight:bold;">${p.current_price}</td>
                <td style="padding:10px; font-weight:bold; color:${color};">${sign}${p.pnl_pct}%</td>
                <td style="padding:10px; text-align:right;">
                    <button onclick="pfClosePosition('${p.id}')" 
                        style="background:#333; border:1px solid #555; color:#fff; padding:4px 8px; border-radius:4px; cursor:pointer; font-size:0.8rem;">
                        CHIUDI 🔒
                    </button>
                </td>
             `;
            openList.appendChild(tr);
        });

        // Render CLOSED
        closedPos.forEach(p => {
            const color = p.pnl_pct >= 0 ? '#00ff88' : '#ff4444';
            const sign = p.pnl_pct >= 0 ? '+' : '';
            const dirIcon = p.direction === 'LONG' ? '🟢' : '🔴';
            const safeStrat = (p.strategy || 'Manuale').replace(/'/g, "\\'");
            const safeNotes = (p.notes || '').replace(/'/g, "\\'");

            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #333';
            tr.innerHTML = `
                <td style="padding:10px; font-weight:bold; color:#aaa;">${p.ticker}</td>
                <td style="padding:10px;">${dirIcon} ${p.direction}</td>
                <td onclick="pfEditStrategy(this, '${p.id}', '${safeStrat}')" title="Clicca per modificare" style="padding:10px; color:#666; font-size:0.9em; cursor:pointer; border-bottom:1px dashed #444;">${p.strategy || 'Manuale'} ✏️</td>
                <td onclick="pfUpdateField('${p.id}', 'notes', '${safeNotes}')" title="Clicca per modificare" style="padding:10px; color:#666; font-style:italic; font-size:0.9em; cursor:pointer; border-bottom:1px dashed #444;">${p.notes || '-'} ✏️</td>
                <td style="padding:10px; color:#666;">${p.entry_date}</td>
                <td style="padding:10px; color:#666;">${p.exit_date}</td>
                <td style="padding:10px; color:#888;">${p.entry_price}</td>
                <td style="padding:10px; color:#888;">${p.exit_price}</td>
                <td style="padding:10px; font-weight:bold; color:${color}; opacity:0.8;">${sign}${p.pnl_pct}%</td>
             `;
            closedList.appendChild(tr);
        });

    } catch (err) {
        console.error(err);
        openList.innerHTML = '<tr><td colspan="9" style="color:red;">Errore caricamento</td></tr>';
    }
}

async function pfOpenPosition() {
    const ticker = document.getElementById('pf-ticker-input').value.trim();
    const direction = document.getElementById('pf-direction-input').value;
    const strategy = document.getElementById('pf-strategy-input').value;
    const notes = document.getElementById('pf-notes-input').value.trim();
    const status = document.getElementById('pf-status');

    if (!ticker) {
        status.innerText = "Inserisci un ticker!";
        status.style.color = "red";
        return;
    }

    status.innerText = "Apertura in corso...";
    status.style.color = "orange";

    try {
        const res = await fetch(`${API_URL}/portfolio/open`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                direction: direction,
                strategy: strategy,
                notes: notes
            })
        });

        if (!res.ok) throw new Error('Errore API');

        status.innerText = "Posizione aperta!";
        status.style.color = "lime";

        // Refresh
        setTimeout(() => {
            status.innerText = "";
            pfLoadData();
            document.getElementById('pf-ticker-input').value = "";
            document.getElementById('pf-notes-input').value = "";
        }, 1000);

    } catch (err) {
        status.innerText = "Errore: " + err.message;
        status.style.color = "red";
    }
}

async function pfClosePosition(id) {
    if (!confirm("Chiudere questa posizione al prezzo di mercato attuale?")) return;

    try {
        const res = await fetch(`${API_URL}/portfolio/close/${id}`, { method: 'POST' });
        if (res.ok) {
            pfLoadData();
        } else {
            alert("Errore durante la chiusura");
        }
    } catch (err) {
        console.error(err);
        alert("Errore di connessione");
    }
}

async function pfQuickOpen(ticker, direction) {
    if (!confirm(`Aprire posizione ${direction} su ${ticker} al prezzo di mercato attuale?`)) return;

    try {
        const res = await fetch(`${API_URL}/portfolio/open`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                direction: direction,
                strategy: "Scanner Daily",
                notes: "⚡ Quick Trade"
            })
        });

        if (!res.ok) throw new Error('Errore API');

        const data = await res.json();
        alert(`✅ Posizione ${data.direction} aperta su ${data.ticker} a ${data.entry_price}$`);
    } catch (err) {
        alert("Errore: " + err.message);
    }
}

async function pfUpdateField(id, field, current) {
    const newVal = prompt(`Modifica ${field}:`, current);
    if (newVal === null || newVal === current) return;

    try {
        const payload = {};
        payload[field] = newVal;

        const res = await fetch(`${API_URL}/portfolio/update/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            pfLoadData();
        } else {
            alert("Errore update");
        }
    } catch (err) {
        alert("Errore update: " + err.message);
    }
}

function pfEditStrategy(td, id, current) {
    // Prevent double clicking
    td.onclick = null;

    const options = [
        "Manuale",
        "Scanner Daily",
        "Frozen Strategy",
        "Sum Strategy",
        "Kinetic Z"
    ];

    let html = `<select style="background:#1a1d2a; color:#fff; border:1px solid #555; padding:4px; border-radius:4px; width:100%;" 
                onchange="pfSaveStrategy('${id}', this.value)" onblur="setTimeout(pfLoadData, 200)">`;

    options.forEach(opt => {
        const sel = opt === current ? 'selected' : '';
        html += `<option value="${opt}" ${sel}>${opt}</option>`;
    });

    html += `</select>`;
    td.innerHTML = html;
    td.querySelector('select').focus();
}

async function pfSaveStrategy(id, val) {
    try {
        const res = await fetch(`${API_URL}/portfolio/update/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy: val })
        });
        if (res.ok) {
            pfLoadData(); // Will also refresh the view
        }
    } catch (e) {
        console.error(e);
    }
}
