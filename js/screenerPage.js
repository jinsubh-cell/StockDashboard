// ==========================================
// AI 조건검색 빌더 (Screener Page)
// 프롬프트 → 키움증권 호환 조건식 생성 + 스캔 실행
// ==========================================

const SCREENER_API = 'http://localhost:8000/api/screener';

// ─── 조건 타입 정의 ────────────────────────────────────────────────
const CONDITION_DEFS = {
  sma_cross: {
    label: 'SMA 크로스',
    icon: '📈',
    params: ['fast', 'slow', 'direction'],
    defaultParams: { fast: 5, slow: 20, direction: 'up' },
    toKiwoom: (p) =>
      `이동평균선 > MA${p.fast} ${p.direction === 'up' ? '골든크로스' : '데드크로스'} (MA${p.slow})`,
    toLabel: (p) =>
      `MA${p.fast} ${p.direction === 'up' ? '골든크로스 ↑' : '데드크로스 ↓'} MA${p.slow}`,
  },
  sma_alignment: {
    label: '이동평균 정배열',
    icon: '📊',
    params: [],
    defaultParams: {},
    toKiwoom: () => '이동평균선 > 정배열 (5>20>60>120)',
    toLabel: () => 'MA 정배열 (5 > 20 > 60 > 120)',
  },
  rsi: {
    label: 'RSI',
    icon: '🔄',
    params: ['operator', 'value'],
    defaultParams: { operator: 'lte', value: 30 },
    toKiwoom: (p) => {
      const ops = { lt: '<', gt: '>', lte: '≤', gte: '≥' };
      return `RSI > RSI(14) ${ops[p.operator]} ${p.value}`;
    },
    toLabel: (p) => {
      const ops = { lt: '<', gt: '>', lte: '≤', gte: '≥' };
      return `RSI(14) ${ops[p.operator]} ${p.value}`;
    },
  },
  macd_cross: {
    label: 'MACD 크로스',
    icon: '⚡',
    params: ['direction'],
    defaultParams: { direction: 'up' },
    toKiwoom: (p) =>
      `MACD > MACD ${p.direction === 'up' ? '골든크로스' : '데드크로스'}`,
    toLabel: (p) =>
      `MACD ${p.direction === 'up' ? '골든크로스 ↑' : '데드크로스 ↓'}`,
  },
  bollinger: {
    label: '볼린저밴드',
    icon: '🎯',
    params: ['direction'],
    defaultParams: { direction: 'touch_lower' },
    toKiwoom: (p) => {
      if (p.direction === 'touch_lower') return '볼린저밴드 > 하단밴드 이하';
      if (p.direction === 'touch_upper') return '볼린저밴드 > 상단밴드 돌파';
      return '볼린저밴드 > 밴드폭 수축 (스퀴즈)';
    },
    toLabel: (p) => {
      if (p.direction === 'touch_lower') return '볼린저 하단밴드 터치 ↓';
      if (p.direction === 'touch_upper') return '볼린저 상단밴드 돌파 ↑';
      return '볼린저 밴드폭 수축 (스퀴즈)';
    },
  },
  volume_spike: {
    label: '거래량 급증',
    icon: '📦',
    params: ['multiplier'],
    defaultParams: { multiplier: 2.0 },
    toKiwoom: (p) => `거래량 > 전일 평균거래량 대비 ${p.multiplier}배 이상`,
    toLabel: (p) => `거래량 급증 (${p.multiplier}배 이상)`,
  },
  price_vs_sma: {
    label: '현재가 vs 이동평균',
    icon: '💰',
    params: ['period', 'direction'],
    defaultParams: { period: 20, direction: 'above' },
    toKiwoom: (p) =>
      `현재가 > MA${p.period} ${p.direction === 'above' ? '이상' : '이하'}`,
    toLabel: (p) =>
      `현재가 ${p.direction === 'above' ? '>' : '<'} MA${p.period}`,
  },
  adx_trend: {
    label: '강한 추세 (ADX)',
    icon: '🚀',
    params: ['value'],
    defaultParams: { value: 25 },
    toKiwoom: (p) => `추세강도 > ADX(14) > ${p.value}`,
    toLabel: (p) => `ADX(14) > ${p.value} (강한 추세)`,
  },
};

// ─── 프리셋 템플릿 ──────────────────────────────────────────────────
const PRESETS = [
  {
    name: '🚀 모멘텀 매수',
    desc: '골든크로스 + 정배열 + 거래량 급증',
    logic: 'AND',
    conditions: [
      { type: 'sma_cross', fast: 5, slow: 20, direction: 'up' },
      { type: 'sma_alignment' },
      { type: 'volume_spike', multiplier: 2.0 },
    ],
  },
  {
    name: '📉 RSI 과매도 반등',
    desc: 'RSI 과매도 + 볼린저 하단 터치',
    logic: 'AND',
    conditions: [
      { type: 'rsi', operator: 'lte', value: 30 },
      { type: 'bollinger', direction: 'touch_lower' },
    ],
  },
  {
    name: '⚡ MACD 상향 돌파',
    desc: 'MACD 골든크로스 + 현재가 20일선 위',
    logic: 'AND',
    conditions: [
      { type: 'macd_cross', direction: 'up' },
      { type: 'price_vs_sma', period: 20, direction: 'above' },
    ],
  },
  {
    name: '🎯 볼린저 상단 돌파',
    desc: '볼린저 상단 돌파 + 거래량 급증',
    logic: 'AND',
    conditions: [
      { type: 'bollinger', direction: 'touch_upper' },
      { type: 'volume_spike', multiplier: 1.5 },
    ],
  },
  {
    name: '🔥 강한 추세 추종',
    desc: '이동평균 정배열 + ADX 강한 추세',
    logic: 'AND',
    conditions: [
      { type: 'sma_alignment' },
      { type: 'adx_trend', value: 25 },
    ],
  },
];

// ─── 프롬프트 파서 (자연어 → 조건식) ──────────────────────────────
function parsePrompt(text) {
  const conditions = [];
  const lower = text.toLowerCase();

  // RSI
  const rsiLtMatch = lower.match(/rsi\s*(?:가\s*)?(?:과매도|(?:이하|미만|<\s*|≤\s*)(\d+))/);
  const rsiGtMatch = lower.match(/rsi\s*(?:가\s*)?(?:과매수|(?:이상|초과|>\s*|≥\s*)(\d+))/);
  const rsiRawMatch = lower.match(/rsi.*?(\d+)\s*(이하|미만|이상|초과)/);

  if (rsiLtMatch || lower.includes('rsi 과매도') || lower.includes('rsi가 30') || lower.includes('rsi 30 이하')) {
    const val = rsiLtMatch?.[1] ? parseInt(rsiLtMatch[1]) : 30;
    conditions.push({ type: 'rsi', operator: 'lte', value: val });
  } else if (rsiGtMatch || lower.includes('rsi 과매수') || lower.includes('rsi 70') || lower.includes('rsi 70 이상')) {
    const val = rsiGtMatch?.[1] ? parseInt(rsiGtMatch[1]) : 70;
    conditions.push({ type: 'rsi', operator: 'gte', value: val });
  } else if (rsiRawMatch) {
    const val = parseInt(rsiRawMatch[1]);
    const op = rsiRawMatch[2].includes('이하') || rsiRawMatch[2].includes('미만') ? 'lte' : 'gte';
    conditions.push({ type: 'rsi', operator: op, value: val });
  }

  // 골든크로스 / SMA 크로스
  if (lower.includes('골든크로스') || lower.includes('golden cross') || lower.includes('상향돌파') || lower.includes('상향 돌파')) {
    // 특정 기간 추출 시도
    const maMatch = lower.match(/(\d+)일선.*?(\d+)일선/) || lower.match(/ma(\d+).*?ma(\d+)/i);
    if (maMatch) {
      conditions.push({ type: 'sma_cross', fast: parseInt(maMatch[1]), slow: parseInt(maMatch[2]), direction: 'up' });
    } else {
      conditions.push({ type: 'sma_cross', fast: 5, slow: 20, direction: 'up' });
    }
  }

  // 데드크로스
  if (lower.includes('데드크로스') || lower.includes('dead cross') || lower.includes('하향돌파') || lower.includes('하향 돌파')) {
    conditions.push({ type: 'sma_cross', fast: 5, slow: 20, direction: 'down' });
  }

  // 이동평균 정배열
  if (lower.includes('정배열') || lower.includes('이평 정배열') || lower.includes('이동평균 정배열')) {
    conditions.push({ type: 'sma_alignment' });
  }

  // MACD
  if (lower.includes('macd 골든') || lower.includes('macd 상향') || lower.includes('macd 골크')) {
    conditions.push({ type: 'macd_cross', direction: 'up' });
  } else if (lower.includes('macd 데드') || lower.includes('macd 하향')) {
    conditions.push({ type: 'macd_cross', direction: 'down' });
  } else if (lower.includes('macd') && !conditions.find(c => c.type === 'macd_cross')) {
    conditions.push({ type: 'macd_cross', direction: 'up' });
  }

  // 볼린저밴드
  if (lower.includes('볼린저 하단') || lower.includes('하단밴드') || lower.includes('bb 하단') || lower.includes('볼린저밴드 하단')) {
    conditions.push({ type: 'bollinger', direction: 'touch_lower' });
  } else if (lower.includes('볼린저 상단') || lower.includes('상단밴드') || lower.includes('bb 상단') || lower.includes('볼린저밴드 상단') || lower.includes('볼린저 돌파')) {
    conditions.push({ type: 'bollinger', direction: 'touch_upper' });
  } else if (lower.includes('볼린저') || lower.includes('bollinger')) {
    conditions.push({ type: 'bollinger', direction: 'touch_lower' });
  }

  // 거래량 급증
  if (lower.includes('거래량 급증') || lower.includes('거래량이 급증') || lower.includes('거래량 폭발') || lower.includes('거래량 터짐')) {
    const multMatch = lower.match(/(\d+(?:\.\d+)?)\s*배/);
    const mult = multMatch ? parseFloat(multMatch[1]) : 2.0;
    conditions.push({ type: 'volume_spike', multiplier: mult });
  }

  // 현재가 > 이동평균
  const priceAboveMatch = lower.match(/현재가\s*(?:가\s*)?(?:>|이상|위)\s*(\d+)일?선/);
  const priceBelowMatch = lower.match(/현재가\s*(?:가\s*)?(?:<|이하|아래)\s*(\d+)일?선/);
  if (priceAboveMatch) {
    conditions.push({ type: 'price_vs_sma', period: parseInt(priceAboveMatch[1]), direction: 'above' });
  } else if (priceBelowMatch) {
    conditions.push({ type: 'price_vs_sma', period: parseInt(priceBelowMatch[1]), direction: 'below' });
  }

  // ADX 강한 추세
  if (lower.includes('adx') || lower.includes('강한 추세') || lower.includes('추세 강도')) {
    const adxValMatch = lower.match(/adx.*?(\d+)/);
    conditions.push({ type: 'adx_trend', value: adxValMatch ? parseInt(adxValMatch[1]) : 25 });
  }

  // 복합 단어 기반 추가 조건
  if (lower.includes('모멘텀') && conditions.length === 0) {
    conditions.push(
      { type: 'sma_cross', fast: 5, slow: 20, direction: 'up' },
      { type: 'volume_spike', multiplier: 2.0 }
    );
  }
  if (lower.includes('반등') && conditions.length === 0) {
    conditions.push(
      { type: 'rsi', operator: 'lte', value: 35 },
      { type: 'bollinger', direction: 'touch_lower' }
    );
  }
  if (lower.includes('상승 추세') || lower.includes('상승추세')) {
    if (!conditions.find(c => c.type === 'sma_alignment'))
      conditions.push({ type: 'sma_alignment' });
  }

  return conditions;
}

// ─── 조건을 키움증권 HTS 스크립트 형식으로 변환 ─────────────────────
function toKiwoomScript(conditions, logic, name = '사용자 조건식') {
  const lines = [
    `■ 조건검색식명: ${name}`,
    `■ 생성일: ${new Date().toLocaleDateString('ko-KR')}`,
    `■ 논리연산: ${logic === 'AND' ? 'AND (모두 만족)' : 'OR (하나 이상 만족)'}`,
    `■ 적용 시장: 코스피 + 코스닥`,
    ``,
    `[조건 목록]`,
  ];

  conditions.forEach((cond, i) => {
    const def = CONDITION_DEFS[cond.type];
    if (!def) return;
    const kiwoomText = def.toKiwoom(cond);
    lines.push(`  ${i + 1}. ${def.icon} ${kiwoomText}`);
  });

  lines.push('');
  lines.push('[키움 HTS 적용 방법]');
  lines.push('1. 키움증권 영웅문 HTS 실행');
  lines.push('2. [조건검색] 화면 (0150) 열기');
  lines.push('3. [조건 만들기] → [수식 편집기]에서 위 조건을 입력');
  lines.push('4. 각 조건을 항목별로 추가하고 AND/OR 논리 설정');
  lines.push('5. [검색] 버튼 클릭하여 조건 충족 종목 확인');
  lines.push('');
  lines.push('[키움 API 연동]');
  lines.push('SetConditionName, SendCondition 함수를 통해 자동화 가능');

  return lines.join('\n');
}

// ─── 상태 ───────────────────────────────────────────────────────────
let screenerState = {
  conditions: [],
  logic: 'AND',
  scanCount: 50,
  results: [],
  scanning: false,
  kiwoomConditions: [],
  kiwoomConnected: false,
};

// ─── 메인 렌더링 ────────────────────────────────────────────────────
export function renderScreenerPage() {
  const container = document.getElementById('page-content');
  container.innerHTML = buildScreenerHTML();
  attachScreenerEvents();
  checkKiwoomConnection();
}

function buildScreenerHTML() {
  return `
<div class="dashboard-grid fade-in" id="screener-root">

  <!-- 헤더 설명 -->
  <div class="card" style="margin-bottom:0; background: linear-gradient(135deg, rgba(108,92,231,0.15) 0%, rgba(0,210,106,0.08) 100%); border: 1px solid rgba(108,92,231,0.3);">
    <div style="display:flex; align-items:center; gap:14px;">
      <div style="width:48px; height:48px; border-radius:12px; background:linear-gradient(135deg,#6C5CE7,#00D26A); display:flex; align-items:center; justify-content:center; flex-shrink:0;">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/><path d="M11 8v6M8 11h6"/></svg>
      </div>
      <div>
        <h2 style="font-size:1.15rem; font-weight:700; margin-bottom:4px;">AI 조건검색 빌더</h2>
        <p style="font-size:0.83rem; color:var(--text-secondary); line-height:1.5;">
          자연어로 조건을 입력하면 키움증권 HTS 호환 조건식으로 자동 변환됩니다.
          생성된 조건으로 실시간 종목 스캔이 가능합니다.
        </p>
      </div>
    </div>
  </div>

  <!-- 2컬럼 레이아웃 -->
  <div style="display:grid; grid-template-columns: 1fr 360px; gap:20px; align-items:start;">

    <!-- 왼쪽: 프롬프트 + 조건 빌더 + 결과 -->
    <div style="display:flex; flex-direction:column; gap:16px;">

      <!-- 프롬프트 입력 -->
      <div class="card">
        <div class="card-header" style="margin-bottom:14px;">
          <span class="card-title">💬 프롬프트로 조건 만들기</span>
        </div>
        <div style="position:relative;">
          <textarea
            id="screener-prompt"
            placeholder="조건을 자연어로 입력하세요&#10;예시: RSI가 30 이하이고 거래량이 급증하는 종목&#10;예시: 골든크로스 발생 + 이동평균 정배열&#10;예시: 볼린저 하단 터치 후 반등 가능성"
            style="width:100%; height:110px; background:var(--bg-tertiary); border:1.5px solid var(--border-color); border-radius:10px; padding:14px; font-size:0.9rem; color:var(--text-primary); resize:vertical; font-family:inherit; line-height:1.6; box-sizing:border-box; outline:none; transition:border-color 0.2s;"
            onfocus="this.style.borderColor='var(--accent-primary)'"
            onblur="this.style.borderColor='var(--border-color)'"
          ></textarea>
        </div>
        <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" id="btn-parse-prompt" style="flex:1; min-width:140px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px; vertical-align:middle;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
            AI 조건 생성
          </button>
          <button class="btn btn-outline" id="btn-clear-conditions" style="padding:0 18px;">초기화</button>
        </div>

        <!-- 빠른 예시 태그 -->
        <div style="margin-top:14px;">
          <div style="font-size:0.75rem; color:var(--text-tertiary); margin-bottom:8px; font-weight:500;">💡 빠른 예시</div>
          <div style="display:flex; flex-wrap:wrap; gap:7px;" id="prompt-examples">
            ${[
              'RSI 과매도 + 거래량 급증',
              '골든크로스 발생 종목',
              '이동평균 정배열',
              'MACD 골든크로스',
              '볼린저 하단 터치',
              '모멘텀 매수 신호',
              '강한 추세 + ADX',
              '볼린저 상단 돌파 + 거래량',
            ].map(ex => `
              <button class="prompt-example-tag" onclick="window._screenerSetPrompt('${ex}')"
                style="padding:4px 12px; border-radius:20px; background:var(--bg-tertiary); border:1px solid var(--border-color); color:var(--text-secondary); font-size:0.78rem; cursor:pointer; transition:all 0.15s;"
                onmouseover="this.style.borderColor='var(--accent-primary)'; this.style.color='var(--accent-primary)'"
                onmouseout="this.style.borderColor='var(--border-color)'; this.style.color='var(--text-secondary)'"
              >${ex}</button>
            `).join('')}
          </div>
        </div>
      </div>

      <!-- 생성된 조건 목록 -->
      <div class="card">
        <div class="card-header" style="margin-bottom:14px;">
          <span class="card-title">⚙️ 조건 목록</span>
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:0.8rem; color:var(--text-tertiary);">논리 연산:</span>
            <div style="display:flex; border:1px solid var(--border-color); border-radius:8px; overflow:hidden;">
              <button id="btn-logic-and" class="logic-btn active"
                onclick="window._screenerSetLogic('AND')"
                style="padding:4px 14px; font-size:0.8rem; font-weight:600; border:none; cursor:pointer; background:var(--accent-primary); color:white; transition:all 0.15s;">AND</button>
              <button id="btn-logic-or" class="logic-btn"
                onclick="window._screenerSetLogic('OR')"
                style="padding:4px 14px; font-size:0.8rem; font-weight:600; border:none; cursor:pointer; background:var(--bg-tertiary); color:var(--text-secondary); transition:all 0.15s;">OR</button>
            </div>
          </div>
        </div>

        <div id="conditions-list" style="display:flex; flex-direction:column; gap:10px; min-height:60px;">
          <div style="text-align:center; padding:30px; color:var(--text-tertiary); font-size:0.85rem;" id="conditions-empty">
            프롬프트를 입력하거나 아래 조건 추가 버튼을 눌러 조건을 만드세요.
          </div>
        </div>

        <!-- 조건 추가 버튼 -->
        <div style="margin-top:14px; padding-top:14px; border-top:1px solid var(--border-color);">
          <div style="font-size:0.78rem; color:var(--text-tertiary); margin-bottom:8px; font-weight:500;">조건 직접 추가</div>
          <div style="display:flex; flex-wrap:wrap; gap:8px;">
            ${Object.entries(CONDITION_DEFS).map(([type, def]) => `
              <button onclick="window._screenerAddCondition('${type}')"
                style="padding:5px 12px; border-radius:8px; background:var(--bg-tertiary); border:1px solid var(--border-color); color:var(--text-secondary); font-size:0.78rem; cursor:pointer; transition:all 0.15s; display:flex; align-items:center; gap:5px;"
                onmouseover="this.style.borderColor='var(--accent-primary)'; this.style.color='var(--accent-primary)'"
                onmouseout="this.style.borderColor='var(--border-color)'; this.style.color='var(--text-secondary)'"
              >${def.icon} ${def.label}</button>
            `).join('')}
          </div>
        </div>
      </div>

      <!-- 스캔 실행 -->
      <div class="card" style="background: linear-gradient(135deg, rgba(0,210,106,0.08) 0%, rgba(108,92,231,0.08) 100%);">
        <div style="display:flex; align-items:center; gap:14px; flex-wrap:wrap;">
          <div style="flex:1; min-width:200px;">
            <div style="font-size:0.85rem; font-weight:600; margin-bottom:4px;">스캔 종목 수</div>
            <div style="display:flex; align-items:center; gap:10px;">
              <input type="range" id="scan-count-slider" min="10" max="100" step="10" value="50"
                style="flex:1; accent-color:var(--accent-primary);"
                oninput="document.getElementById('scan-count-val').textContent=this.value; screenerState.scanCount=parseInt(this.value);" />
              <span id="scan-count-val" style="font-weight:700; color:var(--accent-primary); min-width:35px;">50</span>종목
            </div>
          </div>
          <button class="btn btn-primary" id="btn-run-scan"
            style="padding:12px 28px; font-size:0.95rem; font-weight:700; display:flex; align-items:center; gap:8px;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            종목 스캔 실행
          </button>
        </div>
      </div>

      <!-- 스캔 결과 -->
      <div id="scan-results-section" style="display:none;">
        <div class="card">
          <div class="card-header" style="margin-bottom:16px;">
            <span class="card-title" id="scan-results-title">🔍 검색 결과</span>
            <button class="btn btn-outline" id="btn-export-kiwoom" style="font-size:0.8rem; padding:5px 14px;"
              onclick="window._screenerExportKiwoom()">
              📋 키움 조건식 내보내기
            </button>
          </div>
          <div id="scan-results-content"></div>
        </div>
      </div>

    </div>

    <!-- 오른쪽 사이드바 -->
    <div style="display:flex; flex-direction:column; gap:16px;">

      <!-- 프리셋 템플릿 -->
      <div class="card">
        <div class="card-header" style="margin-bottom:12px;">
          <span class="card-title">📋 조건식 템플릿</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          ${PRESETS.map((preset, i) => `
            <div class="preset-card" onclick="window._screenerApplyPreset(${i})"
              style="padding:12px 14px; border-radius:10px; border:1px solid var(--border-color); cursor:pointer; transition:all 0.15s; background:var(--bg-tertiary);"
              onmouseover="this.style.borderColor='var(--accent-primary)'; this.style.background='rgba(108,92,231,0.08)'"
              onmouseout="this.style.borderColor='var(--border-color)'; this.style.background='var(--bg-tertiary)'"
            >
              <div style="font-weight:600; font-size:0.88rem; margin-bottom:3px;">${preset.name}</div>
              <div style="font-size:0.75rem; color:var(--text-tertiary);">${preset.desc}</div>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- 키움 HTS 연동 -->
      <div class="card">
        <div class="card-header" style="margin-bottom:12px;">
          <span class="card-title">🔗 키움 HTS 연동</span>
          <div id="kiwoom-status-badge" style="padding:3px 10px; border-radius:20px; font-size:0.73rem; font-weight:600; background:rgba(255,100,100,0.15); color:#ff6464;">미연결</div>
        </div>
        <div id="kiwoom-conditions-content">
          <p style="font-size:0.8rem; color:var(--text-tertiary); line-height:1.6;">
            키움증권 Open API WebSocket에 연결되면 HTS에 저장된 조건식을 직접 불러와 실행할 수 있습니다.
          </p>
          <button class="btn btn-outline" id="btn-check-kiwoom" onclick="window._screenerCheckKiwoom()"
            style="width:100%; margin-top:10px; font-size:0.82rem;">
            🔄 연결 상태 확인
          </button>
        </div>
      </div>

      <!-- 키움 조건식 형식 안내 -->
      <div class="card">
        <div class="card-header" style="margin-bottom:10px;">
          <span class="card-title">📖 키움 조건식 형식</span>
        </div>
        <div style="font-size:0.79rem; color:var(--text-secondary); line-height:1.7;">
          <div style="margin-bottom:8px; font-weight:600; color:var(--text-primary);">지원 조건 항목</div>
          ${[
            ['📈', '이동평균선 크로스 (MA5/10/20/60/120)'],
            ['📊', '이동평균 정배열/역배열'],
            ['🔄', 'RSI 과매수/과매도'],
            ['⚡', 'MACD 크로스 신호'],
            ['🎯', '볼린저밴드 상/하단'],
            ['📦', '거래량 급증/감소'],
            ['💰', '현재가 vs 이동평균'],
            ['🚀', 'ADX 추세 강도'],
          ].map(([icon, text]) => `
            <div style="display:flex; gap:8px; padding:3px 0;">
              <span>${icon}</span>
              <span>${text}</span>
            </div>
          `).join('')}
        </div>
      </div>

    </div>
  </div>

  <!-- 키움 조건식 내보내기 모달 -->
  <div id="kiwoom-export-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:1000; align-items:center; justify-content:center;">
    <div style="background:var(--bg-secondary); border-radius:16px; padding:28px; max-width:600px; width:90%; max-height:80vh; display:flex; flex-direction:column; gap:16px; border:1px solid var(--border-color);">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h3 style="font-size:1.05rem; font-weight:700;">📋 키움증권 조건식 스크립트</h3>
        <button onclick="document.getElementById('kiwoom-export-modal').style.display='none'"
          style="background:none; border:none; cursor:pointer; color:var(--text-secondary); font-size:1.5rem; line-height:1;">&times;</button>
      </div>
      <pre id="kiwoom-export-content"
        style="background:var(--bg-tertiary); border-radius:10px; padding:16px; font-size:0.8rem; overflow:auto; flex:1; color:var(--text-primary); line-height:1.7; white-space:pre-wrap; border:1px solid var(--border-color);">
      </pre>
      <div style="display:flex; gap:10px;">
        <button class="btn btn-primary" onclick="window._screenerCopyKiwoom()" style="flex:1;">
          📋 클립보드에 복사
        </button>
        <button class="btn btn-outline" onclick="document.getElementById('kiwoom-export-modal').style.display='none'" style="flex:1;">닫기</button>
      </div>
    </div>
  </div>

</div>`;
}

// ─── 조건 목록 렌더링 ───────────────────────────────────────────────
function renderConditionsList() {
  const list = document.getElementById('conditions-list');
  const empty = document.getElementById('conditions-empty');
  if (!list) return;

  if (screenerState.conditions.length === 0) {
    list.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-tertiary); font-size:0.85rem;" id="conditions-empty">프롬프트를 입력하거나 아래 조건 추가 버튼을 눌러 조건을 만드세요.</div>`;
    return;
  }

  list.innerHTML = screenerState.conditions.map((cond, i) => {
    const def = CONDITION_DEFS[cond.type];
    if (!def) return '';
    const label = def.toLabel(cond);

    const params = renderConditionParams(cond, i);
    return `
    <div class="condition-card" style="padding:10px 14px; border-radius:10px; background:var(--bg-tertiary); border:1px solid var(--border-color);">
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:${params ? '8px' : '0'};">
        <span style="font-size:1.1rem; flex-shrink:0;">${def.icon}</span>
        <div style="flex:1; min-width:0;">
          <span style="font-weight:600; font-size:0.88rem; color:var(--text-primary);">${def.label}</span>
          <span style="font-size:0.78rem; color:var(--accent-primary); margin-left:8px;">${label}</span>
        </div>
        <button onclick="window._screenerRemoveCondition(${i})"
          style="width:26px; height:26px; border-radius:6px; background:rgba(255,100,100,0.1); border:1px solid rgba(255,100,100,0.3); color:#ff6464; cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; font-size:1rem; line-height:1; transition:all 0.15s;"
          onmouseover="this.style.background='rgba(255,100,100,0.2)'"
          onmouseout="this.style.background='rgba(255,100,100,0.1)'"
        >&times;</button>
      </div>
      ${params ? `<div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; padding-left:26px;">${params}</div>` : ''}
    </div>`;
  }).join('');
}

function renderConditionParams(cond, idx) {
  const parts = [];

  if (cond.type === 'rsi') {
    const ops = ['lt', 'lte', 'gt', 'gte'];
    const opLabels = ['<', '≤', '>', '≥'];
    parts.push(`
      <select onchange="window._screenerUpdateParam(${idx},'operator',this.value)"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        ${ops.map((op, i) => `<option value="${op}" ${cond.operator === op ? 'selected' : ''}>${opLabels[i]}</option>`).join('')}
      </select>
      <input type="number" value="${cond.value}" min="1" max="100"
        onchange="window._screenerUpdateParam(${idx},'value',parseFloat(this.value))"
        style="width:60px; padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem; text-align:center;" />
    `);
  } else if (cond.type === 'sma_cross') {
    parts.push(`
      <select onchange="window._screenerUpdateParam(${idx},'direction',this.value)"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        <option value="up" ${cond.direction === 'up' ? 'selected' : ''}>골든크로스</option>
        <option value="down" ${cond.direction === 'down' ? 'selected' : ''}>데드크로스</option>
      </select>
      <select onchange="window._screenerUpdateParam(${idx},'fast',parseInt(this.value))"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        ${[3,5,10,20].map(v => `<option value="${v}" ${cond.fast === v ? 'selected' : ''}>MA${v}</option>`).join('')}
      </select>
      <select onchange="window._screenerUpdateParam(${idx},'slow',parseInt(this.value))"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        ${[10,20,60,120].map(v => `<option value="${v}" ${cond.slow === v ? 'selected' : ''}>MA${v}</option>`).join('')}
      </select>
    `);
  } else if (cond.type === 'macd_cross') {
    parts.push(`
      <select onchange="window._screenerUpdateParam(${idx},'direction',this.value)"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        <option value="up" ${cond.direction === 'up' ? 'selected' : ''}>골든크로스</option>
        <option value="down" ${cond.direction === 'down' ? 'selected' : ''}>데드크로스</option>
      </select>
    `);
  } else if (cond.type === 'bollinger') {
    parts.push(`
      <select onchange="window._screenerUpdateParam(${idx},'direction',this.value)"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        <option value="touch_lower" ${cond.direction === 'touch_lower' ? 'selected' : ''}>하단 터치</option>
        <option value="touch_upper" ${cond.direction === 'touch_upper' ? 'selected' : ''}>상단 돌파</option>
        <option value="squeeze" ${cond.direction === 'squeeze' ? 'selected' : ''}>수축(스퀴즈)</option>
      </select>
    `);
  } else if (cond.type === 'volume_spike') {
    parts.push(`
      <input type="number" value="${cond.multiplier}" min="1.1" max="10" step="0.5"
        onchange="window._screenerUpdateParam(${idx},'multiplier',parseFloat(this.value))"
        style="width:65px; padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem; text-align:center;" />
      <span style="font-size:0.78rem; color:var(--text-tertiary);">배 이상</span>
    `);
  } else if (cond.type === 'price_vs_sma') {
    parts.push(`
      <select onchange="window._screenerUpdateParam(${idx},'period',parseInt(this.value))"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        ${[5,10,20,60,120].map(v => `<option value="${v}" ${cond.period === v ? 'selected' : ''}>MA${v}</option>`).join('')}
      </select>
      <select onchange="window._screenerUpdateParam(${idx},'direction',this.value)"
        style="padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem;">
        <option value="above" ${cond.direction === 'above' ? 'selected' : ''}>위</option>
        <option value="below" ${cond.direction === 'below' ? 'selected' : ''}>아래</option>
      </select>
    `);
  } else if (cond.type === 'adx_trend') {
    parts.push(`
      <input type="number" value="${cond.value || 25}" min="10" max="60"
        onchange="window._screenerUpdateParam(${idx},'value',parseFloat(this.value))"
        style="width:60px; padding:4px 6px; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-primary); font-size:0.8rem; text-align:center;" />
      <span style="font-size:0.78rem; color:var(--text-tertiary);">초과</span>
    `);
  }

  if (parts.length === 0) return '';
  return parts.join('');
}

// ─── 스캔 결과 렌더링 ───────────────────────────────────────────────
function renderScanResults(data) {
  const section = document.getElementById('scan-results-section');
  const content = document.getElementById('scan-results-content');
  const title = document.getElementById('scan-results-title');
  if (!section || !content) return;

  section.style.display = 'block';

  if (data.error) {
    title.textContent = '⚠️ 스캔 오류';
    content.innerHTML = `<div style="padding:20px; text-align:center; color:#ff6464;">${data.error}</div>`;
    return;
  }

  const { count, scanned, logic, results } = data;
  title.textContent = `🔍 검색 결과 — ${count}개 종목 매칭 (${scanned}개 스캔)`;

  if (!results || results.length === 0) {
    content.innerHTML = `
      <div style="padding:40px; text-align:center; color:var(--text-tertiary);">
        <div style="font-size:2.5rem; margin-bottom:10px;">🔍</div>
        <div style="font-size:0.9rem;">조건에 맞는 종목이 없습니다.</div>
        <div style="font-size:0.8rem; margin-top:6px;">조건을 조정하거나 스캔 수를 늘려보세요.</div>
      </div>`;
    return;
  }

  content.innerHTML = `
    <div style="overflow-x:auto;">
      <table class="stock-table" style="width:100%;">
        <thead>
          <tr>
            <th>#</th>
            <th>종목명</th>
            <th>현재가</th>
            <th>거래량</th>
            <th>RSI</th>
            <th>트리거된 조건</th>
          </tr>
        </thead>
        <tbody>
          ${results.map((r, i) => {
            const snap = r.snapshot || {};
            const rsiVal = snap.rsi != null ? snap.rsi.toFixed(1) : '-';
            const rsiColor = snap.rsi != null
              ? (snap.rsi <= 30 ? '#00D26A' : snap.rsi >= 70 ? '#ff6464' : 'var(--text-secondary)')
              : 'var(--text-secondary)';

            return `
            <tr onclick="window.location.hash='#/stock/${r.code}'" style="cursor:pointer;">
              <td style="color:var(--text-tertiary); width:36px;">${i + 1}</td>
              <td>
                <div class="stock-name-cell">
                  <span class="name">${r.name}</span>
                  <span class="code">${r.code}</span>
                </div>
              </td>
              <td style="font-weight:600;">${r.price ? r.price.toLocaleString('ko-KR') : '-'}원</td>
              <td style="color:var(--text-secondary);">${r.volume ? formatVolume(r.volume) : '-'}</td>
              <td style="font-weight:700; color:${rsiColor};">${rsiVal}</td>
              <td>
                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                  ${(r.triggered || []).map(t => `<span style="padding:2px 8px; border-radius:12px; background:rgba(108,92,231,0.15); color:var(--accent-primary); font-size:0.72rem;">${t}</span>`).join('')}
                </div>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`;
}

function formatVolume(v) {
  if (!v) return '-';
  if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
  if (v >= 1000) return (v / 1000).toFixed(0) + 'K';
  return v.toString();
}

// ─── 이벤트 연결 ────────────────────────────────────────────────────
function attachScreenerEvents() {
  // 프롬프트 파싱
  document.getElementById('btn-parse-prompt')?.addEventListener('click', () => {
    const text = document.getElementById('screener-prompt')?.value?.trim();
    if (!text) return;
    const parsed = parsePrompt(text);
    if (parsed.length === 0) {
      showToast('인식된 조건이 없습니다. 다른 표현을 시도해보세요.', 'warn');
      return;
    }
    screenerState.conditions = parsed;
    renderConditionsList();
    showToast(`${parsed.length}개 조건이 생성되었습니다!`, 'success');
  });

  // Enter 키로 파싱
  document.getElementById('screener-prompt')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      document.getElementById('btn-parse-prompt')?.click();
    }
  });

  // 초기화
  document.getElementById('btn-clear-conditions')?.addEventListener('click', () => {
    screenerState.conditions = [];
    document.getElementById('screener-prompt').value = '';
    renderConditionsList();
  });

  // 스캔 실행
  document.getElementById('btn-run-scan')?.addEventListener('click', runScan);

  // 전역 함수 등록
  window._screenerSetPrompt = (text) => {
    const ta = document.getElementById('screener-prompt');
    if (ta) { ta.value = text; ta.focus(); }
  };

  window._screenerSetLogic = (logic) => {
    screenerState.logic = logic;
    document.getElementById('btn-logic-and').style.background = logic === 'AND' ? 'var(--accent-primary)' : 'var(--bg-tertiary)';
    document.getElementById('btn-logic-and').style.color = logic === 'AND' ? 'white' : 'var(--text-secondary)';
    document.getElementById('btn-logic-or').style.background = logic === 'OR' ? 'var(--accent-primary)' : 'var(--bg-tertiary)';
    document.getElementById('btn-logic-or').style.color = logic === 'OR' ? 'white' : 'var(--text-secondary)';
  };

  window._screenerAddCondition = (type) => {
    const def = CONDITION_DEFS[type];
    if (!def) return;
    screenerState.conditions.push({ type, ...def.defaultParams });
    renderConditionsList();
  };

  window._screenerRemoveCondition = (idx) => {
    screenerState.conditions.splice(idx, 1);
    renderConditionsList();
  };

  window._screenerUpdateParam = (idx, key, value) => {
    if (screenerState.conditions[idx]) {
      screenerState.conditions[idx][key] = value;
      renderConditionsList();
    }
  };

  window._screenerApplyPreset = (idx) => {
    const preset = PRESETS[idx];
    if (!preset) return;
    screenerState.conditions = preset.conditions.map(c => ({ ...c }));
    screenerState.logic = preset.logic;
    window._screenerSetLogic(preset.logic);
    renderConditionsList();
    showToast(`"${preset.name}" 템플릿 적용됨`, 'success');
  };

  window._screenerExportKiwoom = () => {
    const script = toKiwoomScript(screenerState.conditions, screenerState.logic);
    const pre = document.getElementById('kiwoom-export-content');
    if (pre) pre.textContent = script;
    document.getElementById('kiwoom-export-modal').style.display = 'flex';
  };

  window._screenerCopyKiwoom = () => {
    const text = document.getElementById('kiwoom-export-content')?.textContent;
    if (text) {
      navigator.clipboard.writeText(text).then(() => {
        showToast('클립보드에 복사되었습니다!', 'success');
      });
    }
  };

  window._screenerCheckKiwoom = checkKiwoomConnection;
}

// ─── 스캔 실행 ──────────────────────────────────────────────────────
async function runScan() {
  if (screenerState.scanning) return;
  if (screenerState.conditions.length === 0) {
    showToast('조건을 최소 1개 이상 추가하세요.', 'warn');
    return;
  }

  screenerState.scanning = true;
  const btn = document.getElementById('btn-run-scan');
  if (btn) {
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" class="spin" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3"/></svg> 스캔 중...`;
    btn.disabled = true;
  }

  // 섹션을 로딩 상태로 표시
  const section = document.getElementById('scan-results-section');
  const content = document.getElementById('scan-results-content');
  const title = document.getElementById('scan-results-title');
  if (section) section.style.display = 'block';
  if (title) title.textContent = '🔄 스캔 실행 중...';
  if (content) content.innerHTML = `
    <div style="padding:40px; text-align:center; color:var(--text-tertiary);">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" class="spin" stroke="var(--accent-primary)" stroke-width="2" style="margin-bottom:12px;">
        <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3"/>
      </svg>
      <div style="font-size:0.9rem;">종목을 스캔하고 있습니다...</div>
      <div style="font-size:0.8rem; margin-top:4px;">${screenerState.scanCount}개 종목 분석 중</div>
    </div>`;

  try {
    const payload = {
      conditions: screenerState.conditions,
      logic: screenerState.logic,
      scan_count: screenerState.scanCount,
    };

    const res = await fetch(`${SCREENER_API}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    screenerState.results = data.results || [];
    renderScanResults(data);
  } catch (err) {
    renderScanResults({
      error: `스캔 실패: ${err.message} — 백엔드 서버가 실행 중인지 확인하세요.`,
    });
  } finally {
    screenerState.scanning = false;
    if (btn) {
      btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> 종목 스캔 실행`;
      btn.disabled = false;
    }
  }
}

// ─── 키움 연결 확인 ─────────────────────────────────────────────────
async function checkKiwoomConnection() {
  const badge = document.getElementById('kiwoom-status-badge');
  const kContent = document.getElementById('kiwoom-conditions-content');

  try {
    const res = await fetch(`${SCREENER_API}/kiwoom/conditions`, { signal: AbortSignal.timeout(4000) });
    const data = await res.json();

    if (data.error) {
      screenerState.kiwoomConnected = false;
      if (badge) {
        badge.textContent = '미연결';
        badge.style.background = 'rgba(255,100,100,0.15)';
        badge.style.color = '#ff6464';
      }
      if (kContent) {
        kContent.innerHTML = `
          <p style="font-size:0.8rem; color:var(--text-tertiary); line-height:1.6;">${data.error}</p>
          <button class="btn btn-outline" onclick="window._screenerCheckKiwoom()"
            style="width:100%; margin-top:10px; font-size:0.82rem;">🔄 재시도</button>`;
      }
    } else if (data.conditions && data.conditions.length > 0) {
      screenerState.kiwoomConnected = true;
      screenerState.kiwoomConditions = data.conditions;
      if (badge) {
        badge.textContent = '연결됨';
        badge.style.background = 'rgba(0,210,106,0.15)';
        badge.style.color = '#00D26A';
      }
      renderKiwoomConditions(data.conditions);
    }
  } catch (e) {
    if (badge) {
      badge.textContent = '미연결';
      badge.style.background = 'rgba(255,100,100,0.15)';
      badge.style.color = '#ff6464';
    }
  }
}

function renderKiwoomConditions(conditions) {
  const content = document.getElementById('kiwoom-conditions-content');
  if (!content) return;
  content.innerHTML = `
    <div style="font-size:0.78rem; color:var(--text-tertiary); margin-bottom:8px;">HTS에 저장된 조건식 (${conditions.length}개)</div>
    <div style="display:flex; flex-direction:column; gap:6px; max-height:200px; overflow-y:auto;">
      ${conditions.map((c) => `
        <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 10px; border-radius:8px; background:var(--bg-tertiary); border:1px solid var(--border-color);">
          <div>
            <div style="font-size:0.83rem; font-weight:600;">${c.name || c.seq}</div>
            <div style="font-size:0.72rem; color:var(--text-tertiary);">조건번호: ${c.seq}</div>
          </div>
          <button onclick="window._screenerRunKiwoom('${c.seq}')"
            style="padding:4px 10px; border-radius:6px; background:rgba(108,92,231,0.15); border:1px solid rgba(108,92,231,0.3); color:var(--accent-primary); font-size:0.75rem; cursor:pointer;">실행</button>
        </div>
      `).join('')}
    </div>
    <button class="btn btn-outline" onclick="window._screenerCheckKiwoom()"
      style="width:100%; margin-top:8px; font-size:0.82rem;">🔄 새로고침</button>`;

  window._screenerRunKiwoom = async (seq) => {
    const section = document.getElementById('scan-results-section');
    const title = document.getElementById('scan-results-title');
    const content = document.getElementById('scan-results-content');
    if (section) section.style.display = 'block';
    if (title) title.textContent = '🔄 키움 HTS 조건 검색 중...';
    if (content) content.innerHTML = `<div style="padding:30px; text-align:center; color:var(--text-tertiary);">키움 HTS 조건식 실행 중...</div>`;

    try {
      const res = await fetch(`${SCREENER_API}/kiwoom/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seq, search_type: '0' }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      if (title) title.textContent = `🔍 키움 HTS 결과 — ${data.count}개 종목`;
      if (content && data.results) {
        content.innerHTML = `
          <div style="overflow-x:auto;">
            <table class="stock-table">
              <thead><tr><th>#</th><th>종목코드</th><th>종목명</th></tr></thead>
              <tbody>
                ${data.results.map((r, i) => `
                  <tr onclick="window.location.hash='#/stock/${r.code || r}'" style="cursor:pointer;">
                    <td>${i + 1}</td>
                    <td>${r.code || r}</td>
                    <td>${r.name || '-'}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>`;
      }
    } catch (e) {
      if (title) title.textContent = '⚠️ 키움 검색 오류';
      if (content) content.innerHTML = `<div style="padding:20px; color:#ff6464;">${e.message}</div>`;
    }
  };
}

// ─── 토스트 알림 ─────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const existing = document.getElementById('screener-toast');
  if (existing) existing.remove();

  const colors = {
    success: { bg: 'rgba(0,210,106,0.15)', border: 'rgba(0,210,106,0.4)', text: '#00D26A' },
    warn: { bg: 'rgba(255,180,0,0.15)', border: 'rgba(255,180,0,0.4)', text: '#FFB400' },
    info: { bg: 'rgba(108,92,231,0.15)', border: 'rgba(108,92,231,0.4)', text: 'var(--accent-primary)' },
  };
  const c = colors[type] || colors.info;
  const toast = document.createElement('div');
  toast.id = 'screener-toast';
  toast.textContent = msg;
  toast.style.cssText = `
    position:fixed; bottom:24px; right:24px; z-index:9999;
    padding:12px 20px; border-radius:10px;
    background:${c.bg}; border:1px solid ${c.border}; color:${c.text};
    font-size:0.88rem; font-weight:600;
    animation: fadeInUp 0.3s ease;
    backdrop-filter: blur(8px);
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
