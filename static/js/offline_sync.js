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
            user_id: userId,
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
            const request = store.get(userId);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    } catch (err) {
        console.error('Error getting snapshot:', err);
        return null;
    }
}

async function renderDashboard(userId) {
    const container = document.getElementById('offline-dashboard-container');
    const badge = document.getElementById('offline-badge');

    if (!container) return; // not on mirror page

    const snapshot = await getSnapshot(userId);

    if (!snapshot) {
        container.innerHTML = `
            <div class="empty d-flex flex-column align-items-center justify-content-center text-center mt-5">
                <div class="empty-icon mb-4 text-muted">
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
                    <div class="card">
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
