const DB_NAME = 'slh_offline_db';
const DB_VERSION = 1;
const STORE_NAME = 'snapshots';

function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'user_id' });
            }
        };

        request.onsuccess = (event) => {
            resolve(event.target.result);
        };

        request.onerror = (event) => {
            reject('IndexedDB error: ' + event.target.errorCode);
        };
    });
}

async function syncSnapshot(userId) {
    if (!navigator.onLine) return; // Only sync when online

    try {
        const response = await fetch('/api/offline_snapshot');
        if (!response.ok) return;

        const data = await response.json();

        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);

        // Upsert logic: Use the specific user ID to prevent cross-user data bleed on same tablet
        store.put({
            user_id: String(userId),
            timestamp: data.timestamp,
            flocks: data.flocks
        });

        tx.oncomplete = () => {
            console.log('Offline snapshot synced to IndexedDB for user:', userId);
        };

        tx.onerror = (e) => {
            console.error('Error syncing snapshot:', e.target.error);
        };
    } catch (err) {
        console.error('Failed to sync snapshot:', err);
    }
}

async function getSnapshot(userId) {
    try {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const request = store.get(String(userId));
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    } catch (err) {
        console.error('Error getting snapshot:', err);
        return null;
    }
}

async function renderDashboard(userId) {
    window.currentUserId = userId; // Save globally for navigation
    const container = document.getElementById('offline-dashboard-container');
    const badge = document.getElementById('offline-badge');

    if (!container) return; // not on mirror page

    const snapshot = await getSnapshot(userId);

    if (!snapshot) {
        container.innerHTML = `
            <div class="empty">
                <div class="empty-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-wifi-off" width="64" height="64" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                       <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
                       <path d="M12 20h.01"></path>
                       <path d="M8.5 16.429a5 5 0 0 1 7.002 -2.128"></path>
                       <path d="M5.467 13.064a8.003 8.003 0 0 1 10.533 -4.564"></path>
                       <path d="M2.564 9.698a11.002 11.002 0 0 1 16.436 -2.198"></path>
                       <path d="M3 3l18 18"></path>
                    </svg>
                </div>
                <p class="empty-title">No Offline Data</p>
                <p class="empty-subtitle text-muted">Please reconnect to the internet to sync data for offline use.</p>
            </div>
        `;
        return;
    }

    // Update Badge
    if (badge) {
        const date = new Date(snapshot.timestamp);
        badge.innerHTML = `🟠 Offline View <span class="d-none d-md-inline">(Last Synced: ${date.toLocaleString()})</span>`;
        badge.style.display = 'inline-block';
    }

    let html = '';

    if (!snapshot.flocks || snapshot.flocks.length === 0) {
         html = '<p class="text-muted text-center mt-5">No active flocks available in offline snapshot.</p>';
    } else {
        // Cache the snapshot object to global scope to make switching houses faster
        window._offlineSnapshot = snapshot;

        html += '<div class="row row-cards">';

        snapshot.flocks.forEach(flock => {
            // Find latest log for KPI
            let latestLog = null;
            if (flock.daily_logs && flock.daily_logs.length > 0) {
                latestLog = flock.daily_logs[flock.daily_logs.length - 1];
            }

            const mortPct = latestLog && latestLog.mortality_cum_female_pct ? parseFloat(latestLog.mortality_cum_female_pct).toFixed(2) + '%' : 'N/A';
            const eggPct = latestLog && latestLog.eggs_production_pct ? parseFloat(latestLog.eggs_production_pct).toFixed(1) + '%' : 'N/A';
            const feed = latestLog && latestLog.feed_female_gp_bird ? parseFloat(latestLog.feed_female_gp_bird).toFixed(1) + 'g' : 'N/A';
            const stock = latestLog && latestLog.stock_female_end ? latestLog.stock_female_end : 'N/A';

            html += `
                <div class="col-md-6 col-lg-4">
                    <div class="card cursor-pointer" onclick="renderFlockDetail(${flock.flock_id})">
                        <div class="card-header bg-primary text-white">
                            <h3 class="card-title text-white mb-0">${flock.house_name}</h3>
                            <div class="card-actions">
                                <span class="badge bg-white text-primary">${flock.calculated_phase}</span>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="row g-3">
                                <div class="col-6">
                                    <div class="text-muted text-uppercase fw-bold small">Egg Prod.</div>
                                    <div class="h3 mb-0">${eggPct}</div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted text-uppercase fw-bold small">Mortality (F)</div>
                                    <div class="h3 mb-0">${mortPct}</div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted text-uppercase fw-bold small">Feed (F)</div>
                                    <div class="h3 mb-0">${feed}</div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted text-uppercase fw-bold small">Stock (F)</div>
                                    <div class="h3 mb-0">${stock}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
    }

    container.innerHTML = html;
}

window.renderFlockDetail = function(flockId) {
    const container = document.getElementById('offline-dashboard-container');
    if (!container || !window._offlineSnapshot) return;

    const flock = window._offlineSnapshot.flocks.find(f => f.flock_id === flockId);
    if (!flock) return;

    // Use recent detailed logs
    const logs = flock.recent_detailed_logs || [];
    // Ensure chronological order
    logs.sort((a, b) => new Date(a.date) - new Date(b.date));

    // Reverse for table display (newest first)
    const reversedLogs = [...logs].reverse();

    // Prepare chart data (chronological)
    const dates = logs.map(l => l.date);
    const ages = logs.map(l => l.week_day_format ? String(l.week_day_format).split('.')[0] : 'N/A');
    const mortM = logs.map(l => l.mortality_male_pct);
    const mortF = logs.map(l => l.mortality_female_pct);
    const cullM = logs.map(l => (l.culls_male / (l.stock_male_start || 1)) * 100);
    const cullF = logs.map(l => (l.culls_female / (l.stock_female_start || 1)) * 100);
    const eggProd = logs.map(l => l.egg_prod_pct);
    const feedM = logs.map(l => l.feed_male_gp_bird);
    const feedF = logs.map(l => l.feed_female_gp_bird);

    let html = `
        <div class="mb-3">
            <button class="btn btn-outline-primary" onclick="renderDashboard(window.currentUserId || localStorage.getItem('slh_offline_user_id'))">
                <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-arrow-left" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
                   <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
                   <path d="M5 12l14 0"></path>
                   <path d="M5 12l6 6"></path>
                   <path d="M5 12l6 -6"></path>
                </svg>
                Back to Dashboard
            </button>
        </div>

        <div class="d-flex flex-wrap justify-content-between align-items-center mb-3 row-gap-2">
            <h2>Flock Details: ${flock.house_name} (${flock.farm_name})</h2>
        </div>

        <div class="card mb-4 shadow-sm border-0">
            <div class="card-header bg-transparent border-0 pb-0">
                <h6 class="text-uppercase text-muted ls-1 mb-0">Overview</h6>
            </div>
            <div class="card-body">
                <div class="row text-center mb-3">
                    <div class="col-md-3 border-end">
                        <span class="text-xs text-muted font-weight-bold text-uppercase">House</span><br>
                        <span class="text-dark font-weight-bold">${flock.house_name}</span>
                    </div>
                    <div class="col-md-3 border-end">
                        <span class="text-xs text-muted font-weight-bold text-uppercase">Farm</span><br>
                        <span class="text-dark font-weight-bold">${flock.farm_name}</span>
                    </div>
                    <div class="col-md-3 border-end">
                        <span class="text-xs text-muted font-weight-bold text-uppercase">Phase</span><br>
                        <span class="badge ${flock.calculated_phase === 'Brooding' ? 'bg-primary' : (flock.calculated_phase === 'Growing' ? 'bg-info' : (flock.calculated_phase === 'Pre-lay' ? 'bg-warning' : 'bg-success'))} mt-1">${flock.calculated_phase}</span>
                    </div>
                    <div class="col-md-3">
                        <span class="text-xs text-muted font-weight-bold text-uppercase">Intake Date</span><br>
                        <span class="text-dark font-weight-bold">${flock.intake_date || 'N/A'}</span>
                    </div>
                </div>
            </div>
        </div>

        <ul class="nav nav-tabs mb-4 gap-2 border-bottom-0" id="flockTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active px-4 py-2 border rounded shadow-sm" id="daily-tab" data-bs-toggle="tab" data-bs-target="#daily" type="button" role="tab">Daily Logs (Last 14 Days)</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link px-4 py-2 border rounded shadow-sm bg-white" id="charts-tab" data-bs-toggle="tab" data-bs-target="#charts" type="button" role="tab">Performance Charts</button>
            </li>
        </ul>

        <div class="tab-content" id="flockTabsContent">
            <!-- Daily Logs Tab -->
            <div class="tab-pane fade show active" id="daily" role="tabpanel">
                <div class="table-responsive">
                    <table class="table table-bordered table-sm text-center align-middle" style="font-size: 0.8rem;">
                        <thead class="table-light text-dark">
                            <tr>
                                <th>Date</th>
                                <th>Age</th>
                                <th>Mortality (M/F)</th>
                                <th>Culls (M/F)</th>
                                <th>Feed g/bird (M/F)</th>
                                <th>Eggs</th>
                                <th>Egg Prod %</th>
                                <th>BW (M/F)</th>
                                <th>Unif % (M/F)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${reversedLogs.length === 0 ? '<tr><td colspan="9" class="text-muted">No detailed logs found for the last 14 days.</td></tr>' : ''}
                            ${reversedLogs.map(l => `
                            <tr>
                                <td class="fw-bold">${l.date}</td>
                                <td>W${l.week_day_format ? String(l.week_day_format).split('.')[0] : 'N/A'}</td>
                                <td><span class="${l.mortality_male > 0 ? 'text-danger fw-bold' : 'text-muted'}">${l.mortality_male || 0}</span> / <span class="${l.mortality_female > 0 ? 'text-danger fw-bold' : 'text-muted'}">${l.mortality_female || 0}</span></td>
                                <td><span class="${l.culls_male > 0 ? 'text-warning fw-bold' : 'text-muted'}">${l.culls_male || 0}</span> / <span class="${l.culls_female > 0 ? 'text-warning fw-bold' : 'text-muted'}">${l.culls_female || 0}</span></td>
                                <td>${l.feed_male_gp_bird !== null ? l.feed_male_gp_bird.toFixed(1) : '0.0'}g / ${l.feed_female_gp_bird !== null ? l.feed_female_gp_bird.toFixed(1) : '0.0'}g</td>
                                <td class="fw-bold">${l.eggs_collected || 0}</td>
                                <td class="${l.egg_prod_pct >= 85 ? 'bg-success text-white' : ''} fw-bold">${l.egg_prod_pct !== null ? l.egg_prod_pct.toFixed(2) : '0.00'}%</td>
                                <td>${l.body_weight_male || 0} / ${l.body_weight_female || 0}</td>
                                <td>${l.uniformity_male !== null ? (l.uniformity_male <= 1 ? (l.uniformity_male * 100).toFixed(1) : l.uniformity_male.toFixed(1)) : '0.0'}% / ${l.uniformity_female !== null ? (l.uniformity_female <= 1 ? (l.uniformity_female * 100).toFixed(1) : l.uniformity_female.toFixed(1)) : '0.0'}%</td>
                            </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Charts Tab -->
            <div class="tab-pane fade" id="charts" role="tabpanel">
                <div class="row">
                    <div class="col-12 mb-4">
                        <div class="card">
                            <div class="card-header">
                                <h3 class="card-title">General Performance (Last 14 Days)</h3>
                            </div>
                            <div class="card-body" style="height: 400px; position: relative;">
                                <canvas id="offlineGeneralChart"></canvas>
                            </div>
                        </div>
                    </div>
                    <div class="col-12 mb-4">
                        <div class="card">
                            <div class="card-header">
                                <h3 class="card-title">Daily Feed per Bird (Last 14 Days)</h3>
                            </div>
                            <div class="card-body" style="height: 400px; position: relative;">
                                <canvas id="offlineFeedChart"></canvas>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;

    // We must initialize the charts after they are inserted into the DOM.
    // Delay slightly to allow the DOM to render the canvas elements.
    setTimeout(() => {
        if (typeof Chart !== 'undefined') {
            const isRearing = (flock.calculated_phase === 'Brooding' || flock.calculated_phase === 'Growing' || flock.calculated_phase === 'Pre-lay');

            // General Performance Chart
            const generalCtx = document.getElementById('offlineGeneralChart');
            if (generalCtx) {
                const datasets = [
                    { label: 'Mortality Male %', data: mortM, backgroundColor: '#B22222', yAxisID: 'y1' },
                    { label: 'Mortality Female %', data: mortF, backgroundColor: '#FF0000', yAxisID: 'y1' },
                    { label: 'Culls Male %', data: cullM, backgroundColor: '#DAA520', yAxisID: 'y1' },
                    { label: 'Culls Female %', data: cullF, backgroundColor: '#FFD700', yAxisID: 'y1' }
                ];

                if (!isRearing) {
                    datasets.push({
                        label: 'Egg Production %',
                        data: eggProd,
                        type: 'line',
                        borderColor: 'green',
                        yAxisID: 'y'
                    });
                }

                new Chart(generalCtx, {
                    type: 'bar',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { stacked: true },
                            y1: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Mortality/Culls %' }, stacked: true },
                            y: isRearing ? { display: false } : { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Egg Prod %' }, grid: { drawOnChartArea: false } }
                        }
                    }
                });
            }

            // Feed Chart
            const feedCtx = document.getElementById('offlineFeedChart');
            if (feedCtx) {
                const datasets = [
                    { label: 'Male Feed (g)', data: feedM, borderColor: '#36A2EB', backgroundColor: '#36A2EB', tension: 0.1 },
                    { label: 'Female Feed (g)', data: feedF, borderColor: '#FF6384', backgroundColor: '#FF6384', tension: 0.1 }
                ];

                if (!isRearing) {
                    datasets.push({ label: 'Egg Prod %', data: eggProd, borderColor: '#2fb344', yAxisID: 'y1', type: 'line', pointRadius: 0 });
                }

                new Chart(feedCtx, {
                    type: 'line',
                    data: { labels: dates, datasets: datasets },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Feed (g)' }, beginAtZero: true },
                            y1: isRearing ? { display: false } : { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Egg Prod %' }, min: 0, max: 100, grid: { drawOnChartArea: false } }
                        }
                    }
                });
            }
        }
    }, 100);
};

// Auto-sync wrapper function attached to window
window.initOfflineSync = async function(userId) {
    if (!userId) return;

    // Sync initially on page load if online
    if (navigator.onLine) {
        await syncSnapshot(userId);
    }

    // Listen for online events to resync
    window.addEventListener('online', async () => {
        console.log("Network restored, syncing snapshot...");
        await syncSnapshot(userId);
    });
};
