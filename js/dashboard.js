// ==========================================
// Dashboard Page Module
// ==========================================

import { marketIndices, recommendations, stocks, getStockByCode, getTopByVolume, getTopGainers, getTopLosers, formatPrice, formatVolume, sectorPerformance, generateDates } from './data.js';
import { createMiniSparkline, createLineChart, createBarChart } from './chart.js';

export function renderDashboard() {
    const container = document.getElementById('page-content');

    container.innerHTML = `
    <div class="dashboard-grid">
      <!-- Market Index Cards -->
      <div class="grid-row cols-4">
        ${marketIndices.map((idx, i) => renderIndexCard(idx, i)).join('')}
      </div>

      <!-- AI Recommendations + Top Volume -->
      <div class="grid-row cols-2-1">
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              오늘의 AI 추천 종목
            </span>
            <a href="#/recommend" class="btn btn-sm btn-outline">전체보기</a>
          </div>
          <div class="grid-row cols-2" style="gap: 12px;">
            ${recommendations.slice(0, 4).map(rec => renderRecommendCard(rec)).join('')}
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              업종별 등락
            </span>
          </div>
          <div style="height: 250px;">
            <canvas id="sector-chart"></canvas>
          </div>
        </div>
      </div>

      <!-- Charts + Top Gainers/Losers -->
      <div class="grid-row cols-2">
        <div class="card">
          <div class="card-header">
            <span class="card-title">코스피 추이 (30일)</span>
            <span class="card-badge ${marketIndices[0].change >= 0 ? 'badge-up' : 'badge-down'}">
              ${marketIndices[0].change >= 0 ? '+' : ''}${marketIndices[0].changePercent}%
            </span>
          </div>
          <div style="height: 220px;">
            <canvas id="kospi-chart"></canvas>
          </div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">코스닥 추이 (30일)</span>
            <span class="card-badge ${marketIndices[1].change >= 0 ? 'badge-up' : 'badge-down'}">
              ${marketIndices[1].change >= 0 ? '+' : ''}${marketIndices[1].changePercent}%
            </span>
          </div>
          <div style="height: 220px;">
            <canvas id="kosdaq-chart"></canvas>
          </div>
        </div>
      </div>

      <!-- Top Volume Table -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg>
            거래량 TOP 10
          </span>
        </div>
        <div class="stock-table-wrap">
          <table class="stock-table" id="volume-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>종목명</th>
                <th>현재가</th>
                <th>전일 대비</th>
                <th>등락률</th>
                <th>거래량</th>
              </tr>
            </thead>
            <tbody>
              ${getTopByVolume(10).map((stock, i) => renderTableRow(stock, i + 1)).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Gainers + Losers -->
      <div class="grid-row cols-2">
        <div class="card">
          <div class="card-header">
            <span class="card-title" style="color: var(--color-up);">
              📈 상승 TOP 5
            </span>
          </div>
          <div class="stock-table-wrap">
            <table class="stock-table">
              <thead>
                <tr><th>종목명</th><th>현재가</th><th>등락률</th></tr>
              </thead>
              <tbody>
                ${getTopGainers(5).map(s => `
                  <tr onclick="window.location.hash='#/stock/${s.code}'">
                    <td><div class="stock-name-cell"><span class="name">${s.name}</span><span class="code">${s.code}</span></div></td>
                    <td style="font-weight:600;">${formatPrice(s.price)}</td>
                    <td class="text-up" style="font-weight:600;">+${s.changePercent.toFixed(2)}%</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title" style="color: var(--color-down);">
              📉 하락 TOP 5
            </span>
          </div>
          <div class="stock-table-wrap">
            <table class="stock-table">
              <thead>
                <tr><th>종목명</th><th>현재가</th><th>등락률</th></tr>
              </thead>
              <tbody>
                ${getTopLosers(5).map(s => `
                  <tr onclick="window.location.hash='#/stock/${s.code}'">
                    <td><div class="stock-name-cell"><span class="name">${s.name}</span><span class="code">${s.code}</span></div></td>
                    <td style="font-weight:600;">${formatPrice(s.price)}</td>
                    <td class="${s.changePercent >= 0 ? 'text-up' : 'text-down'}" style="font-weight:600;">${s.changePercent >= 0 ? '+' : ''}${s.changePercent.toFixed(2)}%</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;

    // Initialize charts after DOM is rendered
    setTimeout(() => {
        initDashboardCharts();
    }, 100);
}

function renderIndexCard(idx, i) {
    const isUp = idx.change >= 0;
    return `
    <div class="card index-card ${isUp ? 'up' : 'down'} fade-in stagger-${i + 1}">
      <div class="card-title" style="margin-bottom: 8px;">${idx.name}</div>
      <div class="index-value">${idx.value.toLocaleString('ko-KR', { minimumFractionDigits: 2 })}</div>
      <div class="index-change">
        <span class="arrow">${isUp ? '▲' : '▼'}</span>
        <span>${Math.abs(idx.change).toFixed(2)}</span>
        <span>(${isUp ? '+' : ''}${idx.changePercent.toFixed(2)}%)</span>
      </div>
      <div class="mini-chart">
        <canvas id="mini-${idx.id}" width="120" height="50"></canvas>
      </div>
    </div>
  `;
}

function renderRecommendCard(rec) {
    const stock = getStockByCode(rec.code);
    if (!stock) return '';
    const isUp = stock.change >= 0;
    const signalClass = rec.signal === 'buy' ? 'signal-buy' : rec.signal === 'sell' ? 'signal-sell' : 'signal-hold';
    const signalText = rec.signal === 'buy' ? '매수' : rec.signal === 'sell' ? '매도' : '관망';

    return `
    <div class="card recommend-card ${rec.signal}" onclick="window.location.hash='#/stock/${stock.code}'">
      <div class="recommend-header">
        <div class="recommend-stock-info">
          <span class="recommend-stock-name">${stock.name}</span>
          <span class="recommend-stock-code">${stock.code}</span>
        </div>
        <span class="recommend-signal ${signalClass}">${signalText}</span>
      </div>
      <div class="recommend-price-row">
        <span class="recommend-price">${formatPrice(stock.price)}</span>
        <span class="recommend-change ${isUp ? 'text-up' : 'text-down'}">${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%</span>
      </div>
      <div class="recommend-target">
        <span class="recommend-target-label">목표가</span>
        <span class="recommend-target-value ${rec.targetPrice > stock.price ? 'text-up' : 'text-down'}">${formatPrice(rec.targetPrice)}</span>
      </div>
      <p class="recommend-reason">${rec.reason}</p>
    </div>
  `;
}

function renderTableRow(stock, rank) {
    const isUp = stock.change >= 0;
    return `
    <tr onclick="window.location.hash='#/stock/${stock.code}'">
      <td style="font-weight: 600; color: var(--text-tertiary);">${rank}</td>
      <td>
        <div class="stock-name-cell">
          <span class="name">${stock.name}</span>
          <span class="code">${stock.code}</span>
        </div>
      </td>
      <td style="font-weight: 600;">${formatPrice(stock.price)}</td>
      <td class="${isUp ? 'text-up' : 'text-down'}">
        ${isUp ? '▲' : '▼'} ${formatPrice(Math.abs(stock.change))}
      </td>
      <td class="${isUp ? 'text-up' : 'text-down'}" style="font-weight: 600;">
        ${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%
      </td>
      <td style="color: var(--text-secondary);">${formatVolume(stock.volume)}</td>
    </tr>
  `;
}

function initDashboardCharts() {
    // Mini sparklines for index cards
    marketIndices.forEach(idx => {
        createMiniSparkline(`mini-${idx.id}`, idx.history.slice(-15));
    });

    // KOSPI 30-day chart
    const dates30 = generateDates(30);
    createLineChart('kospi-chart', dates30, marketIndices[0].history);

    // KOSDAQ 30-day chart
    createLineChart('kosdaq-chart', dates30, marketIndices[1].history);

    // Sector bar chart
    createBarChart(
        'sector-chart',
        sectorPerformance.map(s => s.name),
        sectorPerformance.map(s => s.change),
        sectorPerformance.map(s => s.color)
    );
}
