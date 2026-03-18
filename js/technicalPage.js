// ==========================================
// Technical Analysis Page
// ==========================================

import { getTechnicalIndicators, getTradeSignals, getAllAnalysis, searchStocksApi as apiSearchStocks } from './quantApi.js';
import { stocks, formatPrice } from './data.js';
import { createLineChart, createCandlestickChart, createBarChart, destroyAllCharts } from './chart.js';

let currentCode = '005930'; // Default: Samsung

export function renderTechnicalPage() {
  const container = document.getElementById('page-content');

  container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Stock Selector -->
      <div class="card">
        <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size: 1.5rem;">📊</span>
            <h2 style="font-size: 1.1rem; font-weight: 700;">기술적 분석</h2>
          </div>
          <div class="search-wrapper" id="ta-search-wrapper">
             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="search-icon"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
             <input type="text" class="search-input" id="ta-search-input" placeholder="종목을 검색하여 분석하기..." autocomplete="off">
             <div class="search-dropdown" id="ta-search-dropdown"></div>
          </div>
          <select id="ta-period-select" class="ta-select">
            <option value="90">3개월</option>
            <option value="180" selected>6개월</option>
            <option value="365">1년</option>
          </select>
          <div id="ta-status" style="font-size: 0.82rem; color: var(--text-tertiary);"></div>
        </div>
      </div>

      <!-- Signals Summary -->
      <div id="ta-signals" class="card" style="display:none;">
        <div class="card-header">
          <span class="card-title">🎯 종합 매매 신호</span>
          <span id="ta-overall-badge" class="card-badge"></span>
        </div>
        <div id="ta-signals-grid" class="ta-signals-grid"></div>
      </div>

      <!-- Price + MA Chart -->
      <div class="card">
        <div class="card-header" style="flex-direction: column; align-items: flex-start;">
          <span class="card-title">가격 & 이동평균 (일목균형표)</span>
          <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px; font-weight: normal;">
            <span style="color: #ff4757;">■ SMA 5</span> · <span style="color: #ffa502;">■ SMA 20</span> · <span style="color: #00d26a;">■ SMA 60</span> · <span style="color: #0984e3;">■ SMA 120</span>
          </div>
        </div>
        <div style="height: 350px;"><canvas id="ta-price-chart"></canvas></div>
      </div>

      <!-- RSI + MACD Charts -->
      <div class="grid-row cols-2">
        <div class="card">
          <div class="card-header" style="flex-direction: column; align-items: flex-start;">
            <span class="card-title">RSI (14)</span>
            <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px; font-weight: normal;">
              상대강도지수: <span style="color: #ff4757;">70 이상 과매수 (매도 검토)</span> / <span style="color: #0984e3;">30 이하 과매도 (매수 검토)</span>
            </div>
          </div>
          <div style="height: 200px;"><canvas id="ta-rsi-chart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header" style="flex-direction: column; align-items: flex-start;">
            <span class="card-title">MACD (12, 26, 9)</span>
            <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px; font-weight: normal;">
              <span style="color: #ff4757;">■ MACD선 (단기-장기 추세)</span> · <span style="color: #0984e3;">■ 시그널선</span> · 막대(히스토그램) 방향 전환 시점(0선 교차) 주목
            </div>
          </div>
          <div style="height: 200px;"><canvas id="ta-macd-chart"></canvas></div>
        </div>
      </div>

      <!-- Bollinger + Volume -->
      <div class="grid-row cols-2">
        <div class="card">
          <div class="card-header" style="flex-direction: column; align-items: flex-start;">
            <span class="card-title">볼린저밴드 (20, 2σ)</span>
            <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px; font-weight: normal;">
              주가 변동성: <span style="color: #ff4757;">상단선(저항)</span> · <span style="color: #ffa502;">중심선(20일선)</span> · <span style="color: #0984e3;">하단선(지지)</span>
            </div>
          </div>
          <div style="height: 250px;"><canvas id="ta-bollinger-chart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header" style="flex-direction: column; align-items: flex-start;">
            <span class="card-title">거래량</span>
            <div style="font-size: 0.8rem; color: #8b949e; margin-top: 4px; font-weight: normal;">
              <span style="color: #ff4757;">■ 전일비 상승 (매수 우위)</span> · <span style="color: #0984e3;">■ 전일비 하락 (매도 우위)</span>
            </div>
          </div>
          <div style="height: 250px;"><canvas id="ta-volume-chart"></canvas></div>
        </div>
      </div>
    </div>
  `;

  document.getElementById('ta-period-select').addEventListener('change', loadTechnical);

  // Search bar logic
  const input = document.getElementById('ta-search-input');
  const dropdown = document.getElementById('ta-search-dropdown');

  let searchTimeout = null;

  input.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    if (query.length === 0) {
      dropdown.classList.remove('active');
      return;
    }

    // Debounce search requests (300ms)
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    searchTimeout = setTimeout(async () => {
      try {
        const resultsRes = await apiSearchStocks(query);
        const results = resultsRes.results || [];
        if (results.length === 0) {
          dropdown.innerHTML = `<div class="search-item" style="justify-content: center; color: var(--text-tertiary); cursor: default;">검색 결과가 없습니다</div>`;
        } else {
          dropdown.innerHTML = results.map(stock => {
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
        }
        dropdown.classList.add('active');
      } catch (err) {
        console.error('TA Search failed:', err);
      }
    }, 300);
  });

  input.addEventListener('focus', () => {
    if (input.value.trim().length > 0) dropdown.classList.add('active');
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#ta-search-wrapper') && dropdown) {
      dropdown.classList.remove('active');
    }
  });

  dropdown.addEventListener('click', (e) => {
    const item = e.target.closest('.search-item');
    if (item && item.dataset.code) {
      currentCode = item.dataset.code;
      input.value = item.dataset.name; // Keep name in input box
      dropdown.classList.remove('active');
      loadTechnical();
    }
  });

  // Auto-load with mock data first
  loadTechnicalFromMock();
}

async function loadTechnical() {
  if (window.showLoading) window.showLoading();
  const status = document.getElementById('ta-status');
  status.textContent = '데이터 로딩 중...';

  const code = currentCode;
  const days = document.getElementById('ta-period-select').value;
  const displayDays = parseInt(days);

  try {
    // Fetch extra buffer days so SMA 120 has enough warm-up data
    // SMA 120 needs 120 prior days, add 130 as safety buffer
    const fetchDays = displayDays + 130;
    const result = await getAllAnalysis(code, fetchDays);

    if (result.error || !result.indicators || !result.signals) {
      status.textContent = `⚠️ 오류: ${result.error || '데이터 형식이 올바르지 않습니다.'}`;
      console.error('TA API Error:', result.error);
      loadTechnicalFromMock();
      return;
    }

    renderIndicatorCharts(result.indicators, displayDays);
    renderSignals(result.signals);
    status.textContent = `✅ ${result.signals.name || code} 분석 완료`;
  } catch (err) {
    console.error('Technical analysis load failed:', err);
    status.textContent = '⚠️ 백엔드 연결 실패 - 모의 데이터를 표시합니다.';
    loadTechnicalFromMock();
  } finally {
    if (window.hideLoading) window.hideLoading();
  }
}

function loadTechnicalFromMock() {
  const stock = stocks.find(s => s.code === currentCode) || stocks[0];
  if (!stock) return;

  const n = stock.history.length;
  const dates = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
  }

  const closes = stock.history;
  const opens = stock.ohlcHistory ? stock.ohlcHistory.map(o => o.o) : closes.map(c => c * 0.99);
  const highs = stock.ohlcHistory ? stock.ohlcHistory.map(o => o.h) : closes.map(c => c * 1.02);
  const lows = stock.ohlcHistory ? stock.ohlcHistory.map(o => o.l) : closes.map(c => c * 0.98);

  // Compute basic indicators from mock data
  const sma5 = computeSMA(closes, 5);
  const sma20 = computeSMA(closes, 20);
  const sma60 = computeSMA(closes, 60);
  const sma120 = computeSMA(closes, 120);
  const sma224 = computeSMA(closes, 224);
  const sma448 = computeSMA(closes, 448);
  const rsi = computeRSI(closes, 14);
  const bb = computeBollinger(closes, 20, 2);

  // Basic Mock Ichimoku calculation
  const tenkan = computeDonchian(highs, lows, 9);
  const kijun = computeDonchian(highs, lows, 26);
  const spanA = tenkan.map((t, i) => t != null && kijun[i] != null ? (t + kijun[i]) / 2 : null);
  const spanB = computeDonchian(highs, lows, 52);

  // Shift Senkou spans by 26 days to the future (for rendering we align to current for simplicity or you can pad dates)
  const shiftedSpanA = new Array(26).fill(null).concat(spanA).slice(0, closes.length);
  const shiftedSpanB = new Array(26).fill(null).concat(spanB).slice(0, closes.length);

  // Create OHLC objects array
  const ohlcData = [];
  const nowTime = new Date();
  for (let i = 0; i < closes.length; i++) {
    const d = new Date(nowTime);
    d.setDate(d.getDate() - (closes.length - 1 - i));
    d.setHours(0, 0, 0, 0);
    ohlcData.push({
      x: d.getTime(),
      o: opens[i],
      h: highs[i],
      l: lows[i],
      c: closes[i]
    });
  }

  const indicators = {
    dates, closes, ohlcData,
    sma_5: sma5, sma_20: sma20, sma_60: sma60,
    sma_120: sma120, sma_224: sma224, sma_448: sma448,
    ichimoku_tenkan: tenkan,
    ichimoku_kijun: kijun,
    ichimoku_span_a: shiftedSpanA,
    ichimoku_span_b: shiftedSpanB,
    rsi_14: rsi,
    macd: computeMACD(closes).macd,
    macd_signal: computeMACD(closes).signal,
    macd_hist: computeMACD(closes).hist,
    bb_upper: bb.upper, bb_middle: bb.middle, bb_lower: bb.lower,
    volumes: closes.map(() => Math.floor(Math.random() * 5000000 + 1000000)),
    obv: closes.map((_, i) => i * 100000 + Math.random() * 50000),
  };

  renderIndicatorCharts(indicators);

  // Mock signals
  const lastRsi = rsi[rsi.length - 1];
  document.getElementById('ta-signals').style.display = 'block';
  document.getElementById('ta-overall-badge').className = 'card-badge badge-up';
  document.getElementById('ta-overall-badge').textContent = '종합: 매수';
  document.getElementById('ta-signals-grid').innerHTML = generateMockSignals(stock);
  document.getElementById('ta-status').textContent = `📌 ${stock.name} — 로컬 모의 데이터`;
}

function renderIndicatorCharts(data, displayDays) {
  try {
    destroyAllCharts();
    if (!data || !data.dates || data.dates.length === 0) {
      console.warn('No data available for charts');
      return;
    }
  const dates = data.dates || [];
  const closes = data.closes || [];

  // Normalize OHLC data for Candlestick chart if not already present
  if (!data.ohlcData && data.opens && data.highs && data.lows) {
    data.ohlcData = data.closes.map((c, i) => {
      const d = new Date(data.dates[i]);
      d.setHours(0, 0, 0, 0);
      return {
        x: d.getTime(),
        o: data.opens[i],
        h: data.highs[i],
        l: data.lows[i],
        c: data.closes[i]
      };
    });
  }

  // Price + MA — slice all data to the display period so charts use only valid data
  const priceCanvas = document.getElementById('ta-price-chart');
  if (priceCanvas && data.ohlcData) {
    // ── Step 1: Guarantee chronological order ──────────────────────────────
    // Naver fchart can return newest-first. Sort by timestamp ascending so
    // all downstream logic (SMA warm-up, startIndex) is always correct.
    const rawOhlc = data.ohlcData;
    const isChronological = rawOhlc.length < 2 ||
      rawOhlc[rawOhlc.length - 1].x >= rawOhlc[0].x;

    let allOhlc, allCloses;
    if (isChronological) {
      allOhlc   = rawOhlc;
      allCloses = data.closes ? [...data.closes] : rawOhlc.map(d => d.c);
    } else {
      // Sort ascending by timestamp and reorder closes in lockstep
      const idx = rawOhlc.map((_, i) => i).sort((a, b) => rawOhlc[a].x - rawOhlc[b].x);
      allOhlc   = idx.map(i => rawOhlc[i]);
      allCloses = data.closes
        ? idx.map(i => data.closes[i])
        : allOhlc.map(d => d.c);
    }

    // ── Step 2: Compute SMA locally from sorted closes (sliding-window O(n)) ─
    // This bypasses any backend cache / ordering issues entirely.
    const smaLocal = (arr, period) => {
      const out = new Array(arr.length).fill(null);
      let sum = 0;
      for (let i = 0; i < arr.length; i++) {
        sum += arr[i];
        if (i >= period) sum -= arr[i - period];
        if (i >= period - 1) out[i] = sum / period;
      }
      return out;
    };
    const lSma5   = smaLocal(allCloses, 5);
    const lSma20  = smaLocal(allCloses, 20);
    const lSma60  = smaLocal(allCloses, 60);
    const lSma120 = smaLocal(allCloses, 120);
    const lSma224 = smaLocal(allCloses, 224);
    const lSma448 = smaLocal(allCloses, 448);

    // ── Step 3: Find the start index for the display window ────────────────
    let startIndex = 0;
    if (allOhlc.length > 0 && displayDays) {
      const lastDate = new Date(allOhlc[allOhlc.length - 1].x);
      const displayStart = new Date(lastDate);
      displayStart.setDate(displayStart.getDate() - displayDays);
      const displayStartTime = displayStart.getTime();
      startIndex = allOhlc.findIndex(d => d.x >= displayStartTime);
      if (startIndex === -1) startIndex = 0;
    }

    // ── Step 4: Slice everything to the visible window ────────────────────
    // Derive dates from sorted allOhlc so sub-charts always get correct order
    const sl  = (arr) => Array.isArray(arr) ? arr.slice(startIndex) : [];
    const visibleOhlc   = allOhlc.slice(startIndex);
    const visibleCloses = allCloses.slice(startIndex);
    const visibleDates  = visibleOhlc.map(d => {
      const dt = new Date(d.x);
      return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
    });

    const extraDatasets = [
      { type: 'line', label: '선행스팬1', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(data.ichimoku_span_a)[i] ?? null })), borderColor: 'rgba(0, 210, 106, 0.4)', borderWidth: 1, pointRadius: 0, tension: 0.2, fill: false },
      { type: 'line', label: '선행스팬2', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(data.ichimoku_span_b)[i] ?? null })), borderColor: 'rgba(255, 71, 87, 0.4)', borderWidth: 1, pointRadius: 0, tension: 0.2, fill: '-1', backgroundColor: 'rgba(108, 92, 231, 0.1)' },
      { type: 'line', label: '전환선', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(data.ichimoku_tenkan)[i] ?? null })), borderColor: '#00cec9', borderWidth: 1.5, pointRadius: 0, tension: 0.2, hidden: true },
      { type: 'line', label: '기준선', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(data.ichimoku_kijun)[i] ?? null })), borderColor: '#e17055', borderWidth: 1.5, pointRadius: 0, tension: 0.2, hidden: true },
      { type: 'line', label: 'SMA 5',   data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma5)[i]   })), borderColor: '#ff4757', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'SMA 20',  data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma20)[i]  })), borderColor: '#ffa502', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'SMA 60',  data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma60)[i]  })), borderColor: '#00d26a', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'SMA 120', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma120)[i] })), borderColor: '#0984e3', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: false },
      { type: 'line', label: 'SMA 224', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma224)[i] })), borderColor: '#6c5ce7', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: true },
      { type: 'line', label: 'SMA 448', data: visibleOhlc.map((d, i) => ({ x: d.x, y: sl(lSma448)[i] })), borderColor: '#b2bec3', borderWidth: 1.5, pointRadius: 0, tension: 0.3, hidden: true },
    ];

    createCandlestickChart('ta-price-chart', visibleOhlc, {
      extraDatasets,
      plugins: { legend: { display: false } }
    });

    const subChartOpts = (title) => ({
      ...chartOptions(title),
      plugins: {
        ...chartOptions(title).plugins,
        zoom: {
          pan: { enabled: true, mode: 'x' },
          zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x' }
        }
      }
    });

    // RSI
    const rsiCanvas = document.getElementById('ta-rsi-chart');
    if (rsiCanvas && data.rsi_14) {
      const opts = subChartOpts('RSI');
      createLineChart('ta-rsi-chart', visibleDates, sl(data.rsi_14), {
        ...opts,
        borderColor: '#a29bfe',
        plugins: {
          ...opts.plugins,
          annotation: {
            annotations: {
              overbought: { type: 'line', yMin: 70, yMax: 70, borderColor: '#ff4757', borderWidth: 1, borderDash: [4, 4] },
              oversold: { type: 'line', yMin: 30, yMax: 30, borderColor: '#0984e3', borderWidth: 1, borderDash: [4, 4] },
            }
          }
        },
        scales: { ...opts.scales, y: { ...opts.scales.y, min: 0, max: 100 } }
      });
    }

    // MACD
    const macdCanvas = document.getElementById('ta-macd-chart');
    if (macdCanvas && data.macd) {
      const opts = subChartOpts('MACD');
      const slMacd = sl(data.macd);
      createLineChart('ta-macd-chart', visibleDates, slMacd, {
        ...opts,
        datasets: [
          { label: 'MACD', data: slMacd, borderColor: '#ff4757', borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
          { label: 'Signal', data: sl(data.macd_signal), borderColor: '#0984e3', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4, 3] },
          {
            label: 'Histogram', data: sl(data.macd_hist), type: 'bar',
            backgroundColor: sl(data.macd_hist).map(v => v != null && v >= 0 ? 'rgba(255,71,87,0.4)' : 'rgba(9,132,227,0.4)'),
          },
        ]
      });
    }

    // Bollinger
    const bbCanvas = document.getElementById('ta-bollinger-chart');
    if (bbCanvas && data.bb_upper) {
      const opts = subChartOpts('볼린저');
      createLineChart('ta-bollinger-chart', visibleDates, visibleCloses, {
        ...opts,
        datasets: [
          { label: '상단', data: sl(data.bb_upper), borderColor: 'rgba(255,71,87,0.5)', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: false },
          { label: '종가', data: visibleCloses, borderColor: '#e6edf3', borderWidth: 2, pointRadius: 0, tension: 0.2 },
          { label: '중간', data: sl(data.bb_middle), borderColor: '#ffa502', borderWidth: 1, pointRadius: 0, tension: 0.3, borderDash: [4, 3] },
          { label: '하단', data: sl(data.bb_lower), borderColor: 'rgba(9,132,227,0.5)', borderWidth: 1, pointRadius: 0, tension: 0.3, fill: '-3', backgroundColor: 'rgba(108,92,231,0.05)' },
        ]
      });
    }

    // Volume
    const volCanvas = document.getElementById('ta-volume-chart');
    if (volCanvas && data.volumes) {
      const slVols = sl(data.volumes);
      createBarChart('ta-volume-chart', visibleDates, slVols,
        visibleCloses.map((c, i) => i > 0 && c >= visibleCloses[i - 1] ? 'rgba(255,71,87,0.4)' : 'rgba(9,132,227,0.4)')
      );
    }
  }
} catch (err) {
  console.error('Error rendering technical charts:', err);
}
}

function renderSignals(data) {
  const container = document.getElementById('ta-signals');
  const badge = document.getElementById('ta-overall-badge');
  const grid = document.getElementById('ta-signals-grid');
  container.style.display = 'block';

  const sig = data.overall_signal;
  badge.className = `card-badge badge-${sig === 'buy' ? 'up' : sig === 'sell' ? 'down' : 'neutral'}`;
  badge.textContent = `종합: ${sig === 'buy' ? '매수' : sig === 'sell' ? '매도' : '중립'} (매수 ${data.buy_count} / 매도 ${data.sell_count} / 중립 ${data.neutral_count})`;

  grid.innerHTML = (data.signals || []).map(s => `
    <div class="ta-signal-card ${s.signal}">
      <div class="ta-signal-header">
        <span class="ta-signal-name">${s.indicator}</span>
        <span class="recommend-signal ${s.signal === 'buy' ? 'signal-buy' : s.signal === 'sell' ? 'signal-sell' : 'signal-hold'}">
          ${s.signal === 'buy' ? '매수' : s.signal === 'sell' ? '매도' : '중립'}
        </span>
      </div>
      <div class="ta-signal-value">${s.value}</div>
      <div class="ta-signal-desc">${s.description}</div>
    </div>
  `).join('');
}

function generateMockSignals(stock) {
  const signals = [
    { indicator: '이동평균 배열', signal: stock.changePercent > 0 ? 'buy' : 'sell', value: stock.price, description: `SMA5 ${stock.changePercent > 0 ? '>' : '<'} SMA20` },
    { indicator: 'RSI (14)', signal: 'neutral', value: 52, description: 'RSI 52로 중립 구간' },
    { indicator: 'MACD', signal: stock.changePercent > 1 ? 'buy' : 'neutral', value: 0, description: 'MACD 히스토그램 양전환' },
    { indicator: '볼린저밴드', signal: 'neutral', value: stock.price, description: '밴드 중간 구간에서 거래 중' },
    { indicator: '스토캐스틱', signal: stock.changePercent > 2 ? 'buy' : 'neutral', value: 45, description: '%K=45, 중립' },
    { indicator: 'CCI (20)', signal: 'neutral', value: 15, description: 'CCI=15, 중립' },
  ];
  return signals.map(s => `
    <div class="ta-signal-card ${s.signal}">
      <div class="ta-signal-header">
        <span class="ta-signal-name">${s.indicator}</span>
        <span class="recommend-signal ${s.signal === 'buy' ? 'signal-buy' : s.signal === 'sell' ? 'signal-sell' : 'signal-hold'}">
          ${s.signal === 'buy' ? '매수' : s.signal === 'sell' ? '매도' : '중립'}
        </span>
      </div>
      <div class="ta-signal-value">${typeof s.value === 'number' && s.value > 1000 ? formatPrice(s.value) : s.value}</div>
      <div class="ta-signal-desc">${s.description}</div>
    </div>
  `).join('');
}

function chartOptions(title) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: 'rgba(22,27,34,0.95)', titleColor: '#e6edf3', bodyColor: '#8b949e', borderColor: 'rgba(48,54,61,0.8)', borderWidth: 1, padding: 10, cornerRadius: 6 }
    },
    scales: {
      x: { grid: { color: 'rgba(48,54,61,0.3)' }, ticks: { color: '#6e7681', font: { size: 10 }, maxRotation: 0, maxTicksLimit: 12 } },
      y: { grid: { color: 'rgba(48,54,61,0.3)' }, ticks: { color: '#6e7681', font: { size: 10 }, callback: v => v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v } }
    }
  };
}

// Mock indicator computations for local mode
function computeSMA(data, window) {
  return data.map((_, i) => i < window - 1 ? null : data.slice(i - window + 1, i + 1).reduce((a, b) => a + b) / window);
}

function computeRSI(data, period) {
  const result = data.map(() => null);
  for (let i = period; i < data.length; i++) {
    let gains = 0, losses = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = data[j] - data[j - 1];
      if (diff > 0) gains += diff; else losses -= diff;
    }
    const rs = losses === 0 ? 100 : gains / losses;
    result[i] = 100 - 100 / (1 + rs);
  }
  return result;
}

function computeMACD(data) {
  const ema12 = computeEMA(data, 12);
  const ema26 = computeEMA(data, 26);
  const macd = data.map((_, i) => ema12[i] != null && ema26[i] != null ? ema12[i] - ema26[i] : null);
  const signal = computeEMA(macd.map(v => v || 0), 9);
  const hist = macd.map((m, i) => m != null && signal[i] != null ? m - signal[i] : null);
  return { macd, signal, hist };
}

function computeEMA(data, period) {
  const result = data.map(() => null);
  const mult = 2 / (period + 1);
  let start = -1;
  for (let i = 0; i < data.length; i++) { if (data[i] != null) { start = i; break; } }
  if (start < 0 || start + period > data.length) return result;
  result[start + period - 1] = data.slice(start, start + period).reduce((a, b) => a + b) / period;
  for (let i = start + period; i < data.length; i++) result[i] = (data[i] - result[i - 1]) * mult + result[i - 1];
  return result;
}

function computeBollinger(data, window, numStd) {
  const middle = computeSMA(data, window);
  const upper = [], lower = [];
  for (let i = 0; i < data.length; i++) {
    if (middle[i] == null) { upper.push(null); lower.push(null); continue; }
    const slice = data.slice(Math.max(0, i - window + 1), i + 1);
    const std = Math.sqrt(slice.reduce((sum, v) => sum + (v - middle[i]) ** 2, 0) / slice.length);
    upper.push(middle[i] + numStd * std);
    lower.push(middle[i] - numStd * std);
  }
  return { upper, middle, lower };
}

function computeDonchian(highs, lows, period) {
  const result = highs.map(() => null);
  for (let i = period - 1; i < highs.length; i++) {
    const hSlice = highs.slice(i - period + 1, i + 1);
    const lSlice = lows.slice(i - period + 1, i + 1);
    const maxH = Math.max(...hSlice);
    const minL = Math.min(...lSlice);
    result[i] = (maxH + minL) / 2;
  }
  return result;
}
