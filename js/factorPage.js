// ==========================================
// Factor Analysis Page
// ==========================================

import { getFactorRanking } from './quantApi.js';
import { stocks, formatPrice } from './data.js';
import { destroyAllCharts } from './chart.js';

export function renderFactorPage() {
    const container = document.getElementById('page-content');

    container.innerHTML = `
    <div class="dashboard-grid fade-in">
      <!-- Factor Weights -->
      <div class="card">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
          <span style="font-size:1.5rem;">⚖️</span>
          <h2 style="font-size:1.1rem; font-weight:700;">멀티팩터 분석</h2>
        </div>
        <p style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:16px;">
          팩터 가중치를 조절하여 종합 점수 기반의 종목 순위를 산출합니다.
        </p>
        <div class="factor-sliders">
          <div class="factor-slider-group">
            <label>📈 모멘텀 <span id="w-momentum-val">30%</span></label>
            <input type="range" id="w-momentum" min="0" max="100" value="30" class="factor-range" />
          </div>
          <div class="factor-slider-group">
            <label>💰 가치 <span id="w-value-val">25%</span></label>
            <input type="range" id="w-value" min="0" max="100" value="25" class="factor-range" />
          </div>
          <div class="factor-slider-group">
            <label>✨ 퀄리티 <span id="w-quality-val">25%</span></label>
            <input type="range" id="w-quality" min="0" max="100" value="25" class="factor-range" />
          </div>
          <div class="factor-slider-group">
            <label>🛡️ 저변동성 <span id="w-volatility-val">20%</span></label>
            <input type="range" id="w-volatility" min="0" max="100" value="20" class="factor-range" />
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:12px; margin-top:16px;">
          <button class="btn btn-primary btn-icon" id="factor-run-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg>
            순위 산출
          </button>
          <span id="factor-status" style="font-size:0.82rem; color:var(--text-tertiary);"></span>
        </div>
      </div>

      <!-- Rankings Table -->
      <div class="card" id="factor-results">
        <div class="card-header">
          <span class="card-title">팩터 기반 종목 순위</span>
        </div>
        <div class="stock-table-wrap">
          <table class="stock-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>종목명</th>
                <th>현재가</th>
                <th>등락률</th>
                <th>모멘텀</th>
                <th>가치</th>
                <th>퀄리티</th>
                <th>저변동성</th>
                <th>종합</th>
              </tr>
            </thead>
            <tbody id="factor-tbody"></tbody>
          </table>
        </div>
      </div>

      <!-- Factor Radar Chart -->
      <div class="grid-row cols-2">
        <div class="card">
          <div class="card-header"><span class="card-title">팩터 분포 (상위 10종목)</span></div>
          <div style="height:300px;"><canvas id="factor-radar-chart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">종합 점수 분포</span></div>
          <div style="height:300px;"><canvas id="factor-bar-chart"></canvas></div>
        </div>
      </div>
    </div>
  `;

    // Slider events
    ['momentum', 'value', 'quality', 'volatility'].forEach(f => {
        const slider = document.getElementById(`w-${f}`);
        slider.addEventListener('input', () => {
            document.getElementById(`w-${f}-val`).textContent = `${slider.value}%`;
        });
    });

    document.getElementById('factor-run-btn').addEventListener('click', loadFactorRanking);

    // Load with local data initially
    loadLocalFactorRanking();
}

async function loadFactorRanking() {
    const status = document.getElementById('factor-status');
    status.textContent = '⏳ 팩터 분석 중...';

    const weights = {
        momentum_w: parseInt(document.getElementById('w-momentum').value) / 100,
        value_w: parseInt(document.getElementById('w-value').value) / 100,
        quality_w: parseInt(document.getElementById('w-quality').value) / 100,
        volatility_w: parseInt(document.getElementById('w-volatility').value) / 100,
        count: 20,
    };

    try {
        const result = await getFactorRanking(weights);
        if (result.error || !result.rankings) {
            status.textContent = '⚠️ 백엔드 연결 실패 — 로컬 데이터 사용';
            loadLocalFactorRanking();
            return;
        }
        renderFactorResults(result.rankings);
        status.textContent = `✅ ${result.rankings.length}개 종목 팩터 분석 완료`;
    } catch {
        status.textContent = '⚠️ 백엔드 연결 실패 — 로컬 데이터 사용';
        loadLocalFactorRanking();
    }
}

function loadLocalFactorRanking() {
    const mW = parseInt(document.getElementById('w-momentum')?.value || 30) / 100;
    const vW = parseInt(document.getElementById('w-value')?.value || 25) / 100;
    const qW = parseInt(document.getElementById('w-quality')?.value || 25) / 100;
    const volW = parseInt(document.getElementById('w-volatility')?.value || 20) / 100;

    const rankings = stocks.map(s => {
        const momentum = Math.min(100, Math.max(0, 50 + s.changePercent * 10));
        const value = Math.min(100, Math.max(0, s.per ? (100 - s.per * 2) : 50));
        const quality = Math.min(100, Math.max(0, 30 + Math.random() * 50));
        const volatility = Math.min(100, Math.max(0, 40 + Math.random() * 40));

        const total = momentum * mW + value * vW + quality * qW + volatility * volW;

        return {
            code: s.code, name: s.name,
            price: s.price, change_pct: s.changePercent,
            momentum_score: Math.round(momentum * 10) / 10,
            value_score: Math.round(value * 10) / 10,
            quality_score: Math.round(quality * 10) / 10,
            volatility_score: Math.round(volatility * 10) / 10,
            total_score: Math.round(total * 10) / 10,
            rank: 0,
        };
    });

    rankings.sort((a, b) => b.total_score - a.total_score);
    rankings.forEach((r, i) => r.rank = i + 1);

    renderFactorResults(rankings);
    const status = document.getElementById('factor-status');
    if (status) status.textContent = '📌 로컬 모의 데이터';
}

function renderFactorResults(rankings) {
    destroyAllCharts();
    const tbody = document.getElementById('factor-tbody');

    tbody.innerHTML = rankings.map(r => {
        const isUp = r.change_pct >= 0;
        return `
      <tr onclick="window.location.hash='#/stock/${r.code}'" style="cursor:pointer;">
        <td style="font-weight:700; color: ${r.rank <= 3 ? 'var(--color-up)' : 'var(--text-tertiary)'};">${r.rank}</td>
        <td><div class="stock-name-cell"><span class="name">${r.name}</span><span class="code">${r.code}</span></div></td>
        <td style="font-weight:600;">${formatPrice(r.price)}</td>
        <td class="${isUp ? 'text-up' : 'text-down'}" style="font-weight:600;">${isUp ? '+' : ''}${r.change_pct.toFixed(2)}%</td>
        <td>${renderScoreBar(r.momentum_score)}</td>
        <td>${renderScoreBar(r.value_score)}</td>
        <td>${renderScoreBar(r.quality_score)}</td>
        <td>${renderScoreBar(r.volatility_score)}</td>
        <td><span style="font-weight:700; font-size:1rem; color:${getScoreColor(r.total_score)};">${r.total_score}</span></td>
      </tr>
    `;
    }).join('');

    // Radar Chart (Top 5)
    const radarCanvas = document.getElementById('factor-radar-chart');
    if (radarCanvas) {
        const top5 = rankings.slice(0, 5);
        const colors = ['#6c5ce7', '#00d26a', '#ffa502', '#ff4757', '#00cec9'];
        new Chart(radarCanvas, {
            type: 'radar',
            data: {
                labels: ['모멘텀', '가치', '퀄리티', '저변동성'],
                datasets: top5.map((r, i) => ({
                    label: r.name,
                    data: [r.momentum_score, r.value_score, r.quality_score, r.volatility_score],
                    borderColor: colors[i],
                    backgroundColor: colors[i] + '20',
                    borderWidth: 2,
                    pointRadius: 3,
                    pointBackgroundColor: colors[i],
                }))
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: { r: { beginAtZero: true, max: 100, grid: { color: 'rgba(48,54,61,0.3)' }, ticks: { color: '#6e7681', backdropColor: 'transparent' }, pointLabels: { color: '#8b949e', font: { size: 12 } } } },
                plugins: { legend: { display: true, position: 'bottom', labels: { color: '#8b949e', padding: 12, font: { size: 11 } } } }
            }
        });
    }

    // Bar Chart (Top 10 Total Score)
    const barCanvas = document.getElementById('factor-bar-chart');
    if (barCanvas) {
        const top10 = rankings.slice(0, 10);
        new Chart(barCanvas, {
            type: 'bar',
            data: {
                labels: top10.map(r => r.name),
                datasets: [{
                    label: '종합 점수',
                    data: top10.map(r => r.total_score),
                    backgroundColor: top10.map((_, i) => {
                        const hue = 270 - (i * 20);
                        return `hsla(${hue}, 70%, 60%, 0.6)`;
                    }),
                    borderColor: top10.map((_, i) => {
                        const hue = 270 - (i * 20);
                        return `hsla(${hue}, 70%, 60%, 1)`;
                    }),
                    borderWidth: 1,
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, indexAxis: 'y',
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(48,54,61,0.3)' }, ticks: { color: '#6e7681' }, max: 100 },
                    y: { grid: { display: false }, ticks: { color: '#e6edf3', font: { size: 12 } } }
                }
            }
        });
    }
}

function renderScoreBar(score) {
    const color = getScoreColor(score);
    return `
    <div style="display:flex; align-items:center; gap:6px;">
      <div style="flex:1; height:6px; background:var(--bg-tertiary); border-radius:3px; overflow:hidden; min-width:40px;">
        <div style="height:100%; width:${score}%; background:${color}; border-radius:3px;"></div>
      </div>
      <span style="font-size:0.78rem; color:${color}; min-width:28px; text-align:right;">${score}</span>
    </div>
  `;
}

function getScoreColor(score) {
    if (score >= 70) return '#00d26a';
    if (score >= 50) return '#ffa502';
    if (score >= 30) return '#e17055';
    return '#ff4757';
}
