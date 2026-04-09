// ==========================================
// Trading Page - 주식 주문 & 잔고 관리
// ==========================================

import {
    getTradingStatus, placeOrder, cancelOrder,
    getAccountBalance, getOrderHistory, searchStocksApi as apiSearchStocks,
    getStockDetail, getRealtimePrice,
} from './quantApi.js';
import { formatPrice } from './data.js';

let _balanceRefreshTimer = null;
let _priceRefreshTimer = null;

export function renderTradingPage() {
    const container = document.getElementById('page-content');

    container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Trading Status Banner -->
      <div class="card" id="trading-status-card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:1.5rem;">&#x1F4B9;</span>
          <h2 style="font-size:1.1rem; font-weight:700;">주식 거래</h2>
          <span id="trading-status-badge" class="badge" style="margin-left:auto; padding:4px 12px; border-radius:20px; font-size:0.8rem;">
            확인 중...
          </span>
        </div>
      </div>

      <!-- Order Form -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F4DD;</span>
          <h3 style="font-size:1rem; font-weight:700;">주문</h3>
        </div>
        <div class="bt-form">
          <div class="bt-form-row">
            <div class="bt-form-group">
              <label>종목 검색</label>
              <div id="trade-search-wrapper" class="search-wrapper" style="width:100%;">
                <span class="search-icon">&#x1F50D;</span>
                <input type="text" id="trade-search-input" class="search-input" style="width:100%;" placeholder="종목명 또는 코드 입력" autocomplete="off" />
                <input type="hidden" id="trade-stock-code" value="" />
                <div id="trade-search-dropdown" class="search-dropdown"></div>
              </div>
            </div>
            <div class="bt-form-group">
              <label>현재가</label>
              <div id="trade-current-price" style="font-size:1.1rem; font-weight:700; padding:8px 0; color:var(--text-primary);">-</div>
            </div>
            <div class="bt-form-group">
              <label>매매구분</label>
              <div style="display:flex; gap:8px;">
                <button id="btn-buy-type" class="btn trade-type-btn active-buy" data-type="buy" style="flex:1; padding:8px 0; font-weight:700; border-radius:8px; border:none; cursor:pointer;">매수</button>
                <button id="btn-sell-type" class="btn trade-type-btn" data-type="sell" style="flex:1; padding:8px 0; font-weight:700; border-radius:8px; border:none; cursor:pointer; background:var(--bg-tertiary); color:var(--text-secondary);">매도</button>
              </div>
            </div>
          </div>
          <div class="bt-form-row">
            <div class="bt-form-group">
              <label>주문유형</label>
              <select id="trade-price-type" class="ta-select">
                <option value="limit">지정가</option>
                <option value="market">시장가</option>
              </select>
            </div>
            <div class="bt-form-group" id="trade-price-group">
              <label>주문가격</label>
              <input type="number" id="trade-price" class="ta-select" value="0" min="0" step="1" />
            </div>
            <div class="bt-form-group">
              <label>주문수량</label>
              <input type="number" id="trade-quantity" class="ta-select" value="1" min="1" step="1" />
            </div>
            <div class="bt-form-group">
              <label>주문금액</label>
              <div id="trade-total-amount" style="font-size:1rem; font-weight:600; padding:8px 0; color:var(--text-primary);">0원</div>
            </div>
            <div class="bt-form-group" style="display:flex; align-items:flex-end;">
              <button id="trade-submit-btn" class="btn btn-primary" style="width:100%; padding:10px 0; font-weight:700; font-size:1rem;">
                매수 주문
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Account Balance -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F4BC;</span>
          <h3 style="font-size:1rem; font-weight:700;">계좌 잔고</h3>
          <button id="refresh-balance-btn" class="btn btn-outline" style="margin-left:auto; font-size:0.8rem; padding:4px 12px;">
            새로고침
          </button>
        </div>
        <div id="balance-summary" style="display:flex; gap:20px; flex-wrap:wrap; margin-bottom:16px;">
          <div class="stat-box"><div class="stat-label">예수금</div><div class="stat-value" id="bal-cash">-</div></div>
          <div class="stat-box"><div class="stat-label">총평가</div><div class="stat-value" id="bal-total-eval">-</div></div>
          <div class="stat-box"><div class="stat-label">총매입</div><div class="stat-value" id="bal-total-purchase">-</div></div>
          <div class="stat-box"><div class="stat-label">총손익</div><div class="stat-value" id="bal-total-pnl">-</div></div>
          <div class="stat-box"><div class="stat-label">손익률</div><div class="stat-value" id="bal-total-pnl-pct">-</div></div>
        </div>
        <div style="overflow-x:auto;">
          <table class="data-table" id="holdings-table">
            <thead>
              <tr>
                <th>종목코드</th><th>종목명</th><th>보유수량</th><th>평균매입가</th>
                <th>현재가</th><th>평가금액</th><th>손익</th><th>손익률</th>
              </tr>
            </thead>
            <tbody id="holdings-body">
              <tr><td colspan="8" style="text-align:center; padding:20px; color:var(--text-secondary);">잔고를 조회하려면 새로고침을 클릭하세요</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Order History -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F4CB;</span>
          <h3 style="font-size:1rem; font-weight:700;">주문 내역</h3>
          <button id="refresh-orders-btn" class="btn btn-outline" style="margin-left:auto; font-size:0.8rem; padding:4px 12px;">
            새로고침
          </button>
        </div>
        <div style="overflow-x:auto;">
          <table class="data-table" id="orders-table">
            <thead>
              <tr>
                <th>주문번호</th><th>종목명</th><th>매매</th><th>주문수량</th>
                <th>주문가</th><th>체결수량</th><th>체결가</th><th>상태</th><th>시간</th><th>취소</th>
              </tr>
            </thead>
            <tbody id="orders-body">
              <tr><td colspan="10" style="text-align:center; padding:20px; color:var(--text-secondary);">주문 내역을 조회하려면 새로고침을 클릭하세요</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

    initTradingEvents();
    checkTradingStatus();
}

function initTradingEvents() {
    // Order type toggle (buy / sell)
    let orderType = 'buy';
    const btnBuy = document.getElementById('btn-buy-type');
    const btnSell = document.getElementById('btn-sell-type');
    const submitBtn = document.getElementById('trade-submit-btn');

    function setOrderType(type) {
        orderType = type;
        if (type === 'buy') {
            btnBuy.classList.add('active-buy');
            btnBuy.style.background = '';
            btnBuy.style.color = '';
            btnSell.classList.remove('active-sell');
            btnSell.style.background = 'var(--bg-tertiary)';
            btnSell.style.color = 'var(--text-secondary)';
            submitBtn.textContent = '매수 주문';
            submitBtn.style.background = 'var(--accent-primary)';
        } else {
            btnSell.classList.add('active-sell');
            btnSell.style.background = '';
            btnSell.style.color = '';
            btnBuy.classList.remove('active-buy');
            btnBuy.style.background = 'var(--bg-tertiary)';
            btnBuy.style.color = 'var(--text-secondary)';
            submitBtn.textContent = '매도 주문';
            submitBtn.style.background = '#ef4444';
        }
    }

    btnBuy.addEventListener('click', () => setOrderType('buy'));
    btnSell.addEventListener('click', () => setOrderType('sell'));

    // Price type change (show/hide price input for market orders)
    const priceTypeSelect = document.getElementById('trade-price-type');
    const priceGroup = document.getElementById('trade-price-group');
    priceTypeSelect.addEventListener('change', () => {
        if (priceTypeSelect.value === 'market') {
            priceGroup.style.opacity = '0.4';
            document.getElementById('trade-price').disabled = true;
        } else {
            priceGroup.style.opacity = '1';
            document.getElementById('trade-price').disabled = false;
        }
        updateTotalAmount();
    });

    // Update total amount on price/qty change
    document.getElementById('trade-price').addEventListener('input', updateTotalAmount);
    document.getElementById('trade-quantity').addEventListener('input', updateTotalAmount);

    // Stock search
    initTradeSearch();

    // Submit order
    submitBtn.addEventListener('click', async () => {
        const code = document.getElementById('trade-stock-code').value;
        if (!code) { alert('종목을 선택해 주세요.'); return; }

        const priceType = priceTypeSelect.value;
        const price = priceType === 'market' ? 0 : parseInt(document.getElementById('trade-price').value) || 0;
        const quantity = parseInt(document.getElementById('trade-quantity').value) || 0;

        if (quantity <= 0) { alert('주문 수량을 입력해 주세요.'); return; }
        if (priceType === 'limit' && price <= 0) { alert('주문 가격을 입력해 주세요.'); return; }

        const stockName = document.getElementById('trade-search-input').value;
        const typeLabel = orderType === 'buy' ? '매수' : '매도';
        const confirmed = confirm(
            `${stockName} (${code})\n${typeLabel} ${quantity}주 @ ${priceType === 'market' ? '시장가' : formatPrice(price)}\n\n주문을 진행하시겠습니까?`
        );
        if (!confirmed) return;

        submitBtn.disabled = true;
        submitBtn.textContent = '주문 중...';

        const result = await placeOrder({
            code,
            order_type: orderType,
            quantity,
            price,
            price_type: priceType,
        });

        if (result.success) {
            alert(`주문 완료: ${result.message}\n주문번호: ${result.order_no || '-'}`);
            refreshOrders();
            refreshBalance();
        } else {
            alert(`주문 실패: ${result.message || result.error || '알 수 없는 오류'}`);
        }

        submitBtn.disabled = false;
        submitBtn.textContent = `${typeLabel} 주문`;
    });

    // Refresh buttons
    document.getElementById('refresh-balance-btn').addEventListener('click', refreshBalance);
    document.getElementById('refresh-orders-btn').addEventListener('click', refreshOrders);
}

function updateTotalAmount() {
    const priceType = document.getElementById('trade-price-type').value;
    const price = priceType === 'market' ? 0 : (parseInt(document.getElementById('trade-price').value) || 0);
    const qty = parseInt(document.getElementById('trade-quantity').value) || 0;
    const total = price * qty;
    document.getElementById('trade-total-amount').textContent = priceType === 'market' ? '시장가' : formatPrice(total) + '원';
}

// --- Stock Search for Trading ---
let _tradeSearchTimeout = null;

function initTradeSearch() {
    const input = document.getElementById('trade-search-input');
    const dropdown = document.getElementById('trade-search-dropdown');

    input.addEventListener('input', () => {
        clearTimeout(_tradeSearchTimeout);
        const q = input.value.trim();
        if (q.length < 1) { dropdown.innerHTML = ''; dropdown.style.display = 'none'; return; }

        _tradeSearchTimeout = setTimeout(async () => {
            const res = await apiSearchStocks(q);
            const results = res.results || [];
            if (results.length === 0) {
                dropdown.innerHTML = '<div style="padding:8px 12px; color:var(--text-secondary);">검색 결과 없음</div>';
                dropdown.style.display = 'block';
                return;
            }
            dropdown.innerHTML = results.slice(0, 10).map(s =>
                `<div class="search-result-item" data-code="${s.code}" data-name="${s.name}" style="padding:8px 12px; cursor:pointer;">
                    <strong>${s.name}</strong> <span style="color:var(--text-secondary); font-size:0.85rem;">${s.code}</span>
                </div>`
            ).join('');
            dropdown.style.display = 'block';

            dropdown.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    const code = item.dataset.code;
                    const name = item.dataset.name;
                    input.value = name;
                    document.getElementById('trade-stock-code').value = code;
                    dropdown.style.display = 'none';
                    loadStockPrice(code);
                });
            });
        }, 300);
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#trade-search-wrapper')) {
            dropdown.style.display = 'none';
        }
    });
}

async function loadStockPrice(code) {
    const priceEl = document.getElementById('trade-current-price');
    priceEl.textContent = '조회 중...';

    // Try real-time WS data first, fallback to REST API
    let price = 0, change = 0, changePct = 0, bid = 0, ask = 0;

    const rt = await getRealtimePrice(code);
    if (rt && !rt.error && rt.price) {
        price = rt.price;
        change = rt.change || 0;
        changePct = rt.change_pct || 0;
        bid = rt.bid || 0;
        ask = rt.ask || 0;
    } else {
        const data = await getStockDetail(code);
        if (data && data.close) {
            price = data.close;
            change = data.change || 0;
            changePct = data.change_pct || 0;
        }
    }

    if (price > 0) {
        const color = change >= 0 ? 'var(--accent-primary)' : '#ef4444';
        const sign = change >= 0 ? '+' : '';
        let html = `<span style="color:${color}">${formatPrice(price)}</span> <span style="font-size:0.85rem; color:${color}">${sign}${changePct}%</span>`;
        if (bid && ask) {
            html += `<br><span style="font-size:0.75rem; color:var(--text-secondary);">매수호가 ${formatPrice(bid)} / 매도호가 ${formatPrice(ask)}</span>`;
        }
        priceEl.innerHTML = html;
        // Auto-fill price
        document.getElementById('trade-price').value = price;
        updateTotalAmount();
    } else {
        priceEl.textContent = '조회 실패';
    }

    // Start periodic real-time price refresh
    clearInterval(_priceRefreshTimer);
    _priceRefreshTimer = setInterval(() => refreshRealtimePrice(code), 2000);
}

async function refreshRealtimePrice(code) {
    // Only update if we're still on the trading page and same stock is selected
    const currentCode = document.getElementById('trade-stock-code')?.value;
    if (!currentCode || currentCode !== code) {
        clearInterval(_priceRefreshTimer);
        return;
    }

    const rt = await getRealtimePrice(code);
    if (rt && !rt.error && rt.price) {
        const priceEl = document.getElementById('trade-current-price');
        if (!priceEl) { clearInterval(_priceRefreshTimer); return; }

        const color = (rt.change || 0) >= 0 ? 'var(--accent-primary)' : '#ef4444';
        const sign = (rt.change || 0) >= 0 ? '+' : '';
        let html = `<span style="color:${color}">${formatPrice(rt.price)}</span> <span style="font-size:0.85rem; color:${color}">${sign}${rt.change_pct || 0}%</span>`;
        if (rt.bid && rt.ask) {
            html += `<br><span style="font-size:0.75rem; color:var(--text-secondary);">매수호가 ${formatPrice(rt.bid)} / 매도호가 ${formatPrice(rt.ask)}</span>`;
        }
        priceEl.innerHTML = html;
    }
}

// --- Trading Status ---
async function checkTradingStatus() {
    const badge = document.getElementById('trading-status-badge');
    const card = document.getElementById('trading-status-card');
    const data = await getTradingStatus();

    if (data.available) {
        const label = data.simulation ? 'SIMULATION' : 'LIVE';
        const bgColor = data.simulation ? '#f59e0b' : '#10b981';
        const wsLabel = data.ws_connected ? `WS ON (${data.realtime_stocks || 0} stocks)` : 'WS OFF';
        badge.textContent = `${label} | ${wsLabel}`;
        badge.style.background = bgColor;
        badge.style.color = '#fff';

        // Auto-refresh balance and orders on connect
        refreshBalance();
        refreshOrders();
    } else {
        let msg = 'OFFLINE';
        if (data.auth_error) msg += ` - ${data.auth_error}`;
        badge.textContent = msg;
        badge.style.background = 'var(--bg-tertiary)';
        badge.style.color = 'var(--text-secondary)';
    }
}

// --- Balance ---
async function refreshBalance() {
    const btn = document.getElementById('refresh-balance-btn');
    btn.textContent = '조회 중...';
    btn.disabled = true;

    const data = await getAccountBalance();
    btn.textContent = '새로고침';
    btn.disabled = false;

    if (data.error) {
        document.getElementById('holdings-body').innerHTML =
            `<tr><td colspan="8" style="text-align:center; padding:20px; color:#ef4444;">${data.error}</td></tr>`;
        return;
    }

    document.getElementById('bal-cash').textContent = formatPrice(data.cash) + '원';
    document.getElementById('bal-total-eval').textContent = formatPrice(data.total_eval) + '원';
    document.getElementById('bal-total-purchase').textContent = formatPrice(data.total_purchase) + '원';

    const pnlColor = data.total_pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
    const pnlSign = data.total_pnl >= 0 ? '+' : '';
    document.getElementById('bal-total-pnl').innerHTML = `<span style="color:${pnlColor}">${pnlSign}${formatPrice(data.total_pnl)}원</span>`;
    document.getElementById('bal-total-pnl-pct').innerHTML = `<span style="color:${pnlColor}">${pnlSign}${data.total_pnl_pct}%</span>`;

    const holdings = data.holdings || [];
    if (holdings.length === 0) {
        document.getElementById('holdings-body').innerHTML =
            '<tr><td colspan="8" style="text-align:center; padding:20px; color:var(--text-secondary);">보유 종목이 없습니다</td></tr>';
        return;
    }

    document.getElementById('holdings-body').innerHTML = holdings.map(h => {
        const color = h.pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
        const sign = h.pnl >= 0 ? '+' : '';
        return `<tr>
            <td><a href="#/stock/${h.code}" style="color:var(--accent-primary);">${h.code}</a></td>
            <td>${h.name}</td>
            <td style="text-align:right;">${h.quantity.toLocaleString()}</td>
            <td style="text-align:right;">${formatPrice(h.avg_price)}</td>
            <td style="text-align:right;">${formatPrice(h.current_price)}</td>
            <td style="text-align:right;">${formatPrice(h.eval_amount)}</td>
            <td style="text-align:right; color:${color};">${sign}${formatPrice(h.pnl)}</td>
            <td style="text-align:right; color:${color};">${sign}${h.pnl_pct}%</td>
        </tr>`;
    }).join('');
}

// --- Order History ---
async function refreshOrders() {
    const btn = document.getElementById('refresh-orders-btn');
    btn.textContent = '조회 중...';
    btn.disabled = true;

    const data = await getOrderHistory();
    btn.textContent = '새로고침';
    btn.disabled = false;

    const orders = data.orders || [];
    if (orders.length === 0) {
        document.getElementById('orders-body').innerHTML =
            '<tr><td colspan="10" style="text-align:center; padding:20px; color:var(--text-secondary);">주문 내역이 없습니다</td></tr>';
        return;
    }

    const statusMap = {
        filled: '<span style="color:var(--accent-primary);">체결</span>',
        partial: '<span style="color:#f59e0b;">부분체결</span>',
        pending: '<span style="color:var(--text-secondary);">대기</span>',
        cancelled: '<span style="color:#ef4444;">취소</span>',
    };

    document.getElementById('orders-body').innerHTML = orders.map(o => {
        const typeColor = o.order_type === 'buy' ? 'var(--accent-primary)' : '#ef4444';
        const typeLabel = o.order_type === 'buy' ? '매수' : '매도';
        const canCancel = o.status === 'pending' || o.status === 'partial';
        return `<tr>
            <td>${o.order_no}</td>
            <td>${o.name}</td>
            <td style="color:${typeColor}; font-weight:600;">${typeLabel}</td>
            <td style="text-align:right;">${o.quantity.toLocaleString()}</td>
            <td style="text-align:right;">${formatPrice(o.price)}</td>
            <td style="text-align:right;">${o.filled_quantity.toLocaleString()}</td>
            <td style="text-align:right;">${o.filled_price ? formatPrice(o.filled_price) : '-'}</td>
            <td>${statusMap[o.status] || o.status}</td>
            <td>${o.order_time}</td>
            <td>${canCancel
                ? `<button class="btn btn-outline cancel-order-btn" data-orderno="${o.order_no}" data-code="${o.code}" data-qty="${o.quantity - o.filled_quantity}" style="font-size:0.75rem; padding:2px 8px; color:#ef4444; border-color:#ef4444;">취소</button>`
                : '-'
            }</td>
        </tr>`;
    }).join('');

    // Bind cancel buttons
    document.querySelectorAll('.cancel-order-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const orderNo = btn.dataset.orderno;
            const code = btn.dataset.code;
            const qty = parseInt(btn.dataset.qty);
            if (!confirm(`주문번호 ${orderNo} 을(를) 취소하시겠습니까?`)) return;

            btn.disabled = true;
            btn.textContent = '취소 중...';
            const result = await cancelOrder({ org_order_no: orderNo, code, quantity: qty });
            if (result.success) {
                alert(result.message);
                refreshOrders();
            } else {
                alert(`취소 실패: ${result.message || result.error}`);
                btn.disabled = false;
                btn.textContent = '취소';
            }
        });
    });
}
