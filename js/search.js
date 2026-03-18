// ==========================================
// Search Module
// ==========================================

import { formatPrice, getStockByCode } from './data.js';
import { searchStocksApi as apiSearchStocks } from './quantApi.js';

let isDropdownOpen = false;

export function initSearch() {
    const input = document.getElementById('search-input');
    const dropdown = document.getElementById('search-dropdown');

    if (!input || !dropdown) return;

    input.addEventListener('input', async (e) => {
        const query = e.target.value.trim();
        if (query.length === 0) {
            closeDropdown();
            return;
        }

        try {
            const resultsRes = await apiSearchStocks(query);
            const results = resultsRes.results || [];

            if (results.length === 0) {
                dropdown.innerHTML = `
          <div class="search-item" style="justify-content: center; color: var(--text-tertiary); cursor: default;">
            검색 결과가 없습니다
          </div>
        `;
            } else {
                dropdown.innerHTML = results.map(stock => {
                    const isUp = (stock.change || 0) >= 0;
                    return `
            <div class="search-item" data-code="${stock.code}">
              <div class="search-item-left">
                <span class="search-item-name">${highlightMatch(stock.name, query)}</span>
                <span class="search-item-code">${stock.code}</span>
              </div>
              <div class="search-item-price">
                <div class="price">${formatPrice(stock.price || getStockByCode(stock.code)?.price || 0)}</div>
                <div class="change ${isUp ? 'text-up' : 'text-down'}">${isUp ? '+' : ''}${(stock.change_pct || 0).toFixed(2)}%</div>
              </div>
            </div>
          `;
                }).join('');
            }
            openDropdown();
        } catch (err) {
            console.error('Search failed:', err);
        }
    });

    input.addEventListener('focus', () => {
        if (input.value.trim().length > 0) {
            openDropdown();
        }
    });

    dropdown.addEventListener('click', (e) => {
        const item = e.target.closest('.search-item');
        if (item && item.dataset.code) {
            window.location.hash = `#/stock/${item.dataset.code}`;
            input.value = '';
            closeDropdown();
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#search-wrapper')) {
            closeDropdown();
        }
    });

    // Keyboard navigation
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDropdown();
            input.blur();
        }
        if (e.key === 'Enter') {
            const firstItem = dropdown.querySelector('.search-item[data-code]');
            if (firstItem) {
                window.location.hash = `#/stock/${firstItem.dataset.code}`;
                input.value = '';
                closeDropdown();
            }
        }
    });
}

function openDropdown() {
    const dropdown = document.getElementById('search-dropdown');
    if (dropdown) dropdown.classList.add('active');
    isDropdownOpen = true;
}

function closeDropdown() {
    const dropdown = document.getElementById('search-dropdown');
    if (dropdown) dropdown.classList.remove('active');
    isDropdownOpen = false;
}

function highlightMatch(text, query) {
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx < 0) return text;
    return text.substring(0, idx) +
        `<strong style="color: var(--accent-primary-light)">${text.substring(idx, idx + query.length)}</strong>` +
        text.substring(idx + query.length);
}
