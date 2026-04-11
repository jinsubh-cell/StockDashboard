// ==========================================
// Quant API Client Module
// Communicates with the FastAPI backend
// ==========================================

// Auto-detect backend URL: same host, port 8000
const API_BASE = window.location.port === '8000' ? '' : `http://${window.location.hostname}:8000`;

let _backendDown = false;
let _backendDownSince = 0;
const _BACKEND_COOLDOWN = 10000; // 10s cooldown before retrying a down backend

async function fetchApi(endpoint, options = {}, retries = 1) {
    // If backend was recently detected as down, fail fast
    if (_backendDown && (Date.now() - _backendDownSince) < _BACKEND_COOLDOWN) {
        return { error: '백엔드 서버에 연결할 수 없습니다.' };
    }

    // Longer timeout for endpoints that wait for WS connection
    const isLongOp = endpoint.includes('/start') || endpoint.includes('/stop') || endpoint.includes('/scan');
    const timeoutMs = isLongOp ? 20000 : 5000;

    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

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
            // Only mark backend as down for network errors, not timeouts on long ops
            if (!isLongOp) {
                _backendDown = true;
                _backendDownSince = Date.now();
            }
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

// --- Trading ---
export async function getTradingStatus() {
    return fetchApi('/api/trading/status');
}

export async function loginKiwoom() {
    return fetchApi('/api/trading/login', { method: 'POST' });
}

export async function logoutKiwoom() {
    return fetchApi('/api/trading/logout', { method: 'POST' });
}

export async function getAccountSummary() {
    return fetchApi('/api/trading/account-summary');
}

export async function placeOrder(params) {
    return fetchApi('/api/trading/order', {
        method: 'POST',
        body: JSON.stringify(params),
    });
}

export async function modifyOrder(params) {
    return fetchApi('/api/trading/order/modify', {
        method: 'POST',
        body: JSON.stringify(params),
    });
}

export async function cancelOrder(params) {
    return fetchApi('/api/trading/order/cancel', {
        method: 'POST',
        body: JSON.stringify(params),
    });
}

export async function getAccountBalance() {
    return fetchApi('/api/trading/balance');
}

export async function getOrderHistory() {
    return fetchApi('/api/trading/orders');
}

export async function getRealtimePrice(code) {
    return fetchApi(`/api/trading/realtime/${code}`);
}

// --- Scalping ---
export async function getScalpingStatus() {
    return fetchApi('/api/scalping/status');
}

export async function startScalping(codes) {
    // Reset backend-down flag for explicit user action
    _backendDown = false;
    return fetchApi('/api/scalping/start', {
        method: 'POST',
        body: JSON.stringify({ codes }),
    });
}

export async function stopScalping() {
    _backendDown = false;
    return fetchApi('/api/scalping/stop', { method: 'POST' });
}

export async function getScalpingConfig() {
    return fetchApi('/api/scalping/config');
}

export async function updateScalpingConfig(config) {
    return fetchApi('/api/scalping/config', {
        method: 'POST',
        body: JSON.stringify({ config }),
    });
}

export async function getScalpingSignals() {
    return fetchApi('/api/scalping/signals');
}

export async function getScalpingTrades() {
    return fetchApi('/api/scalping/trades');
}

export async function scanScalpingPicks(force = false) {
    return fetchApi(`/api/scalping/picker/scan?force=${force}`);
}

export async function getPickerConfig() {
    return fetchApi('/api/scalping/picker/config');
}

export async function updatePickerConfig(config) {
    return fetchApi('/api/scalping/picker/config', {
        method: 'POST',
        body: JSON.stringify({ config }),
    });
}

// --- Auto Scalping (완전 자동 매매) ---
export async function getAutoScalpingStatus() {
    return fetchApi('/api/auto-scalping/status');
}

export async function startAutoScalping() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/start', { method: 'POST' });
}

export async function stopAutoScalping() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/stop', { method: 'POST' });
}

export async function getAutoScalpingConfig() {
    return fetchApi('/api/auto-scalping/config');
}

export async function updateAutoScalpingConfig(config) {
    return fetchApi('/api/auto-scalping/config', {
        method: 'POST',
        body: JSON.stringify({ config }),
    });
}

export async function forceAutoScan() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/scan', { method: 'POST' });
}

// --- AI Supervisor (감독관) ---
export async function getAIStatus() {
    return fetchApi('/api/auto-scalping/ai-status');
}
export async function runDailyReview() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/ai-review/daily', { method: 'POST' });
}
export async function runWeeklyReview() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/ai-review/weekly', { method: 'POST' });
}
export async function applyLatestReview() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/ai-review/apply-latest', { method: 'POST' });
}
export async function getReviewHistory(limit = 20) {
    return fetchApi(`/api/auto-scalping/ai-review/history?limit=${limit}`);
}

// --- Skill Presets (스킬 프리셋) ---
export async function getPresets() {
    return fetchApi('/api/auto-scalping/presets');
}
export async function getPreset(name) {
    return fetchApi(`/api/auto-scalping/presets/${name}`);
}
export async function activatePreset(name) {
    _backendDown = false;
    return fetchApi(`/api/auto-scalping/presets/${name}/activate`, { method: 'POST' });
}
export async function clonePreset(name) {
    _backendDown = false;
    return fetchApi(`/api/auto-scalping/presets/${name}/clone`, { method: 'POST' });
}
export async function deletePresetApi(name) {
    _backendDown = false;
    return fetchApi(`/api/auto-scalping/presets/${name}`, { method: 'DELETE' });
}
export async function optimizePreset(name) {
    _backendDown = false;
    return fetchApi(`/api/auto-scalping/presets/${name}/optimize`, { method: 'POST' });
}
export async function toggleAutoSwitch() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/presets/auto-switch/toggle', { method: 'POST' });
}
export async function resetAll() {
    _backendDown = false;
    return fetchApi('/api/auto-scalping/reset-all', { method: 'POST' });
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
