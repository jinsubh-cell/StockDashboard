// ==========================================
// Scalping Dashboard - 초단타 자동매매
// ==========================================

import {
    getScalpingStatus, startScalping, stopScalping,
    getScalpingConfig, updateScalpingConfig,
    scanScalpingPicks,
    searchStocksApi as apiSearchStocks,
    getAutoScalpingStatus, startAutoScalping, stopAutoScalping,
    getAutoScalpingConfig, updateAutoScalpingConfig, forceAutoScan,
} from './quantApi.js';
import { formatPrice, getStockByCode } from './data.js';

let _pollTimer = null;

// 종목코드 → 종목명 헬퍼
function stockLabel(code, scores) {
    // Auto 모드: stock_scores에서 이름 가져옴
    if (scores && scores[code] && scores[code].name) {
        return `${scores[code].name}<br><span style="color:var(--text-secondary);font-size:0.75rem;">${code}</span>`;
    }
    // Manual 모드: data.js의 종목 목록에서 조회
    const stock = getStockByCode(code);
    if (stock && stock.name) {
        return `${stock.name}<br><span style="color:var(--text-secondary);font-size:0.75rem;">${code}</span>`;
    }
    return code;
}

function stockLabelInline(code, scores) {
    if (scores && scores[code] && scores[code].name) {
        return `${scores[code].name}(${code})`;
    }
    const stock = getStockByCode(code);
    if (stock && stock.name) return `${stock.name}(${code})`;
    return code;
}
let _selectedCodes = [];
let _autoMode = false;  // false = 수동, true = 자동

export function renderScalpingPage() {
    const container = document.getElementById('page-content');

    container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Mode Toggle + Control Panel -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.5rem;">&#x26A1;</span>
          <h2 style="font-size:1.1rem; font-weight:700;">초단타 스캘핑</h2>
          <!-- Mode Toggle -->
          <div id="mode-toggle" style="display:flex; background:var(--bg-tertiary); border-radius:20px; overflow:hidden; border:1px solid var(--border-color); margin-left:16px;">
            <button id="mode-manual-btn" class="btn" style="padding:6px 18px; font-size:0.8rem; font-weight:700; border:none; border-radius:20px; cursor:pointer; background:#00b894; color:#fff;">
              수동
            </button>
            <button id="mode-auto-btn" class="btn" style="padding:6px 18px; font-size:0.8rem; font-weight:700; border:none; border-radius:20px; cursor:pointer; background:transparent; color:var(--text-secondary);">
              자동매매
            </button>
          </div>
          <span id="scalp-status-badge" style="margin-left:auto; padding:4px 14px; border-radius:20px; font-size:0.8rem; font-weight:600; background:var(--bg-tertiary); color:var(--text-secondary);">STOPPED</span>
        </div>

        <!-- ═══ Manual Mode Panel ═══ -->
        <div id="manual-panel">
          <div class="bt-form" style="margin-bottom:16px;">
            <div class="bt-form-row">
              <div class="bt-form-group" style="flex:2;">
                <label>대상 종목 추가</label>
                <div id="scalp-search-wrapper" class="search-wrapper" style="width:100%;">
                  <span class="search-icon">&#x1F50D;</span>
                  <input type="text" id="scalp-search-input" class="search-input" style="width:100%;" placeholder="종목명 검색 후 Enter" autocomplete="off" />
                  <div id="scalp-search-dropdown" class="search-dropdown"></div>
                </div>
              </div>
              <div class="bt-form-group" style="flex:3;">
                <label>선택된 종목</label>
                <div id="scalp-selected-codes" style="display:flex; flex-wrap:wrap; gap:6px; min-height:36px; align-items:center;">
                  <span style="color:var(--text-secondary); font-size:0.85rem;">종목을 추가해 주세요</span>
                </div>
              </div>
              <div class="bt-form-group" style="display:flex; align-items:flex-end; gap:8px;">
                <button id="scalp-start-btn" class="btn btn-primary" style="padding:10px 24px; font-weight:700; font-size:1rem; background:#00b894;">
                  &#x25B6; 시작
                </button>
                <button id="scalp-stop-btn" class="btn" style="padding:10px 24px; font-weight:700; font-size:1rem; background:#ef4444; color:#fff; border:none; border-radius:8px; cursor:pointer;" disabled>
                  &#x25A0; 정지
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ Auto Mode Panel ═══ -->
        <div id="auto-panel" style="display:none;">
          <div style="background:linear-gradient(135deg, #6c5ce720, #a29bfe20); border:1px solid #a29bfe40; border-radius:12px; padding:16px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
              <span style="font-size:1.3rem;">&#x1F916;</span>
              <div>
                <div style="font-weight:700; font-size:1rem;">완전 자동 매매 모드</div>
                <div style="font-size:0.8rem; color:var(--text-secondary);">종목 검색 → 실시간 구독 → 시그널 감지 → 매수 → 모니터링 → 매도 → 종목 교체 (전 과정 자동)</div>
              </div>
            </div>
            <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
              <button id="auto-start-btn" class="btn btn-primary" style="padding:10px 28px; font-weight:700; font-size:1rem; background:linear-gradient(135deg, #6c5ce7, #a29bfe); border:none; border-radius:8px; color:#fff; cursor:pointer;">
                &#x1F680; 자동매매 시작
              </button>
              <button id="auto-stop-btn" class="btn" style="padding:10px 28px; font-weight:700; font-size:1rem; background:#ef4444; color:#fff; border:none; border-radius:8px; cursor:pointer;" disabled>
                &#x23F9; 자동매매 정지
              </button>
              <button id="auto-rescan-btn" class="btn btn-outline" style="padding:8px 16px; font-size:0.85rem;" disabled>
                &#x1F504; 종목 재검색
              </button>
              <span id="auto-state-badge" style="padding:4px 14px; border-radius:20px; font-size:0.8rem; font-weight:600; background:var(--bg-tertiary); color:var(--text-secondary);">IDLE</span>
            </div>
          </div>

          <!-- Auto: 감시 종목 -->
          <div style="margin-bottom:12px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
              <span style="font-size:0.95rem;">&#x1F3AF;</span>
              <span style="font-weight:600; font-size:0.9rem;">자동 감시 종목</span>
              <span id="auto-target-count" style="font-size:0.8rem; color:var(--text-secondary);">(0종목)</span>
            </div>
            <div id="auto-targets" style="display:flex; flex-wrap:wrap; gap:6px; min-height:30px;">
              <span style="color:var(--text-secondary); font-size:0.85rem;">자동매매 시작 시 자동으로 종목이 선정됩니다</span>
            </div>
          </div>

          <!-- Auto: 최근 시그널 -->
          <div>
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
              <span style="font-size:0.95rem;">&#x1F4E1;</span>
              <span style="font-weight:600; font-size:0.9rem;">최근 시그널</span>
            </div>
            <div id="auto-signals" style="max-height:120px; overflow-y:auto; font-size:0.8rem; font-family:monospace; background:var(--bg-secondary); border-radius:8px; padding:8px;">
              <span style="color:var(--text-secondary);">시그널 대기 중...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Stock Picker - AI 종목 선정 -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F3AF;</span>
          <h3 style="font-size:1rem; font-weight:700;">AI 종목 선정</h3>
          <span style="font-size:0.8rem; color:var(--text-secondary);">거래량 / 변동성 / 스프레드 / 틱빈도 / 모멘텀 종합 분석</span>
          <button id="picker-scan-btn" class="btn btn-outline" style="margin-left:auto; font-size:0.8rem; padding:6px 16px;">
            &#x1F50D; 스캔
          </button>
          <button id="picker-apply-btn" class="btn btn-primary" style="font-size:0.8rem; padding:6px 16px;" disabled>
            선택 종목 적용
          </button>
        </div>
        <div id="picker-results" style="overflow-x:auto;">
          <table class="data-table">
            <thead><tr>
              <th style="width:30px;"><input type="checkbox" id="picker-check-all" /></th>
              <th>등급</th><th>종목코드</th><th>종목명</th><th>현재가</th><th>등락률</th>
              <th>거래량</th><th>거래량비</th><th>변동성</th><th>스프레드</th>
              <th>종합점수</th>
              <th style="font-size:0.7rem;">거래량</th><th style="font-size:0.7rem;">변동성</th>
              <th style="font-size:0.7rem;">스프레드</th><th style="font-size:0.7rem;">틱빈도</th>
              <th style="font-size:0.7rem;">가격대</th><th style="font-size:0.7rem;">모멘텀</th>
            </tr></thead>
            <tbody id="picker-body">
              <tr><td colspan="17" style="text-align:center; padding:20px; color:var(--text-secondary);">
                &#x1F50D; 스캔 버튼을 클릭하여 스캘핑 적합 종목을 분석하세요
              </td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Live Stats -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <span style="font-size:1.2rem;">&#x1F4CA;</span>
          <h3 style="font-size:1rem; font-weight:700;">실시간 현황</h3>
        </div>
        <div id="scalp-stats" style="display:flex; gap:16px; flex-wrap:wrap; justify-content:center;">
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">총 시그널</div><div class="stat-value" id="s-total-signals">0</div></div>
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">총 매매</div><div class="stat-value" id="s-total-trades">0</div></div>
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">승률</div><div class="stat-value" id="s-win-rate">0%</div></div>
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">승/패</div><div class="stat-value" id="s-win-loss">0 / 0</div></div>
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">일일 손익</div><div class="stat-value" id="s-daily-pnl">0원</div></div>
          <div class="stat-box" style="flex:1; min-width:120px;"><div class="stat-label">총 손익</div><div class="stat-value" id="s-total-pnl">0원</div></div>
        </div>
      </div>

      <!-- Active Positions -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <span style="font-size:1.2rem;">&#x1F4CD;</span>
          <h3 style="font-size:1rem; font-weight:700;">보유 포지션</h3>
          <span id="s-pos-count" style="font-size:0.85rem; color:var(--text-secondary);">(0)</span>
        </div>
        <div style="overflow-x:auto;">
          <table class="data-table">
            <thead><tr>
              <th>종목</th><th>방향</th><th>진입가</th><th>현재가</th><th>수량</th>
              <th>손익</th><th>손익률</th><th>보유시간</th><th>손절</th><th>익절</th>
            </tr></thead>
            <tbody id="scalp-positions-body">
              <tr><td colspan="10" style="text-align:center; padding:16px; color:var(--text-secondary);">포지션 없음</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Signals + Trades (side by side) -->
      <div class="card">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <span style="font-size:1.2rem;">&#x1F4E1;</span>
          <h3 style="font-size:1rem; font-weight:700;">최근 시그널</h3>
        </div>
        <div style="overflow-x:auto; max-height:350px; overflow-y:auto;">
          <table class="data-table">
            <thead><tr><th>시간</th><th>종목</th><th>방향</th><th>전략</th><th>강도</th><th>사유</th></tr></thead>
            <tbody id="scalp-signals-body">
              <tr><td colspan="6" style="text-align:center; padding:16px; color:var(--text-secondary);">시그널 대기 중</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
          <span style="font-size:1.2rem;">&#x1F4DD;</span>
          <h3 style="font-size:1rem; font-weight:700;">매매 내역</h3>
        </div>
        <div style="overflow-x:auto; max-height:350px; overflow-y:auto;">
          <table class="data-table">
            <thead><tr><th>시간</th><th>종목</th><th>방향</th><th>진입</th><th>청산</th><th>수량</th><th>손익</th><th>보유</th></tr></thead>
            <tbody id="scalp-trades-body">
              <tr><td colspan="8" style="text-align:center; padding:16px; color:var(--text-secondary);">매매 내역 없음</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Strategy Config -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.2rem;">&#x2699;&#xFE0F;</span>
          <h3 style="font-size:1rem; font-weight:700;">전략 설정</h3>
          <div style="margin-left:auto; display:flex; align-items:center; gap:10px;">
            <label style="font-size:0.85rem; font-weight:600; color:var(--text-secondary);">프리셋</label>
            <select id="cfg-preset" class="ta-select" style="width:160px; font-weight:600; padding:6px 12px;">
              <option value="default">기본</option>
              <option value="gemini">제미나이추천</option>
            </select>
            <button id="scalp-save-config" class="btn btn-outline" style="font-size:0.8rem; padding:4px 14px;">저장</button>
          </div>
        </div>
        <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:16px;">
          <!-- Strategy Toggles -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:var(--accent-primary);">전략 ON/OFF</h4>
            <label class="config-toggle"><input type="checkbox" id="cfg-tick-momentum" checked /> 틱 모멘텀</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-vwap" checked /> VWAP 이탈</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-orderbook" checked /> 호가 불균형</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-bollinger" checked /> 볼린저 스캘핑</label>
            <h4 style="font-size:0.85rem; font-weight:600; margin:12px 0 8px; color:#e17055;">제미나이 전략</h4>
            <label class="config-toggle"><input type="checkbox" id="cfg-ema-cross" /> EMA 크로스(9/21)</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-stochastic" /> 스토캐스틱(5,3,3)</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-macd" /> MACD(8,21,5)</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-alma" /> ALMA(21)</label>
            <label class="config-toggle"><input type="checkbox" id="cfg-exec-strength" /> 체결강도 필터</label>
          </div>
          <!-- Order Settings -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:var(--accent-primary);">주문 설정</h4>
            <label class="config-field">주문수량 <input type="number" id="cfg-quantity" class="ta-select" value="10" min="1" style="width:80px;" /></label>
            <label class="config-field">주문유형
              <select id="cfg-price-type" class="ta-select" style="width:100px;">
                <option value="market">시장가</option>
                <option value="limit">지정가</option>
              </select>
            </label>
          </div>
          <!-- Risk Settings -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:#ef4444;">리스크 관리</h4>
            <label class="config-field">손절(%) <input type="number" id="cfg-stop-loss" class="ta-select" value="0.5" step="0.1" min="0.3" style="width:80px;" /></label>
            <label class="config-field">익절(%) <input type="number" id="cfg-take-profit" class="ta-select" value="1.5" step="0.1" min="0.5" style="width:80px;" /></label>
            <label class="config-field">최대포지션 <input type="number" id="cfg-max-pos" class="ta-select" value="3" min="1" max="10" style="width:80px;" /></label>
            <label class="config-field">일일손실한도 <input type="number" id="cfg-max-loss" class="ta-select" value="100000" step="10000" style="width:100px;" /></label>
            <label class="config-field">최대보유(초) <input type="number" id="cfg-max-hold" class="ta-select" value="300" step="30" style="width:80px;" /></label>
            <label class="config-field">쿨다운(초) <input type="number" id="cfg-cooldown" class="ta-select" value="5" step="1" style="width:80px;" /></label>
          </div>
          <!-- Strategy Params -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:var(--accent-secondary);">전략 파라미터</h4>
            <label class="config-field">틱윈도우 <input type="number" id="cfg-tick-window" class="ta-select" value="20" min="5" style="width:80px;" /></label>
            <label class="config-field">모멘텀 임계값 <input type="number" id="cfg-momentum-threshold" class="ta-select" value="0.7" step="0.05" style="width:80px;" /></label>
            <label class="config-field">VWAP 이탈(%) <input type="number" id="cfg-vwap-dev" class="ta-select" value="0.3" step="0.05" style="width:80px;" /></label>
            <label class="config-field">호가비율 임계 <input type="number" id="cfg-imbalance" class="ta-select" value="2.0" step="0.5" style="width:80px;" /></label>
            <label class="config-field">BB윈도우 <input type="number" id="cfg-bb-window" class="ta-select" value="30" min="10" style="width:80px;" /></label>
            <label class="config-field">BB 표준편차 <input type="number" id="cfg-bb-std" class="ta-select" value="2.0" step="0.5" style="width:80px;" /></label>
          </div>
        </div>
      </div>
    </div>`;

    initScalpingEvents();
    loadConfig();
    startPolling();
}

function initScalpingEvents() {
    // Search & add stocks
    initScalpSearch();

    // Start/Stop
    document.getElementById('scalp-start-btn').addEventListener('click', async () => {
        if (_selectedCodes.length === 0) { alert('대상 종목을 추가해 주세요.'); return; }
        const btn = document.getElementById('scalp-start-btn');
        btn.disabled = true;
        btn.textContent = '시작 중...';
        try {
            console.log('[Scalping] Starting with codes:', _selectedCodes);
            const result = await startScalping(_selectedCodes);
            console.log('[Scalping] Start result:', result);
            if (result.success) {
                updateUIRunning(true);
            } else if (result.message && result.message.includes('이미 실행')) {
                // Already running - just update UI
                updateUIRunning(true);
                console.log('[Scalping] Already running, updating UI');
            } else {
                alert('스캘핑 시작 실패: ' + (result.message || result.error || JSON.stringify(result)));
            }
        } catch (err) {
            console.error('[Scalping] Start error:', err);
            alert('스캘핑 시작 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x25B6; 시작';
        }
    });

    document.getElementById('scalp-stop-btn').addEventListener('click', async () => {
        if (!confirm('스캘핑을 정지하고 모든 포지션을 청산하시겠습니까?')) return;
        const btn = document.getElementById('scalp-stop-btn');
        btn.disabled = true;
        btn.textContent = '정지 중...';
        try {
            const result = await stopScalping();
            if (result.success) {
                updateUIRunning(false);
            } else {
                alert('정지 실패: ' + (result.message || result.error || JSON.stringify(result)));
            }
        } catch (err) {
            console.error('[Scalping] Stop error:', err);
            alert('정지 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x25A0; 정지';
        }
    });

    // Preset selector
    document.getElementById('cfg-preset').addEventListener('change', (e) => {
        const presetKey = e.target.value;
        applyPreset(presetKey);
    });

    // Save config
    document.getElementById('scalp-save-config').addEventListener('click', saveConfig);

    // Picker: Scan
    document.getElementById('picker-scan-btn').addEventListener('click', runPickerScan);

    // Picker: Check all
    document.getElementById('picker-check-all').addEventListener('change', (e) => {
        document.querySelectorAll('.picker-check').forEach(cb => { cb.checked = e.target.checked; });
        updateApplyBtn();
    });

    // Picker: Apply selected to target
    document.getElementById('picker-apply-btn').addEventListener('click', () => {
        const checked = document.querySelectorAll('.picker-check:checked');
        checked.forEach(cb => {
            const code = cb.dataset.code;
            const name = cb.dataset.name;
            if (!_selectedCodes.includes(code)) {
                _selectedCodes.push(code);
            }
        });
        renderSelectedCodes();
    });

    // ═══ Mode Toggle ═══
    document.getElementById('mode-manual-btn').addEventListener('click', () => switchMode(false));
    document.getElementById('mode-auto-btn').addEventListener('click', () => switchMode(true));

    // ═══ Auto Mode Buttons ═══
    document.getElementById('auto-start-btn').addEventListener('click', async () => {
        const btn = document.getElementById('auto-start-btn');
        btn.disabled = true;
        btn.textContent = '시작 중...';
        try {
            console.log('[AutoScalp] Starting auto scalping...');
            const result = await startAutoScalping();
            console.log('[AutoScalp] Start result:', result);
            if (result.success) {
                updateAutoUIRunning(true);
            } else {
                alert('자동매매 시작 실패: ' + (result.message || result.error || JSON.stringify(result)));
            }
        } catch (err) {
            console.error('[AutoScalp] Start error:', err);
            alert('자동매매 시작 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x1F680; 자동매매 시작';
        }
    });

    document.getElementById('auto-stop-btn').addEventListener('click', async () => {
        if (!confirm('자동매매를 정지하고 모든 포지션을 청산하시겠습니까?')) return;
        const btn = document.getElementById('auto-stop-btn');
        btn.disabled = true;
        btn.textContent = '정지 중...';
        try {
            const result = await stopAutoScalping();
            if (result.success) {
                updateAutoUIRunning(false);
            } else {
                alert('자동매매 정지 실패: ' + (result.message || result.error));
            }
        } catch (err) {
            alert('정지 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x23F9; 자동매매 정지';
        }
    });

    document.getElementById('auto-rescan-btn').addEventListener('click', async () => {
        const btn = document.getElementById('auto-rescan-btn');
        btn.disabled = true;
        btn.textContent = '검색 중...';
        try {
            const result = await forceAutoScan();
            if (result.success) {
                console.log('[AutoScalp] Rescan result:', result);
            } else {
                alert(result.message || '재검색 실패');
            }
        } catch (err) {
            alert('재검색 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x1F504; 종목 재검색';
        }
    });
}

// ═══ Mode Switching ═══
function switchMode(auto) {
    _autoMode = auto;
    const manualPanel = document.getElementById('manual-panel');
    const autoPanel = document.getElementById('auto-panel');
    const manualBtn = document.getElementById('mode-manual-btn');
    const autoBtn = document.getElementById('mode-auto-btn');

    if (auto) {
        manualPanel.style.display = 'none';
        autoPanel.style.display = 'block';
        manualBtn.style.background = 'transparent';
        manualBtn.style.color = 'var(--text-secondary)';
        autoBtn.style.background = 'linear-gradient(135deg, #6c5ce7, #a29bfe)';
        autoBtn.style.color = '#fff';
    } else {
        manualPanel.style.display = 'block';
        autoPanel.style.display = 'none';
        manualBtn.style.background = '#00b894';
        manualBtn.style.color = '#fff';
        autoBtn.style.background = 'transparent';
        autoBtn.style.color = 'var(--text-secondary)';
    }
    // Restart polling for the correct mode
    startPolling();
}

function updateAutoUIRunning(running) {
    const badge = document.getElementById('scalp-status-badge');
    const startBtn = document.getElementById('auto-start-btn');
    const stopBtn = document.getElementById('auto-stop-btn');
    const rescanBtn = document.getElementById('auto-rescan-btn');

    if (running) {
        badge.textContent = 'AUTO RUNNING';
        badge.style.background = 'linear-gradient(135deg, #6c5ce7, #a29bfe)';
        badge.style.color = '#fff';
        startBtn.disabled = true;
        stopBtn.disabled = false;
        rescanBtn.disabled = false;
    } else {
        badge.textContent = 'STOPPED';
        badge.style.background = 'var(--bg-tertiary)';
        badge.style.color = 'var(--text-secondary)';
        startBtn.disabled = false;
        stopBtn.disabled = true;
        rescanBtn.disabled = true;
    }
}

function updateUIRunning(running) {
    const badge = document.getElementById('scalp-status-badge');
    const startBtn = document.getElementById('scalp-start-btn');
    const stopBtn = document.getElementById('scalp-stop-btn');

    if (running) {
        badge.textContent = 'RUNNING';
        badge.style.background = '#00b894';
        badge.style.color = '#fff';
        startBtn.disabled = true;
        stopBtn.disabled = false;
    } else {
        badge.textContent = 'STOPPED';
        badge.style.background = 'var(--bg-tertiary)';
        badge.style.color = 'var(--text-secondary)';
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
}

// --- Stock Search ---
let _scalpSearchTimeout = null;

function initScalpSearch() {
    const input = document.getElementById('scalp-search-input');
    const dropdown = document.getElementById('scalp-search-dropdown');

    input.addEventListener('input', () => {
        clearTimeout(_scalpSearchTimeout);
        const q = input.value.trim();
        if (q.length < 1) { dropdown.innerHTML = ''; dropdown.style.display = 'none'; return; }

        _scalpSearchTimeout = setTimeout(async () => {
            const res = await apiSearchStocks(q);
            const results = res.results || [];
            if (results.length === 0) { dropdown.innerHTML = '<div style="padding:8px 12px; color:var(--text-secondary);">결과 없음</div>'; dropdown.style.display = 'block'; return; }
            dropdown.innerHTML = results.slice(0, 8).map(s =>
                `<div class="search-result-item" data-code="${s.code}" data-name="${s.name}" style="padding:8px 12px; cursor:pointer;">
                    <strong>${s.name}</strong> <span style="color:var(--text-secondary); font-size:0.85rem;">${s.code}</span>
                </div>`
            ).join('');
            dropdown.style.display = 'block';

            dropdown.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    addCode(item.dataset.code, item.dataset.name);
                    input.value = '';
                    dropdown.style.display = 'none';
                });
            });
        }, 300);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#scalp-search-wrapper')) dropdown.style.display = 'none';
    });
}

function addCode(code, name) {
    if (_selectedCodes.includes(code)) return;
    _selectedCodes.push(code);
    renderSelectedCodes();
}

function removeCode(code) {
    _selectedCodes = _selectedCodes.filter(c => c !== code);
    renderSelectedCodes();
}

function renderSelectedCodes() {
    const el = document.getElementById('scalp-selected-codes');
    if (_selectedCodes.length === 0) {
        el.innerHTML = '<span style="color:var(--text-secondary); font-size:0.85rem;">종목을 추가해 주세요</span>';
        return;
    }
    el.innerHTML = _selectedCodes.map(code =>
        `<span class="code-chip" style="display:inline-flex; align-items:center; gap:4px; background:var(--bg-tertiary); border:1px solid var(--border-color); border-radius:16px; padding:4px 10px; font-size:0.85rem;">
            ${code}
            <span class="remove-code" data-code="${code}" style="cursor:pointer; color:var(--text-secondary); font-weight:700;">&times;</span>
        </span>`
    ).join('');

    el.querySelectorAll('.remove-code').forEach(btn => {
        btn.addEventListener('click', () => removeCode(btn.dataset.code));
    });
}

// --- Polling ---
function startPolling() {
    if (_pollTimer) clearInterval(_pollTimer);
    pollStatus();
    _pollTimer = setInterval(pollStatus, 1500);
}

async function pollStatus() {
    if (_autoMode) {
        await pollAutoStatus();
        return;
    }

    const data = await getScalpingStatus();
    if (data.error) {
        console.warn('[Scalping] Poll error:', data.error);
        return;
    }

    updateUIRunning(data.running);

    // Stats
    const st = data.stats || {};
    document.getElementById('s-total-signals').textContent = st.total_signals || 0;
    document.getElementById('s-total-trades').textContent = st.total_trades || 0;
    document.getElementById('s-win-rate').textContent = (st.win_rate || 0) + '%';
    document.getElementById('s-win-loss').textContent = `${st.wins || 0} / ${st.losses || 0}`;

    const dailyPnl = st.daily_pnl || 0;
    const totalPnl = st.total_pnl || 0;
    const dailyColor = dailyPnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
    const totalColor = totalPnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
    document.getElementById('s-daily-pnl').innerHTML = `<span style="color:${dailyColor}">${dailyPnl >= 0 ? '+' : ''}${formatPrice(dailyPnl)}원</span>`;
    document.getElementById('s-total-pnl').innerHTML = `<span style="color:${totalColor}">${totalPnl >= 0 ? '+' : ''}${formatPrice(totalPnl)}원</span>`;

    // Positions
    const positions = data.positions || [];
    document.getElementById('s-pos-count').textContent = `(${positions.length})`;
    if (positions.length === 0) {
        document.getElementById('scalp-positions-body').innerHTML = '<tr><td colspan="10" style="text-align:center; padding:16px; color:var(--text-secondary);">포지션 없음</td></tr>';
    } else {
        document.getElementById('scalp-positions-body').innerHTML = positions.map(p => {
            const color = p.pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
            const sideColor = p.side === 'buy' ? 'var(--accent-primary)' : '#ef4444';
            return `<tr>
                <td>${stockLabel(p.code)}</td>
                <td style="color:${sideColor}; font-weight:600;">${p.side === 'buy' ? '매수' : '매도'}</td>
                <td style="text-align:center;">${formatPrice(p.entry_price)}</td>
                <td style="text-align:center;">${formatPrice(p.current_price)}</td>
                <td style="text-align:center;">${p.quantity}</td>
                <td style="text-align:center; color:${color};">${p.pnl >= 0 ? '+' : ''}${formatPrice(p.pnl)}</td>
                <td style="text-align:center; color:${color};">${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct}%</td>
                <td style="text-align:center;">${p.hold_seconds}초</td>
                <td style="text-align:center; color:#ef4444;">${formatPrice(p.stop_loss)}</td>
                <td style="text-align:center; color:#00b894;">${formatPrice(p.take_profit)}</td>
            </tr>`;
        }).join('');
    }

    // Signals
    const signals = data.signals || [];
    if (signals.length === 0) {
        document.getElementById('scalp-signals-body').innerHTML = '<tr><td colspan="6" style="text-align:center; padding:16px; color:var(--text-secondary);">시그널 대기 중</td></tr>';
    } else {
        document.getElementById('scalp-signals-body').innerHTML = signals.slice().map(s => {
            const sideColor = s.side === 'buy' ? 'var(--accent-primary)' : '#ef4444';
            const strengthBg = s.strength === 'strong' ? 'rgba(0,184,148,0.2)' : s.strength === 'normal' ? 'rgba(108,92,231,0.15)' : 'transparent';
            return `<tr style="background:${strengthBg}">
                <td>${s.time}</td>
                <td>${stockLabel(s.code)}</td>
                <td style="color:${sideColor}; font-weight:600;">${s.side === 'buy' ? '매수' : '매도'}</td>
                <td>${strategyLabel(s.strategy)}</td>
                <td>${strengthLabel(s.strength)}</td>
                <td style="font-size:0.8rem;">${s.reason}</td>
            </tr>`;
        }).join('');
    }

    // Trades
    const trades = data.recent_trades || [];
    if (trades.length === 0) {
        document.getElementById('scalp-trades-body').innerHTML = '<tr><td colspan="8" style="text-align:center; padding:16px; color:var(--text-secondary);">매매 내역 없음</td></tr>';
    } else {
        document.getElementById('scalp-trades-body').innerHTML = trades.slice().map(t => {
            const color = t.pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
            const sideColor = t.side === 'buy' ? 'var(--accent-primary)' : '#ef4444';
            return `<tr>
                <td>${t.exit_time}</td>
                <td>${stockLabel(t.code)}</td>
                <td style="color:${sideColor}; font-weight:600;">${t.side === 'buy' ? '매수' : '매도'}</td>
                <td style="text-align:center;">${formatPrice(t.entry_price)}</td>
                <td style="text-align:center;">${formatPrice(t.exit_price)}</td>
                <td style="text-align:center;">${t.quantity}</td>
                <td style="text-align:center; color:${color};">${t.pnl >= 0 ? '+' : ''}${formatPrice(t.pnl)}</td>
                <td>${t.hold_seconds}초</td>
            </tr>`;
        }).join('');
    }

    // Sync selected codes from engine state
    if (data.running && data.target_codes && data.target_codes.length > 0) {
        _selectedCodes = [...data.target_codes];
        renderSelectedCodes();
    }
}

// ═══ Auto Mode Polling ═══
async function pollAutoStatus() {
    const data = await getAutoScalpingStatus();
    if (data.error) {
        console.warn('[AutoScalp] Poll error:', data.error);
        return;
    }

    updateAutoUIRunning(data.running);

    // State badge
    const stateBadge = document.getElementById('auto-state-badge');
    const stateMap = { idle: 'IDLE', scanning: '종목 검색 중...', trading: '매매 중', rotating: '종목 교체 중', stopped: 'STOPPED', market_closed: '장 마감' };
    const stateColors = { idle: 'var(--bg-tertiary)', scanning: '#fdcb6e', trading: '#00b894', rotating: '#6c5ce7', stopped: 'var(--bg-tertiary)', market_closed: '#636e72' };
    stateBadge.textContent = stateMap[data.state] || data.state;
    stateBadge.style.background = stateColors[data.state] || 'var(--bg-tertiary)';
    stateBadge.style.color = ['trading', 'rotating', 'market_closed'].includes(data.state) ? '#fff' : 'var(--text-primary)';

    // Targets
    const targets = data.target_stocks || [];
    const scores = data.stock_scores || {};
    document.getElementById('auto-target-count').textContent = `(${targets.length}종목)`;
    if (targets.length === 0) {
        document.getElementById('auto-targets').innerHTML = '<span style="color:var(--text-secondary); font-size:0.85rem;">감시 종목 없음</span>';
    } else {
        document.getElementById('auto-targets').innerHTML = targets.map(code => {
            const info = scores[code] || {};
            const name = info.name || '';
            const scoreVal = typeof info.score === 'number' ? info.score.toFixed(1) : (typeof info === 'number' ? info.toFixed(1) : '');
            const label = name ? `${name}(${code})` : code;
            const scoreBadge = scoreVal ? ` <span style="color:#6c5ce7; font-size:0.75rem;">${scoreVal}점</span>` : '';
            return `<span style="display:inline-flex; align-items:center; gap:4px; background:linear-gradient(135deg, #6c5ce720, #a29bfe20); border:1px solid #a29bfe40; border-radius:16px; padding:4px 12px; font-size:0.85rem; font-weight:600;">${label}${scoreBadge}</span>`;
        }).join('');
    }

    // Signals
    const signals = data.recent_signals || [];
    const signalEl = document.getElementById('auto-signals');
    if (signals.length === 0) {
        signalEl.innerHTML = '<span style="color:var(--text-secondary);">시그널 대기 중...</span>';
    } else {
        signalEl.innerHTML = signals.slice().map(s => {
            const color = s.side === 'buy' ? '#00b894' : '#ef4444';
            const actionColor = s.action === 'ENTRY' ? '#ff7675' : '#636e72';
            return `<div style="margin-bottom:2px;"><span style="color:var(--text-secondary);">${s.time}</span> <span style="color:${color}; font-weight:700;">${s.side === 'buy' ? 'BUY' : 'SELL'}</span> ${stockLabelInline(s.code, scores)} <span style="color:#6c5ce7;">${s.strategy}</span> <span style="color:${actionColor}; font-weight:600;">[${s.action}]</span> <span style="color:var(--text-secondary);">${s.reason || ''}</span></div>`;
        }).join('');
    }

    // Stats (shared stat elements)
    const st = data.stats || {};
    document.getElementById('s-total-signals').textContent = st.total_signals || 0;
    document.getElementById('s-total-trades').textContent = st.total_trades || 0;
    document.getElementById('s-win-rate').textContent = (st.win_rate || 0) + '%';
    document.getElementById('s-win-loss').textContent = `${st.wins || 0} / ${st.losses || 0}`;

    const dailyPnl = st.daily_pnl || 0;
    const totalPnl = st.total_net_pnl || 0;
    const dailyColor = dailyPnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
    const totalColor = totalPnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
    document.getElementById('s-daily-pnl').innerHTML = `<span style="color:${dailyColor}">${dailyPnl >= 0 ? '+' : ''}${formatPrice(dailyPnl)}원</span>`;
    document.getElementById('s-total-pnl').innerHTML = `<span style="color:${totalColor}">${totalPnl >= 0 ? '+' : ''}${formatPrice(totalPnl)}원</span>`;

    // Positions
    const positions = data.positions || [];
    document.getElementById('s-pos-count').textContent = `(${positions.length})`;
    if (positions.length === 0) {
        document.getElementById('scalp-positions-body').innerHTML = '<tr><td colspan="10" style="text-align:center; padding:16px; color:var(--text-secondary);">포지션 없음</td></tr>';
    } else {
        document.getElementById('scalp-positions-body').innerHTML = positions.map(p => {
            const color = p.pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
            const sideColor = p.side === 'buy' ? 'var(--accent-primary)' : '#ef4444';
            return `<tr>
                <td>${stockLabel(p.code, scores)}</td>
                <td style="color:${sideColor}; font-weight:600;">${p.side === 'buy' ? '매수' : '매도'}</td>
                <td style="text-align:center;">${formatPrice(p.entry_price)}</td>
                <td style="text-align:center;">${formatPrice(p.current_price)}</td>
                <td style="text-align:center;">${p.quantity}</td>
                <td style="text-align:center; color:${color};">${p.pnl >= 0 ? '+' : ''}${formatPrice(p.pnl)}</td>
                <td style="text-align:center; color:${color};">${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct}%</td>
                <td style="text-align:center;">${p.hold_seconds}초</td>
                <td style="text-align:center; color:#ef4444;">${formatPrice(p.stop_loss)}</td>
                <td style="text-align:center; color:#00b894;">${formatPrice(p.take_profit)}</td>
            </tr>`;
        }).join('');
    }

    // Trades
    const trades = data.recent_trades || [];
    if (trades.length === 0) {
        document.getElementById('scalp-trades-body').innerHTML = '<tr><td colspan="8" style="text-align:center; padding:16px; color:var(--text-secondary);">매매 내역 없음</td></tr>';
    } else {
        document.getElementById('scalp-trades-body').innerHTML = trades.slice().map(t => {
            const color = t.net_pnl >= 0 ? 'var(--accent-primary)' : '#ef4444';
            const sideColor = t.side === 'buy' ? 'var(--accent-primary)' : '#ef4444';
            return `<tr>
                <td>${t.time}</td>
                <td>${stockLabel(t.code, scores)}</td>
                <td style="color:${sideColor}; font-weight:600;">${t.side === 'buy' ? '매수' : '매도'}</td>
                <td style="text-align:center;">${formatPrice(t.entry)}</td>
                <td style="text-align:center;">${formatPrice(t.exit)}</td>
                <td style="text-align:center;">${t.qty}</td>
                <td style="text-align:center; color:${color};">${t.net_pnl >= 0 ? '+' : ''}${formatPrice(t.net_pnl)}원 (수수료 ${formatPrice(t.commission)})</td>
                <td>${t.hold_sec}초</td>
            </tr>`;
        }).join('');
    }
}

function strategyLabel(s) {
    const map = {
        'tick_momentum': '틱모멘텀',
        'vwap_deviation': 'VWAP이탈',
        'orderbook_imbalance': '호가불균형',
        'bollinger_scalp': '볼린저',
        'ema_cross': 'EMA크로스',
        'stochastic': '스토캐스틱',
        'macd': 'MACD',
        'alma': 'ALMA',
        'exec_strength': '체결강도',
    };
    return map[s] || s;
}

function strengthLabel(s) {
    if (s === 'strong') return '<span style="color:#00b894; font-weight:700;">STRONG</span>';
    if (s === 'normal') return '<span style="color:var(--accent-primary);">NORMAL</span>';
    return '<span style="color:var(--text-secondary);">WEAK</span>';
}

// --- Stock Picker ---
async function runPickerScan() {
    const btn = document.getElementById('picker-scan-btn');
    btn.disabled = true;
    btn.innerHTML = '&#x23F3; 분석 중...';

    const data = await scanScalpingPicks(true);
    btn.disabled = false;
    btn.innerHTML = '&#x1F50D; 스캔';

    const candidates = data.candidates || [];
    if (candidates.length === 0) {
        document.getElementById('picker-body').innerHTML =
            '<tr><td colspan="17" style="text-align:center; padding:20px; color:var(--text-secondary);">분석 가능한 종목이 없습니다. 백엔드 서버와 데이터를 확인하세요.</td></tr>';
        return;
    }

    document.getElementById('picker-body').innerHTML = candidates.map((c, i) => {
        const gradeColors = { S: '#ff6b6b', A: '#00b894', B: '#6c5ce7', C: '#fdcb6e', D: '#636e72' };
        const gradeColor = gradeColors[c.grade] || '#636e72';
        const changeColor = c.change_pct >= 0 ? 'var(--accent-primary)' : '#ef4444';
        const scores = c.scores || {};

        return `<tr>
            <td><input type="checkbox" class="picker-check" data-code="${c.code}" data-name="${c.name}" /></td>
            <td><span style="display:inline-block; width:28px; height:28px; line-height:28px; text-align:center; border-radius:50%; background:${gradeColor}; color:#fff; font-weight:800; font-size:0.85rem;">${c.grade}</span></td>
            <td><a href="#/stock/${c.code}" style="color:var(--accent-primary);">${c.code}</a></td>
            <td style="font-weight:600;">${c.name}</td>
            <td style="text-align:center;">${formatPrice(c.price)}</td>
            <td style="text-align:center; color:${changeColor};">${c.change_pct >= 0 ? '+' : ''}${c.change_pct}%</td>
            <td style="text-align:center;">${formatVolume(c.volume)}</td>
            <td style="text-align:center; font-weight:600; color:${c.volume_ratio >= 1.5 ? '#00b894' : 'var(--text-primary)'};">${c.volume_ratio}x</td>
            <td style="text-align:center;">${c.volatility_pct}%</td>
            <td style="text-align:center;">${c.spread_pct}%</td>
            <td style="text-align:center;"><span style="font-weight:700; font-size:1rem; color:${gradeColor};">${(c.total_score * 100).toFixed(0)}</span></td>
            ${renderScoreBar(scores.volume)}
            ${renderScoreBar(scores.volatility)}
            ${renderScoreBar(scores.spread)}
            ${renderScoreBar(scores.tick_freq)}
            ${renderScoreBar(scores.price_fit)}
            ${renderScoreBar(scores.momentum)}
        </tr>`;
    }).join('');

    // Bind checkbox changes
    document.querySelectorAll('.picker-check').forEach(cb => {
        cb.addEventListener('change', updateApplyBtn);
    });
}

function renderScoreBar(score) {
    const pct = Math.round((score || 0) * 100);
    const color = pct >= 70 ? '#00b894' : pct >= 40 ? '#6c5ce7' : '#ef4444';
    return `<td style="text-align:center;">
        <div style="width:40px; height:6px; background:var(--bg-tertiary); border-radius:3px; display:inline-block; vertical-align:middle;">
            <div style="width:${pct}%; height:100%; background:${color}; border-radius:3px;"></div>
        </div>
        <span style="font-size:0.7rem; color:var(--text-secondary); margin-left:2px;">${pct}</span>
    </td>`;
}

function formatVolume(v) {
    if (v >= 100_000_000) return (v / 100_000_000).toFixed(1) + '억';
    if (v >= 10_000) return (v / 10_000).toFixed(0) + '만';
    return v.toLocaleString();
}

function updateApplyBtn() {
    const checked = document.querySelectorAll('.picker-check:checked');
    const btn = document.getElementById('picker-apply-btn');
    btn.disabled = checked.length === 0;
    btn.textContent = checked.length > 0 ? `선택 ${checked.length}종목 적용` : '선택 종목 적용';
}

// --- Presets ---
const PRESETS = {
    default: {
        label: '기본',
        use_tick_momentum: true,
        use_vwap_deviation: true,
        use_orderbook_imbalance: true,
        use_bollinger_scalp: true,
        use_ema_cross: false,
        use_stochastic: false,
        use_macd: false,
        use_alma: false,
        use_execution_strength: false,
        order_quantity: 10,
        price_type: 'market',
        stop_loss_pct: 0.3,
        take_profit_pct: 0.5,
        max_position_count: 3,
        max_daily_loss: 100000,
        max_hold_seconds: 300,
        cooldown_seconds: 5,
        tick_window: 20,
        tick_momentum_threshold: 0.7,
        vwap_entry_deviation: 0.3,
        imbalance_threshold: 2.0,
        bb_window: 30,
        bb_std: 2.0,
    },
    gemini: {
        label: '제미나이추천',
        // 단기 소파동에 빠르게 반응하는 공격적 스캘핑 세팅
        // EMA(9/21), Stochastic(5,3,3), MACD(8,21,5), ALMA(21), 체결강도 활성화
        use_tick_momentum: true,
        use_vwap_deviation: true,
        use_orderbook_imbalance: true,
        use_bollinger_scalp: true,
        use_ema_cross: true,           // EMA 9/21 크로스
        use_stochastic: true,          // 스토캐스틱 (5,3,3), 20/80
        use_macd: true,                // MACD (8,21,5)
        use_alma: true,                // ALMA (21,0.85,6) 추세 확인
        use_execution_strength: true,  // 체결강도 100%+ 필터
        order_quantity: 10,
        price_type: 'market',
        stop_loss_pct: 0.1,          // 하드스탑 0.05~0.1%
        take_profit_pct: 0.2,        // 익절 0.15~0.2%
        max_position_count: 3,
        max_daily_loss: 50000,       // 타이트한 일일손실한도
        max_hold_seconds: 180,       // 3분 최대보유
        cooldown_seconds: 3,         // 빠른 재진입
        tick_window: 15,             // 짧은 틱윈도우
        tick_momentum_threshold: 0.6, // 민감한 모멘텀 감지
        vwap_entry_deviation: 0.2,   // 타이트한 VWAP 이탈
        imbalance_threshold: 2.5,    // 엄격한 호가비율
        bb_window: 20,               // 볼린저(20,2)
        bb_std: 2.0,
    },
};

let _currentPreset = 'default';

function applyPreset(presetKey) {
    const preset = PRESETS[presetKey];
    if (!preset) return;
    _currentPreset = presetKey;

    document.getElementById('cfg-tick-momentum').checked = preset.use_tick_momentum;
    document.getElementById('cfg-vwap').checked = preset.use_vwap_deviation;
    document.getElementById('cfg-orderbook').checked = preset.use_orderbook_imbalance;
    document.getElementById('cfg-bollinger').checked = preset.use_bollinger_scalp;
    document.getElementById('cfg-ema-cross').checked = preset.use_ema_cross;
    document.getElementById('cfg-stochastic').checked = preset.use_stochastic;
    document.getElementById('cfg-macd').checked = preset.use_macd;
    document.getElementById('cfg-alma').checked = preset.use_alma;
    document.getElementById('cfg-exec-strength').checked = preset.use_execution_strength;
    document.getElementById('cfg-quantity').value = preset.order_quantity;
    document.getElementById('cfg-price-type').value = preset.price_type;
    document.getElementById('cfg-stop-loss').value = preset.stop_loss_pct;
    document.getElementById('cfg-take-profit').value = preset.take_profit_pct;
    document.getElementById('cfg-max-pos').value = preset.max_position_count;
    document.getElementById('cfg-max-loss').value = preset.max_daily_loss;
    document.getElementById('cfg-max-hold').value = preset.max_hold_seconds;
    document.getElementById('cfg-cooldown').value = preset.cooldown_seconds;
    document.getElementById('cfg-tick-window').value = preset.tick_window;
    document.getElementById('cfg-momentum-threshold').value = preset.tick_momentum_threshold;
    document.getElementById('cfg-vwap-dev').value = preset.vwap_entry_deviation;
    document.getElementById('cfg-imbalance').value = preset.imbalance_threshold;
    document.getElementById('cfg-bb-window').value = preset.bb_window;
    document.getElementById('cfg-bb-std').value = preset.bb_std;
}

function detectPreset(config) {
    // Check if current config matches Gemini preset (check key differentiators)
    if (
        config.use_ema_cross === true &&
        config.use_stochastic === true &&
        config.use_macd === true
    ) {
        return 'gemini';
    }
    return 'default';
}

// --- Config ---
async function loadConfig() {
    const config = await getScalpingConfig();
    if (config.error) return;

    document.getElementById('cfg-tick-momentum').checked = config.use_tick_momentum !== false;
    document.getElementById('cfg-vwap').checked = config.use_vwap_deviation !== false;
    document.getElementById('cfg-orderbook').checked = config.use_orderbook_imbalance !== false;
    document.getElementById('cfg-bollinger').checked = config.use_bollinger_scalp !== false;
    document.getElementById('cfg-ema-cross').checked = config.use_ema_cross === true;
    document.getElementById('cfg-stochastic').checked = config.use_stochastic === true;
    document.getElementById('cfg-macd').checked = config.use_macd === true;
    document.getElementById('cfg-alma').checked = config.use_alma === true;
    document.getElementById('cfg-exec-strength').checked = config.use_execution_strength === true;
    document.getElementById('cfg-quantity').value = config.order_quantity || 10;
    document.getElementById('cfg-price-type').value = config.price_type || 'market';
    document.getElementById('cfg-stop-loss').value = config.stop_loss_pct || 0.5;
    document.getElementById('cfg-take-profit').value = config.take_profit_pct || 1.5;
    document.getElementById('cfg-max-pos').value = config.max_position_count || 3;
    document.getElementById('cfg-max-loss').value = config.max_daily_loss || 100000;
    document.getElementById('cfg-max-hold').value = config.max_hold_seconds || 300;
    document.getElementById('cfg-cooldown').value = config.cooldown_seconds || 5;
    document.getElementById('cfg-tick-window').value = config.tick_window || 20;
    document.getElementById('cfg-momentum-threshold').value = config.tick_momentum_threshold || 0.7;
    document.getElementById('cfg-vwap-dev').value = config.vwap_entry_deviation || 0.3;
    document.getElementById('cfg-imbalance').value = config.imbalance_threshold || 2.0;
    document.getElementById('cfg-bb-window').value = config.bb_window || 30;
    document.getElementById('cfg-bb-std').value = config.bb_std || 2.0;

    // Detect and set current preset
    _currentPreset = detectPreset(config);
    document.getElementById('cfg-preset').value = _currentPreset;
}

async function saveConfig() {
    const presetKey = document.getElementById('cfg-preset').value;
    const config = {
        preset: presetKey,
        use_tick_momentum: document.getElementById('cfg-tick-momentum').checked,
        use_vwap_deviation: document.getElementById('cfg-vwap').checked,
        use_orderbook_imbalance: document.getElementById('cfg-orderbook').checked,
        use_bollinger_scalp: document.getElementById('cfg-bollinger').checked,
        use_ema_cross: document.getElementById('cfg-ema-cross').checked,
        use_stochastic: document.getElementById('cfg-stochastic').checked,
        use_macd: document.getElementById('cfg-macd').checked,
        use_alma: document.getElementById('cfg-alma').checked,
        use_execution_strength: document.getElementById('cfg-exec-strength').checked,
        order_quantity: parseInt(document.getElementById('cfg-quantity').value),
        price_type: document.getElementById('cfg-price-type').value,
        stop_loss_pct: parseFloat(document.getElementById('cfg-stop-loss').value),
        take_profit_pct: parseFloat(document.getElementById('cfg-take-profit').value),
        max_position_count: parseInt(document.getElementById('cfg-max-pos').value),
        max_daily_loss: parseFloat(document.getElementById('cfg-max-loss').value),
        max_hold_seconds: parseFloat(document.getElementById('cfg-max-hold').value),
        cooldown_seconds: parseFloat(document.getElementById('cfg-cooldown').value),
        tick_window: parseInt(document.getElementById('cfg-tick-window').value),
        tick_momentum_threshold: parseFloat(document.getElementById('cfg-momentum-threshold').value),
        vwap_entry_deviation: parseFloat(document.getElementById('cfg-vwap-dev').value),
        imbalance_threshold: parseFloat(document.getElementById('cfg-imbalance').value),
        bb_window: parseInt(document.getElementById('cfg-bb-window').value),
        bb_std: parseFloat(document.getElementById('cfg-bb-std').value),
    };

    const btn = document.getElementById('scalp-save-config');
    btn.textContent = '저장 중...';

    // 수동 모드 설정 저장
    const result = await updateScalpingConfig(config);

    // 자동 모드 설정도 동기화 (공통 파라미터)
    try {
        await updateAutoScalpingConfig({
            stop_loss_pct: config.stop_loss_pct,
            take_profit_pct: config.take_profit_pct,
            trailing_stop_pct: Math.max(0.5, config.stop_loss_pct),
            max_position_count: config.max_position_count,
            max_daily_loss: config.max_daily_loss,
            max_hold_seconds: config.max_hold_seconds,
            cooldown_seconds: config.cooldown_seconds,
            order_quantity: config.order_quantity,
            price_type: config.price_type,
            use_tick_momentum: config.use_tick_momentum,
            use_vwap_deviation: config.use_vwap_deviation,
            use_orderbook_imbalance: config.use_orderbook_imbalance,
            use_bollinger_scalp: config.use_bollinger_scalp,
            tick_window: config.tick_window,
            tick_momentum_threshold: config.tick_momentum_threshold,
            vwap_entry_deviation: config.vwap_entry_deviation,
            imbalance_threshold: config.imbalance_threshold,
            bb_window: config.bb_window,
            bb_std: config.bb_std,
        });
        console.log('[Config] Auto-scalping config synced');
    } catch (e) {
        console.warn('[Config] Auto-scalping sync failed:', e);
    }

    const presetLabel = PRESETS[presetKey]?.label || presetKey;
    btn.textContent = result.success ? `[${presetLabel}] 저장 완료!` : '저장 실패';
    setTimeout(() => { btn.textContent = '저장'; }, 2000);
}
