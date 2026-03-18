// ==========================================
// Chart Helper Module
// Chart.js wrapper for dark-theme stock charts
// ==========================================

const chartInstances = new Map();

const defaultOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
        intersect: false,
        mode: 'index'
    },
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: 'rgba(22, 27, 34, 0.95)',
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            borderColor: 'rgba(48, 54, 61, 0.8)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            titleFont: { family: "'Inter', sans-serif", weight: '600' },
            bodyFont: { family: "'Inter', sans-serif" },
            displayColors: true,
            boxWidth: 8,
            boxHeight: 8,
            usePointStyle: true
        }
    },
    scales: {
        x: {
            grid: { color: 'rgba(48, 54, 61, 0.3)', drawBorder: false },
            ticks: { color: '#6e7681', font: { size: 11, family: "'Inter', sans-serif" }, maxRotation: 0 }
        },
        y: {
            grid: { color: 'rgba(48, 54, 61, 0.3)', drawBorder: false },
            ticks: {
                color: '#6e7681',
                font: { size: 11, family: "'Inter', sans-serif" },
                callback: function (value) {
                    return value.toLocaleString('ko-KR');
                }
            }
        }
    }
};

export function destroyChart(canvasId) {
    if (chartInstances.has(canvasId)) {
        chartInstances.get(canvasId).destroy();
        chartInstances.delete(canvasId);
    }
}

export function destroyAllCharts() {
    chartInstances.forEach((chart, id) => {
        chart.destroy();
    });
    chartInstances.clear();
}

export function createLineChart(canvasId, labels, data, options = {}) {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const isPositive = data[data.length - 1] >= data[0];
    const lineColor = isPositive ? '#00d26a' : '#ff4757';

    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.parentElement?.clientHeight || 350);
    gradient.addColorStop(0, isPositive ? 'rgba(0, 210, 106, 0.15)' : 'rgba(255, 71, 87, 0.15)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    const datasets = [{
                data,
                borderColor: lineColor,
                backgroundColor: gradient,
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHitRadius: 10,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: lineColor,
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            }];

    // Support extra datasets (e.g. moving averages)
    if (options.extraDatasets) {
        datasets.push(...options.extraDatasets);
    }

    // Support replacing datasets entirely (e.g. multi-line charts like MACD)
    if (options.datasets) {
        datasets.length = 0;
        datasets.push(...options.datasets);
    }

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets
        },
        options: {
            ...defaultOptions,
            ...options,
            scales: {
                ...defaultOptions.scales,
                ...(options.scales || {}),
                x: {
                    ...defaultOptions.scales.x,
                    ...(options.scales?.x || {})
                },
                y: {
                    ...defaultOptions.scales.y,
                    ...(options.scales?.y || {})
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                ...(options.plugins || {}),
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    ...(options.plugins?.tooltip || {}),
                    callbacks: {
                        label: function (context) {
                            return `${context.parsed.y.toLocaleString('ko-KR')}`;
                        },
                        ...(options.plugins?.tooltip?.callbacks || {})
                    }
                }
            }
        }
    });

    chartInstances.set(canvasId, chart);
    return chart;
}

export function createMiniSparkline(canvasId, data, color = null) {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const isPositive = data[data.length - 1] >= data[0];
    const lineColor = color || (isPositive ? '#00d26a' : '#ff4757');

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map((_, i) => i),
            datasets: [{
                data,
                borderColor: lineColor,
                borderWidth: 1.5,
                fill: false,
                tension: 0.4,
                pointRadius: 0,
                pointHitRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            animation: { duration: 800 }
        }
    });

    chartInstances.set(canvasId, chart);
    return chart;
}

export function createBarChart(canvasId, labels, data, colors) {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors || data.map(v => v >= 0 ? 'rgba(255, 71, 87, 0.6)' : 'rgba(9, 132, 227, 0.6)'),
                borderColor: colors || data.map(v => v >= 0 ? '#ff4757' : '#0984e3'),
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        options: {
            ...defaultOptions,
            scales: {
                ...defaultOptions.scales,
                y: {
                    ...defaultOptions.scales.y,
                    ticks: {
                        ...defaultOptions.scales.y.ticks,
                        callback: function (value) {
                            return value.toFixed(1) + '%';
                        }
                    }
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    callbacks: {
                        label: function (context) {
                            return `${context.parsed.y >= 0 ? '+' : ''}${context.parsed.y.toFixed(2)}%`;
                        }
                    }
                }
            }
        }
    });

    chartInstances.set(canvasId, chart);
    return chart;
}

export function createCandlestickChart(canvasId, data, options = {}) {
    destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');

    const datasets = [{
        label: '주가',
        data: data,
        color: { up: '#ff4757', down: '#0984e3', unchanged: '#999' } // fallback
    }];

    if (options.extraDatasets) {
        datasets.push(...options.extraDatasets);
    }

    const chart = new Chart(ctx, {
        type: 'candlestick',
        data: { datasets },
        options: {
            ...defaultOptions,
            ...options,
            parsing: false, // Required for chartjs-chart-financial
            elements: {
                candlestick: {
                    backgroundColors: { up: '#ff4757', down: '#0984e3', unchanged: '#999' },
                    borderColors: { up: '#ff4757', down: '#0984e3', unchanged: '#999' },
                    color: { up: '#ff4757', down: '#0984e3', unchanged: '#999' },
                    borderColor: { up: '#ff4757', down: '#0984e3', unchanged: '#999' }
                }
            },
            scales: {
                ...defaultOptions.scales,
                ...(options.scales || {}),
                x: {
                    ...defaultOptions.scales.x,
                    type: 'time',
                    time: {
                        unit: 'day',
                        displayFormats: {
                            day: 'MM/dd'
                        },
                        tooltipFormat: 'yyyy-MM-dd'
                    },
                    ticks: {
                        ...defaultOptions.scales.x.ticks,
                        source: 'auto'
                    },
                    ...(options.scales?.x || {})
                },
                y: {
                    ...defaultOptions.scales.y,
                    ...(options.scales?.y || {})
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                ...options.plugins,
                zoom: {
                    pan: {
                        enabled: true,
                        mode: 'x',
                        // Remove modifierKey so simple click & drag or touch pans
                    },
                    zoom: {
                        wheel: {
                            enabled: true
                        },
                        pinch: {
                            enabled: true
                        },
                        drag: {
                            enabled: false
                        },
                        mode: 'x',
                    }
                },
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    callbacks: {
                        label: function (context) {
                            const d = context.raw;
                            if (d && d.o !== undefined) {
                                return `시가: ${d.o.toLocaleString()} 고가: ${d.h.toLocaleString()} 저가: ${d.l.toLocaleString()} 종가: ${d.c.toLocaleString()}`;
                            }
                            // Fallback for line datasets (Moving Averages, etc.)
                            return `${context.dataset.label}: ${context.parsed.y.toLocaleString('ko-KR')}`;
                        }
                    }
                }
            }
        }
    });

    chartInstances.set(canvasId, chart);

    return chart;
}
