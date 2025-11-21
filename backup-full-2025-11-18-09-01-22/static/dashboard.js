// PingIT Dashboard JavaScript

let responseTimeOverTimeChart = null;
let currentRange = '24h';
let targetColors = {}; // Store colors for each target

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    loadData();
    setInterval(loadData, 60000); // Auto-refresh every minute
    
    // Handle window resize for chart responsiveness
    let resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            if (responseTimeOverTimeChart) {
                responseTimeOverTimeChart.destroy();
                responseTimeOverTimeChart = null;
                loadData();
            }
        }, 250);
    });
    
    // Also listen for orientation change (more reliable on mobile)
    window.addEventListener('orientationchange', function() {
        setTimeout(function() {
            if (responseTimeOverTimeChart) {
                responseTimeOverTimeChart.destroy();
                responseTimeOverTimeChart = null;
                loadData();
            }
        }, 100);
    });
});

// Setup event listeners
function setupEventListeners() {
    // Time range buttons
    document.querySelectorAll('.btn-time').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.btn-time').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentRange = this.dataset.range;
            loadData();
        });
    });

    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', loadData);
}

// Load data from API
async function loadData() {
    try {
        const response = await fetch(`/api/data?range=${currentRange}`);
        const data = await response.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        updateDashboard(data);
        showSuccess('Data updated at ' + new Date().toLocaleTimeString());
    } catch (error) {
        showError('Failed to load data: ' + error.message);
    }
}

// Update dashboard with data
function updateDashboard(data) {
    const targets = data.targets || [];
    const disconnects = data.disconnects || [];
    const timeseries = data.timeseries || {};

    // Update stats
    updateStats(data);

    // Update charts
    updateChart(targets, timeseries, disconnects);

    // Update tables
    updateStatsTable(targets);
    updateDisconnectsTable(disconnects);

    // Update last update time
    const timeStr = new Date().toLocaleTimeString();
    const headerLastUpdate = document.getElementById('headerLastUpdate');
    if (headerLastUpdate) {
        headerLastUpdate.textContent = timeStr;
    }
}

// Update statistics cards
function updateStats(data) {
    document.getElementById('totalTargets').textContent = data.total_targets || 0;
    document.getElementById('totalDisconnects').textContent = data.total_disconnect_events || 0;
    document.getElementById('uptime').textContent = (data.uptime_percentage || 0) + '%';
}

// Update all charts
function updateChart(targets, timeseries, disconnects) {
    // Destroy existing charts
    if (responseTimeOverTimeChart) responseTimeOverTimeChart.destroy();

    // Response Time Over Time Chart
    if (Object.keys(timeseries).length > 0) {
        // Build a map of disconnect times by target name for quick lookup
        const disconnectsByTarget = {};
        if (disconnects && disconnects.length > 0) {
            disconnects.forEach(disconnect => {
                if (!disconnectsByTarget[disconnect.name]) {
                    disconnectsByTarget[disconnect.name] = [];
                }
                // Parse disconnect_time to milliseconds
                const disconnectTime = new Date(disconnect.last_disconnect).getTime();
                disconnectsByTarget[disconnect.name].push(disconnectTime);
            });
        }
        const colors = ['#0066cc', '#28a745', '#dc3545', '#ffc107', '#17a2b8'];
        
        // Sort target names to maintain consistent order across dashboard
        const sortedTargetNames = Object.keys(timeseries).sort();
        
        // Collect all unique timestamps from all targets
        const allTimestamps = new Set();
        for (const targetName of sortedTargetNames) {
            const data = timeseries[targetName];
            data.timestamps.forEach(ts => allTimestamps.add(ts));
        }
        const sortedTimestamps = Array.from(allTimestamps).sort();
        
        // Create a map of timestamps for each target for alignment
        const timestampMap = {};
        for (const targetName of sortedTargetNames) {
            const data = timeseries[targetName];
            timestampMap[targetName] = {};
            data.timestamps.forEach((ts, idx) => {
                timestampMap[targetName][ts] = data.avg_response_times[idx];
            });
        }
        
        // Build datasets with aligned data (null for missing timestamps)
        const datasets = [];
        let idx = 0;
        for (const targetName of sortedTargetNames) {
            const data = timeseries[targetName];
            const color = colors[idx % colors.length];
            targetColors[targetName] = color;  // Store color for later use
            
            const alignedData = sortedTimestamps.map(ts => 
                timestampMap[targetName][ts] || null
            );
            datasets.push({
                label: targetName,
                data: alignedData,
                borderColor: color,
                backgroundColor: color + '20',
                borderWidth: 2,
                tension: 0.3,
                fill: false,
                spanGaps: true  // Don't draw lines through null values
            });
            idx++;
        }
        
        const ctxOverTime = document.getElementById('responseTimeOverTimeChart').getContext('2d');
        
        // Convert datasets to use x values (timestamps) instead of labels for proper time axis
        const timeseriesDatasets = datasets.map(dataset => {
            const points = [];
            for (let i = 0; i < sortedTimestamps.length; i++) {
                const ts = sortedTimestamps[i];
                const dataIndex = dataset.data.indexOf(dataset.data.find((_, idx) => {
                    return dataset.data[idx] !== null;
                }));
                // Map timestamps to dataset values
                const value = dataset.data[i];
                if (value !== null) {
                    points.push({
                        x: new Date(ts).getTime(),
                        y: value
                    });
                }
            }
            return {
                ...dataset,
                data: points
            };
        });
        
        const isPortrait = window.innerWidth < 768;
        
        // Hide points in all modes (no circles on the chart)
        timeseriesDatasets.forEach(dataset => {
            dataset.pointRadius = 0;
            dataset.pointHoverRadius = 0;
        });
        
        // Calculate min and max timestamps from all data points
        let minTimestamp = Infinity;
        let maxTimestamp = -Infinity;
        timeseriesDatasets.forEach(dataset => {
            dataset.data.forEach(point => {
                if (point.x < minTimestamp) minTimestamp = point.x;
                if (point.x > maxTimestamp) maxTimestamp = point.x;
            });
        });
        
        // If no data, use current time as reference
        if (!isFinite(minTimestamp)) {
            minTimestamp = Date.now();
            maxTimestamp = Date.now();
        }
        
        // Plugin to draw disconnect markers
        const disconnectMarkersPlugin = {
            id: 'disconnectMarkers',
            afterDraw(chart) {
                const ctx = chart.ctx;
                const xScale = chart.scales.x;
                const yScale = chart.scales.y;
                
                if (!xScale || !yScale) return;
                
                // Get all datasets to find their target names and colors
                chart.data.datasets.forEach((dataset) => {
                    const targetName = dataset.label;
                    const targetColor = dataset.borderColor;
                    const disconnectTimes = disconnectsByTarget[targetName] || [];
                    
                    // Find the data point for this target to calculate trend line position
                    const dataPoints = dataset.data || [];
                    
                    // Draw disconnect markers
                    disconnectTimes.forEach(disconnectTimeMs => {
                        const x = xScale.getPixelForValue(disconnectTimeMs);
                        const yTop = yScale.getPixelForValue(yScale.max);
                        const yBottom = yScale.getPixelForValue(yScale.min);
                        
                        // Find the response time value at this disconnect time (for positioning on trend)
                        let yValue = null;
                        let nearestDistance = Infinity;
                        let nearestPoint = null;
                        
                        // Find the closest data point (within time range)
                        dataPoints.forEach(point => {
                            const distance = Math.abs(point.x - disconnectTimeMs);
                            if (distance < nearestDistance) {
                                nearestDistance = distance;
                                nearestPoint = point;
                            }
                        });
                        
                        // Use nearest point if found, otherwise estimate from average
                        if (nearestPoint) {
                            yValue = yScale.getPixelForValue(nearestPoint.y);
                        } else if (dataPoints.length > 0) {
                            // Calculate average response time from all data points
                            const avgResponseTime = dataPoints.reduce((sum, p) => sum + p.y, 0) / dataPoints.length;
                            yValue = yScale.getPixelForValue(avgResponseTime);
                        } else {
                            // No data points, use middle
                            yValue = (yTop + yBottom) / 2;
                        }
                        
                        // Draw X mark on the trend line
                        const markSize = 7;
                        ctx.strokeStyle = targetColor;
                        ctx.lineWidth = 3;
                        ctx.lineCap = 'round';
                        ctx.lineJoin = 'round';
                        
                        // X mark
                        ctx.beginPath();
                        ctx.moveTo(x - markSize, yValue - markSize);
                        ctx.lineTo(x + markSize, yValue + markSize);
                        ctx.stroke();
                        
                        ctx.beginPath();
                        ctx.moveTo(x + markSize, yValue - markSize);
                        ctx.lineTo(x - markSize, yValue + markSize);
                        ctx.stroke();
                        
                        // Draw circle around X
                        ctx.strokeStyle = targetColor;
                        ctx.lineWidth = 2;
                        ctx.globalAlpha = 0.8;
                        ctx.beginPath();
                        ctx.arc(x, yValue, markSize + 3, 0, Math.PI * 2);
                        ctx.stroke();
                        ctx.globalAlpha = 1;
                    });
                });
            }
        };
        
        // Register the plugin
        Chart.register(disconnectMarkersPlugin);
        
        responseTimeOverTimeChart = new Chart(ctxOverTime, {
            type: 'line',
            data: {
                datasets: timeseriesDatasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: !isPortrait,
                plugins: {
                    filler: false,
                    legend: { 
                        display: false  // Hide built-in legend
                    },
                    disconnectMarkers: {}  // Use the plugin defined above
                },
                scales: {
                    x: {
                        type: 'linear',
                        position: 'bottom',
                        title: { display: true, text: 'Time' },
                        min: minTimestamp,
                        max: maxTimestamp,
                        ticks: {
                            callback: function(value) {
                                return new Date(value).toLocaleTimeString();
                            }
                        }
                    },
                    y: {
                        title: { display: true, text: 'Response Time (ms)' },
                        beginAtZero: true
                    }
                }
            }
        });
        
        // Create custom legend above the table
        const legendContainer = document.getElementById('chartLegend');
        legendContainer.innerHTML = '';
        
        const legendHTML = datasets.map((dataset, idx) => `
            <div class="legend-item">
                <span class="legend-color" style="background-color: ${dataset.borderColor}"></span>
                <span class="legend-label" style="color: ${dataset.borderColor}; font-weight: bold;">${dataset.label}</span>
            </div>
        `).join('');
        
        legendContainer.innerHTML = legendHTML;
    }
}

// Update statistics table
function updateStatsTable(targets) {
    const tbody = document.getElementById('statsTableBody');
    tbody.innerHTML = '';

    if (targets.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="loading">No data available</td></tr>';
        return;
    }

    targets.forEach(target => {
        let statusBadge = 'status-good';
        let statusText = 'Excellent';

        if (target.success_rate === 100) {
            statusBadge = 'status-good';
            statusText = 'Excellent';
        } else if (target.success_rate >= 95) {
            statusBadge = 'status-warning';
            statusText = 'Good';
        } else {
            statusBadge = 'status-bad';
            statusText = 'Poor';
        }

        const avgRespTime = (parseFloat(target.avg_response_time) || 0).toFixed(2);
        const minRespTime = (parseFloat(target.min_response_time) || 0).toFixed(2);
        const maxRespTime = (parseFloat(target.max_response_time) || 0).toFixed(2);

        // Table row
        const row = document.createElement('tr');
        const targetColor = targetColors[target.name] || '#000000';
        row.innerHTML = `
            <td><strong style="color: ${targetColor};">${target.name}</strong></td>
            <td><code>${target.host}</code></td>
            <td>${target.pings || 0}</td>
            <td>${(target.success_rate || 0).toFixed(2)}%</td>
            <td>${avgRespTime} ms</td>
            <td>${minRespTime} ms</td>
            <td>${maxRespTime} ms</td>
            <td><span class="status-badge ${statusBadge}">${statusText}</span></td>
        `;
        tbody.appendChild(row);
    });
}

// Update disconnects table
function updateDisconnectsTable(disconnects) {
    const tbody = document.getElementById('disconnectsTableBody');
    tbody.innerHTML = '';

    if (disconnects.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading">No disconnects recorded</td></tr>';
        return;
    }

    disconnects.forEach(disconnect => {
        const lastDisconnect = new Date(disconnect.last_disconnect).toLocaleString();
        const targetColor = targetColors[disconnect.name] || '#000000';
        
        // Table row
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong style="color: ${targetColor};">${disconnect.name}</strong></td>
            <td><code>${disconnect.host}</code></td>
            <td><strong style="color: #dc3545;">${disconnect.disconnect_count}</strong></td>
            <td>${lastDisconnect}</td>
        `;
        tbody.appendChild(row);
    });
}

// Show error message
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    errorDiv.classList.remove('info');

    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

// Show success message
function showSuccess(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.classList.add('info');
    errorDiv.style.display = 'block';

    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 3000);
}

