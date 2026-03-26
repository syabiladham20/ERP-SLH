const CACHE_NAME = 'slh-erp-v{{ version }}';
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
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/js/tabler.min.js?v={{ version }}'
];

// Install Event: Cache Core Assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// Fetch Event: Network-First Strategy
self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate' || (event.request.method === 'GET' && event.request.headers.get('accept').includes('text/html'))) {
    event.respondWith(
      fetch(event.request).catch(() => {
        // Redirect to offline mirror for dashboard-like navigations
        return caches.match('/offline_mirror');
      })
    );
  } else {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match(event.request);
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

  const title = pushData.title || "SLH-OP Alert";
  const options = {
    body: pushData.body || "You have a new alert.",
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png', // A small icon for Android status bar
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