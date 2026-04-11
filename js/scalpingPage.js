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
    getAIStatus, runDailyReview, runWeeklyReview, applyLatestReview, getReviewHistory,
    getPresets, activatePreset, clonePreset, deletePresetApi, optimizePreset,
    toggleAutoSwitch, resetAll,
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

      <!-- 스킬 프리셋 패널 -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F3AF;</span>
          <h3 style="font-size:1rem; font-weight:700;">스킬 프리셋</h3>
          <span style="font-size:0.8rem; color:var(--text-secondary);">매매 스킬 세트 관리 &amp; 승률 기반 자동 전환</span>
          <label style="margin-left:auto; display:flex; align-items:center; gap:6px; font-size:0.8rem; cursor:pointer;">
            <input type="checkbox" id="auto-switch-toggle" />
            자동 전환
          </label>
          <button id="reset-all-btn" class="btn" style="padding:6px 14px; font-size:0.75rem; background:#ef4444; color:#fff; border:none; border-radius:6px; cursor:pointer;">
            전체 초기화
          </button>
        </div>
        <div id="preset-list" style="display:flex; flex-wrap:wrap; gap:10px; margin-bottom:16px;">
          <span style="color:var(--text-secondary); font-size:0.85rem;">프리셋 로딩 중...</span>
        </div>
      </div>

      <!-- 프리셋 매매 설정 (익절/손절 사용자 설정) -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
          <span style="font-size:1.2rem;">&#x2699;&#xFE0F;</span>
          <h3 style="font-size:1rem; font-weight:700;">매매 설정</h3>
          <span id="preset-config-name" style="font-size:0.8rem; color:#6c5ce7; font-weight:600;"></span>
          <button id="scalp-save-config" class="btn btn-primary" style="margin-left:auto; font-size:0.8rem; padding:6px 18px;">설정 저장</button>
        </div>
        <div style="background:#fff3cd; border:1px solid #ffc107; border-radius:8px; padding:8px 12px; margin-bottom:14px; font-size:0.78rem; color:#856404;">
          &#x26A0; 왕복 수수료 약 0.21% (매수 0.015% + 매도 0.015% + 거래세 0.18%) | 익절은 반드시 0.3% 이상, 손절은 수수료 감안 필요
        </div>
        <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:16px;">
          <!-- 활성 전략 표시 (읽기 전용) -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:var(--accent-primary);">활성 전략 (프리셋 기반)</h4>
            <div id="preset-active-strategies" style="font-size:0.85rem; line-height:1.8;">
              <span style="color:var(--text-secondary);">프리셋 로딩 중...</span>
            </div>
          </div>
          <!-- 익절/손절 사용자 설정 -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:#e74c3c;">익절 / 손절 설정</h4>
            <label class="config-field">익절(%) <input type="number" id="cfg-take-profit" class="ta-select" value="1.5" step="0.1" min="0.3" max="5.0" style="width:80px;" /></label>
            <label class="config-field">손절(%) <input type="number" id="cfg-stop-loss" class="ta-select" value="0.5" step="0.1" min="0.2" max="2.0" style="width:80px;" /></label>
            <label class="config-field">트레일링 스탑(%) <input type="number" id="cfg-trailing-stop" class="ta-select" value="0.5" step="0.1" min="0.1" style="width:80px;" /></label>
            <label class="config-toggle" style="margin-top:6px;"><input type="checkbox" id="cfg-use-trailing" /> 트레일링 스탑 사용</label>
          </div>
          <!-- 리스크 관리 -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:#3498db;">리스크 관리</h4>
            <label class="config-field">최대보유(초) <input type="number" id="cfg-max-hold" class="ta-select" value="300" step="30" style="width:80px;" /></label>
            <label class="config-field">최대포지션 <input type="number" id="cfg-max-pos" class="ta-select" value="3" min="1" max="5" style="width:80px;" /></label>
            <label class="config-field">일일손실한도 <input type="number" id="cfg-max-loss" class="ta-select" value="50000" step="10000" style="width:100px;" /></label>
            <label class="config-field">1회 투자금 <input type="number" id="cfg-max-invest" class="ta-select" value="500000" step="100000" style="width:110px;" /></label>
          </div>
          <!-- 주문 설정 -->
          <div class="config-section">
            <h4 style="font-size:0.9rem; font-weight:600; margin-bottom:10px; color:var(--accent-primary);">주문 설정</h4>
            <label class="config-field">주문수량 <input type="number" id="cfg-quantity" class="ta-select" value="10" min="1" style="width:80px;" /></label>
            <label class="config-field">쿨다운(초) <input type="number" id="cfg-cooldown" class="ta-select" value="3" step="1" style="width:80px;" /></label>
            <label class="config-field">일일거래한도 <input type="number" id="cfg-max-trades" class="ta-select" value="50" min="10" style="width:80px;" /></label>
          </div>
        </div>
      </div>

      <!-- AI 감독관 패널 -->
      <div class="card" style="grid-column: 1 / -1;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.3rem;">&#x1F9E0;</span>
          <h3 style="font-size:1rem; font-weight:700;">AI 감독관</h3>
          <span style="font-size:0.8rem; color:var(--text-secondary);">Claude AI: 전략 리뷰 &amp; 프리셋 최적화</span>
          <span id="ai-status-badge" style="margin-left:auto; padding:4px 14px; border-radius:20px; font-size:0.75rem; font-weight:600; background:var(--bg-tertiary); color:var(--text-secondary);">API 미연결</span>
        </div>
        <div style="display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap;">
          <button id="ai-daily-review-btn" class="btn btn-outline" style="padding:8px 20px; font-size:0.85rem;">
            &#x1F4CA; 일간 리뷰
          </button>
          <button id="ai-weekly-review-btn" class="btn btn-outline" style="padding:8px 20px; font-size:0.85rem;">
            &#x1F4C8; 주간 리뷰
          </button>
          <button id="ai-optimize-btn" class="btn btn-outline" style="padding:8px 20px; font-size:0.85rem;">
            &#x2728; 현재 프리셋 AI 최적화
          </button>
          <button id="ai-apply-btn" class="btn btn-primary" style="padding:8px 20px; font-size:0.85rem;" disabled>
            &#x2705; 리뷰 적용
          </button>
        </div>
        <div id="ai-review-result" style="background:var(--bg-secondary); border-radius:10px; padding:16px; font-size:0.85rem; display:none;">
          <div id="ai-review-content"></div>
        </div>
        <div style="margin-top:12px;">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            <span style="font-size:0.95rem;">&#x1F4DD;</span>
            <span style="font-weight:600; font-size:0.9rem;">리뷰 히스토리</span>
          </div>
          <div id="ai-review-history" style="max-height:150px; overflow-y:auto; font-size:0.8rem; font-family:monospace; background:var(--bg-secondary); border-radius:8px; padding:8px;">
            <span style="color:var(--text-secondary);">리뷰 기록 없음</span>
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

    // ═══ AI 감독관 이벤트 ═══
    document.getElementById('ai-daily-review-btn').addEventListener('click', async () => {
        const btn = document.getElementById('ai-daily-review-btn');
        btn.disabled = true;
        btn.textContent = 'Claude 분석 중...';
        try {
            const result = await runDailyReview();
            if (result.success) {
                displayReviewResult(result.review);
                document.getElementById('ai-apply-btn').disabled = false;
            } else {
                alert('리뷰 실패: ' + (result.message || ''));
            }
        } catch (err) {
            alert('리뷰 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x1F4CA; 일간 리뷰 실행';
        }
    });

    document.getElementById('ai-weekly-review-btn').addEventListener('click', async () => {
        const btn = document.getElementById('ai-weekly-review-btn');
        btn.disabled = true;
        btn.textContent = 'Claude 심층 분석 중...';
        try {
            const result = await runWeeklyReview();
            if (result.success) {
                displayReviewResult(result.review);
                document.getElementById('ai-apply-btn').disabled = false;
            } else {
                alert('리뷰 실패: ' + (result.message || ''));
            }
        } catch (err) {
            alert('리뷰 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x1F4C8; 주간 심층 리뷰';
        }
    });

    document.getElementById('ai-apply-btn').addEventListener('click', async () => {
        const btn = document.getElementById('ai-apply-btn');
        btn.disabled = true;
        try {
            const result = await applyLatestReview();
            if (result.success) {
                const applied = result.applied || {};
                const count = Object.keys(applied).length;
                alert(`${count}개 파라미터 적용 완료:\n${JSON.stringify(applied, null, 2)}`);
            } else {
                alert('적용 실패: ' + (result.message || ''));
            }
        } catch (err) {
            alert('적용 오류: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '&#x2705; 최근 리뷰 적용';
        }
    });

    // ═══ 프리셋 이벤트 ═══
    document.getElementById('auto-switch-toggle').addEventListener('change', async () => {
        try { await toggleAutoSwitch(); } catch (e) { console.warn(e); }
    });

    document.getElementById('reset-all-btn').addEventListener('click', async () => {
        if (!confirm('정말 전체 초기화하시겠습니까?\n\n모든 거래 기록, AI 학습 데이터, 프리셋 성과가 삭제됩니다.\n5개 기본 프리셋으로 다시 시작합니다.')) return;
        try {
            const result = await resetAll();
            if (result.success) {
                alert('전체 초기화 완료!\n' + result.message);
                loadPresets();
            } else {
                alert('초기화 실패: ' + (result.message || ''));
            }
        } catch (e) { alert('초기화 오류: ' + e.message); }
    });

    // AI 최적화 버튼
    document.getElementById('ai-optimize-btn').addEventListener('click', async () => {
        const btn = document.getElementById('ai-optimize-btn');
        btn.disabled = true;
        btn.textContent = 'AI 최적화 중...';
        try {
            const status = await getAutoScalpingStatus();
            const presetName = status.active_preset || 'aggressive';
            const result = await optimizePreset(presetName);
            if (result.success) {
                alert(`프리셋 최적화 완료!\n새 프리셋: ${result.new_preset_name}\n사유: ${result.reason}`);
                loadPresets();
            } else {
                alert('최적화 실패: ' + (result.reason || result.message || ''));
            }
        } catch (e) { alert('최적화 오류: ' + e.message); }
        finally { btn.disabled = false; btn.innerHTML = '&#x2728; 현재 프리셋 AI 최적화'; }
    });

    // AI 상태 & 프리셋 & 히스토리 초기 로드
    loadAIStatus();
    loadPresets();
}

// 전략명 한글 매핑
const STRATEGY_KR = {
    tick_momentum: '틱 모멘텀',
    vwap_deviation: 'VWAP 이탈',
    orderbook_imbalance: '호가 불균형',
    bollinger_scalp: '볼린저 스캘핑',
    rsi_extreme: 'RSI 과매수/과매도',
    volume_spike: '거래량 급증',
    ema_crossover: 'EMA 크로스',
    trade_intensity: '체결강도',
    tick_acceleration: '틱 가속도',
};
function strategyKr(name) { return STRATEGY_KR[name] || name; }

// 한국식 색상: 수익=빨강, 손실=파랑
function pnlColor(val) { return val > 0 ? '#e74c3c' : val < 0 ? '#3498db' : 'var(--text-secondary)'; }
function pnlSign(val) { return val > 0 ? '+' : ''; }

async function loadPresets() {
    try {
        const data = await getPresets();
        const presets = data.presets || [];
        const container = document.getElementById('preset-list');

        if (presets.length === 0) {
            container.innerHTML = '<span style="color:var(--text-secondary);">프리셋 없음</span>';
            return;
        }

        container.innerHTML = presets.map(p => {
            const isActive = p.is_active;
            const bgColor = isActive ? 'linear-gradient(135deg, #6c5ce720, #a29bfe40)' : 'var(--bg-secondary)';
            const borderColor = isActive ? '#a29bfe' : 'var(--border-color)';
            const winColor = p.recent_win_rate >= 50 ? '#e74c3c' : p.recent_win_rate >= 30 ? '#fdcb6e' : '#3498db';
            const strategiesKr = p.strategies.map(s => strategyKr(s)).join(', ');

            return `
            <div style="background:${bgColor}; border:1px solid ${borderColor}; border-radius:10px; padding:14px 16px; min-width:200px; flex:1; max-width:260px; text-align:center;">
                <div style="display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:8px;">
                    ${isActive ? '<span style="font-size:0.7rem; background:#6c5ce7; color:#fff; padding:2px 8px; border-radius:10px;">활성</span>' : ''}
                    <span style="font-weight:700; font-size:0.95rem;">${p.display_name}</span>
                </div>
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:10px;">${strategiesKr}</div>
                <div style="display:flex; justify-content:center; gap:14px; font-size:0.8rem; margin-bottom:10px;">
                    <span>거래 <b>${p.total_trades}</b></span>
                    <span style="color:${winColor};">승률 <b>${p.recent_win_rate || 0}%</b></span>
                    <span style="color:${pnlColor(p.total_net_pnl)};">손익 <b>${pnlSign(p.total_net_pnl)}${Math.round(p.total_net_pnl).toLocaleString()}</b></span>
                </div>
                <div style="display:flex; justify-content:center; gap:6px;">
                    ${!isActive ? `<button class="btn btn-primary preset-activate-btn" data-name="${p.name}" style="padding:4px 12px; font-size:0.75rem;">활성화</button>` : ''}
                    <button class="btn btn-outline preset-clone-btn" data-name="${p.name}" style="padding:4px 10px; font-size:0.7rem;">복제</button>
                    ${!isActive && p.created_by !== 'system' ? `<button class="btn preset-delete-btn" data-name="${p.name}" style="padding:4px 10px; font-size:0.7rem; color:#3498db; border:1px solid #3498db; background:transparent; border-radius:6px; cursor:pointer;">삭제</button>` : ''}
                </div>
            </div>`;
        }).join('');

        // 이벤트 바인딩
        container.querySelectorAll('.preset-activate-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const name = btn.dataset.name;
                btn.disabled = true;
                try {
                    const result = await activatePreset(name);
                    if (result.success) { loadPresets(); loadConfig(); }
                    else alert('활성화 실패: ' + result.message);
                } catch (e) { alert(e.message); }
                finally { btn.disabled = false; }
            });
        });
        container.querySelectorAll('.preset-clone-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    const result = await clonePreset(btn.dataset.name);
                    if (result.success) loadPresets();
                } catch (e) { alert(e.message); }
            });
        });
        container.querySelectorAll('.preset-delete-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`프리셋 '${btn.dataset.name}'을 삭제하시겠습니까?`)) return;
                try {
                    const result = await deletePresetApi(btn.dataset.name);
                    if (result.success) loadPresets();
                } catch (e) { alert(e.message); }
            });
        });

        // 자동 전환 토글 상태 반영
        const status = await getAutoScalpingStatus();
        const toggle = document.getElementById('auto-switch-toggle');
        if (toggle && status.preset_status) {
            toggle.checked = status.preset_status.auto_switch_enabled;
        }
    } catch (e) {
        console.warn('[Presets] 로드 실패:', e);
    }
}

function displayReviewResult(review) {
    const container = document.getElementById('ai-review-result');
    const content = document.getElementById('ai-review-content');
    container.style.display = 'block';

    const isWeekly = review.review_type === 'weekly';
    const summary = isWeekly ? review.weekly_summary : review.performance_summary;
    const changes = review.parameter_changes || {};
    const changeCount = Object.keys(changes).length;
    const recommendations = isWeekly
        ? (review.strategy_overhaul || [])
        : (review.strategy_recommendations || []);

    content.innerHTML = `
        <div style="margin-bottom:10px;">
            <span style="font-weight:700; color:#6c5ce7;">[${isWeekly ? '주간 심층' : '일간'} 리뷰]</span>
            <span style="font-size:0.75rem; color:var(--text-secondary);">${review.timestamp || ''}</span>
        </div>
        <div style="margin-bottom:10px; line-height:1.5;">${summary}</div>
        ${review.risk_assessment ? `<div style="margin-bottom:8px;"><b>리스크:</b> ${review.risk_assessment}</div>` : ''}
        ${review.next_action ? `<div style="margin-bottom:8px;"><b>내일 핵심:</b> ${review.next_action}</div>` : ''}
        ${isWeekly && review.insight ? `<div style="margin-bottom:8px;"><b>인사이트:</b> ${review.insight}</div>` : ''}
        ${changeCount > 0 ? `
            <div style="margin-top:10px; padding:10px; background:var(--bg-tertiary); border-radius:8px;">
                <b>파라미터 조정안 (${changeCount}개):</b>
                <pre style="margin:6px 0 0; font-size:0.8rem; white-space:pre-wrap;">${JSON.stringify(changes, null, 2)}</pre>
            </div>` : '<div style="color:var(--text-secondary);">파라미터 변경 없음</div>'}
        ${recommendations.length > 0 ? `
            <div style="margin-top:8px;">
                <b>전략 권고:</b>
                <ul style="margin:4px 0 0 16px; padding:0;">${recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
            </div>` : ''}
    `;
}

async function loadAIStatus() {
    try {
        const status = await getAIStatus();
        const badge = document.getElementById('ai-status-badge');
        if (status.available) {
            badge.textContent = '감독관 모드';
            badge.style.background = 'linear-gradient(135deg, #6c5ce720, #a29bfe40)';
            badge.style.color = '#6c5ce7';
        } else {
            badge.textContent = 'API 미연결';
        }

        if (status.last_review_result) {
            displayReviewResult(status.last_review_result);
            document.getElementById('ai-apply-btn').disabled = false;
        }

        // 히스토리 로드
        const historyData = await getReviewHistory(10);
        const historyEl = document.getElementById('ai-review-history');
        const reviews = historyData.reviews || [];
        if (reviews.length > 0) {
            historyEl.innerHTML = reviews.map(r => {
                const type = r.review_type === 'weekly' ? '[주간]' : '[일간]';
                const summary = r.performance_summary || r.weekly_summary || '';
                const ts = r.timestamp ? r.timestamp.split('T')[0] : '';
                const changes = Object.keys(r.parameter_changes || {}).length;
                return `<div style="padding:4px 0; border-bottom:1px solid var(--border-color);">
                    <span style="color:#6c5ce7; font-weight:600;">${type}</span>
                    <span style="color:var(--text-secondary);">${ts}</span>
                    ${changes > 0 ? `<span style="color:#00b894;">[${changes}개 변경]</span>` : ''}
                    <br>${summary.substring(0, 100)}${summary.length > 100 ? '...' : ''}
                </div>`;
            }).join('');
        }
    } catch (err) {
        console.warn('[AI Status] 로드 실패:', err);
    }
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
    // 프리셋 기반 설정 로드
    try {
        const status = await getAutoScalpingStatus();
        const config = status.config || {};
        const presetName = status.active_preset || '';

        // 프리셋 이름 표시
        const nameEl = document.getElementById('preset-config-name');
        if (nameEl) nameEl.textContent = presetName ? `[${status.preset_status?.active_display_name || presetName}]` : '';

        // 활성 전략 표시
        const stratEl = document.getElementById('preset-active-strategies');
        if (stratEl) {
            const allStrats = [
                ['use_tick_momentum', '틱 모멘텀'],
                ['use_vwap_deviation', 'VWAP 이탈'],
                ['use_orderbook_imbalance', '호가 불균형'],
                ['use_bollinger_scalp', '볼린저 스캘핑'],
                ['use_rsi_extreme', 'RSI 과매수/과매도'],
                ['use_volume_spike', '거래량 급증'],
                ['use_ema_crossover', 'EMA 크로스'],
                ['use_trade_intensity', '체결강도'],
                ['use_tick_acceleration', '틱 가속도'],
            ];
            stratEl.innerHTML = allStrats.map(([key, label]) => {
                const on = config[key] === true;
                return `<div style="display:flex; align-items:center; gap:8px; padding:2px 0;">
                    <span style="width:8px; height:8px; border-radius:50%; background:${on ? '#00b894' : '#ddd'}; display:inline-block;"></span>
                    <span style="color:${on ? 'var(--text-primary)' : 'var(--text-secondary)'}; ${on ? 'font-weight:600' : ''}">${label}</span>
                </div>`;
            }).join('');
        }

        // 익절/손절/리스크 설정
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };
        setVal('cfg-take-profit', config.take_profit_pct || 1.5);
        setVal('cfg-stop-loss', config.stop_loss_pct || 0.5);
        setVal('cfg-trailing-stop', config.trailing_stop_pct || 0.5);
        setChk('cfg-use-trailing', config.use_trailing_stop === true);
        setVal('cfg-max-hold', config.max_hold_seconds || 300);
        setVal('cfg-max-pos', config.max_position_count || 3);
        setVal('cfg-max-loss', config.max_daily_loss || 50000);
        setVal('cfg-max-invest', config.max_investment_per_trade || 500000);
        setVal('cfg-quantity', config.order_quantity || 10);
        setVal('cfg-cooldown', config.cooldown_seconds || 3);
        setVal('cfg-max-trades', config.max_daily_trades || 50);
    } catch (e) {
        console.warn('[Config] 로드 실패:', e);
    }
}

async function saveConfig() {
    const config = {
        take_profit_pct: parseFloat(document.getElementById('cfg-take-profit').value),
        stop_loss_pct: parseFloat(document.getElementById('cfg-stop-loss').value),
        trailing_stop_pct: parseFloat(document.getElementById('cfg-trailing-stop').value),
        use_trailing_stop: document.getElementById('cfg-use-trailing').checked,
        max_hold_seconds: parseFloat(document.getElementById('cfg-max-hold').value),
        max_position_count: parseInt(document.getElementById('cfg-max-pos').value),
        max_daily_loss: parseFloat(document.getElementById('cfg-max-loss').value),
        max_investment_per_trade: parseInt(document.getElementById('cfg-max-invest').value),
        order_quantity: parseInt(document.getElementById('cfg-quantity').value),
        cooldown_seconds: parseFloat(document.getElementById('cfg-cooldown').value),
        max_daily_trades: parseInt(document.getElementById('cfg-max-trades').value),
    };

    const btn = document.getElementById('scalp-save-config');
    btn.textContent = '저장 중...';

    try {
        // 수동 모드 저장
        await updateScalpingConfig(config);
        // 자동 모드 동기화
        await updateAutoScalpingConfig(config);
        btn.textContent = '저장 완료!';
        btn.style.background = '#00b894';
    } catch (e) {
        btn.textContent = '저장 실패';
        btn.style.background = '#e74c3c';
    }
    setTimeout(() => { btn.textContent = '설정 저장'; btn.style.background = ''; }, 2000);
}
