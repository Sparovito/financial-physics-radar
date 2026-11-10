// ============================================================
//  apiFetch — fetch con chiave API per gli endpoint che modificano dati
//  (email, config, journal, portfolio).
//
//  Il server richiede l'header X-API-Key solo se ha la variabile
//  d'ambiente API_KEY impostata. La chiave viene chiesta una volta, alla
//  prima risposta 401, e ricordata in questo browser (localStorage).
// ============================================================

const FPR_KEY_STORAGE = 'FPR_API_KEY';

function getStoredApiKey() {
    try { return localStorage.getItem(FPR_KEY_STORAGE) || ''; } catch (e) { return ''; }
}

function storeApiKey(key) {
    try {
        if (key) localStorage.setItem(FPR_KEY_STORAGE, key);
        else localStorage.removeItem(FPR_KEY_STORAGE);
    } catch (e) { /* storage non disponibile: la chiave vale solo per questa chiamata */ }
}

async function apiFetch(url, opts) {
    opts = opts || {};
    const withKey = (key) => {
        const headers = Object.assign({}, opts.headers || {});
        if (key) headers['X-API-Key'] = key;
        return Object.assign({}, opts, { headers });
    };

    let resp = await fetch(url, withKey(getStoredApiKey()));
    if (resp.status !== 401) return resp;

    // chiave assente o non più valida: la chiedo e riprovo una volta
    storeApiKey('');
    const entered = window.prompt(
        'Questa azione modifica dati sul server e richiede la API key.\n' +
        'Inserisci la chiave (viene ricordata solo in questo browser):');
    if (!entered) return resp;
    const key = entered.trim();
    resp = await fetch(url, withKey(key));
    if (resp.status !== 401) storeApiKey(key);
    return resp;
}
