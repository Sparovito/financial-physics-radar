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
    const endDate = document.getElementById('end-date').value || null; // null if empty

    if (!ticker) {
        alert("Inserisci un Ticker!");
        return;
    }

    // UI Loading State
    btn.disabled = true;
    status.style.display = 'flex';
    statusText.innerText = endDate
        ? `Analisi storica (fino a ${endDate}) per ${ticker}...`
        : `Scaricando dati per ${ticker}...`;

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
                end_date: endDate
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
function shiftDate(days) {
    const dateInput = document.getElementById('end-date');
    let currentDate = dateInput.value ? new Date(dateInput.value) : new Date();

    currentDate.setDate(currentDate.getDate() + days);

    // Format as YYYY-MM-DD
    const year = currentDate.getFullYear();
    const month = String(currentDate.getMonth() + 1).padStart(2, '0');
    const day = String(currentDate.getDate()).padStart(2, '0');
    dateInput.value = `${year}-${month}-${day}`;

    // Re-run analysis
    runAnalysis();
}

function renderCharts(data) {
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
        name: '❄️ Z-Kin (Frozen)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#00e5ff', width: 2 }, // Cyan
        xaxis: 'x',
        yaxis: 'y6' // DEDICATED PANEL
    };

    const traceFrozenPot = {
        x: data.frozen?.dates || [],
        y: data.frozen?.z_potential || [],
        name: '❄️ Z-Pot (Frozen)',
        type: 'scatter',
        fill: 'tozeroy',
        line: { color: '#ff6600', width: 2 }, // Orange
        xaxis: 'x',
        yaxis: 'y6'
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
    let backtestStats = null;

    if (showBacktest && data.backtest && data.backtest.trade_pnl_curve) {
        traceBacktest = {
            x: data.dates,
            y: data.backtest.trade_pnl_curve,
            name: `Trade P/L % (Avg: ${data.backtest.stats.avg_trade}%)`,
            type: 'scatter',
            fill: 'tozeroy',
            line: { color: '#00ff88', width: 2 },
            fillcolor: 'rgba(0, 255, 136, 0.3)',
            xaxis: 'x',
            yaxis: 'y5'
        };
        backtestStats = data.backtest.stats;
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

    // --- LAYOUT COMBINATO (Adjust domains based on backtest visibility) ---
    const layout = {
        // Grid rimosso per garantire il rispetto dei domini manuali

        // --- Asse X Condiviso ---
        xaxis: {
            anchor: showBacktest ? 'y5' : 'y3', // TODO: Anchor to lowest axis 
            domain: [0, 1],
            gridcolor: '#333'
        },

        // --- Configurazione Assi Y (Domini RE-LAYOUT) ---
        // WITH FROZEN PANEL:
        // Price (y1): Top
        // Energy (y2): Below Price
        // Frozen (y6): Below Energy
        // Indicators (y3): Below Frozen
        // Backtest (y5): Bottom (if enabled)

        yaxis: {
            domain: showBacktest ? [0.65, 1] : [0.60, 1],
            gridcolor: '#333',
            title: 'Prezzo (€)',
            tickfont: { color: '#e0e0e0' }
        },
        yaxis2: {
            domain: showBacktest ? [0.50, 0.62] : [0.45, 0.55],
            gridcolor: '#333333',
            title: 'Energy',
            tickfont: { color: '#9966ff' }
        },
        yaxis6: { // NEW FROZEN PANEL
            domain: showBacktest ? [0.35, 0.47] : [0.30, 0.40],
            gridcolor: '#333333',
            title: 'Frozen (No-Bias)',
            tickfont: { color: '#00e5ff' }
        },
        yaxis3: {
            domain: showBacktest ? [0.20, 0.32] : [0.15, 0.25],
            gridcolor: '#333333',
            title: 'Ind.',
            tickfont: { color: '#ff9966' }
        },
        yaxis4: {
            // Z-Score Axis (Right side of Indicators panel)
            overlaying: 'y3',
            side: 'right',
            gridcolor: 'rgba(0,0,0,0)',
            tickfont: { color: '#00ffff' },
            showgrid: false
        },

        title: { text: titleText, font: { color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#aaa', size: isMobile ? 10 : 12 },
        showlegend: true,
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
    if (showBacktest) {
        layout.yaxis5 = {
            domain: [0, 0.15],
            gridcolor: '#333333',
            title: 'Trade P/L %',
            tickfont: { color: '#00ff88' },
            zeroline: true,
            zerolinecolor: '#666',
            zerolinewidth: 2
        };
    }

    // FORCE HEIGHT ON MOBILE (Use viewport height)
    if (isMobile) {
        layout.height = window.innerHeight - 80;
    }

    const config = {
        responsive: true,
        displayModeBar: !isMobile
    };

    // Build traces array
    const traces = [
        tracePrice, tracePath, traceFund, traceForecast,
        traceKinetic, tracePotential,
        traceSlope, traceZ, traceZRoc,
        traceFrozenKin, traceFrozenPot  // Frozen (point-in-time) values
    ];

    if (traceBacktest) {
        traces.push(traceBacktest);
    }

    Plotly.newPlot('chart-combined', traces, layout, config);

    // Display backtest stats if available
    if (backtestStats) {
        const statsDiv = document.getElementById('backtest-stats');
        if (statsDiv) {
            statsDiv.innerHTML = `
                <strong>📊 Backtest Stats:</strong><br>
                Trades: ${backtestStats.total_trades} | 
                Win: ${backtestStats.win_rate}% | 
                Return: ${backtestStats.total_return}%
            `;
        }

        // Store trades globally and show button
        if (data.backtest && data.backtest.trades && data.backtest.trades.length > 0) {
            window.BACKTEST_TRADES = data.backtest.trades;
            document.getElementById('btn-view-trades').style.display = 'block';
        } else {
            window.BACKTEST_TRADES = [];
            document.getElementById('btn-view-trades').style.display = 'none';
        }
    } else {
        document.getElementById('btn-view-trades').style.display = 'none';
    }
}

// --- TRADES MODAL FUNCTIONS ---
function openTradesModal() {
    const modal = document.getElementById('trades-modal');
    const listDiv = document.getElementById('trades-list');

    if (!window.BACKTEST_TRADES || window.BACKTEST_TRADES.length === 0) {
        listDiv.innerHTML = '<p style="color: #888;">Nessuna operazione disponibile.</p>';
    } else {
        let html = '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">';
        html += `<tr style="color: #888; border-bottom: 1px solid #333;">
            <th style="text-align: left; padding: 8px;">Data</th>
            <th style="text-align: center; padding: 8px;">Tipo</th>
            <th style="text-align: right; padding: 8px;">Entry</th>
            <th style="text-align: right; padding: 8px;">Exit</th>
            <th style="text-align: right; padding: 8px;">P/L %</th>
        </tr>`;

        window.BACKTEST_TRADES.forEach(t => {
            const pnlColor = t.pnl_pct >= 0 ? '#00ff88' : '#ff4444';
            const pnlSign = t.pnl_pct >= 0 ? '+' : '';
            const typeEmoji = t.direction === 'LONG' ? '🟢' : '🔴';

            html += `<tr style="border-bottom: 1px solid #222;">
                <td style="padding: 8px; color: #aaa;">${t.entry_date}<br><small>→ ${t.exit_date}</small></td>
                <td style="padding: 8px; text-align: center;">${typeEmoji} ${t.direction}</td>
                <td style="padding: 8px; text-align: right; color: #ccc;">${t.entry_price}</td>
                <td style="padding: 8px; text-align: right; color: #ccc;">${t.exit_price}</td>
                <td style="padding: 8px; text-align: right; color: ${pnlColor}; font-weight: bold;">${pnlSign}${t.pnl_pct}%</td>
            </tr>`;
        });

        html += '</table>';
        listDiv.innerHTML = html;
    }

    modal.style.display = 'flex';
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

    // Attiva Listener
    slider.oninput = updateRadarFrame;
    trailsCheck.onchange = updateRadarFrame;

    // CRITICAL: Clear loading message
    chartDiv.innerHTML = "";

    // Reset focus when loading new data
    FOCUSED_TICKER = null;
    updateAnalyzeButton();

    // Render Iniziale
    updateRadarFrame();
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
let currentCategory = "Highlights"; // Default

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
