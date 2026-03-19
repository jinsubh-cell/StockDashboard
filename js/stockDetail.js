// ==========================================
// Stock Detail Page Module
// ==========================================

import { getStockByCode, getOrCreateStock, getRecommendationByCode, formatPrice, formatVolume } from './data.js';
import { createLineChart, createCandlestickChart, destroyAllCharts } from './chart.js';

let currentInterval = 1;
let currentChartType = 'candle';
let isViewAll = false;
let isFullscreen = false;

export function renderStockDetail(code) {
  const container = document.getElementById('page-content');
  const displayStock = getOrCreateStock(code);
  const rec = getRecommendationByCode(code);
  const isUp = displayStock.change >= 0;
  const isInWatchlist = getWatchlist().includes(code);

  container.innerHTML = `
    <div class="stock-detail">
      <button class="back-button" onclick="window.history.back()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
        돌아가기
      </button>

      <div class="stock-detail-header">
        <div class="stock-detail-info">
          <div style="display:flex; align-items:center; gap:12px;">
            <h1 class="stock-detail-name">${displayStock.name}</h1>
            <span class="watchlist-star ${isInWatchlist ? 'active' : ''}" id="watchlist-toggle" data-code="${code}" title="관심 종목">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="${isInWatchlist ? '#ffd700' : 'none'}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </span>
          </div>
          <div class="stock-detail-code">${displayStock.code} · ${displayStock.sector}</div>
        </div>
        <div class="stock-detail-price-wrap">
          <div class="stock-detail-price ${isUp ? 'text-up' : 'text-down'}">${formatPrice(displayStock.price)}원</div>
          <div class="stock-detail-change ${isUp ? 'text-up' : 'text-down'}">
            ${isUp ? '▲' : '▼'} ${formatPrice(Math.abs(displayStock.change))} (${isUp ? '+' : ''}${displayStock.changePercent.toFixed(2)}%)
          </div>
        </div>
      </div>

      <!-- Stats -->
      <div class="detail-stats">
        <div class="stat-item">
          <div class="stat-label">시가</div>
          <div class="stat-value">${formatPrice(displayStock.open)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">고가</div>
          <div class="stat-value text-up">${formatPrice(displayStock.high)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">저가</div>
          <div class="stat-value text-down">${formatPrice(displayStock.low)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">전일 종가</div>
          <div class="stat-value">${formatPrice(displayStock.prevClose)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">거래량</div>
          <div class="stat-value">${formatVolume(displayStock.volume)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">시가총액</div>
          <div class="stat-value">${displayStock.marketCap}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">52주 최고</div>
          <div class="stat-value text-up">${formatPrice(displayStock.high52w)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">52주 최저</div>
          <div class="stat-value text-down">${formatPrice(displayStock.low52w)}</div>
        </div>
      </div>

      <!-- Chart -->
      <div class="detail-chart-section">
        <div class="chart-container">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div class="chart-tabs">
              <button class="chart-tab active" data-interval="1">일봉</button>
              <button class="chart-tab" data-interval="5">주봉</button>
              <button class="chart-tab" data-interval="20">월봉</button>
              <button class="chart-tab" data-interval="40">2개월봉</button>
              <button class="chart-tab" data-interval="80">4개월봉</button>
              <button class="chart-tab" data-interval="120">6개월봉</button>
              <button class="chart-tab" data-interval="240">1년봉</button>
            </div>
            <div class="chart-tabs">
              <button class="view-all-btn" id="view-fullscreen-toggle" style="margin-right: 8px; padding: 6px 12px; font-size: 0.8rem; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">전체화면</button>
              <button class="view-all-btn" id="view-all-toggle" style="margin-right: 8px; padding: 6px 12px; font-size: 0.8rem; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">전체보기</button>
              <button class="chart-type-tab active" data-type="candle" style="padding: 6px 12px; font-size: 0.8rem; border-radius: 6px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">캔들</button>
              <button class="chart-type-tab" data-type="line" style="padding: 6px 12px; font-size: 0.8rem; border-radius: 6px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">라인</button>
            </div>
          </div>
          <style>
              .chart-type-tab.active { background: var(--bg-hover); color: var(--text-primary); font-weight: 500; }
              .view-all-btn.active { background: rgba(108, 92, 231, 0.15); color: var(--accent-primary-light); border-color: var(--accent-primary-light); }
              .chart-fullscreen-mode {
                  position: fixed !important;
                  top: 0 !important;
                  left: 0 !important;
                  width: 100vw !important;
                  height: 100vh !important;
                  z-index: 9999 !important;
                  background: var(--bg-primary) !important;
                  padding: 20px !important;
                  display: flex !important;
                  flex-direction: column !important;
               }
               .chart-fullscreen-mode .chart-wrapper {
                  flex: 1 !important;
                  height: auto !important;
               }
               .ma-legend { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 8px 4px; }
               .ma-legend-item { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--text-secondary); }
               .ma-legend-line { width: 18px; height: 3px; border-radius: 2px; }
          </style>
          <div class="ma-legend" id="ma-legend">
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#ff4757;"></span>5일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#ffa502;"></span>15일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#e84393;"></span>33일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#0984e3;"></span>56일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#00b894; height:4px;"></span>112일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#dfe6e9; height:4px;"></span>224일</span>
            <span class="ma-legend-item"><span class="ma-legend-line" style="background:#636e72; border-top:2px dashed #636e72; height:0;"></span>448일</span>
          </div>
          <div class="chart-wrapper">
            <canvas id="detail-chart"></canvas>
          </div>
        </div>
      </div>

      <!-- Opinion & Company Info -->
      <div class="opinion-section">
        <div class="card opinion-card">
          <h3 class="opinion-title">📊 투자 지표</h3>
          <div class="company-info-list">
            <div class="company-info-row">
              <span class="label">PER</span>
              <span class="value">${displayStock.per}배</span>
            </div>
            <div class="company-info-row">
              <span class="label">PBR</span>
              <span class="value">${displayStock.pbr}배</span>
            </div>
            <div class="company-info-row">
              <span class="label">외국인 보유율</span>
              <span class="value">${displayStock.foreignRate}%</span>
            </div>
            <div class="company-info-row">
              <span class="label">시가총액</span>
              <span class="value">${displayStock.marketCap}</span>
            </div>
          </div>
          ${rec ? `
            <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border-color-light);">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span class="stat-label" style="margin:0;">AI 투자 의견</span>
                <span class="recommend-signal ${rec.signal === 'buy' ? 'signal-buy' : rec.signal === 'sell' ? 'signal-sell' : 'signal-hold'}">
                  ${rec.signal === 'buy' ? '매수' : rec.signal === 'sell' ? '매도' : '관망'}
                </span>
              </div>
              <div class="opinion-meter">
                <span class="meter-label text-up">매수</span>
                <div class="meter-bar">
                  <div class="meter-fill buy" style="width: ${rec.confidence}%"></div>
                </div>
                <span class="meter-label">${rec.confidence}%</span>
              </div>
              <div style="font-size: 0.82rem; color: var(--text-secondary);">
                목표가: <strong class="${rec.targetPrice > displayStock.price ? 'text-up' : 'text-down'}">${formatPrice(rec.targetPrice)}원</strong>
              </div>
            </div>
          ` : ''}
        </div>

        <div class="card opinion-card">
          <h3 class="opinion-title">🏢 기업 정보</h3>
          <p style="font-size: 0.88rem; color: var(--text-secondary); line-height: 1.7; margin-bottom: 16px;">
            ${displayStock.description}
          </p>
          ${rec ? `
            <div style="padding-top: 16px; border-top: 1px solid var(--border-color-light);">
              <h4 style="font-size: 0.88rem; font-weight: 600; margin-bottom: 10px;">💡 AI 분석 요약</h4>
              <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 12px;">${rec.reason}</p>
              <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                ${rec.factors.map(f => `<span class="card-badge badge-${rec.signal === 'buy' ? 'up' : rec.signal === 'sell' ? 'down' : 'neutral'}">${f}</span>`).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      </div>
    </div>
  `;

  // Initialize chart
  setTimeout(() => {
    currentInterval = 1;
    currentChartType = 'candle';
    renderDetailChart(displayStock);
    setupChartTabs(displayStock);
    setupWatchlistToggle();
  }, 100);
}

/**
 * Partial update for real-time price changes on the detail page
 */
export function updateStockDetailDOM(stockData) {
  const priceEl = document.querySelector('.stock-detail-price');
  const changeEl = document.querySelector('.stock-detail-change');
  if (!priceEl || !changeEl) return;

  const isUp = stockData.change >= 0;
  const colorClass = isUp ? 'text-up' : 'text-down';

  priceEl.textContent = `${formatPrice(stockData.close || stockData.price)}원`;
  priceEl.className = `stock-detail-price ${colorClass}`;

  // Update stock name if available
  if (stockData.name) {
    const nameEl = document.querySelector('.stock-detail-name');
    if (nameEl && (nameEl.textContent === '불러오는 중...' || nameEl.textContent === stockData.code)) {
      nameEl.textContent = stockData.name;
    }
  }

  const changePct = stockData.change_pct ?? stockData.changePercent ?? 0;
  changeEl.innerHTML = `
    ${isUp ? '▲' : '▼'} ${formatPrice(Math.abs(stockData.change))} (${isUp ? '+' : ''}${changePct.toFixed(2)}%)
  `;
  changeEl.className = `stock-detail-change ${colorClass}`;

  // Update all stats
  const stats = document.querySelectorAll('.stat-value');
  if (stats.length >= 8) {
    stats[0].textContent = formatPrice(stockData.open || 0);
    stats[1].textContent = formatPrice(stockData.high || 0);
    stats[2].textContent = formatPrice(stockData.low || 0);
    stats[3].textContent = formatPrice(stockData.prev_close || stockData.prevClose || 0);
    stats[4].textContent = formatVolume(stockData.volume || 0);
    if (stockData.market_cap) stats[5].textContent = `${(stockData.market_cap / 1e12).toFixed(1)}조`;
    if (stockData.high_52w) stats[6].textContent = formatPrice(stockData.high_52w);
    if (stockData.low_52w) stats[7].textContent = formatPrice(stockData.low_52w);
  }

  // Update investment indicators (PER, PBR, foreignRate, marketCap)
  const infoRows = document.querySelectorAll('.company-info-row .value');
  if (infoRows.length >= 4) {
    if (stockData.per) infoRows[0].textContent = `${stockData.per}배`;
    if (stockData.pbr) infoRows[1].textContent = `${stockData.pbr}배`;
    const fr = stockData.foreign_rate ?? stockData.foreignRate;
    if (fr !== undefined) infoRows[2].textContent = `${Number(fr).toFixed(1)}%`;
    if (stockData.market_cap) infoRows[3].textContent = `${(stockData.market_cap / 1e12).toFixed(1)}조`;
  }
}

export function renderDetailChart(stock) {
  const allOhlc = stock.ohlcHistory;
  const aggregated = aggregateOHLC(allOhlc, currentInterval);
  // Pass all data to the chart to allow panning back in time
  const displayData = aggregated;

  // Calculate initial view window (6 months by default or all if View All is checked)
  let startIndex = 0;
  if (!isViewAll && displayData.length > 0) {
    const lastDate = new Date(displayData[displayData.length - 1].x);
    const sixMonthsAgo = new Date(lastDate);
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const sixMonthsAgoTime = sixMonthsAgo.getTime();

    // Find the first index where timestamp is >= sixMonthsAgo
    startIndex = displayData.findIndex(d => new Date(d.x).getTime() >= sixMonthsAgoTime);
    if (startIndex === -1) startIndex = 0;
  }
  const displayCount = displayData.length - startIndex;
  const minX = displayData[startIndex]?.x;
  const maxX = displayData[displayData.length - 1]?.x;
  const xLimits = minX && maxX ? { min: minX, max: maxX } : {};

  // Compute indicators based on FULL aggregated series (needed for both chart types)
  const closes = aggregated.map(d => d.c);
  const highs = aggregated.map(d => d.h);
  const lows = aggregated.map(d => d.l);

  if (currentChartType === 'line') {
    const lineData = displayData.map(d => d.c);
    const lineDates = displayData.map(d => {
      const dt = new Date(d.x);
      return `${dt.getMonth() + 1}/${dt.getDate()}`;
    });

    // Compute EMAs for line chart (주식단테 설정: EMA 5,15,33,56,112,224,448)
    const ema5Line = computeEMA(closes, 5);
    const ema15Line = computeEMA(closes, 15);
    const ema33Line = computeEMA(closes, 33);
    const ema56Line = computeEMA(closes, 56);
    const ema112Line = computeEMA(closes, 112);
    const ema224Line = computeEMA(closes, 224);
    const ema448Line = computeEMA(closes, 448);

    const extraDatasets = [
      { label: 'EMA 5', data: ema5Line, borderColor: '#ff4757', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 15', data: ema15Line, borderColor: '#ffa502', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 33', data: ema33Line, borderColor: '#e84393', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 56', data: ema56Line, borderColor: '#0984e3', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 112', data: ema112Line, borderColor: '#00b894', borderWidth: 2.5, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 224', data: ema224Line, borderColor: '#dfe6e9', borderWidth: 2.5, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'EMA 448', data: ema448Line, borderColor: '#636e72', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, tension: 0.3, fill: false },
    ];

    createLineChart('detail-chart', lineDates, lineData, {
      extraDatasets,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          min: lineDates[startIndex],
          max: lineDates[displayData.length - 1]
        }
      }
    });
  } else {
    // Candle chart with indicators

    // Compute EMAs on full aggregated series (주식단테 설정: EMA 5,15,33,56,112,224,448)
    const ema5 = computeEMA(closes, 5);
    const ema15 = computeEMA(closes, 15);
    const ema33 = computeEMA(closes, 33);
    const ema56 = computeEMA(closes, 56);
    const ema112 = computeEMA(closes, 112);
    const ema224 = computeEMA(closes, 224);
    const ema448 = computeEMA(closes, 448);

    // 일목균형표: 선행스펜1, 선행스펜2만 표시 (구름대), 전환선/기준선 숨김
    const tenkan = computeDonchian(highs, lows, 9);
    const kijun = computeDonchian(highs, lows, 26);
    const spanA = tenkan.map((t, i) => t != null && kijun[i] != null ? (t + kijun[i]) / 2 : null);
    const spanB = computeDonchian(highs, lows, 52);

    const shiftedSpanA = new Array(26).fill(null).concat(spanA).slice(0, aggregated.length);
    const shiftedSpanB = new Array(26).fill(null).concat(spanB).slice(0, aggregated.length);

    const extraDatasets = [
      // 일목균형표 구름대 (파란색 통일, 채우기)
      { type: 'line', label: '선행스팬1', data: displayData.map((d, i) => ({ x: d.x, y: shiftedSpanA[i] })), borderColor: 'rgba(52, 152, 219, 0.5)', borderWidth: 1, pointRadius: 0, tension: 0.2, fill: false },
      { type: 'line', label: '선행스팬2', data: displayData.map((d, i) => ({ x: d.x, y: shiftedSpanB[i] })), borderColor: 'rgba(52, 152, 219, 0.5)', borderWidth: 1, pointRadius: 0, tension: 0.2, fill: '-1', backgroundColor: 'rgba(52, 152, 219, 0.08)' },
      // EMA 이동평균선 (주식단테 설정)
      { type: 'line', label: 'EMA 5', data: displayData.map((d, i) => ({ x: d.x, y: ema5[i] })), borderColor: '#ff4757', borderWidth: 1, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 15', data: displayData.map((d, i) => ({ x: d.x, y: ema15[i] })), borderColor: '#ffa502', borderWidth: 1, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 33', data: displayData.map((d, i) => ({ x: d.x, y: ema33[i] })), borderColor: '#e84393', borderWidth: 1, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 56', data: displayData.map((d, i) => ({ x: d.x, y: ema56[i] })), borderColor: '#0984e3', borderWidth: 1, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 112', data: displayData.map((d, i) => ({ x: d.x, y: ema112[i] })), borderColor: '#00b894', borderWidth: 2.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 224', data: displayData.map((d, i) => ({ x: d.x, y: ema224[i] })), borderColor: '#dfe6e9', borderWidth: 2.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'EMA 448', data: displayData.map((d, i) => ({ x: d.x, y: ema448[i] })), borderColor: '#636e72', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, tension: 0.3, hidden: false },
    ];

    createCandlestickChart('detail-chart', displayData, {
      extraDatasets,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          ...xLimits
        }
      }
    });
  }
}

function setupChartTabs(stock) {
  const periodTabs = document.querySelectorAll('.chart-tab');
  periodTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      periodTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentInterval = parseInt(tab.dataset.interval);
      renderDetailChart(stock);
    });
  });

  const typeTabs = document.querySelectorAll('.chart-type-tab');
  typeTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      typeTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentChartType = tab.dataset.type;
      renderDetailChart(stock);
    });
  });

  const viewAllToggle = document.getElementById('view-all-toggle');
  if (viewAllToggle) {
    // Initial state setup if the widget was just rendered but isViewAll is true
    if (isViewAll) {
      viewAllToggle.classList.add('active');
    }
    viewAllToggle.addEventListener('click', () => {
      isViewAll = !isViewAll;
      viewAllToggle.classList.toggle('active', isViewAll);
      renderDetailChart(stock);
    });
  }

  const fullscreenToggle = document.getElementById('view-fullscreen-toggle');
  const chartContainer = document.querySelector('.chart-container');
  if (fullscreenToggle && chartContainer) {
    if (isFullscreen) {
      fullscreenToggle.classList.add('active');
      chartContainer.classList.add('chart-fullscreen-mode');
    }
    fullscreenToggle.addEventListener('click', () => {
      isFullscreen = !isFullscreen;
      fullscreenToggle.classList.toggle('active', isFullscreen);
      chartContainer.classList.toggle('chart-fullscreen-mode', isFullscreen);
      // Trigger resize so chart.js adjusts to the new container size properly
      setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
    });
  }
}

function setupWatchlistToggle() {
  const toggle = document.getElementById('watchlist-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', () => {
    const code = toggle.dataset.code;
    const watchlist = getWatchlist();
    const idx = watchlist.indexOf(code);
    if (idx >= 0) {
      watchlist.splice(idx, 1);
      toggle.classList.remove('active');
      toggle.querySelector('svg').setAttribute('fill', 'none');
    } else {
      watchlist.push(code);
      toggle.classList.add('active');
      toggle.querySelector('svg').setAttribute('fill', '#ffd700');
    }
    localStorage.setItem('watchlist', JSON.stringify(watchlist));
  });
}

function getWatchlist() {
  try {
    return JSON.parse(localStorage.getItem('watchlist') || '[]');
  } catch {
    return [];
  }
}

// Indicator Computing Helpers
function aggregateOHLC(ohlcData, interval) {
  if (interval === 1) return ohlcData;
  const aggregated = [];
  let currentGroup = [];
  for (let i = 0; i < ohlcData.length; i++) {
    currentGroup.push(ohlcData[i]);
    if (currentGroup.length === interval || i === ohlcData.length - 1) {
      aggregated.push({
        x: currentGroup[currentGroup.length - 1].x,
        o: currentGroup[0].o,
        h: Math.max(...currentGroup.map(d => d.h)),
        l: Math.min(...currentGroup.map(d => d.l)),
        c: currentGroup[currentGroup.length - 1].c
      });
      currentGroup = [];
    }
  }
  return aggregated;
}

function computeSMA(data, window) {
  return data.map((_, i) => i < window - 1 ? null : data.slice(i - window + 1, i + 1).reduce((a, b) => a + b) / window);
}

function computeEMA(data, period) {
  const k = 2 / (period + 1);
  const result = new Array(data.length).fill(null);
  // Start EMA from the first SMA value
  let sum = 0;
  for (let i = 0; i < period && i < data.length; i++) {
    sum += data[i];
  }
  if (period <= data.length) {
    result[period - 1] = sum / period;
    for (let i = period; i < data.length; i++) {
      result[i] = data[i] * k + result[i - 1] * (1 - k);
    }
  }
  return result;
}

function computeDonchian(highs, lows, period) {
  const result = highs.map(() => null);
  for (let i = period - 1; i < highs.length; i++) {
    const maxH = Math.max(...highs.slice(i - period + 1, i + 1));
    const minL = Math.min(...lows.slice(i - period + 1, i + 1));
    result[i] = (maxH + minL) / 2;
  }
  return result;
}

export { getWatchlist };
