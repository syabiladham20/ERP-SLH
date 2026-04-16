const CACHE_NAME = 'slh-erp-v{{ version }}';
const DYNAMIC_CACHE_NAME = 'slh-erp-dynamic-v{{ version }}';
const ASSETS_TO_CACHE = [
  '/',
  '/offline',
  '/offline_mirror',
  '/static/js/offline_sync.js?v={{ version }}',
  '/static/manifest.json?v={{ version }}',
  '/static/icon-192.png?v={{ version }}',
  '/static/icon-512.png?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler.min.css?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-flags.min.css?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-payments.min.css?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-vendors.min.css?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/js/tabler.min.js?v={{ version }}',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.0.0',
  'https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.1.0/dist/chartjs-plugin-annotation.min.js',
  'https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js'
];

// Install Event: Cache Core Assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// Fetch Event: Network-First Strategy for HTML, Cache-First for Assets
self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate' || (event.request.method === 'GET' && event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html'))) {
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        // Successful network request -> store clone in dynamic cache
        return caches.open(DYNAMIC_CACHE_NAME).then((cache) => {
          cache.put(event.request, networkResponse.clone());
          return networkResponse;
        });
      }).catch(() => {
        // Network failed -> return from dynamic cache, fallback to offline_mirror if not found
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return caches.match('/offline_mirror').then(fallbackResponse => {
            return fallbackResponse || new Response('Offline. Please check your connection.', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({ 'Content-Type': 'text/plain' })
            });
          });
        });
      })
    );
  } else {
    // Cache-First strategy for static assets
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).catch(() => {
          // If it's an image or something else, we could return a placeholder or 404
          return new Response('', { status: 404, statusText: 'Not Found' });
        });
      })
    );
  }
});

// Push Event: Handle incoming Push Notifications
self.addEventListener('push', function(event) {
  let pushData = {};
  if (event.data) {
    try {
      pushData = event.data.json();
    } catch (e) {
      pushData = { title: "New Notification", body: event.data.text() };
    }
  }

  const title = "SLH-OP";
  const options = {
    body: pushData.body || "Alert: Check the dashboard for details.",
    icon: '/static/img/icon-192.png',
    badge: '/static/img/icon-192.png',
    tag: 'farm-alert',
    renotify: true,
    data: {
      url: pushData.url || '/'
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// Notification Click Event: Open Dashboard or specific URL
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  const urlToOpen = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      for (let i = 0; i < clientList.length; i++) {
        const client = clientList[i];
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          // Optionally navigate the existing focused window
          if (client.url !== new URL(urlToOpen, self.location.origin).href) {
            client.navigate(urlToOpen);
          }
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});