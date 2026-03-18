// ==========================================
// Quant API Client Module
// Communicates with the FastAPI backend
// ==========================================

const API_BASE = '';

let _backendDown = false;
let _backendDownSince = 0;
const _BACKEND_COOLDOWN = 10000; // 10s cooldown before retrying a down backend

async function fetchApi(endpoint, options = {}, retries = 1) {
    // If backend was recently detected as down, fail fast
    if (_backendDown && (Date.now() - _backendDownSince) < _BACKEND_COOLDOWN) {
        return { error: '백엔드 서버에 연결할 수 없습니다.' };
    }

    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000); // 5s timeout

            const res = await fetch(`${API_BASE}${endpoint}`, {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (!res.ok) throw new Error(`API error: ${res.status}`);
            _backendDown = false; // Backend is reachable
            return await res.json();
        } catch (err) {
            if (attempt < retries) {
                await new Promise(r => setTimeout(r, 300));
                continue;
            }
            // Mark backend as down to avoid repeated slow failures
            _backendDown = true;
            _backendDownSince = Date.now();
            console.error(`API call failed: ${endpoint}`, err);
            return { error: err.message };
        }
    }
}

// --- Market ---
export async function getIndices() {
    return fetchApi('/api/market/indices');
}

export async function getStocks(count = 30, market = 'ALL') {
    return fetchApi(`/api/market/stocks?count=${count}&market=${market}`);
}

export async function getStockDetail(code) {
    return fetchApi(`/api/market/stock/${code}`);
}

export async function getStockHistory(code, days = 90) {
    return fetchApi(`/api/market/stock/${code}/history?days=${days}`);
}

export async function searchStocksApi(q) {
    return fetchApi(`/api/market/search?q=${encodeURIComponent(q)}`);
}

// --- Technical Analysis ---
export async function getTechnicalIndicators(code, days = 180) {
    return fetchApi(`/api/analysis/${code}?days=${days}`);
}

export async function getTradeSignals(code) {
    return fetchApi(`/api/analysis/${code}/signal`);
}

// Combined: indicators + signals in a single request (faster)
export async function getAllAnalysis(code, days = 180) {
    return fetchApi(`/api/analysis/${code}/all?days=${days}`);
}

// --- Backtesting ---
export async function runBacktest(params) {
    return fetchApi('/api/backtest/run', {
        method: 'POST',
        body: JSON.stringify(params),
    });
}

// --- Factor Analysis ---
export async function getFactorRanking(params = {}) {
    const query = new URLSearchParams({
        count: params.count || 20,
        momentum_w: params.momentum_w || 0.30,
        value_w: params.value_w || 0.25,
        quality_w: params.quality_w || 0.25,
        volatility_w: params.volatility_w || 0.20,
    });
    return fetchApi(`/api/factor/ranking?${query}`);
}

// --- Health Check ---
export async function checkBackendHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
        return res.ok;
    } catch {
        return false;
    }
}
