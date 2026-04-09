// ==========================================
// Backtesting Page
// ==========================================

import { runBacktest, searchStocksApi as apiSearchStocks } from './quantApi.js';
import { stocks, formatPrice, generateDates } from './data.js';
import { destroyAllCharts } from './chart.js';

export function renderBacktestPage() {
    const container = document.getElementById('page-content');

    const today = new Date();
    const oneYearAgo = new Date(today);
    oneYearAgo.setFullYear(today.getFullYear() - 1);

    container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Settings Card -->
      <div class="card">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.5rem;">🧪</span>
          <h2 style="font-size:1.1rem; font-weight:700;">전략 백테스팅</h2>
        </div>
        <div class="bt-form">
          <div class="bt-form-row">
            <div class="bt-form-group">
              <label>종목 검색</label>
              <div id="bt-search-wrapper" class="search-wrapper" style="width: 100%;">
                <span class="search-icon">🔍</span>
                <input type="text" id="bt-search-input" class="search-input" style="width: 100%;" placeholder="종목명 또는 코드 입력" value="삼성전자" autocomplete="off" />
                <input type="hidden" id="bt-stock-code" value="005930" />
                <div id="bt-search-dropdown" class="search-dropdown"></div>
              </div>
            </div>
            <div class="bt-form-group">
              <label>전략</label>
              <select id="bt-strategy" class="ta-select">
                <option value="golden_cross">골든크로스 (SMA)</option>
                <option value="rsi">RSI 과매수/과매도</option>
                <option value="macd">MACD 크로스오버</option>
                <option value="bollinger">볼린저밴드</option>
              </select>
            </div>
            <div class="bt-form-group">
              <label>시작일</label>
              <input type="date" id="bt-start" class="ta-select" value="${oneYearAgo.toISOString().split('T')[0]}" />
            </div>
            <div class="bt-form-group">
              <label>종료일</label>
              <input type="date" id="bt-end" class="ta-select" value="${today.toISOString().split('T')[0]}" />
            </div>
            <div class="bt-form-group">
              <label>초기자본</label>
              <input type="number" id="bt-capital" class="ta-select" value="10000000" step="1000000" />
            </div>
          </div>
          <div class="bt-form-row" id="bt-params-row">
            <div class="bt-form-group">
              <label>단기 MA</label>
              <input type="number" id="bt-short-window" class="ta-select" value="5" min="2" max="50" />
            </div>
            <div class="bt-form-group">
              <label>장기 MA</label>
              <input type="number" id="bt-long-window" class="ta-select" value="20" min="5" max="200" />
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:12px; margin-top:12px;">
            <button class="btn btn-primary btn-icon" id="bt-run-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              백테스트 실행
            </button>
            <span id="bt-status" style="font-size:0.82rem; color:var(--text-tertiary);"></span>
          </div>
        </div>
      </div>

      <!-- Results (hidden initially) -->
      <div id="bt-results" style="display:none;">
        <!-- Performance Metrics -->
        <div class="grid-row cols-4" style="margin-bottom:20px;" id="bt-metrics"></div>

        <!-- Equity Curve -->
        <div class="card" style="margin-bottom:20px;">
          <div class="card-header">
            <span class="card-title">수익률 곡선</span>
          </div>
          <div style="height:350px;"><canvas id="bt-equity-chart"></canvas></div>
        </div>

        <!-- Trade History -->
        <div class="card">
          <div class="card-header">
            <span class="card-title">거래 내역</span>
            <span id="bt-trade-count" class="card-badge badge-neutral"></span>
          </div>
          <div class="stock-table-wrap">
            <table class="stock-table" id="bt-trades-table">
              <thead>
                <tr><th>날짜</th><th>구분</th><th>가격</th><th>수량</th><th>금액</th><th>손익</th></tr>
              </thead>
              <tbody id="bt-trades-body"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;

    document.getElementById('bt-run-btn').addEventListener('click', executeBacktest);
    // Initial load: render params for default strategy
    updateParamsUI();

    // Standardized Stock Search Implementation
    const input = document.getElementById('bt-search-input');
    const dropdown = document.getElementById('bt-search-dropdown');
    const codeInput = document.getElementById('bt-stock-code');
    let searchTimeout = null;

    input.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        if (query.length === 0) {
            dropdown.classList.remove('active');
            return;
        }

        if (searchTimeout) clearTimeout(searchTimeout);

        searchTimeout = setTimeout(async () => {
            try {
                const resultsRes = await apiSearchStocks(query);
                const results = resultsRes.results || [];
                renderSearchDropdown(results);
            } catch (err) {
                console.error('Backtest search failed:', err);
            }
        }, 300);
    });

    function renderSearchDropdown(items) {
        if (!items || items.length === 0) {
            dropdown.innerHTML = `<div class="search-item" style="justify-content: center; color: var(--text-tertiary); cursor: default;">검색 결과가 없습니다</div>`;
        } else {
            dropdown.innerHTML = items.map(stock => {
                const isUp = (stock.change || 0) >= 0;
                return `
          <div class="search-item" data-code="${stock.code}" data-name="${stock.name}">
            <div class="search-item-left">
              <span class="search-item-name">${stock.name}</span>
              <span class="search-item-code">${stock.code}</span>
            </div>
            <div class="search-item-price" style="text-align: right;">
              <div class="price">${formatPrice(stock.price || 0)}</div>
              <div class="change ${isUp ? 'text-up' : 'text-down'}">${isUp ? '+' : ''}${(stock.change_pct || 0).toFixed(2)}%</div>
            </div>
          </div>
        `;
            }).join('');

            dropdown.querySelectorAll('.search-item').forEach(el => {
                el.addEventListener('click', () => {
                    const code = el.dataset.code;
                    const name = el.dataset.name;
                    input.value = name;
                    codeInput.value = code;
                    dropdown.classList.remove('active');
                });
            });
        }
        dropdown.classList.add('active');
    }

    input.addEventListener('focus', () => {
        if (input.value.trim().length > 0) dropdown.classList.add('active');
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#bt-search-wrapper') && dropdown) {
            dropdown.classList.remove('active');
        }
    });
}

function updateParamsUI() {
    const strategy = document.getElementById('bt-strategy').value;
    const row = document.getElementById('bt-params-row');

    const paramConfigs = {
        golden_cross: `
      <div class="bt-form-group"><label>단기 MA</label><input type="number" id="bt-short-window" class="ta-select" value="5" min="2" max="50" /></div>
      <div class="bt-form-group"><label>장기 MA</label><input type="number" id="bt-long-window" class="ta-select" value="20" min="5" max="200" /></div>
    `,
        rsi: `
      <div class="bt-form-group"><label>과매도 기준</label><input type="number" id="bt-rsi-oversold" class="ta-select" value="30" min="10" max="50" /></div>
      <div class="bt-form-group"><label>과매수 기준</label><input type="number" id="bt-rsi-overbought" class="ta-select" value="70" min="50" max="90" /></div>
    `,
        macd: `<div class="bt-form-group"><label>MACD 기본 파라미터</label><span style="font-size:0.82rem;color:var(--text-tertiary);">Fast=12, Slow=26, Signal=9</span></div>`,
        bollinger: `<div class="bt-form-group"><label>볼린저밴드 기본 파라미터</label><span style="font-size:0.82rem;color:var(--text-tertiary);">Period=20, Std=2.0</span></div>`,
    };
    row.innerHTML = paramConfigs[strategy] || '';
}

async function executeBacktest() {
    const status = document.getElementById('bt-status');
    status.textContent = '⏳ 백테스트 실행 중...';

    const params = {
        code: document.getElementById('bt-stock-code').value || '005930',
        strategy: document.getElementById('bt-strategy').value,
        start_date: document.getElementById('bt-start').value,
        end_date: document.getElementById('bt-end').value,
        initial_capital: parseFloat(document.getElementById('bt-capital').value),
        short_window: parseInt(document.getElementById('bt-short-window')?.value || 5),
        long_window: parseInt(document.getElementById('bt-long-window')?.value || 20),
        rsi_oversold: parseInt(document.getElementById('bt-rsi-oversold')?.value || 30),
        rsi_overbought: parseInt(document.getElementById('bt-rsi-overbought')?.value || 70),
    };

    try {
        const result = await runBacktest(params);
        if (result.error) {
            status.textContent = `⚠️ 백엔드 연결 실패 — 모의 백테스트 실행`;
            renderLocalBacktest(params);
            return;
        }
        renderBacktestResults(result);
        status.textContent = `✅ 백테스트 완료 — ${result.strategy}`;
    } catch (err) {
        status.textContent = '⚠️ 백엔드 연결 실패 — 모의 백테스트 실행';
        renderLocalBacktest(params);
    }
}

function renderLocalBacktest(params) {
    const stock = stocks.find(s => s.code === params.code);
    if (!stock) return;

    const n = stock.history.length;
    const dates = generateDates(n);
    const initial = params.initial_capital;

    // Simple mock: random walk performance
    const equityCurve = [initial];
    const benchmarkCurve = [initial];
    const benchmarkStart = stock.history[0] || 1;

    for (let i = 1; i < n; i++) {
        const dailyReturn = (stock.history[i] - stock.history[i - 1]) / stock.history[i - 1];
        equityCurve.push(equityCurve[i - 1] * (1 + dailyReturn * (0.8 + Math.random() * 0.4)));
        benchmarkCurve.push(initial * (stock.history[i] / benchmarkStart));
    }

    const finalValue = equityCurve[equityCurve.length - 1];
    const totalReturn = (finalValue - initial) / initial * 100;

    const trades = [];
    for (let i = 0; i < 8; i++) {
        const idx = Math.floor(Math.random() * (n - 10)) + 5;
        trades.push({
            date: dates[idx], action: i % 2 === 0 ? '매수' : '매도',
            price: stock.history[idx], shares: Math.floor(initial / stock.history[0]),
            value: stock.history[idx] * Math.floor(initial / stock.history[0]),
            pnl: i % 2 === 1 ? Math.floor((Math.random() - 0.3) * 500000) : null,
        });
    }

    const strategyNames = { golden_cross: '골든크로스', rsi: 'RSI 과매수/과매도', macd: 'MACD 크로스오버', bollinger: '볼린저밴드' };

    renderBacktestResults({
        strategy: strategyNames[params.strategy] || params.strategy,
        code: params.code, name: stock.name,
        period: `${params.start_date} ~ ${params.end_date}`,
        initial_capital: initial, final_value: Math.round(finalValue),
        total_return: Math.round(totalReturn * 100) / 100,
        cagr: Math.round(totalReturn / 1 * 100) / 100,
        sharpe_ratio: Math.round((totalReturn / 15) * 100) / 100,
        max_drawdown: Math.round(Math.random() * 20 + 5),
        win_rate: Math.round(50 + Math.random() * 30),
        total_trades: trades.length,
        equity_curve: equityCurve.map(Math.round),
        equity_dates: dates,
        benchmark_curve: benchmarkCurve.map(Math.round),
        trades: trades,
    });
}

function renderBacktestResults(result) {
    destroyAllCharts();
    document.getElementById('bt-results').style.display = 'block';

    const isPositive = result.total_return >= 0;

    // Metrics
    document.getElementById('bt-metrics').innerHTML = `
    <div class="stat-item"><div class="stat-label">총 수익률</div><div class="stat-value ${isPositive ? 'text-up' : 'text-down'}">${isPositive ? '+' : ''}${result.total_return}%</div></div>
    <div class="stat-item"><div class="stat-label">최종 자산</div><div class="stat-value">${formatPrice(result.final_value)}원</div></div>
    <div class="stat-item"><div class="stat-label">샤프 비율</div><div class="stat-value">${result.sharpe_ratio}</div></div>
    <div class="stat-item"><div class="stat-label">최대 낙폭</div><div class="stat-value text-down">-${result.max_drawdown}%</div></div>
    <div class="stat-item"><div class="stat-label">CAGR</div><div class="stat-value">${result.cagr}%</div></div>
    <div class="stat-item"><div class="stat-label">승률</div><div class="stat-value">${result.win_rate}%</div></div>
    <div class="stat-item"><div class="stat-label">총 거래 수</div><div class="stat-value">${result.total_trades}회</div></div>
    <div class="stat-item"><div class="stat-label">전략</div><div class="stat-value" style="font-size:0.9rem;">${result.strategy}</div></div>
  `;

    // Equity Chart
    const canvas = document.getElementById('bt-equity-chart');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        const labels = (result.equity_dates || []).map(d => {
            if (d.includes('-')) { const p = d.split('-'); return `${parseInt(p[1])}/${parseInt(p[2])}`; }
            return d;
        });
        new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: '전략', data: result.equity_curve, borderColor: isPositive ? '#00d26a' : '#ff4757', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true, backgroundColor: isPositive ? 'rgba(0,210,106,0.08)' : 'rgba(255,71,87,0.08)' },
                    { label: '벤치마크(바이앤홀드)', data: result.benchmark_curve, borderColor: '#8b949e', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4, 3] },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: { legend: { display: true, labels: { color: '#5f6876' } }, tooltip: { backgroundColor: 'rgba(255,255,255,0.97)', titleColor: '#1a1d23', bodyColor: '#5f6876', borderColor: 'rgba(0,0,0,0.1)', borderWidth: 1, padding: 10, callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString()}원` } } },
                scales: {
                    x: { grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { color: '#8b95a5', maxRotation: 0, maxTicksLimit: 12 } },
                    y: { grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { color: '#8b95a5', callback: v => (v / 10000).toFixed(0) + '만' } }
                }
            }
        });
    }

    // Trade Table
    document.getElementById('bt-trade-count').textContent = `${result.total_trades}건`;
    const tbody = document.getElementById('bt-trades-body');
    tbody.innerHTML = (result.trades || []).map(t => `
    <tr>
      <td>${t.date}</td>
      <td><span class="recommend-signal ${t.action === '매수' ? 'signal-buy' : 'signal-sell'}">${t.action}</span></td>
      <td style="font-weight:600;">${formatPrice(t.price)}</td>
      <td>${t.shares?.toLocaleString()}</td>
      <td>${formatPrice(Math.round(t.value))}</td>
      <td class="${t.pnl && t.pnl > 0 ? 'text-up' : t.pnl && t.pnl < 0 ? 'text-down' : ''}" style="font-weight:600;">
        ${t.pnl != null ? (t.pnl > 0 ? '+' : '') + formatPrice(Math.round(t.pnl)) : '-'}
      </td>
    </tr>
  `).join('');
}
