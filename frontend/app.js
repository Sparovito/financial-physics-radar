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

    if (!ticker) {
        alert("Inserisci un Ticker!");
        return;
    }

    // UI Loading State
    btn.disabled = true;
    status.style.display = 'flex';
    statusText.innerText = `Scaricando dati per ${ticker}...`;

    try {
        // 2. Chiama API Backend
        const response = await fetch(`${API_URL}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                alpha: alpha,
                beta: beta,
                forecast_days: forecast
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

    // --- LAYOUT COMBINATO ---
    const layout = {
        // Grid rimosso per garantire il rispetto dei domini manuali

        // --- Asse X Condiviso ---
        xaxis: {
            anchor: 'y3', // Ancorato all'ultimo grafico
            domain: [0, 1],
            gridcolor: '#333'
        },

        // --- Configurazione Assi Y (Domini) ---
        // Grafico 1: Prezzo (55-100%)
        yaxis: {
            domain: [0.55, 1],
            gridcolor: '#333',
            title: 'Prezzo'
        },
        // Grafico 2: Energia (30-50%)
        yaxis2: {
            domain: [0.30, 0.50],
            gridcolor: '#333',
            title: 'Energia'
        },
        // Grafico 3: Slope (Left) & Z-Res (Right) (0-25%)
        yaxis3: {
            domain: [0, 0.25],
            gridcolor: '#333',
            title: 'Slope',
            titlefont: { color: '#eba834' },
            tickfont: { color: '#eba834' }
        },
        yaxis4: {
            domain: [0, 0.25],
            gridcolor: '#333333',
            title: 'Z-Score',
            titlefont: { color: '#ff88ff' },
            tickfont: { color: '#ff88ff' },
            anchor: 'x',
            overlaying: 'y3',
            side: 'right'
        },

        title: { text: `Analisi: ${data.ticker}`, font: { color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#aaa' },
        showlegend: true,
        legend: {
            orientation: 'h',
            x: 0.5,
            y: 1.05,
            xanchor: 'center',
            bgcolor: 'rgba(0,0,0,0)'
        },
        margin: { t: 60, r: 50, l: 50, b: 40 }, // Right margin increased for 2nd axis

        hovermode: 'x unified'
    };

    Plotly.newPlot('chart-combined', [
        tracePrice, tracePath, traceFund, traceForecast,
        traceKinetic, tracePotential,
        traceSlope, traceZ
    ], layout, { responsive: true });
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
const radarSlider = document.getElementById('radar-slider');
const radarDateLabel = document.getElementById('radar-date');
const radarTrailsCheck = document.getElementById('radar-trails');

// Global Cache per Timeline
let RADAR_RESULTS_CACHE = null;

function openRadar() {
    radarModal.style.display = 'flex';
    if (document.getElementById('radar-chart').innerHTML === "") {
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

    // 1. Raccogli Tickers
    let tickersToScan = [];
    if (category === "ALL") {
        tickersToScan = Object.values(TICKERS_DATA).flat().map(t => t.symbol);
    } else if (category === "Tech") {
        tickersToScan = TICKERS_DATA["💻 US Tech & Growth"].map(t => t.symbol);
    } else if (category === "Crypto") {
        tickersToScan = TICKERS_DATA["🪙 Crypto"].map(t => t.symbol);
    } else if (category === "Europe") {
        tickersToScan = TICKERS_DATA["🇪🇺 Europe"].map(t => t.symbol);
    } else {
        tickersToScan = TICKERS_DATA["Highlights"].map(t => t.symbol);
    }

    tickersToScan = [...new Set(tickersToScan)];

    chartDiv.innerHTML = `<div style="display:flex; height:100%; align-items:center; justify-content:center; color:#eba834;">
        <h3>📡 Scansione Temporale di ${tickersToScan.length} titoli...</h3>
    </div>`;

    try {
        const response = await fetch(`${API_URL}/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tickers: tickersToScan })
        });

        const data = await response.json();
        if (data.status !== "ok") throw new Error(data.detail);

        // SALVA CACHE
        RADAR_RESULTS_CACHE = data.results;

        // Setup Slider
        if (RADAR_RESULTS_CACHE.length > 0) { // Safety
            const maxIdx = RADAR_RESULTS_CACHE[0].history.dates.length - 1;
            radarSlider.max = maxIdx;
            radarSlider.value = maxIdx;

            // Attiva Listener
            radarSlider.oninput = updateRadarFrame;
            radarTrailsCheck.onchange = updateRadarFrame;

            // Render Iniziale
            updateRadarFrame();
        }

    } catch (e) {
        chartDiv.innerHTML = `<h3 style="color:red">Errore: ${e.message}</h3>`;
    }
}

// Funzione Core per il "Time Travel"
function updateRadarFrame() {
    if (!RADAR_RESULTS_CACHE) return;

    const dayIdx = parseInt(radarSlider.value);
    const showTrails = radarTrailsCheck.checked;

    // Recupera data corrente
    const currentDate = RADAR_RESULTS_CACHE[0].history.dates[dayIdx];
    radarDateLabel.innerText = currentDate;

    // 1. Dati Punti (Teste)
    const xHead = [];
    const yHead = [];
    const texts = [];
    const colors = [];
    const tickers = [];

    RADAR_RESULTS_CACHE.forEach(r => {
        // Safety check index
        if (dayIdx < r.history.z_kin.length) {
            xHead.push(r.history.z_kin[dayIdx]);
            yHead.push(r.history.z_pot[dayIdx]);
            texts.push(r.ticker);
            colors.push(r.history.z_pot[dayIdx]);
            tickers.push(r.ticker);
        }
    });

    // 2. Dati Scie (Trails) - Solo se attive
    // Tecnica: Unica traccia con NaN per separare i segmenti
    const xTail = [];
    const yTail = [];

    if (showTrails) {
        const TAIL_LEN = 10; // Lunghezza scia
        const startIdx = Math.max(0, dayIdx - TAIL_LEN);

        RADAR_RESULTS_CACHE.forEach(r => {
            for (let i = startIdx; i <= dayIdx; i++) {
                xTail.push(r.history.z_kin[i]);
                yTail.push(r.history.z_pot[i]);
            }
            // Interruzione linea (Gap) tra un ticker e l'altro
            xTail.push(null);
            yTail.push(null);
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
        marker: {
            size: 15,
            color: colors,
            colorscale: 'RdBu',
            reversescale: true,
            showscale: true,
            colorbar: { title: 'Z-Potential' },
            line: { color: 'white', width: 0.5 },
            opacity: 0.9
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
        title: { text: `Market Radar (${currentDate})`, font: { color: 'white' } },
        xaxis: { title: 'Volatilità (Kinetic Z)', gridcolor: '#333', range: [-3, 5] },
        yaxis: { title: 'Tensione (Potential Z)', gridcolor: '#333', range: [-3, 5] },
        paper_bgcolor: '#0f111a',
        plot_bgcolor: '#0f111a',
        font: { color: '#aaa' },
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
        transition: { duration: 0 } // Disabilita animazione nativa plotly per performance
    };

    // Usa react per performance (aggiorna solo dati)
    Plotly.react('radar-chart', dataToPlot, layout, { responsive: true });

    // Re-bind Click
    document.getElementById('radar-chart').on('plotly_click', function (data) {
        // Attenzione: se ci sono 2 tracce (scia+head), l'indice cambia.
        // traceMain è la seconda (index 1) o la prima (index 0)
        const point = data.points[0];
        // Cerca il punto che ha "text" definita (è un marker)
        if (point.data.mode === 'lines') return; // Ignora click sulla scia

        const tickerClicked = point.text; // Abbiamo messo ticker nel text
        if (tickerClicked) {
            closeRadar();
            document.getElementById('ticker').value = tickerClicked;
            runAnalysis();
        }
    });
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
