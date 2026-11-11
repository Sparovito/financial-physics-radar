const API_URL = ""; // Relative path for production (same origin)

// --- GLOBAL CONFIGURATION ---
window.SHOW_LEGEND = false; // Default OFF
window.SHOW_FOURIER = false; // Default OFF

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
    const fourierDays = parseInt(document.getElementById('fourier-days').value) || 504;
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
                fourier_days: fourierDays,
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

    // --- TRACCE GRAFICO PRINCIPALE (Prezzo) ---
    // [MODIFIED] Multi-Scenario Fourier
    // [MODIFIED] Multi-Scenario Fourier

    const traceForecasts = [];
    const scenarioColors = ['#ab63fa', '#19d3f3', '#00cc96', '#ffa15a', '#ff6692']; // Purple, Cyan, Teal, Orange, Pink

    // [MODIFIED] Check Global Fourier Toggle
    const showFourier = (typeof window.SHOW_FOURIER === 'undefined') ? true : window.SHOW_FOURIER;

    if (showFourier && data.forecast.scenarios && Array.isArray(data.forecast.scenarios)) {
        data.forecast.scenarios.forEach((scenario, i) => {
            const color = scenarioColors[i % scenarioColors.length];
            traceForecasts.push({
                x: data.forecast.dates,
                y: scenario,
                name: `Scenario ${i + 1}`,
                type: 'scatter',
                line: { color: color, width: 2, dash: 'dot' },
                opacity: 0.8,
                xaxis: 'x',
                yaxis: 'y',
                showlegend: true
            });
        });
    } else if (data.forecast.values) {
        // Fallback for legacy format
        traceForecasts.push({
            x: data.forecast.dates,
            y: data.forecast.values,
            name: 'Proiezione Fourier',
            type: 'scatter',
            line: { color: '#ab63fa', width: 2, dash: 'dot' },
            xaxis: 'x',
            yaxis: 'y'
        });
    }

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
        name: 'Kinetic Z (live)',
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        line: { color: '#bf00ff', width: 2 }, // Neon Purple
        xaxis: 'x',
        yaxis: 'y9'
    };

    // --- STABLE KINETIC Z (causal, never changes) - separate panel ---
    const skinz_data = data.indicators?.stable_kinetic_z || [];
    const skinz_regime = data.indicators?.stable_kinetic_z_regime || [];
    console.warn('stable_kinetic_z:', skinz_data.length, 'pts | regime:', skinz_regime.length, 'pts');

    // Build regime-colored traces: green when bullish (+1), red when bearish (-1)
    const skinz_bullish_y = skinz_data.map((v, i) => skinz_regime[i] > 0 ? v : null);
    const skinz_bearish_y = skinz_data.map((v, i) => skinz_regime[i] < 0 ? v : null);
    const skinz_neutral_y = skinz_data.map((v, i) => skinz_regime[i] === 0 ? v : null);

    const traceStableKinZ_bull = {
        x: data.dates,
        y: skinz_bullish_y,
        name: 'S.KinZ (Bull)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#00ff88', width: 2.5 },
        fill: 'tozeroy',
        fillcolor: 'rgba(0, 255, 136, 0.18)',
        connectgaps: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    const traceStableKinZ_bear = {
        x: data.dates,
        y: skinz_bearish_y,
        name: 'S.KinZ (Bear)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#ff4444', width: 2.5 },
        fill: 'tozeroy',
        fillcolor: 'rgba(255, 68, 68, 0.18)',
        connectgaps: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    const traceStableKinZ_neutral = {
        x: data.dates,
        y: skinz_neutral_y,
        name: 'S.KinZ (Wait)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#888888', width: 1.5 },
        connectgaps: false,
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    // Threshold lines at ±0.5 (hysteresis band)
    const skinz_first = data.dates?.[0] || '';
    const skinz_last = data.dates?.[data.dates.length - 1] || '';
    const traceStableKinZ_threshUp = {
        x: [skinz_first, skinz_last],
        y: [0.5, 0.5],
        name: '+0.5',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#555555', width: 1, dash: 'dash' },
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    const traceStableKinZ_threshDn = {
        x: [skinz_first, skinz_last],
        y: [-0.5, -0.5],
        name: '-0.5',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#555555', width: 1, dash: 'dash' },
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    // Zero reference line
    const traceStableKinZ_zero = {
        x: [skinz_first, skinz_last],
        y: [0, 0],
        name: 'Zero',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#666666', width: 1, dash: 'dot' },
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y12'
    };
    // Kinetic Z live overlay (reference) — prominent purple
    const traceKineticZ_overlay = {
        x: data.dates,
        y: data.energy.z_kinetic || [],
        name: 'Kinetic Z (live)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#cc55ff', width: 2, dash: 'dash' },
        opacity: 0.75,
        xaxis: 'x',
        yaxis: 'y12'
    };

    // --- PANNELLO DIREZIONE (sostituisce Kinetic Z) ---
    // Blu = cinetica dell'oracolo con il segno della sua velocità (ridisegnata col futuro).
    // Arancione = stima di oggi del blu, causale e NON spostata nel tempo.
    // Sopra lo zero = salita, sotto = discesa.
    const dirTraces = getDirectionTraces(data);

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

    // --- STABLE SLOPE: causal indicator that estimates what SLOPE will become ---
    // dF_smooth = EMA(14) of diff(EMA(prices,20)). Purely causal, covers ALL dates.
    // Correlation ~0.87 with stabilized SLOPE. Value at T=0 predicts SLOPE[T+25].
    // This NEVER changes for past dates — no boundary effects at all.
    const ssData = data.indicators?.stable_slope || [];
    const slData = data.indicators?.slope || [];
    console.warn('📐 v12 STABLE SLOPE:', ssData.length, 'pts, last=', ssData.slice(-3),
                 '| SLOPE live:', slData.length, 'pts, last=', slData.slice(-3));
    const traceStableSlope = {
        x: data.dates,
        y: data.indicators?.stable_slope || [],
        name: 'Stable Slope (dF)',
        type: 'scatter',
        line: { color: '#00ff88', width: 2.5 },
        xaxis: 'x',
        yaxis: 'y10'
    };

    // Overlay: live SLOPE on SAME axis for visual comparison
    const traceSlope_overlay = {
        x: data.dates,
        y: data.indicators?.slope || [],
        name: 'SLOPE (live)',
        type: 'scatter',
        line: { color: '#eba834', width: 1.5, dash: 'dot' },
        opacity: 0.5,
        xaxis: 'x',
        yaxis: 'y10'
    };

    // --- BACKTEST TRACE (Equity Curve) ---
    const showBacktest = document.getElementById('show-backtest')?.checked ?? false;
    let traceBacktest = null;
    let traceFrozenStrat = null;
    let traceV2Strat = null;
    let traceV2RiseStrat = null;
    let backtestStats = null;
    let frozenStats = null;
    let v2Stats = null;
    let v2RiseStats = null;
    let traceDirStrat = null;
    let dirStats = null;

    if (showBacktest) {
        // 1. Live Strategy (Green)
        if (data.backtest && data.backtest.trade_pnl_curve) {
            traceBacktest = {
                x: data.dates,
                y: data.backtest.trade_pnl_curve,
                name: `LIVE = ORACOLO, usa il futuro (Avg: ${data.backtest.stats.avg_trade}%)`,
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

        // 3. Frozen V2 (oro): energia alta + prezzo sotto il percorso
        if (data.frozen_v2_strategy && data.frozen_v2_strategy.trade_pnl_curve) {
            traceV2Strat = {
                x: data.dates,
                y: data.frozen_v2_strategy.trade_pnl_curve,
                name: `🧭 V2 (Avg: ${data.frozen_v2_strategy.stats.avg_trade_pct}%)`,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#ffd166', width: 2 },
                xaxis: 'x',
                yaxis: 'y5'
            };
            v2Stats = data.frozen_v2_strategy.stats;
        }

        // 4. V2 Risalita (rosa): entra con la V2, tiene la risalita, esce al massimo dell'arancione
        if (data.frozen_v2_rise_strategy && data.frozen_v2_rise_strategy.trade_pnl_curve) {
            traceV2RiseStrat = {
                x: data.dates,
                y: data.frozen_v2_rise_strategy.trade_pnl_curve,
                name: `🧭 V2 Risalita (Avg: ${data.frozen_v2_rise_strategy.stats.avg_trade_pct}%)`,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#ff7ab8', width: 2.5 },
                xaxis: 'x',
                yaxis: 'y5'
            };
            v2RiseStats = data.frozen_v2_rise_strategy.stats;
        }
        // 5. Direzione (azzurro): dentro finché l'arancione col segno è sopra lo zero, in tempo reale
        if (data.frozen_dir_strategy && data.frozen_dir_strategy.trade_pnl_curve) {
            traceDirStrat = {
                x: data.dates,
                y: data.frozen_dir_strategy.trade_pnl_curve,
                name: `🧭 Direzione (Avg: ${data.frozen_dir_strategy.stats.avg_trade_pct}%)`,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#4da6ff', width: 2, dash: 'dot' },
                xaxis: 'x',
                yaxis: 'y5'
            };
            dirStats = data.frozen_dir_strategy.stats;
        }
        // SUM e STABLE non si disegnano più qui (richiesta utente 11/2026): restano
        // nello Scanner Strategie, nel selettore dei trade e in "Vedi Operazioni".
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
    const showStableSlope = document.getElementById('show-stable-slope')?.checked ?? false;
    const showStableKinZ = document.getElementById('show-stable-kinz')?.checked ?? false;
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
    if (showStableSlope) visiblePanels.push('stableslope');
    if (showStableKinZ) visiblePanels.push('stablekinz');
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
            title: showKineticZ ? (dirTraces ? 'Direzione' : 'Kinetic Z') : '',
            tickfont: { color: dirTraces ? '#00bfff' : '#bf00ff' },
            zeroline: true,
            zerolinecolor: '#888888',
            visible: showKineticZ
        },
        yaxis10: { // FROZEN SLOPE PANEL
            domain: domains.stableslope || defaultDomain,
            gridcolor: '#333333',
            title: showStableSlope ? 'F.Slope' : '',
            tickfont: { color: '#00ff88' },
            visible: showStableSlope
        },
        yaxis11: { // unused, kept for axis numbering compatibility
            visible: false
        },
        yaxis12: { // STABLE KINETIC Z PANEL
            domain: domains.stablekinz || defaultDomain,
            gridcolor: '#333333',
            title: showStableKinZ ? 'S.KinZ' : '',
            tickfont: { color: '#00ff88' },
            visible: showStableKinZ
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
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#aaa', size: isMobile ? 10 : 12 },
        showlegend: (typeof window.SHOW_LEGEND === 'undefined' ? true : window.SHOW_LEGEND) && !isMobile,
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
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: 'rgba(20, 20, 30, 0.8)',
            bordercolor: '#444',
            font: { color: '#fff' }
        }
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
        traces.push(tracePrice, tracePath, traceFund, ...traceForecasts);
    }

    // Energy group
    if (showEnergy) {
        traces.push(traceKinetic, tracePotential);
    }

    // Frozen group
    if (showFrozen) {
        traces.push(traceFrozenKin, traceFrozenPot);
    }

    // Zone V2: ▼ sul massimo dell'arancione e voci di legenda (le fasce sono shapes)
    traces.push(...getV2ZoneTraces(data, showFrozen, showPrice));

    // Indicators group
    if (showIndicators) {
        traces.push(traceSlope, traceZ, traceZRoc);
    }

    // Backtest / Strategy traces
    if (traceBacktest) traces.push(traceBacktest);
    if (traceFrozenStrat) traces.push(traceFrozenStrat);
    if (traceV2Strat) traces.push(traceV2Strat);
    if (traceV2RiseStrat) traces.push(traceV2RiseStrat);
    if (traceDirStrat) traces.push(traceDirStrat);

    // Pannello Direzione (al posto di Kinetic Z; le vecchie curve solo se mancano i dati nuovi)
    if (showKineticZ) {
        if (dirTraces) traces.push(...dirTraces);
        else traces.push(traceKineticZ, traceFrozenSum);
    }

    // Stable Kinetic Z (separate panel)
    if (showStableKinZ) {
        console.warn('⚡ S.KinZ:', skinz_data.length, 'pts | regime:', skinz_regime.length, 'pts');
        traces.push(
            traceStableKinZ_zero,
            traceStableKinZ_threshUp,
            traceStableKinZ_threshDn,
            traceStableKinZ_bull,
            traceStableKinZ_bear,
            traceStableKinZ_neutral,
            traceKineticZ_overlay
        );
    }

    // Stable Slope + SLOPE live overlay
    if (showStableSlope) {
        console.warn('📐 PUSHING traces:', traceStableSlope.name, traceStableSlope.y.length, 'pts |',
                     traceSlope_overlay.name, traceSlope_overlay.y.length, 'pts');
        traces.push(traceStableSlope, traceSlope_overlay);
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

    // [NEW] Portfolio Markers Trace (Dots)
    // [NEW] Portfolio Markers Trace (Dots)
    const tracePortfolio = getPortfolioTrace();
    // [NEW] User Dots Trace
    const userDotAnnotations = getUserDotAnnotations();

    if (tracePortfolio) {
        traces.push(tracePortfolio);
    }

    // Add saved annotation shapes to layout
    loadAnnotations();
    layout.shapes = getAnnotationShapes();

    // Merge portfolio text annotations with user dots
    const portfolioAnnos = getPortfolioAnnotations();
    layout.annotations = [...portfolioAnnos, ...userDotAnnotations];

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
                    <strong title="Calcolata con lo smoother bidirezionale: conosce il futuro. È il soffitto teorico, non una strategia eseguibile.">🟢 LIVE (oracolo, non eseguibile):</strong>
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

        if (v2Stats) {
            html += `
                <div style="color: #ffd166; margin-top: 4px; border-top: 1px dashed #333; padding-top: 4px;">
                    <strong title="Dentro quando l'energia è sopra la media e il prezzo è sotto il percorso. Candidata, non validata in avanti.">🧭 V2:</strong>
                    Trades: ${v2Stats.total_trades} |
                    Win: ${v2Stats.win_rate}% |
                    Return: ${v2Stats.total_return}%
                </div>`;
        }

        if (v2RiseStats) {
            html += `
                <div style="color: #ff7ab8;">
                    <strong title="Entra come la V2, tiene la risalita ed esce al massimo dell'arancione sopra il percorso (o se il prezzo torna sotto). Senza stop. Candidata, non validata in avanti.">🧭 V2 Risalita:</strong>
                    Trades: ${v2RiseStats.total_trades} |
                    Win: ${v2RiseStats.win_rate}% |
                    Return: ${v2RiseStats.total_return}%
                </div>`;
        }

        if (dirStats) {
            html += `
                <div style="color: #4da6ff;">
                    <strong title="Compra quando la stima di oggi del blu (arancione del pannello Direzione) diventa positiva e vende quando diventa negativa. Riconosce una svolta in circa 5 barre ma gira spesso a vuoto: in media rende meno del compra-e-tieni. Serve a vedere dove arrivano i segnali.">🧭 Direzione:</strong>
                    Trades: ${dirStats.total_trades} |
                    Win: ${dirStats.win_rate}% |
                    Return: ${dirStats.total_return}%
                </div>`;
        }

        statsDiv.innerHTML = html || 'No Stats Available';
    }

    // Store trades globally and show button
    window.TRADES_LIVE = (data.backtest && data.backtest.trades) ? data.backtest.trades : [];
    window.TRADES_FROZEN = (data.frozen_strategy && data.frozen_strategy.trades) ? data.frozen_strategy.trades : [];
    window.TRADES_SUM = (data.frozen_sum_strategy && data.frozen_sum_strategy.trades) ? data.frozen_sum_strategy.trades : [];
    window.TRADES_STABLE = (data.stable_strategy && data.stable_strategy.trades) ? data.stable_strategy.trades : [];
    window.TRADES_V2 = (data.frozen_v2_strategy && data.frozen_v2_strategy.trades) ? data.frozen_v2_strategy.trades : [];
    window.TRADES_V2R = (data.frozen_v2_rise_strategy && data.frozen_v2_rise_strategy.trades) ? data.frozen_v2_rise_strategy.trades : [];
    window.TRADES_DIR = (data.frozen_dir_strategy && data.frozen_dir_strategy.trades) ? data.frozen_dir_strategy.trades : [];

    if (window.TRADES_LIVE.length > 0 || window.TRADES_FROZEN.length > 0 || window.TRADES_SUM.length > 0 || window.TRADES_STABLE.length > 0) {
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
    const btnSum = document.getElementById('btn-trades-sum');
    const btnStable = document.getElementById('btn-trades-stable');

    const buttons = [
        { btn: btnLive, mode: 'LIVE', color: '#00ff88', textColor: '#000' },
        { btn: btnFrozen, mode: 'FROZEN', color: '#ff9900', textColor: '#000' },
        { btn: btnSum, mode: 'SUM', color: '#ff4444', textColor: '#fff' },
        { btn: btnStable, mode: 'STABLE', color: '#aa44ff', textColor: '#fff' },
        { btn: document.getElementById('btn-trades-v2'), mode: 'FROZEN_V2', color: '#ffd166', textColor: '#000' },
        { btn: document.getElementById('btn-trades-v2r'), mode: 'FROZEN_V2R', color: '#ff7ab8', textColor: '#000' },
        { btn: document.getElementById('btn-trades-dir'), mode: 'FROZEN_DIR', color: '#4da6ff', textColor: '#000' }
    ];

    buttons.forEach(item => {
        if (item.btn) {
            // Reset
            item.btn.style.background = 'transparent';
            item.btn.style.color = '#888';
            item.btn.style.border = 'none';

            // Activate if matches
            if (item.mode === mode) {
                item.btn.style.background = item.color;
                item.btn.style.color = item.textColor;
            }
        }
    });

    renderTradesList();
}



function openTradesModal() {
    // Force Default to Live on open unless we want persistence
    if (!window.CURRENT_TRADES_VIEW) window.CURRENT_TRADES_VIEW = 'LIVE';

    switchTradesView(window.CURRENT_TRADES_VIEW);
    document.getElementById('trades-modal').style.display = 'flex';
}

// Global storage for ORIGINAL trades (baseline - saved once, never overwritten)
window.ORIGINAL_TRADES = window.ORIGINAL_TRADES || { LIVE: null, FROZEN: null, SUM: null, STABLE: null, FROZEN_V2: null, FROZEN_V2R: null, FROZEN_DIR: null };

function renderTradesList() {
    const listDiv = document.getElementById('trades-list');
    const viewMode = window.CURRENT_TRADES_VIEW;
    let trades;
    if (viewMode === 'LIVE') {
        trades = window.TRADES_LIVE;
    } else if (viewMode === 'FROZEN') {
        trades = window.TRADES_FROZEN;
    } else if (viewMode === 'SUM') {
        trades = window.TRADES_SUM;
    } else if (viewMode === 'STABLE') {
        trades = window.TRADES_STABLE;
    } else if (viewMode === 'FROZEN_V2') {
        trades = window.TRADES_V2;
    } else if (viewMode === 'FROZEN_V2R') {
        trades = window.TRADES_V2R;
    } else if (viewMode === 'FROZEN_DIR') {
        trades = window.TRADES_DIR;
    } else {
        trades = [];
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

    let html = '';

    // --- STABLE: Summary header con stats LONG/SHORT separati ---
    if (viewMode === 'STABLE') {
        const longTrades = trades.filter(t => t.direction === 'LONG');
        const shortTrades = trades.filter(t => t.direction === 'SHORT');
        const longClosed = longTrades.filter(t => t.exit_date !== 'OPEN');
        const shortClosed = shortTrades.filter(t => t.exit_date !== 'OPEN');
        const longOpen = longTrades.filter(t => t.exit_date === 'OPEN');
        const shortOpen = shortTrades.filter(t => t.exit_date === 'OPEN');

        const longWins = longClosed.filter(t => t.pnl_pct > 0).length;
        const shortWins = shortClosed.filter(t => t.pnl_pct > 0).length;
        const longPnl = longClosed.reduce((s, t) => s + t.pnl_pct, 0);
        const shortPnl = shortClosed.reduce((s, t) => s + t.pnl_pct, 0);
        const longWR = longClosed.length > 0 ? Math.round(longWins / longClosed.length * 100) : 0;
        const shortWR = shortClosed.length > 0 ? Math.round(shortWins / shortClosed.length * 100) : 0;

        html += `<div style="display:flex; gap:10px; margin-bottom:15px;">`;
        // LONG box
        html += `<div style="flex:1; background:rgba(0,255,136,0.08); border:1px solid rgba(0,255,136,0.3); border-radius:8px; padding:12px;">
            <div style="color:#00ff88; font-weight:bold; font-size:0.95rem; margin-bottom:8px;">🟢 LONG</div>
            <div style="color:#aaa; font-size:0.82rem;">
                Trades: <span style="color:#fff;">${longClosed.length}</span>${longOpen.length > 0 ? ` <span style="color:#ff9900;">(+${longOpen.length} open)</span>` : ''}<br>
                Win Rate: <span style="color:#fff;">${longWR}%</span><br>
                P/L Tot: <span style="color:${longPnl >= 0 ? '#00ff88' : '#ff4444'}; font-weight:bold;">${longPnl >= 0 ? '+' : ''}${longPnl.toFixed(1)}%</span>
            </div>
        </div>`;
        // SHORT box
        html += `<div style="flex:1; background:rgba(255,68,68,0.08); border:1px solid rgba(255,68,68,0.3); border-radius:8px; padding:12px;">
            <div style="color:#ff4444; font-weight:bold; font-size:0.95rem; margin-bottom:8px;">🔴 SHORT</div>
            <div style="color:#aaa; font-size:0.82rem;">
                Trades: <span style="color:#fff;">${shortClosed.length}</span>${shortOpen.length > 0 ? ` <span style="color:#ff9900;">(+${shortOpen.length} open)</span>` : ''}<br>
                Win Rate: <span style="color:#fff;">${shortWR}%</span><br>
                P/L Tot: <span style="color:${shortPnl >= 0 ? '#00ff88' : '#ff4444'}; font-weight:bold;">${shortPnl >= 0 ? '+' : ''}${shortPnl.toFixed(1)}%</span>
            </div>
        </div>`;
        // COMBINED box
        const totalPnl = longPnl + shortPnl;
        const totalTrades = longClosed.length + shortClosed.length;
        const totalWins = longWins + shortWins;
        const totalWR = totalTrades > 0 ? Math.round(totalWins / totalTrades * 100) : 0;
        html += `<div style="flex:1; background:rgba(170,68,255,0.08); border:1px solid rgba(170,68,255,0.3); border-radius:8px; padding:12px;">
            <div style="color:#aa44ff; font-weight:bold; font-size:0.95rem; margin-bottom:8px;">🟣 COMBINED</div>
            <div style="color:#aaa; font-size:0.82rem;">
                Trades: <span style="color:#fff;">${totalTrades}</span><br>
                Win Rate: <span style="color:#fff;">${totalWR}%</span><br>
                P/L Tot: <span style="color:${totalPnl >= 0 ? '#00ff88' : '#ff4444'}; font-weight:bold;">${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(1)}%</span>
            </div>
        </div>`;
        html += `</div>`;
    }

    html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">';
    html += `<tr style="color: #888; border-bottom: 1px solid #333;">
        <th style="text-align: left; padding: 8px;">Data</th>
        <th style="text-align: center; padding: 8px;">Tipo</th>
        <th style="text-align: right; padding: 8px;">Entry</th>
        <th style="text-align: right; padding: 8px;">Exit</th>
        <th style="text-align: right; padding: 8px;">P/L %</th>
    </tr>`;

    // Trades are oldest to newest. Reverse for newest first.
    const tradesReversed = [...trades].reverse();

    tradesReversed.forEach((t, idx) => {
        const isOpen = t.exit_date === 'OPEN';

        // Custom styling for OPEN trades + STABLE LONG/SHORT border
        const stableBorder = (viewMode === 'STABLE')
            ? `border-left: 3px solid ${t.direction === 'LONG' ? '#00ff88' : '#ff4444'};`
            : '';
        const rowStyle = isOpen
            ? `border-bottom: 1px solid #444; background: rgba(255, 153, 0, 0.15); box-shadow: 0 0 5px rgba(255,153,0,0.2) inset; ${stableBorder}`
            : `border-bottom: 1px solid #222; ${stableBorder}`;

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
    if (strategy === 'FROZEN_V2' || strategy === 'FROZEN_V2R' || strategy === 'FROZEN_DIR') {
        // V2 e V2 Risalita usano solo serie causali (filtro di Kalman in avanti): il passato
        // non viene mai ridisegnato, quindi non c'è niente da verificare (lo garantiscono i test).
        alert('La verifica serve alle strategie che possono essere ridisegnate. V2, V2 Risalita e Direzione usano solo dati passati: le operazioni non cambiano quando arrivano nuovi prezzi.');
        return;
    }
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

// ============================================================
//  SCANNER STRATEGIE (Massivo)
//  Dati da POST /scan-strategies (calcolo dedicato, a batch).
//  Stato in memoria (SCAN_ROWS) e UNA funzione di resa: filtri,
//  ordinamento, riga delle medie e spunte restano coerenti.
// ============================================================
const SCAN_STRATS = ['live', 'frozen', 'frozen2', 'frozen2r', 'sum', 'stable', 'orange', 'combo'];
const SCAN_LABELS = { live: 'Oracolo', frozen: 'Frozen', frozen2: 'Frozen V2', frozen2r: 'V2 Risalita', sum: 'SUM', stable: 'Stable', orange: 'Arancione', combo: 'Combo' };
const SCAN_COLORS = { live: '#6a8f7a', frozen: '#ff9900', frozen2: '#ffd166', frozen2r: '#ff7ab8', sum: '#ff6666', stable: '#aa44ff', orange: '#ffb347', combo: '#00e5ff' };
const SCAN_BATCH_SIZE = 20;
let SCAN_ROWS = [];                 // [{ticker, bh, trend, strategies:{...}}]
let SCAN_ERRORS = {};               // {ticker: motivo}
let SCAN_WEEKLY = {};               // {strategia: {lunedì: [somma eccesso tra i titoli, n titoli]}}
let SCAN_UNCHECKED = new Set();     // titoli esclusi dal simulatore
let SCAN_SORT = { key: 'ticker', dir: 1 };

function scanEsc(v) {
    return String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function scanMetric() {
    return document.getElementById('scan-metric')?.value || 'roi';
}

function scanFmt(v, metric) {
    if (v == null || !Number.isFinite(v)) return '—';
    if (metric === 'trades') return String(v);
    const sign = (metric === 'roi' || metric === 'alpha' || metric === 'timing') && v > 0 ? '+' : '';
    return sign + v.toFixed(1) + '%';
}

// Colore della cella: in ROI il confronto è col compra-e-tieni dello stesso titolo
function scanColor(v, metric, bh) {
    if (v == null) return '#666';
    if (metric === 'roi') return v < 0 ? '#ff4444' : (v > bh ? '#00ff88' : '#ddd');
    if (metric === 'alpha' || metric === 'timing') return v > 0 ? '#00ff88' : (v < 0 ? '#ff4444' : '#ddd');
    return '#ccc';
}

function scanCellTitle(st, bh) {
    return `ROI ${scanFmt(st.roi, 'roi')} · B&H ${scanFmt(bh, 'roi')} · timing ${scanFmt(st.timing, 'timing')} · alpha vecchio ${scanFmt(st.alpha, 'alpha')}` +
        ` · win rate ${st.win_rate}% su ${st.trades} trade chiusi · esposizione ${st.expo}%`;
}

async function startBulkScan() {
    const cat = document.getElementById('scanner-category').value;
    const progressBar = document.getElementById('scan-progress');
    const statusLabel = document.getElementById('scan-status');
    const btnStart = document.getElementById('btn-start-scan');
    const btnStop = document.getElementById('btn-stop-scan');

    // Elenco titoli
    let tickersToScan = [];
    if (cat === 'ALL') {
        Object.values(TICKERS_DATA).forEach(list => {
            tickersToScan = tickersToScan.concat(list.map(t => t.symbol));
        });
    } else {
        tickersToScan = (TICKERS_DATA[cat] || []).map(t => t.symbol);
    }
    tickersToScan = [...new Set(tickersToScan)];
    if (tickersToScan.length === 0) {
        statusLabel.innerHTML = '⚠️ Nessun titolo in questa categoria.';
        return;
    }

    // Reset stato e interfaccia
    SCAN_ROWS = [];
    SCAN_ERRORS = {};
    SCAN_WEEKLY = {};
    SCAN_UNCHECKED = new Set();
    SCAN_STOP_SIGNAL = false;
    window.SCAN_TRADES = { LIVE: [], FROZEN: [], FROZEN_V2: [], FROZEN_V2R: [], SUM: [], STABLE: [], ARANCIONE: [], COMBO: [] };
    window.ALL_SCAN_TRADES_LIVE = window.SCAN_TRADES.LIVE;
    window.ALL_SCAN_TRADES_FROZEN = window.SCAN_TRADES.FROZEN;
    window.ALL_SCAN_TRADES = window.SCAN_TRADES.COMBO;
    renderScanTable();
    progressBar.style.display = 'block';
    progressBar.max = tickersToScan.length;
    progressBar.value = 0;
    btnStart.style.display = 'none';
    btnStop.style.display = 'inline-block';

    const alpha = parseFloat(document.getElementById('alpha').value) || 200;
    const beta = parseFloat(document.getElementById('beta').value) || 1.0;
    const startDate = document.getElementById('scanner-start').value || '2023-01-01';
    const endDate = document.getElementById('scanner-end').value || null;
    // il selettore "x1/x4/x6" diventa il numero di richieste a batch in parallelo (max 3:
    // ogni batch scarica già più titoli insieme lato server)
    const concurrency = Math.max(1, Math.min(3, parseInt(document.getElementById('scan-parallel').value) || 2));
    const tradeKey = { live: 'LIVE', frozen: 'FROZEN', frozen2: 'FROZEN_V2', frozen2r: 'FROZEN_V2R', sum: 'SUM', stable: 'STABLE', orange: 'ARANCIONE', combo: 'COMBO' };

    const batches = [];
    for (let i = 0; i < tickersToScan.length; i += SCAN_BATCH_SIZE) {
        batches.push(tickersToScan.slice(i, i + SCAN_BATCH_SIZE));
    }
    let done = 0;
    const t0 = Date.now();

    async function runBatch(batch) {
        try {
            const response = await fetch(`${API_URL}/scan-strategies`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tickers: batch, start_date: startDate, end_date: endDate, alpha, beta })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            for (const [ticker, r] of Object.entries(data.results || {})) {
                SCAN_ROWS.push({ ticker, bh: r.bh, trend: r.trend, strategies: r.strategies });
                for (const name of SCAN_STRATS) {
                    (r.trades?.[name] || []).forEach(t => window.SCAN_TRADES[tradeKey[name]].push({ ...t, ticker }));
                }
            }
            scanMergeWeekly(data.weekly);
            Object.assign(SCAN_ERRORS, data.errors || {});
        } catch (e) {
            console.error('Scanner batch fallito:', batch, e);
            batch.forEach(t => { SCAN_ERRORS[t] = 'richiesta fallita: ' + e.message; });
        }
        done += batch.length;
        progressBar.value = done;
        const nErr = Object.keys(SCAN_ERRORS).length;
        statusLabel.innerHTML = `⚡ ${done}/${tickersToScan.length} titoli` + (nErr ? ` · ${nErr} non analizzati` : '');
        renderScanTable();
    }

    const queue = [...batches];
    async function worker() {
        while (queue.length > 0 && !SCAN_STOP_SIGNAL) {
            await runBatch(queue.shift());
        }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, batches.length) }, worker));

    const nErr = Object.keys(SCAN_ERRORS).length;
    const secs = ((Date.now() - t0) / 1000).toFixed(0);
    const errNames = Object.keys(SCAN_ERRORS).slice(0, 40).join(', ');
    statusLabel.innerHTML = (SCAN_STOP_SIGNAL ? '🛑 Interrotto: ' : '✅ Completato: ') +
        `${SCAN_ROWS.length} analizzati in ${secs}s` +
        (nErr ? ` · <span title="${scanEsc(errNames)}" style="color:#ff9900; cursor:help;">${nErr} non analizzati</span>` : '');

    btnStop.style.display = 'none';
    btnStart.style.display = 'inline-block';
    renderScanTable();
}

function scanVisibleRows() {
    const trendFilter = document.getElementById('filter-trend')?.value || 'all';
    const metric = scanMetric();
    const rows = SCAN_ROWS.filter(r => trendFilter === 'all' || r.trend === trendFilter);
    const { key, dir } = SCAN_SORT;
    const val = (r) => {
        if (key === 'ticker') return r.ticker;
        if (key === 'bh') return r.bh;
        return r.strategies[key]?.[metric] ?? -Infinity;
    };
    rows.sort((x, y) => {
        const a = val(x), b = val(y);
        if (typeof a === 'string') return a.localeCompare(b) * dir;
        return (a - b) * dir;
    });
    return rows;
}

function renderScanTable() {
    const tbody = document.getElementById('scanner-results');
    if (!tbody) return;
    const metric = scanMetric();
    const rows = scanVisibleRows();
    const trendIcon = { up: ['▲', '#00ff88'], down: ['▼', '#ff4444'], stable: ['●', '#888'] };

    let html = rows.map(r => {
        const [icon, color] = trendIcon[r.trend] || trendIcon.stable;
        const t = scanEsc(r.ticker);
        const cells = SCAN_STRATS.map(name => {
            const st = r.strategies[name];
            if (!st) return '<td style="padding:10px; text-align:right; color:#666;">—</td>';
            const v = st[metric];
            const dim = name === 'live' ? ' opacity:0.55; font-style:italic;' : '';
            return `<td style="padding:10px; text-align:right; color:${scanColor(v, metric, r.bh)};${dim}" title="${scanEsc(scanCellTitle(st, r.bh))}">${scanFmt(v, metric)}</td>`;
        }).join('');
        return `<tr class="scan-row" data-trend="${r.trend}" style="border-bottom:1px solid #333;">
            <td style="padding:10px; text-align:center;">
                <input type="checkbox" class="scan-ticker-checkbox" data-ticker="${t}" ${SCAN_UNCHECKED.has(r.ticker) ? '' : 'checked'}
                    onchange="scanToggleTicker(this)">
            </td>
            <td style="padding:10px; font-weight:bold;">${t}</td>
            <td style="padding:10px; color:${color}; font-size:1.1em;">${icon}</td>
            <td style="padding:10px; text-align:right; color:${r.bh >= 0 ? '#fff' : '#ff4444'}; font-weight:bold;">${scanFmt(r.bh, 'roi')}</td>
            ${cells}
            <td style="padding:10px;">
                <button onclick="loadTickerFromScan('${t}')" style="background:#333; color:#fff; border:none; padding:4px 8px; cursor:pointer; font-size:0.8em; border-radius:4px;">🔍 Vedi</button>
            </td>
        </tr>`;
    }).join('');

    // --- riga di sintesi: media e, in ROI, quota di titoli che batte il compra-e-tieni ---
    if (rows.length > 0) {
        const mean = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;
        const median = (arr) => { const v = [...arr].sort((a, b) => a - b); const m = v.length >> 1; return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2; };
        const avgBh = mean(rows.map(r => r.bh));
        const cells = SCAN_STRATS.map(name => {
            const have = rows.filter(r => r.strategies[name]);
            if (have.length === 0) return '<td style="padding:12px; text-align:right;">—</td>';
            const vals = have.map(r => r.strategies[name][metric]).filter(v => v != null && Number.isFinite(v));
            if (vals.length === 0) return '<td style="padding:12px; text-align:right;">—</td>';
            const avg = mean(vals);
            const beat = have.filter(r => r.strategies[name].roi > r.bh).length / have.length * 100;
            // la media è trascinata da pochi titoli estremi: la mediana dice cosa è successo al titolo "tipico"
            let sub = '';
            if (metric === 'roi' || metric === 'alpha' || metric === 'timing') {
                sub = `<div style="font-size:0.72em; font-weight:normal; color:#aaa;" title="Mediana: metà dei titoli ha fatto meglio, metà peggio">mediana ${scanFmt(median(vals), metric)}</div>`;
            }
            if (metric === 'roi') {
                sub += `<div style="font-size:0.72em; font-weight:normal; color:#aaa;" title="Quota di titoli in cui la strategia ha reso più del compra-e-tieni">batte B&H ${beat.toFixed(0)}%</div>`;
            } else if (metric === 'timing') {
                const pos = vals.filter(v => v > 0).length / vals.length * 100;
                sub += `<div style="font-size:0.72em; font-weight:normal; color:#aaa;" title="Quota di titoli con timing positivo (50% = tempi a caso)">positivo ${pos.toFixed(0)}%</div>`;
            }
            const dim = name === 'live' ? ' opacity:0.55; font-style:italic;' : '';
            return `<td style="padding:12px; text-align:right; color:${scanColor(avg, metric, avgBh)};${dim}">${scanFmt(avg, metric)}${sub}</td>`;
        }).join('');
        html += `<tr id="scanner-stats-row" style="border-top:3px solid #eba834; background:rgba(235,168,52,0.15); font-weight:bold;">
            <td></td>
            <td colspan="2" style="padding:12px; color:#eba834;">📊 MEDIA (${rows.length})</td>
            <td style="padding:12px; text-align:right; color:#fff;">${scanFmt(avgBh, 'roi')}</td>
            ${cells}
            <td style="padding:12px;">
                <button onclick="openSimulatorModal()" style="background:#00ff88; color:#000; font-weight:bold; border:none; padding:6px 10px; cursor:pointer; border-radius:4px;">💰 SIMULA</button>
            </td>
        </tr>`;
    } else if (SCAN_ROWS.length > 0) {
        html = '<tr><td colspan="13" style="padding:15px; color:#888; text-align:center;">Nessun risultato con questo filtro</td></tr>';
    }
    tbody.innerHTML = html;
    renderScanSignificance();

    // freccia sull'intestazione ordinata
    document.querySelectorAll('.scan-sort').forEach(th => {
        const base = th.dataset.label || (th.dataset.label = th.textContent.trim());
        th.textContent = base + (th.dataset.sort === SCAN_SORT.key ? (SCAN_SORT.dir > 0 ? ' ▲' : ' ▼') : '');
    });
}

// --- Significatività sul portafoglio di tutti i titoli ---
// Ogni batch restituisce, per strategia e per settimana, la somma tra i titoli
// dell'eccesso di rendimento (strategia − stessi tempi a caso) e il numero di titoli.
// Sommando i batch e dividendo si ottiene l'eccesso settimanale del portafoglio a
// pesi uguali: il t va fatto su queste settimane, perché i titoli si muovono insieme
// e contarli come prove indipendenti gonfierebbe la significatività.
function scanMergeWeekly(weekly) {
    for (const [name, weeks] of Object.entries(weekly || {})) {
        const dst = SCAN_WEEKLY[name] || (SCAN_WEEKLY[name] = {});
        for (const [k, v] of Object.entries(weeks)) {
            const cell = dst[k] || (dst[k] = [0, 0]);
            cell[0] += v[0];
            cell[1] += v[1];
        }
    }
}

function scanTStat(x) {
    if (x.length < 3) return null;
    const m = x.reduce((a, b) => a + b, 0) / x.length;
    const sd = Math.sqrt(x.reduce((a, b) => a + (b - m) * (b - m), 0) / (x.length - 1));
    return sd > 0 ? m / (sd / Math.sqrt(x.length)) : null;
}

function scanWeeklyStats(weeks) {
    const keys = Object.keys(weeks || {}).sort();
    const x = keys.map(k => weeks[k][0] / weeks[k][1]);
    if (x.length === 0) return null;
    const half = x.length >> 1;
    let acc = 0;
    return {
        weeks: keys,
        cum: x.map(v => (acc += v) * 100),
        perYear: x.reduce((a, b) => a + b, 0) / x.length * 52 * 100,
        t: scanTStat(x), t1: scanTStat(x.slice(0, half)), t2: scanTStat(x.slice(half)),
    };
}

function renderScanSignificance() {
    const box = document.getElementById('scan-significance');
    if (!box) return;
    const stats = {};
    SCAN_STRATS.forEach(name => { const s = scanWeeklyStats(SCAN_WEEKLY[name]); if (s) stats[name] = s; });
    if (Object.keys(stats).length === 0) { box.style.display = 'none'; return; }
    const wasOpen = box.querySelector('details')?.open;
    const tfmt = (t) => t == null ? '—' : (t > 0 ? '+' : '') + t.toFixed(1);
    const tcol = (t) => t == null ? '#888' : (t >= 2 ? '#00ff88' : (t <= -2 ? '#ff4444' : '#ddd'));
    const cell = 'padding:3px 10px; text-align:right;';
    const rows = SCAN_STRATS.filter(n => stats[n]).map(name => {
        const s = stats[name];
        const dim = name === 'live' ? ' opacity:0.55; font-style:italic;' : '';
        return `<tr style="${dim}"><td style="padding:3px 10px; color:${SCAN_COLORS[name]};">${SCAN_LABELS[name]}</td>
            <td style="${cell} color:${s.perYear > 0 ? '#00ff88' : '#ff4444'};">${(s.perYear > 0 ? '+' : '') + s.perYear.toFixed(1)}%</td>
            <td style="${cell} color:${tcol(s.t)}; font-weight:bold;">${tfmt(s.t)}</td>
            <td style="${cell} color:${tcol(s.t1)};">${tfmt(s.t1)}</td>
            <td style="${cell} color:${tcol(s.t2)};">${tfmt(s.t2)}</td></tr>`;
    }).join('');
    const nWeeks = Math.max(...Object.values(stats).map(s => s.weeks.length));
    box.style.display = 'block';
    box.innerHTML = `<details ${wasOpen ? 'open' : ''}>
        <summary style="cursor:pointer; color:#eba834; font-weight:bold;">📐 I tempi delle strategie aggiungono valore? (tutti i titoli insieme, ${nWeeks} settimane)</summary>
        <div style="display:flex; gap:20px; flex-wrap:wrap; margin-top:8px; align-items:flex-start;">
            <table style="border-collapse:collapse; font-size:0.85rem;">
                <thead><tr style="color:#888;">
                    <th style="padding:3px 10px; text-align:left;">Strategia</th>
                    <th style="${cell}" title="Rendimento annuo in più rispetto agli stessi tempi scelti a caso, sul portafoglio di tutti i titoli a pesi uguali">Timing / anno</th>
                    <th style="${cell}" title="Quanto il risultato è distinguibile dal caso. Sopra +2: difficilmente casuale. Tra −2 e +2: non distinguibile dal caso.">t</th>
                    <th style="${cell}" title="Lo stesso t, solo sulla prima metà del periodo">t 1ª metà</th>
                    <th style="${cell}" title="Lo stesso t, solo sulla seconda metà del periodo">t 2ª metà</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>
            <div id="scan-significance-chart" style="flex:1; min-width:320px; height:230px;"></div>
        </div>
        <div style="margin-top:6px; color:#888; line-height:1.5;">
            Come leggerla: <b>t</b> tra −2 e +2 = i tempi della strategia non si distinguono dal caso; conta che il segno sia lo stesso nelle due metà.
            Nel grafico, una linea che sale = i tempi aggiungono valore con continuità; piatta o che scende = no. Senza costi.
        </div>
    </details>`;
    const details = box.querySelector('details');
    const draw = () => {
        const el = document.getElementById('scan-significance-chart');
        if (!el || typeof Plotly === 'undefined' || !details.open) return;
        const traces = SCAN_STRATS.filter(n => stats[n] && n !== 'live').map(name => ({
            x: stats[name].weeks, y: stats[name].cum, name: SCAN_LABELS[name], mode: 'lines',
            line: { color: SCAN_COLORS[name], width: 1.6 },
        }));
        Plotly.react(el, traces, {
            paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#aaa', size: 10 },
            margin: { l: 40, r: 10, t: 22, b: 30 }, showlegend: true, legend: { orientation: 'h', y: 1.18 },
            title: { text: 'Timing cumulato del portafoglio (%)', font: { size: 11 }, x: 0.01, y: 0.99 },
            xaxis: { gridcolor: '#222' }, yaxis: { gridcolor: '#222', zerolinecolor: '#555', ticksuffix: '%' },
        }, { displayModeBar: false, responsive: true });
    };
    details.addEventListener('toggle', draw);
    draw();
}

// --- Esportazione CSV: una riga per titolo, tutte le metriche di tutte le strategie ---
function scanRowsToCsv(rows) {
    const metrics = ['roi', 'timing', 'alpha', 'win_rate', 'trades', 'expo'];
    const head = ['ticker', 'trend', 'bh_pct'];
    SCAN_STRATS.forEach(s => metrics.forEach(m => head.push(`${s}_${m}`)));
    const lines = [head.join(',')];
    rows.forEach(r => {
        const cells = [r.ticker, r.trend, r.bh];
        SCAN_STRATS.forEach(s => metrics.forEach(m => {
            const v = r.strategies[s]?.[m];
            cells.push(v == null ? '' : v);
        }));
        lines.push(cells.map(c => /[",\n]/.test(String(c)) ? `"${String(c).replace(/"/g, '""')}"` : c).join(','));
    });
    return lines.join('\n');
}

function exportScanCsv() {
    if (SCAN_ROWS.length === 0) {
        alert('Esegui prima una scansione: non c\'è ancora nulla da esportare.');
        return;
    }
    // esporta ciò che si vede: filtro trend e ordinamento correnti
    const csv = scanRowsToCsv(scanVisibleRows());
    const start = document.getElementById('scanner-start').value || '2023-01-01';
    const end = document.getElementById('scanner-end').value || new Date().toISOString().slice(0, 10);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `scanner_strategie_${start}_${end}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
}

function scanToggleTicker(cb) {
    if (cb.checked) SCAN_UNCHECKED.delete(cb.dataset.ticker);
    else SCAN_UNCHECKED.add(cb.dataset.ticker);
}

// Ordinamento: clic sull'intestazione (secondo clic inverte)
document.addEventListener('click', (ev) => {
    const th = ev.target.closest && ev.target.closest('.scan-sort');
    if (!th) return;
    const key = th.dataset.sort;
    if (SCAN_SORT.key === key) SCAN_SORT.dir *= -1;
    else SCAN_SORT = { key, dir: key === 'ticker' ? 1 : -1 };
    renderScanTable();
});

// --- PORTFOLIO SIMULATOR FUNCTIONS ---

function openSimulatorModal() {
    const modal = document.getElementById('simulator-modal');
    // Check if we have trades
    if (!window.SCAN_TRADES || SCAN_ROWS.length === 0) {
        alert("Esegui prima una scansione per raccogliere i dati!");
        return;
    }

    modal.style.display = 'flex';
    runPortfolioSimulation();
}

function closeSimulatorModal() {
    document.getElementById('simulator-modal').style.display = 'none';
}

function runPortfolioSimulation() {
    const capitalPerTrade = parseFloat(document.getElementById('sim-capital').value) || 100;
    const mode = document.getElementById('sim-mode').value; // LIVE or FROZEN

    // Select Source Data
    let sourceTrades = (window.SCAN_TRADES && window.SCAN_TRADES[mode]) || [];
    const content = document.getElementById('sim-modal-content');

    if (mode === 'LIVE') {
        // ORACOLO: usa il futuro -> sfondo di avvertimento
        if (content) content.style.background = 'linear-gradient(180deg, rgba(60, 20, 20, 1) 0%, #1a1d2a 100%)';
    } else {
        if (content) content.style.background = '#1a1d2a';
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

// Toggle All Checkboxes (solo le righe visibili col filtro corrente)
function toggleAllScanRows(source) {
    scanVisibleRows().forEach(r => {
        if (source.checked) SCAN_UNCHECKED.delete(r.ticker);
        else SCAN_UNCHECKED.add(r.ticker);
    });
    renderScanTable();
}

// FORMAT MARKET CAP
function formatMarketCap(value) {
    if (!value) return '-';
    if (value >= 1e12) return (value / 1e12).toFixed(2) + 'T';
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    return parseInt(value).toLocaleString();
}

// APPLY FILTERS (trend e metrica mostrata): la resa è tutta in renderScanTable
function applyScanFilters() {
    renderScanTable();
}

// --- CHART VISIBILITY TOGGLE LISTENERS ---
// Re-render chart when toggles change (uses cached data)
['show-price', 'show-energy', 'show-frozen', 'show-indicators', 'show-zigzag', 'show-backtest', 'show-volume', 'show-kinetic-z', 'show-stable-slope', 'show-stable-kinz', 'show-v2-zones'].forEach(id => {
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

// --- LEGEND TOGGLE ---
// --- LEGEND TOGGLE ---
function toggleLegend() {
    window.SHOW_LEGEND = !window.SHOW_LEGEND;

    // Update button visual state
    const btn = document.getElementById('btn-toggle-legend');
    if (btn) {
        btn.style.opacity = window.SHOW_LEGEND ? '1' : '0.3';
    }

    // Re-render if data exists
    if (window.LAST_ANALYSIS_DATA) {
        renderCharts(window.LAST_ANALYSIS_DATA);
    }
}
// Init Legend Button State
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-toggle-legend');
    if (btn) btn.style.opacity = window.SHOW_LEGEND ? '1' : '0.3';
});

// --- FOURIER TOGGLE ---
function toggleFourier() {
    window.SHOW_FOURIER = !window.SHOW_FOURIER;

    // Update button visual state
    const btn = document.getElementById('btn-toggle-fourier');
    if (btn) {
        btn.style.opacity = window.SHOW_FOURIER ? '1' : '0.3';
    }

    // Re-render if data exists
    if (window.LAST_ANALYSIS_DATA) {
        renderCharts(window.LAST_ANALYSIS_DATA);
    }
}
// Init Fourier Button State
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-toggle-fourier');
    if (btn) btn.style.opacity = window.SHOW_FOURIER ? '1' : '0.3';
});



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
        if (mode === 'blue') activeBtn = btnBlue;
        if (mode === 'purple') activeBtn = btnPurple;
        if (mode === 'white-dot') activeBtn = btnDot;

        if (activeBtn) activeBtn.style.background = 'rgba(255,255,255,0.15)';
    }

    console.log('Annotation mode:', window.ANNOTATION_MODE);
}

// [NEW] Helper for white dots
function getUserDotAnnotations() {
    return window.CHART_ANNOTATIONS
        .filter(anno => anno.type === 'dot')
        .map(anno => ({
            x: anno.x,
            y: anno.y,
            xref: 'x', // Link to data coordinates
            yref: 'y',
            text: '●', // White dot symbol
            showarrow: false,
            font: {
                family: 'Arial',
                size: 16,
                color: '#ffffff'
            },
            bgcolor: 'transparent',
            captureevents: true // Allow detailed tooltips if needed?
        }));
}

// Convert annotations to Plotly shapes
function getAnnotationShapes() {
    // Manual annotations
    const manualShapes = window.CHART_ANNOTATIONS.map(anno => {
        let color = '#ffffff';
        if (anno.color === 'green') color = '#00ff88';
        if (anno.color === 'red') color = '#ff4444';
        if (anno.color === 'blue') color = '#3366ff';
        if (anno.color === 'purple') color = '#aa33ff';

        // [NEW] Point Annotation
        // [NEW] Point Annotation
        if (anno.type === 'dot') {
            return null; // Handled by layout.annotations (getUserDotAnnotations)
        }

        // [MODIFIED] Use Layout Annotations for Dots logic instead of Shapes?
        // Actually, converting to shapes is what this function does.
        // Let's return null here for dots and handle dots in a separate trace or layout.annotations.
        // Re-reading `getAnnotationShapes`.

        // Let's assume for now we use vertical lines for lines.
        return {
            type: 'line',
            x0: anno.x,
            x1: anno.x,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: { color: color, width: 2, dash: 'solid' },
            layer: 'below'
        };
    }).filter(s => s); // Filter nulls

    // Trade marker shapes
    const tradeShapes = getTradeMarkerShapes();

    return [...getV2ZoneShapes(), ...getV2PeakShapes(), ...manualShapes, ...tradeShapes];
}

// --- PANNELLO DIREZIONE: blu (oracolo) e arancione sovrapposti, con il segno ---
// L'arancione qui è la STIMA DI OGGI del blu (frozen_v2.direction.nowcast): calcolata ogni giorno
// con i soli dati di quel giorno, non spostata nel tempo e mai ridisegnata. Dove non combacia col
// blu, la differenza è la parte che dipende dai prezzi futuri.
function getDirectionTraces(data) {
    const full = data?.frozen_v2?.direction;
    if (!full || !full.oracle) return null;
    // scala di velocità (senza quadrato) quando disponibile: i crolli non schiacciano il resto
    const dir = full.velocity ? { ...full, ...full.velocity } : full;
    const now = (dir.nowcast && dir.nowcast.length) ? dir.nowcast : dir.orange;
    if (!now || !now.length) return null;
    const traces = [
        {
            x: data.dates, y: dir.oracle,
            name: 'Blu: velocità del percorso dell\'oracolo (ridisegnata col futuro)',
            type: 'scatter', mode: 'lines', fill: 'tozeroy',
            line: { color: '#00bfff', width: 1.5 }, fillcolor: 'rgba(0, 191, 255, 0.22)',
            hovertemplate: '%{x}<br>blu: %{y:.2f} per barra<extra></extra>',
            xaxis: 'x', yaxis: 'y9'
        },
        {
            x: data.dates, y: now,
            name: 'Arancione: stima di oggi del blu (in tempo reale, non spostata)',
            type: 'scatter', mode: 'lines',
            line: { color: '#ff6600', width: 2 },
            hovertemplate: '%{x}<br>stima di oggi: %{y:.2f} per barra<extra></extra>',
            xaxis: 'x', yaxis: 'y9'
        }
    ];
    if (dir.nowcast && dir.orange) {
        traces.push({
            x: data.dates, y: dir.orange,
            name: `Arancione vecchio (scostamento dal filtro: ripete il blu ${dir.lag ?? 9} barre dopo)`,
            type: 'scatter', mode: 'lines',
            line: { color: '#ffb347', width: 1, dash: 'dot' },
            visible: 'legendonly',
            xaxis: 'x', yaxis: 'y9'
        });
    }
    return [...traces, ...getDirectionSignalTraces(data, now)];
}

// Cambi di segno della stima di oggi: ▲ compra, ▼ vendi, nel giorno in cui si conoscono.
function getDirectionSignalTraces(data, series) {
    const buyX = [], sellX = [];
    let prev = null;
    for (let i = 0; i < series.length; i++) {
        const v = series[i];
        if (v == null || v === 0) continue;
        const sg = v > 0 ? 1 : -1;
        if (prev !== null && sg !== prev) (sg > 0 ? buyX : sellX).push(data.dates[i]);
        prev = sg;
    }
    const marker = (symbol, color) => ({ symbol, size: 11, color, line: { color: '#ffffff', width: 1 } });
    return [
        {
            x: buyX, y: buyX.map(() => 0),
            name: '▲ Compra: la stima di oggi diventa positiva',
            type: 'scatter', mode: 'markers', marker: marker('triangle-up', '#00ff88'),
            hovertemplate: '%{x}<br>la stima di oggi diventa positiva<extra></extra>',
            xaxis: 'x', yaxis: 'y9'
        },
        {
            x: sellX, y: sellX.map(() => 0),
            name: '▼ Vendi: la stima di oggi diventa negativa',
            type: 'scatter', mode: 'markers', marker: marker('triangle-down', '#ff2d55'),
            hovertemplate: '%{x}<br>la stima di oggi diventa negativa<extra></extra>',
            xaxis: 'x', yaxis: 'y9'
        }
    ];
}

// --- ZONE V2: stato dell'arancione (causale, non viene ridisegnato) ---
// data.frozen_v2.state ha un valore per barra, allineato a data.dates:
//   1 = prezzo sotto il percorso, energia alta, in carica   → fascia verde piena
//   2 = prezzo sotto il percorso, energia alta, in scarica  → fascia verde chiara
//   3 = sopra il percorso, energia alta, in carica          → niente
//   4 = sopra il percorso, energia alta, in scarica         → ▼ sul primo giorno (massimo arancione)
const V2_ZONE_FILL = { 1: 'rgba(0, 255, 136, 0.22)', 2: 'rgba(0, 255, 136, 0.09)' };

function v2ZonesVisible() {
    return document.getElementById('show-v2-zones')?.checked ?? true;
}

// tratti consecutivi con lo stesso stato: [{state, from, to}] (indici di barra, estremi inclusi)
function v2StateRuns(states) {
    const runs = [];
    let from = 0;
    for (let i = 1; i <= states.length; i++) {
        if (i === states.length || states[i] !== states[from]) {
            runs.push({ state: states[from], from, to: i - 1 });
            from = i;
        }
    }
    return runs;
}

function getV2ZoneShapes() {
    const data = window.LAST_ANALYSIS_DATA;
    const states = data?.frozen_v2?.state;
    if (!v2ZonesVisible() || !states || !states.length || !data.dates) return [];
    const last = data.dates.length - 1;
    return v2StateRuns(states)
        .filter(r => V2_ZONE_FILL[r.state])
        .map(r => ({
            type: 'rect',
            xref: 'x',
            yref: 'paper',
            x0: data.dates[r.from],
            x1: data.dates[Math.min(r.to + 1, last)],
            y0: 0,
            y1: 1,
            fillcolor: V2_ZONE_FILL[r.state],
            line: { width: 0 },
            layer: 'below'
        }));
}

// Picchi dell'arancione, uno per episodio (tratto continuo di energia alta dalla stessa parte):
//   above = primo giorno in cui, col prezzo SOPRA il percorso, l'energia comincia a scendere (stato 4)
//   below = lo stesso col prezzo SOTTO il percorso (stato 2): il panico comincia a scaricarsi
function v2PeakIndices(states) {
    const out = { above: [], below: [] };
    let side = 0, marked = false;
    for (let i = 0; i < states.length; i++) {
        const st = states[i];
        const cur = (st === 3 || st === 4) ? 1 : ((st === 1 || st === 2) ? -1 : 0);
        if (cur !== side) { side = cur; marked = false; }
        if (!marked && st === 4) { out.above.push(i); marked = true; }
        if (!marked && st === 2) { out.below.push(i); marked = true; }
    }
    return out;
}

// linee guida verticali sui picchi, dentro il pannello Frozen
function getV2PeakShapes() {
    const data = window.LAST_ANALYSIS_DATA;
    const states = data?.frozen_v2?.state;
    const showFrozen = document.getElementById('show-frozen')?.checked ?? true;
    if (!v2ZonesVisible() || !showFrozen || !states || !states.length) return [];
    const peaks = v2PeakIndices(states);
    const mk = (i, color) => ({
        type: 'line', xref: 'x', yref: 'y6 domain',
        x0: data.dates[i], x1: data.dates[i], y0: 0, y1: 1,
        line: { color, width: 1.2, dash: 'dot' }, layer: 'below'
    });
    return [...peaks.above.map(i => mk(i, 'rgba(255, 45, 85, 0.7)')),
            ...peaks.below.map(i => mk(i, 'rgba(0, 255, 136, 0.7)'))];
}

function getV2ZoneTraces(data, showFrozen, showPrice) {
    const states = data?.frozen_v2?.state;
    if (!v2ZonesVisible() || !states || !states.length) return [];
    const traces = [];

    // ▼ / ▲ sui picchi dell'arancione (uno per episodio). Il ▼ è l'evento che fa uscire la V2 Risalita.
    if (showFrozen && data.frozen?.dates?.length) {
        const potByDate = {};
        data.frozen.dates.forEach((d, i) => { potByDate[d] = data.frozen.z_potential[i]; });
        const peaks = v2PeakIndices(states);
        const mk = (idxs, name, symbol, color, hover) => {
            const pts = idxs.filter(i => potByDate[data.dates[i]] !== undefined);
            if (!pts.length) return;
            traces.push({
                x: pts.map(i => data.dates[i]), y: pts.map(i => potByDate[data.dates[i]]),
                name, type: 'scatter', mode: 'markers',
                marker: { symbol, size: 15, color, line: { color: '#ffffff', width: 1.5 } },
                hovertemplate: `%{x}<br>${hover}<extra></extra>`,
                xaxis: 'x', yaxis: 'y6'
            });
        };
        mk(peaks.above, '▼ Picco dell\'arancione sopra il percorso (salita matura)', 'triangle-down', '#ff2d55',
            'picco dell\'arancione sopra il percorso: la salita è matura');
        mk(peaks.below, '▲ Picco dell\'arancione sotto il percorso (il panico si scarica)', 'triangle-up', '#00ff88',
            'picco dell\'arancione sotto il percorso: il panico comincia a scaricarsi');
    }

    // voci di legenda per le fasce (le fasce vere sono shapes del layout)
    const yref = showPrice ? 'y' : (showFrozen ? 'y6' : null);
    if (yref) {
        [[1, '🟩 Zona V2 in carica (sotto il percorso, energia in aumento)'],
         [2, '▫️ Zona V2 in scarica (sotto il percorso, energia in calo)']].forEach(([st, label]) => {
            traces.push({
                x: [null], y: [null], name: label, type: 'scatter', mode: 'markers',
                marker: { symbol: 'square', size: 12, color: V2_ZONE_FILL[st].replace(/[\d.]+\)$/, st === 1 ? '0.8)' : '0.35)') },
                hoverinfo: 'skip', xaxis: 'x', yaxis: yref
            });
        });
    }
    return traces;
}

// Get Scatter Trace for open portfolio positions (Dots)
function getPortfolioTrace() {
    const currentTicker = document.getElementById('ticker')?.value.toUpperCase();
    if (!currentTicker || !window.PORTFOLIO_POSITIONS) return null;

    // Filter for current ticker and OPEN status
    const openPositions = window.PORTFOLIO_POSITIONS.filter(p =>
        p.ticker === currentTicker && p.status === 'OPEN'
    );

    if (openPositions.length === 0) return null;

    const x = [];
    const y = [];
    const colors = [];
    const text = [];

    openPositions.forEach(p => {
        x.push(p.entry_date);
        y.push(p.entry_price || p.current_price); // Fallback if entry price missing
        colors.push(p.direction === 'LONG' ? '#00ff88' : '#ff4444');
        text.push(`${p.direction}<br>${p.entry_price}`);
    });

    return {
        x: x,
        y: y,
        mode: 'markers',
        type: 'scatter',
        name: 'My Trades',
        marker: {
            size: 12,
            color: colors,
            line: { color: '#fff', width: 2 }
        },
        text: text,
        hoverinfo: 'text+x+y',
        xaxis: 'x',
        yaxis: 'y' // Price axis
    };
}

// Get annotations for open portfolio positions (Text above dot)
function getPortfolioAnnotations() {
    const currentTicker = document.getElementById('ticker')?.value.toUpperCase();
    if (!currentTicker || !window.PORTFOLIO_POSITIONS) return [];

    // Filter for current ticker and OPEN status
    const openPositions = window.PORTFOLIO_POSITIONS.filter(p =>
        p.ticker === currentTicker && p.status === 'OPEN'
    );

    const annotations = [];
    openPositions.forEach(p => {
        const color = p.direction === 'LONG' ? '#00ff88' : '#ff4444'; // Green/Red
        const label = p.direction === 'LONG' ? 'LONG' : 'SHORT';

        annotations.push({
            x: p.entry_date,
            y: p.entry_price, // At price level
            xref: 'x',
            yref: 'y',
            text: label,
            showarrow: true,
            arrowhead: 2,
            ax: 0,
            ay: -25, // Point down to the dot
            font: {
                color: '#ffffff',
                size: 11,
                weight: 'bold'
            },
            bgcolor: color,
            bordercolor: color,
            borderwidth: 1,
            borderpad: 4,
            opacity: 0.9
        });
    });

    return annotations;
}

// Get trade marker shapes based on selected strategy
function getTradeMarkerShapes() {

    const showMarkers = document.getElementById('show-trade-markers')?.checked;
    if (!showMarkers) return [];

    const strategy = document.getElementById('trade-strategy-select')?.value || 'LIVE';
    const cachedData = window.LAST_ANALYSIS_DATA;
    if (!cachedData) return [];

    let trades = [];
    const buyColor = '#00ff88';   // Always green for entry
    const sellColor = '#ff4444';  // Always red for exit

    if (strategy === 'LIVE') {
        trades = cachedData.backtest?.trades || [];
    } else if (strategy === 'FROZEN') {
        trades = cachedData.frozen_strategy?.trades || [];
    } else if (strategy === 'SUM') {
        trades = cachedData.frozen_sum_strategy?.trades || [];
    } else if (strategy === 'STABLE') {
        trades = cachedData.stable_strategy?.trades || [];
    } else if (strategy === 'FROZEN_V2') {
        trades = cachedData.frozen_v2_strategy?.trades || [];
    } else if (strategy === 'FROZEN_V2R') {
        trades = cachedData.frozen_v2_rise_strategy?.trades || [];
    } else if (strategy === 'FROZEN_DIR') {
        trades = cachedData.frozen_dir_strategy?.trades || [];
    }

    const shapes = [];

    trades.forEach(trade => {
        // Entry line (BUY - green/colored)
        if (trade.entry_date) {
            shapes.push({
                type: 'line',
                x0: trade.entry_date,
                x1: trade.entry_date,
                y0: 0,
                y1: 1,
                yref: 'paper',
                line: {
                    color: buyColor,
                    width: 1.5,
                    dash: 'dash'
                },
                layer: 'below'
            });
        }

        // Exit line (SELL - darker) — skip if OPEN (no exit yet)
        if (trade.exit_date && trade.exit_date !== 'OPEN') {
            shapes.push({
                type: 'line',
                x0: trade.exit_date,
                x1: trade.exit_date,
                y0: 0,
                y1: 1,
                yref: 'paper',
                line: {
                    color: sellColor,
                    width: 1.5,
                    dash: 'dot'
                },
                layer: 'below'
            });
        }
    });

    return shapes;
}

// Toggle trade markers visibility
function toggleTradeMarkers() {
    const checkbox = document.getElementById('show-trade-markers');
    const icon = checkbox?.parentElement?.querySelector('.toggle-icon');

    if (icon) {
        icon.style.opacity = checkbox.checked ? '1' : '0.5';
        icon.dataset.active = checkbox.checked ? 'true' : 'false';
    }

    // Update chart shapes
    const chartDiv = document.getElementById('chart-combined');
    if (chartDiv && chartDiv.layout) {
        const newShapes = getAnnotationShapes();
        Plotly.relayout(chartDiv, { shapes: newShapes });
    }
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
        const clickY = data.points[0]?.y; // [NEW] Capture Y for dots

        if (!clickX) return;

        // [MODIFIED] Logic for Dots vs Lines
        if (window.ANNOTATION_MODE === 'white-dot') {
            // Allow multiple dots, just add new one
            window.CHART_ANNOTATIONS.push({
                x: clickX,
                y: clickY,
                type: 'dot',
                color: 'white'
            });
        } else {
            // Vertical Lines Logic (Toggle behavior)
            const existingIndex = window.CHART_ANNOTATIONS.findIndex(a => a.x === clickX && a.type !== 'dot');
            if (existingIndex >= 0) {
                window.CHART_ANNOTATIONS.splice(existingIndex, 1);
            } else {
                window.CHART_ANNOTATIONS.push({
                    x: clickX,
                    type: 'line',
                    color: window.ANNOTATION_MODE
                });
            }
        }

        saveAnnotations();

        // Update chart shapes AND annotations without full re-render
        const currentLayout = chartDiv.layout || {};
        const newShapes = getAnnotationShapes();

        // Re-merge annotations (Portfolio + User Dots)
        const portfolioAnnos = getPortfolioAnnotations();
        const userDotAnnos = getUserDotAnnotations();
        const newAnnotations = [...portfolioAnnos, ...userDotAnnos];

        // Relayout both shapes (lines) and annotations (dots)
        Plotly.relayout(chartDiv, {
            shapes: newShapes,
            annotations: newAnnotations
        });
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
        const response = await fetch(`${API_URL}/scan-daily-orange`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tickers: tickers, as_of_date: asOfDate })
        });

        if (!response.ok) throw new Error("Errore scansione backend");

        const results = await response.json();

        progress.value = 100;
        const nNew = (results.signals_new || []).length;
        status.innerText = `Scansione completata: ${results.n_scanned}/${results.n_requested} titoli, ` +
            `${nNew} segnal${nNew === 1 ? 'e nuovo' : 'i nuovi'}.`;

        renderDailyScanResults(results);

    } catch (err) {
        console.error(err);
        status.innerText = "Errore durante la scansione.";
        progress.style.display = 'none';
    }
}

function renderDailyScanResults(res) {
    // Scansione giornaliera sull'ARANCIONE. La versione precedente dava
    // "STRONG BUY / BUY" in base a Frozen e SUM, strategie che nei test non
    // hanno mostrato vantaggio: qui si mostrano solo i segnali del potenziale.
    const tbody = document.getElementById('daily-scan-results');
    const summary = document.getElementById('daily-scan-summary');
    const esc = (v) => String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const pct = (v, d = 1) => (v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%');

    if (!res || !Array.isArray(res.signals_new)) {
        summary.style.display = 'none';
        tbody.innerHTML = '<tr><td colspan="8" style="padding:20px; text-align:center; color:#888;">Errore di connessione o risposta non valida.</td></tr>';
        return;
    }

    const fresh = res.signals_new;
    const recent = res.signals_recent || [];
    const exp = res.expected || {};
    const horizon = res.horizon || 21;
    const failed = (res.failed || []).length;

    // --- riepilogo ---
    let html = `<b style="color:#fff;">${res.as_of ? 'Alla data ' + esc(res.as_of) : 'Oggi'}:</b> ` +
        `${fresh.length} segnal${fresh.length === 1 ? 'e nuovo' : 'i nuovi'} su ${res.n_scanned} titoli ` +
        `(${Number(res.breadth_pct).toFixed(1)}%)` + (failed ? `, ${failed} non scaricati` : '') + '. ';
    if (fresh.length === 0) {
        html += 'Nessun segnale è la norma: in media scatta circa 1 titolo su 800 al giorno, a grappoli nei giorni di tensione.';
    } else {
        html += `Ingresso alla prossima chiusura, uscita dopo ${horizon} barre. `;
        // l'ampiezza ha senso solo su un universo largo: 1 segnale su 30 titoli non è "panico"
        if (res.breadth_pct >= 2 && res.n_scanned >= 200) {
            html += `<br><span style="color:#ff9900;"><b>Panico diffuso</b>: ha dato segnale almeno il 2% dei titoli. ` +
                `Nel backtest, dopo giornate così, anche l'indice SPY ha reso +3.9% in 21 barre contro +1.1% di un giorno qualsiasi (26 casi).</span>`;
        }
    }
    html += `<br><span style="color:#888;">Cosa aspettarsi (backtest, 21 barre, costi inclusi): titolo del segnale ` +
        `${pct(exp.signal)}, titolo a caso lo stesso giorno ${pct(exp.control)}, titolo a caso in un giorno qualsiasi ${pct(exp.baseline)}. ` +
        `Il vantaggio sta soprattutto nel giorno, poco nel singolo titolo: è indicativo, non provato.</span>`;
    const fw = res.forward;
    if (fw) {
        const labels = { IN_CORSO: 'in corso', COERENTE: 'coerente col backtest', STOP: 'stop', ESTENDI: 'da estendere', NON_CONFERMATO: 'non confermato' };
        html += `<br><b style="color:#fff;">Forward test:</b> ${fw.closed} chiusi, ${fw.open} aperti` +
            (fw.closed ? `, media ${pct(fw.avg_pnl_pct, 2)} (base giornaliera ${pct(fw.baseline_avg_pnl_pct, 2)})` : '') +
            ` — semaforo: ${labels[fw.verdict] || fw.verdict}.`;
    }
    summary.innerHTML = html;
    summary.style.display = 'block';

    // --- tabella ---
    const rowHtml = (r, isNew) => {
        const state = isNew
            ? '<span style="color:#00ff88; font-weight:bold;">NUOVO</span>'
            : `<span style="color:#888;">${r.days_ago} g fa (${pct(r.change_since_pct)})</span>`;
        const t = esc(r.ticker);
        return `<tr style="border-bottom:1px solid #333;${isNew ? '' : ' opacity:0.75;'}">
            <td style="padding:12px; font-weight:bold; color:#fff;">${t}</td>
            <td style="padding:12px;">${state}</td>
            <td style="padding:12px; color:#ccc;">${esc(r.signal_date)}</td>
            <td style="padding:12px; text-align:right; color:#ccc;">${Number(r.price).toFixed(2)}</td>
            <td style="padding:12px; text-align:right; color:#ff9900;">${Number(r.depth_pct).toFixed(1)}%</td>
            <td style="padding:12px; text-align:right; color:#ccc;">${Number(r.z).toFixed(1)}</td>
            <td style="padding:12px; color:#ccc;">~${esc(r.exit_estimate)}</td>
            <td style="padding:12px;">
                <div style="display:flex; justify-content:center; gap:8px;">
                    <button onclick="pfQuickOpen('${t}', 'LONG')"
                        style="background:#2d3342; border:1px solid #7d4bf0; color:#d9ccff; border-radius:4px; padding:4px 8px; cursor:pointer;" title="Apri in Portafoglio Reale">
                        💼
                    </button>
                    <button onclick="loadTickerFromScanner('${t}')"
                        style="background:#333; border:1px solid #555; color:#fff; border-radius:4px; padding:4px 8px; cursor:pointer;" title="Carica nel Grafico">
                        ⚡
                    </button>
                </div>
            </td>
        </tr>`;
    };

    const rows = fresh.map(r => rowHtml(r, true)).concat(recent.map(r => rowHtml(r, false)));
    tbody.innerHTML = rows.length
        ? rows.join('')
        : '<tr><td colspan="8" style="padding:20px; text-align:center; color:#888;">Nessun segnale arancione negli ultimi 5 giorni su questi titoli.</td></tr>';
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

// Global storage for portfolio positions
window.PORTFOLIO_POSITIONS = [];

async function fetchPortfolioData() {
    try {
        const res = await fetch(`${API_URL}/portfolio`);
        const data = await res.json();
        window.PORTFOLIO_POSITIONS = data.positions || [];
        return data;
    } catch (err) {
        console.error("Error fetching portfolio:", err);
        return { positions: [] };
    }
}

async function pfLoadData() {
    const openList = document.getElementById('pf-open-list');
    const closedList = document.getElementById('pf-closed-list');

    // Clear (9 cols)
    openList.innerHTML = '<tr><td colspan="9">Caricamento...</td></tr>';
    console.log("DEBUG: pfLoadData started");

    try {
        console.log("DEBUG: Calling fetchPortfolioData...");
        const data = await fetchPortfolioData(); // Use shared fetcher
        console.log("DEBUG: fetchPortfolioData returned", data);

        openList.innerHTML = '';
        closedList.innerHTML = '';

        const positions = data.positions || [];

        // Split Open vs Closed
        const openPos = positions.filter(p => p.status === 'OPEN').reverse(); // Newest first
        const closedPos = positions.filter(p => p.status === 'CLOSED').reverse();

        // Render OPEN
        let avgPnl = 0;
        let validPosCount = 0;

        if (openPos.length === 0) {
            openList.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:#555;">Nessuna posizione aperta</td></tr>';
        } else {
            // [MODIFIED] Equal-weighted average of percentages (Price Independent)
            // Filter out positions with invalid data to avoid skewing the average
            const validPositions = openPos.filter(p => p.pnl_pct !== undefined && p.pnl_pct !== null && !isNaN(parseFloat(p.pnl_pct)));

            if (validPositions.length > 0) {
                const totalPnl = validPositions.reduce((sum, p) => sum + parseFloat(p.pnl_pct), 0);
                avgPnl = totalPnl / validPositions.length;
                validPosCount = validPositions.length;
            }
        }

        // Update Header with Open Positions Average
        const openHeader = document.querySelector('#portfolio-modal h4');
        if (openHeader) {
            const avgColor = avgPnl >= 0 ? '#00ff88' : '#ff4444';
            const avgSign = avgPnl >= 0 ? '+' : '';
            openHeader.innerHTML = `Posizioni Aperte <span style="font-size:0.9em; margin-left:10px; color:${avgColor}">(Media Equipesata: ${avgSign}${avgPnl.toFixed(2)}%)</span>`;
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
                    <button onclick="pfAnalyzeTicker('${p.ticker}')" 
                        style="background:#eba834; border:1px solid #eba834; color:#000; padding:4px 8px; border-radius:4px; cursor:pointer; font-size:0.8rem; margin-right:5px; font-weight:bold;" title="Analizza Grafico">
                        📊
                    </button>
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
        const res = await apiFetch(`${API_URL}/portfolio/open`, {
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
        const res = await apiFetch(`${API_URL}/portfolio/close/${id}`, { method: 'POST' });
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
        const res = await apiFetch(`${API_URL}/portfolio/open`, {
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

        const res = await apiFetch(`${API_URL}/portfolio/update/${id}`, {
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
        const res = await apiFetch(`${API_URL}/portfolio/update/${id}`, {
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

async function runAlertScan() {
    if (!confirm("Avviare scansione completa e invio email? (Richiede circa 2-5 minuti)")) return;

    try {
        const res = await apiFetch(`${API_URL}/scan/email`, { method: 'POST' });
        const data = await res.json();
        alert(data.message);
    } catch (e) {
        console.error(e);
        alert("Errore scansione email");
    }
}

// Add this new function to handle clicks
function closePortfolioModal() {
    const m = document.getElementById('portfolio-modal');
    if (m) m.style.display = 'none';
}

function pfAnalyzeTicker(ticker) {
    // 1. Set the main input
    const input = document.getElementById('ticker');
    if (input) {
        input.value = ticker;
    }

    // 2. Close the portfolio modal
    closePortfolioModal();

    // 3. Trigger analysis (small delay to ensure modal closes smoothly)
    setTimeout(() => {
        runAnalysis();
    }, 100);
}

// Init
window.onload = function () {
    // Other init logic if needed
    fetchPortfolioData(); // Ensure portfolio is loaded for chart markers
};

