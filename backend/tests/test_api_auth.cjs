#!/usr/bin/env node
/**
 * Test per frontend/api_auth.js (apiFetch): la chiave viene inviata se
 * presente, chiesta una sola volta su 401, ricordata solo se accettata.
 *
 * Esecuzione: node backend/tests/test_api_auth.cjs
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'api_auth.js'), 'utf8');

function makeEnv({ serverKey, promptAnswer }) {
    const store = {};
    const calls = [];
    let prompts = 0;
    const sandbox = {
        localStorage: {
            getItem: k => (k in store ? store[k] : null),
            setItem: (k, v) => { store[k] = String(v); },
            removeItem: k => { delete store[k]; },
        },
        window: { prompt: () => { prompts++; return promptAnswer; } },
        fetch: async (url, opts) => {
            const sent = (opts && opts.headers && opts.headers['X-API-Key']) || null;
            calls.push(sent);
            const ok = !serverKey || sent === serverKey;
            return { status: ok ? 200 : 401, ok };
        },
        Object, String,
    };
    vm.createContext(sandbox);
    vm.runInContext(src + '\nthis.apiFetch = apiFetch;', sandbox);
    return { sandbox, store, calls, prompts: () => prompts };
}

function assert(cond, msg) { if (!cond) { console.error('FAIL:', msg); process.exit(1); } }

(async () => {
    // 1. server aperto: nessuna richiesta di chiave
    let env = makeEnv({ serverKey: null, promptAnswer: 'x' });
    let r = await env.sandbox.apiFetch('/u', { method: 'POST' });
    assert(r.status === 200 && env.prompts() === 0, 'server aperto: niente prompt');

    // 2. server protetto, nessuna chiave salvata: prompt, retry, chiave ricordata
    env = makeEnv({ serverKey: 'segreta', promptAnswer: ' segreta ' });
    r = await env.sandbox.apiFetch('/u', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    assert(r.status === 200, 'dopo la chiave giusta deve passare');
    assert(env.prompts() === 1, 'un solo prompt');
    assert(env.calls.length === 2 && env.calls[0] === null && env.calls[1] === 'segreta', 'retry con la chiave');
    assert(env.store.FPR_API_KEY === 'segreta', 'chiave ricordata (senza spazi)');

    // 3. chiamata successiva: chiave inviata subito, nessun prompt
    r = await env.sandbox.apiFetch('/u', { method: 'POST' });
    assert(r.status === 200 && env.prompts() === 1 && env.calls[2] === 'segreta', 'chiave riusata');

    // 4. chiave sbagliata: resta 401 e NON viene ricordata
    env = makeEnv({ serverKey: 'segreta', promptAnswer: 'sbagliata' });
    r = await env.sandbox.apiFetch('/u', { method: 'POST' });
    assert(r.status === 401, 'chiave errata: 401');
    assert(!('FPR_API_KEY' in env.store), 'chiave errata non ricordata');

    // 5. prompt annullato: 401 restituito, nessun secondo tentativo
    env = makeEnv({ serverKey: 'segreta', promptAnswer: null });
    r = await env.sandbox.apiFetch('/u', { method: 'POST' });
    assert(r.status === 401 && env.calls.length === 1, 'annullato: nessun retry');

    console.log('OK test_api_auth — server aperto, prompt su 401, chiave ricordata solo se valida');
})();
