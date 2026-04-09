// ==========================================
// App Router & Navigation
// ==========================================

import { renderDashboard } from './dashboard.js';
import { renderStockDetail, getWatchlist, renderDetailChart } from './stockDetail.js';
import { initSearch } from './search.js';
import { destroyAllCharts } from './chart.js';
import { recommendations, getStockByCode, getOrCreateStock, formatPrice, stocks, getTopByVolume, formatVolume, generateDates, marketIndices, sectorPerformance } from './data.js';
import { createLineChart, createBarChart, createMiniSparkline } from './chart.js';
import { renderTechnicalPage } from './technicalPage.js';
import { renderBacktestPage } from './backtestPage.js';
import { renderFactorPage } from './factorPage.js';
import { renderScreenerPage } from './screenerPage.js';
import { renderTradingPage } from './tradingPage.js';
import { renderScalpingPage } from './scalpingPage.js';
import { getIndices, getStocks, getStockDetail, getStockHistory, searchStocksApi, loginKiwoom, logoutKiwoom, getAccountSummary } from './quantApi.js';
import { updateStockDetailDOM } from './stockDetail.js';

let pollingInterval = null;

// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
  initSearch();
  initNavigation();
  initMenuToggle();
  updateTime();
  setInterval(updateTime, 1000);
  handleRoute();

  // Manual refresh button binding
  const refreshBtn = document.getElementById('refresh-data-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      const originalText = refreshBtn.innerHTML;
      refreshBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" class="spin" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3"/></svg> 갱신 중...`;
      refreshBtn.disabled = true;
      const success = await pollMarketData(true);
      if (success) {
        setTimeout(() => {
          refreshBtn.innerHTML = originalText;
          refreshBtn.disabled = false;
        }, 500);
      } else {
        refreshBtn.innerHTML = `⚠️ 연결 실패`;
        setTimeout(() => {
          refreshBtn.innerHTML = originalText;
          refreshBtn.disabled = false;
        }, 2000);
      }
    });
  }

  // Initialize account panel
  initAccountPanel();

  // Start polling
  startPolling();
});

window.addEventListener('hashchange', () => {
  handleRoute();
  startPolling();
});

// --- Account Panel ---
let _accountRefreshTimer = null;

function initAccountPanel() {
  const loginBtn = document.getElementById('account-login-btn');
  const statusEl = document.getElementById('account-status');
  const dropdown = document.getElementById('account-dropdown');
  const refreshBtn = document.getElementById('dd-refresh-btn');
  const logoutBtn = document.getElementById('dd-logout-btn');

  // Toggle dropdown on status click
  statusEl.addEventListener('click', () => {
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
  });

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#account-panel')) {
      dropdown.style.display = 'none';
    }
  });

  // Login button
  loginBtn.addEventListener('click', async () => {
    const btnText = document.getElementById('account-btn-text');
    const isLoggedIn = loginBtn.dataset.loggedIn === 'true';

    if (isLoggedIn) {
      // Toggle dropdown instead
      dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
      return;
    }

    btnText.textContent = '연결 중...';
    loginBtn.disabled = true;

    const result = await loginKiwoom();
    loginBtn.disabled = false;

    if (result.success) {
      refreshAccountPanel();
    } else {
      btnText.textContent = '로그인';
      // Show error inline instead of blocking alert
      const label = document.getElementById('account-label');
      label.textContent = result.message || '연결 실패';
      label.style.color = '#ef4444';
      setTimeout(() => { label.style.color = ''; refreshAccountPanel(); }, 3000);
    }
  });

  // Refresh button in dropdown
  refreshBtn.addEventListener('click', () => {
    refreshAccountPanel();
  });

  // Logout button
  logoutBtn.addEventListener('click', async () => {
    await logoutKiwoom();
    dropdown.style.display = 'none';
    updateAccountUI({
      logged_in: false,
      simulation: false,
      ws_connected: false,
      has_keys: true,
      balance: null,
    });
  });

  // Initial fetch — auto-login if keys are available but not logged in
  refreshAccountPanel().then(async () => {
    const status = await getAccountSummary();
    if (status && !status.error && status.has_keys && !status.logged_in) {
      // Auto-login attempt
      const result = await loginKiwoom();
      if (result.success) {
        refreshAccountPanel();
      }
    }
  });

  // Auto-refresh every 30s (more frequent for real-time trading)
  _accountRefreshTimer = setInterval(refreshAccountPanel, 30000);
}

async function refreshAccountPanel() {
  const data = await getAccountSummary();
  if (!data.error) {
    updateAccountUI(data);
  }
}

function updateAccountUI(data) {
  const dot = document.getElementById('account-dot');
  const label = document.getElementById('account-label');
  const loginBtn = document.getElementById('account-login-btn');
  const btnText = document.getElementById('account-btn-text');
  const balanceMini = document.getElementById('account-balance-mini');
  const cashDisplay = document.getElementById('account-cash-display');

  // Dropdown elements
  const ddTitle = document.getElementById('dropdown-title');
  const ddMode = document.getElementById('dropdown-mode');
  const ddCash = document.getElementById('dd-cash');
  const ddEval = document.getElementById('dd-eval');
  const ddPnl = document.getElementById('dd-pnl');
  const ddPnlPct = document.getElementById('dd-pnl-pct');
  const ddHoldings = document.getElementById('dd-holdings');
  const ddWsDot = document.getElementById('dd-ws-dot');
  const ddWsLabel = document.getElementById('dd-ws-label');

  if (data.logged_in) {
    // Online state
    const isSim = data.simulation;
    dot.className = 'account-status-dot ' + (isSim ? 'simulation' : 'online');
    label.textContent = isSim ? '모의투자' : '실거래';
    loginBtn.dataset.loggedIn = 'true';
    loginBtn.classList.add('logged-in');
    btnText.textContent = '계좌';

    // Mode badge in dropdown
    ddMode.textContent = isSim ? '모의투자' : '실거래';
    ddMode.className = 'account-dropdown-mode ' + (isSim ? 'sim' : 'live');

    // Balance
    if (data.balance) {
      balanceMini.style.display = '';
      cashDisplay.textContent = formatPrice(data.balance.cash) + '원';

      ddCash.textContent = formatPrice(data.balance.cash) + '원';
      ddEval.textContent = formatPrice(data.balance.total_eval) + '원';

      const pnlColor = data.balance.total_pnl >= 0 ? '#00b894' : '#ef4444';
      const pnlSign = data.balance.total_pnl >= 0 ? '+' : '';
      ddPnl.innerHTML = `<span style="color:${pnlColor}">${pnlSign}${formatPrice(data.balance.total_pnl)}원</span>`;
      ddPnlPct.innerHTML = `<span style="color:${pnlColor}">${pnlSign}${data.balance.total_pnl_pct}%</span>`;
      ddHoldings.textContent = data.balance.holding_count + '종목';
    } else {
      balanceMini.style.display = 'none';
      if (data.balance_error) {
        ddCash.innerHTML = `<span style="color:#ef4444; font-size:0.85em;">${data.balance_error}</span>`;
      } else {
        ddCash.textContent = '조회 중...';
      }
      ddEval.textContent = '-';
      ddPnl.textContent = '-';
      ddPnlPct.textContent = '-';
      ddHoldings.textContent = '-';
    }

    // WebSocket status
    ddWsDot.className = 'account-ws-dot' + (data.ws_connected ? ' connected' : '');
    ddWsLabel.textContent = data.ws_connected ? 'WS 연결됨' : 'WS 미연결';

  } else {
    // Offline state
    dot.className = 'account-status-dot offline';
    label.textContent = data.has_keys ? '미연결' : 'API키 없음';
    loginBtn.dataset.loggedIn = 'false';
    loginBtn.classList.remove('logged-in');
    btnText.textContent = '로그인';
    balanceMini.style.display = 'none';

    ddMode.textContent = '';
    ddMode.className = 'account-dropdown-mode';
    ddCash.textContent = '-';
    ddEval.textContent = '-';
    ddPnl.textContent = '-';
    ddPnlPct.textContent = '-';
    ddHoldings.textContent = '-';
    ddWsDot.className = 'account-ws-dot';
    ddWsLabel.textContent = 'WS 미연결';
  }
}

// --- Routing ---
function handleRoute() {
  const hash = window.location.hash || '#/';
  destroyAllCharts();

  if (hash.startsWith('#/stock/')) {
    const code = hash.replace('#/stock/', '');
    let stock = getOrCreateStock(code);
    setPageTitle(stock?.name || '종목 상세');
    setActiveNav(null);
    renderStockDetail(code);
    // Trigger immediate refresh for this stock
    refreshStockDetail(code);
  } else if (hash === '#/recommend') {
    setPageTitle('AI 추천');
    setActiveNav('nav-recommend');
    renderRecommendPage();
  } else if (hash === '#/market') {
    setPageTitle('시장 현황');
    setActiveNav('nav-market');
    renderMarketPage();
  } else if (hash === '#/ta') {
    setPageTitle('기술적 분석');
    setActiveNav('nav-ta');
    renderTechnicalPage();
  } else if (hash === '#/backtest') {
    setPageTitle('전략 백테스팅');
    setActiveNav('nav-backtest');
    renderBacktestPage();
  } else if (hash === '#/factor') {
    setPageTitle('멀티팩터 분석');
    setActiveNav('nav-factor');
    renderFactorPage();
  } else if (hash === '#/screener') {
    setPageTitle('AI 조건검색');
    setActiveNav('nav-screener');
    renderScreenerPage();
  } else if (hash === '#/trading') {
    setPageTitle('주식 거래');
    setActiveNav('nav-trading');
    renderTradingPage();
  } else if (hash === '#/scalping') {
    setPageTitle('초단타 스캘핑');
    setActiveNav('nav-scalping');
    renderScalpingPage();
  } else if (hash === '#/watchlist') {
    setPageTitle('관심 종목');
    setActiveNav('nav-watchlist');
    renderWatchlistPage();
  } else {
    setPageTitle('대시보드');
    setActiveNav('nav-dashboard');
    renderDashboard();
  }

  // Close mobile sidebar
  document.getElementById('sidebar')?.classList.remove('open');
}

// --- Navigation ---
function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.getElementById('sidebar')?.classList.remove('open');
    });
  });
}

function initMenuToggle() {
  const toggle = document.getElementById('menu-toggle');
  const sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }
}

function setPageTitle(title) {
  const el = document.getElementById('page-title');
  if (el) el.textContent = title;
}

function setActiveNav(id) {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  if (id) {
    document.getElementById(id)?.classList.add('active');
  }
}

function updateTime() {
  const el = document.getElementById('header-time');
  if (!el) return;
  const now = new Date();
  const timeStr = now.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  el.textContent = timeStr;
}

// --- Loading Overlay ---
function showLoading() {
  const loader = document.getElementById('global-loader');
  if (loader) loader.style.display = 'flex';
}
window.showLoading = showLoading;

function hideLoading() {
  const loader = document.getElementById('global-loader');
  if (loader) loader.style.display = 'none';
}
window.hideLoading = hideLoading;

// --- Data Fetch Logic ---
function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval);

  // Fetch data on every navigation to keep prices updated
  pollMarketData(false);
}

// Explicit refresh for detail page — parallel fetch detail + history
async function refreshStockDetail(code) {
  try {
    const [detail, history] = await Promise.all([
      getStockDetail(code),
      getStockHistory(code, 365)
    ]);

    if (detail && !detail.error) {
      // Sync API detail into local stock object so re-renders use fresh data
      updateStocksDOM([{
        code: detail.code || code,
        name: detail.name,
        close: detail.close || detail.price,
        change: detail.change,
        change_pct: detail.change_pct ?? detail.changePercent,
        volume: detail.volume,
        market_cap: detail.market_cap,
        open: detail.open,
        high: detail.high,
        low: detail.low,
        prev_close: detail.prev_close,
        high_52w: detail.high_52w,
        low_52w: detail.low_52w,
        per: detail.per,
        pbr: detail.pbr,
        foreign_rate: detail.foreign_rate,
      }]);
      updateStockDetailDOM(detail);
    }

    // Convert API history to ohlcHistory format and update chart
    if (history && !history.error && history.dates && history.dates.length > 0) {
      const ohlc = history.dates.map((dateStr, i) => ({
        x: new Date(dateStr).valueOf(),
        o: history.opens[i],
        h: history.highs[i],
        l: history.lows[i],
        c: history.closes[i]
      }));

      // Update local stock data with real OHLC history
      let existing = stocks.find(s => s.code === code);
      if (!existing) {
        existing = {
          code: code,
          name: detail?.name || code,
          sector: '-',
          history: history.closes,
          ohlcHistory: ohlc
        };
        stocks.push(existing);
      } else {
        existing.ohlcHistory = ohlc;
        existing.history = history.closes;
      }

      // Re-render chart with real OHLC data
      const chartCanvas = document.getElementById('detail-chart');
      if (chartCanvas) {
        destroyAllCharts();
        renderDetailChart(existing);
      }
    }
  } catch (e) {
    console.error('Immediate detail refresh failed:', e);
  }
}

function updateStocksDOM(stocksData) {
  // Sync backend data into local stocks array
  stocksData.forEach(s => {
    let existing = stocks.find(ls => ls.code === s.code);
    if (!existing) {
      existing = {
        code: s.code,
        name: s.name,
        sector: s.market || '코스피/코스닥',
        marketCap: s.market_cap ? `${(s.market_cap / 1000000000000).toFixed(1)}조` : '-',
        history: [],
        ohlcHistory: []
      };
      stocks.push(existing);
    }
    existing.price = s.close;
    existing.change = s.change;
    existing.changePercent = s.change_pct;
    existing.volume = s.volume;
    if (s.open) existing.open = s.open;
    if (s.high) existing.high = s.high;
    if (s.low) existing.low = s.low;
    if (s.prev_close) existing.prevClose = s.prev_close;
    if (s.high_52w) existing.high52w = s.high_52w;
    if (s.low_52w) existing.low52w = s.low_52w;
    if (s.per) existing.per = s.per;
    if (s.pbr) existing.pbr = s.pbr;
    if (s.foreign_rate !== undefined) existing.foreignRate = s.foreign_rate;
    if (s.market_cap) {
      existing.marketCap = `${(s.market_cap / 1000000000000).toFixed(1)}조`;
    }
    if (s.name) existing.name = s.name;
  });
}

async function pollMarketData(showSpinner = false) {
  const hash = window.location.hash || '#/';
  let success = false;

  if (showSpinner) showLoading();

  // Only fetch on relevant pages
  if (hash === '#/' || hash === '#/market' || hash === '#/recommend') {
    try {
      const [indicesRes, stocksRes] = await Promise.all([
        getIndices(),
        getStocks(60)
      ]);

      const hasIndices = indicesRes && indicesRes.indices && !indicesRes.error;
      const hasStocks = stocksRes && stocksRes.stocks && !stocksRes.error;

      if (hasIndices) {
        updateIndicesDOM(indicesRes.indices);
      }

      if (hasStocks) {
        updateStocksDOM(stocksRes.stocks);
      }

      success = hasIndices || hasStocks;

      // For recommend page: fetch prices for KOSDAQ recommendation stocks not in top 60
      if (hash === '#/recommend') {
        const missingCodes = recommendations
          .filter(r => !getStockByCode(r.code))
          .map(r => r.code);
        if (missingCodes.length > 0) {
          const details = await Promise.all(
            missingCodes.map(code => getStockDetail(code).catch(() => null))
          );
          details.forEach(d => {
            if (d && !d.error && d.code) {
              updateStocksDOM([{
                code: d.code,
                name: d.name,
                close: d.close,
                change: d.change,
                change_pct: d.change_pct,
                volume: d.volume,
                market_cap: d.market_cap
              }]);
            }
          });
        }
      }

      // Re-check current hash before rendering (prevent race condition with navigation)
      const currentHash = window.location.hash || '#/';
      if (currentHash === '#/') {
        renderDashboard();
      } else if (currentHash === '#/market') {
        renderMarketPage();
      } else if (currentHash === '#/recommend') {
        renderRecommendPage();
      }
    } catch (e) {
      console.error('Data fetch failed:', e);
      // Re-check current hash — don't overwrite if user navigated away
      const currentHash = window.location.hash || '#/';
      if (currentHash === '#/') renderDashboard();
      else if (currentHash === '#/market') renderMarketPage();
      else if (currentHash === '#/recommend') renderRecommendPage();
    }
  } else if (hash.startsWith('#/stock/')) {
    const code = hash.replace('#/stock/', '');
    try {
      const detail = await getStockDetail(code);
      if (detail && !detail.error) {
        updateStockDetailDOM(detail);
        success = true;
      }
    } catch (e) {
      console.error('Detail fetch failed:', e);
    }
  }

  hideLoading();
  return success;
}

function updateIndicesDOM(indices) {
  indices.forEach(idx => {
    const local = marketIndices.find(m => m.name === idx.name);
    if (local) {
      local.value = idx.value;
      local.change = idx.change;
      local.changePercent = idx.change_pct;
    }
  });
}

// --- Recommend Page ---
function renderRecommendPage() {
  const container = document.getElementById('page-content');
  
  const kospiRecs = recommendations.filter(r => r.market === 'KOSPI');
  const kosdaqRecs = recommendations.filter(r => r.market === 'KOSDAQ');

  container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <div class="card" style="margin-bottom: 20px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size: 1.5rem;">🤖</span>
          <div>
            <h2 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 2px;">AI 종목 분석 리포트</h2>
            <p style="font-size: 0.85rem; color: var(--text-secondary);">
              기술적 분석, 재무 지표, 시장 트렌드를 종합하여 도출한 마켓별 TOP 20 투자 의견입니다.
            </p>
          </div>
        </div>
      </div>

      <!-- KOSPI Section -->
      <div class="market-section" style="margin-bottom: 30px;">
        <div class="section-title"><span class="dot" style="background: var(--color-up);"></span> 코스피 AI 추천 (TOP 20)</div>
        <div class="recommend-page-grid">
          ${kospiRecs.map(rec => renderFullRecommendCard(rec)).join('')}
        </div>
      </div>

      <!-- KOSDAQ Section -->
      <div class="market-section">
        <div class="section-title"><span class="dot" style="background: var(--color-primary);"></span> 코스닥 AI 추천 (TOP 20)</div>
        <div class="recommend-page-grid">
          ${kosdaqRecs.map(rec => renderFullRecommendCard(rec)).join('')}
        </div>
      </div>
    </div>
  `;
}

function renderFullRecommendCard(rec) {
  const stock = getStockByCode(rec.code);
  const name = rec.name || (stock ? stock.name : rec.code);
  const price = (stock && stock.price) ? stock.price : (rec.price || 0);
  const changePct = (stock && stock.changePercent !== undefined) ? stock.changePercent : (rec.changePct || 0);
  const sector = rec.sector || (stock ? stock.sector : (rec.market || '-'));
  
  const isUp = changePct >= 0;
  const signalClass = rec.signal === 'buy' ? 'signal-buy' : rec.signal === 'sell' ? 'signal-sell' : 'signal-hold';
  const signalText = rec.signal === 'buy' ? '강력 매수' : rec.signal === 'sell' ? '매도' : '관망';
  
  return `
    <div class="card recommend-full-card ${rec.signal}" onclick="window.location.hash='#/stock/${rec.code}'" style="cursor:pointer;">
      <div class="recommend-header">
        <div class="recommend-stock-info">
          <span class="recommend-stock-name">${name}</span>
          <span class="recommend-stock-code">${rec.code} · ${sector}</span>
        </div>
        <span class="recommend-signal ${signalClass}">${signalText}</span>
      </div>
      <div class="recommend-price-row">
        <span class="recommend-price">${formatPrice(price)}</span>
        <span class="recommend-change ${isUp ? 'text-up' : 'text-down'}">${isUp ? '+' : ''}${changePct.toFixed(2)}%</span>
      </div>
      <div class="recommend-target">
        <span class="recommend-target-label">목표가</span>
        <span class="recommend-target-value ${rec.targetPrice > price ? 'text-up' : 'text-down'}">${formatPrice(rec.targetPrice)}원</span>
      </div>
      <p class="recommend-reason" style="-webkit-line-clamp:3;">${rec.reason}</p>
      <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:10px;">
        ${rec.factors.map(f => `<span class="card-badge badge-${rec.signal === 'buy' ? 'up' : rec.signal === 'sell' ? 'down' : 'neutral'}">${f}</span>`).join('')}
      </div>
      <div class="recommend-score">
        <span style="font-size:0.78rem; color:var(--text-tertiary);">신뢰도</span>
        <div class="score-bar">
          <div class="score-fill" style="width: ${rec.confidence}%"></div>
        </div>
        <span class="score-label">${rec.confidence}%</span>
      </div>
    </div>
  `;
}

// --- Market Page ---
function renderMarketPage() {
  const container = document.getElementById('page-content');

  container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Market Indices -->
      <div class="market-section">
        <div class="section-title"><span class="dot"></span> 주요 지수</div>
        <div class="grid-row cols-4">
          ${marketIndices.map((idx, i) => {
    const isUp = idx.change >= 0;
    return `
              <div class="card index-card ${isUp ? 'up' : 'down'} fade-in stagger-${i + 1}">
                <div class="card-title" style="margin-bottom:8px;">${idx.name}</div>
                <div class="index-value">${idx.value.toLocaleString('ko-KR', { minimumFractionDigits: 2 })}</div>
                <div class="index-change">
                  <span class="arrow">${isUp ? '▲' : '▼'}</span>
                  <span>${Math.abs(idx.change).toFixed(2)}</span>
                  <span>(${isUp ? '+' : ''}${idx.changePercent.toFixed(2)}%)</span>
                </div>
                <div class="mini-chart"><canvas id="market-mini-${idx.id}" width="120" height="50"></canvas></div>
              </div>
            `;
  }).join('')}
        </div>
      </div>

      <!-- Sector Performance -->
      <div class="market-section">
        <div class="section-title"><span class="dot"></span> 업종별 등락률</div>
        <div class="card">
          <div style="height: 300px;">
            <canvas id="market-sector-chart"></canvas>
          </div>
        </div>
      </div>

      <!-- All Stocks Table -->
      <div class="market-section">
        <div class="section-title"><span class="dot"></span> 전체 종목</div>
        <div class="card">
          <div class="stock-table-wrap">
            <table class="stock-table">
              <thead>
                <tr>
                  <th>종목명</th>
                  <th>현재가</th>
                  <th>전일 대비</th>
                  <th>등락률</th>
                  <th>거래량</th>
                  <th>시가총액</th>
                </tr>
              </thead>
              <tbody>
                ${stocks.map(stock => {
    const isUp = stock.change >= 0;
    return `
                    <tr onclick="window.location.hash='#/stock/${stock.code}'">
                      <td><div class="stock-name-cell"><span class="name">${stock.name}</span><span class="code">${stock.code} · ${stock.sector}</span></div></td>
                      <td style="font-weight:600;">${formatPrice(stock.price)}</td>
                      <td class="${isUp ? 'text-up' : 'text-down'}">${isUp ? '▲' : '▼'} ${formatPrice(Math.abs(stock.change))}</td>
                      <td class="${isUp ? 'text-up' : 'text-down'}" style="font-weight:600;">${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%</td>
                      <td style="color:var(--text-secondary);">${formatVolume(stock.volume)}</td>
                      <td style="font-weight:600;">${stock.marketCap}</td>
                    </tr>
                  `;
  }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;

  setTimeout(() => {
    marketIndices.forEach(idx => {
      createMiniSparkline(`market-mini-${idx.id}`, idx.history.slice(-15));
    });
    createBarChart(
      'market-sector-chart',
      sectorPerformance.map(s => s.name),
      sectorPerformance.map(s => s.change),
      sectorPerformance.map(s => s.color)
    );
  }, 100);
}

// --- Watchlist Page ---
function renderWatchlistPage() {
  const container = document.getElementById('page-content');
  const watchlist = getWatchlist();

  if (watchlist.length === 0) {
    container.innerHTML = `
      <div class="watchlist-empty fade-in">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        <h3>관심 종목이 없습니다</h3>
        <p style="margin-bottom: 20px;">종목 상세 페이지에서 ⭐ 버튼을 눌러 관심 종목을 추가하세요.</p>
        <button class="btn btn-primary" onclick="window.location.hash='#/'">종목 둘러보기</button>
      </div>
    `;
    return;
  }

  const watchlistStocks = watchlist.map(code => getStockByCode(code)).filter(Boolean);

  container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <div class="card">
        <div class="card-header">
          <span class="card-title">⭐ 내 관심 종목 (${watchlistStocks.length})</span>
        </div>
        <div class="stock-table-wrap">
          <table class="stock-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>현재가</th>
                <th>전일 대비</th>
                <th>등락률</th>
                <th>거래량</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${watchlistStocks.map(stock => {
    const isUp = stock.change >= 0;
    return `
                  <tr>
                    <td style="cursor:pointer;" onclick="window.location.hash='#/stock/${stock.code}'">
                      <div class="stock-name-cell"><span class="name">${stock.name}</span><span class="code">${stock.code} · ${stock.sector}</span></div>
                    </td>
                    <td style="font-weight:600; cursor:pointer;" onclick="window.location.hash='#/stock/${stock.code}'">${formatPrice(stock.price)}</td>
                    <td class="${isUp ? 'text-up' : 'text-down'}">${isUp ? '▲' : '▼'} ${formatPrice(Math.abs(stock.change))}</td>
                    <td class="${isUp ? 'text-up' : 'text-down'}" style="font-weight:600;">${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%</td>
                    <td style="color:var(--text-secondary);">${formatVolume(stock.volume)}</td>
                    <td>
                      <span class="watchlist-star active" onclick="removeFromWatchlist('${stock.code}')" style="cursor:pointer;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="#ffd700" stroke="#ffd700" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                      </span>
                    </td>
                  </tr>
                `;
  }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

// Global function for watchlist removal
window.removeFromWatchlist = function (code) {
  const watchlist = getWatchlist();
  const idx = watchlist.indexOf(code);
  if (idx >= 0) {
    watchlist.splice(idx, 1);
    localStorage.setItem('watchlist', JSON.stringify(watchlist));
    renderWatchlistPage();
  }
};
