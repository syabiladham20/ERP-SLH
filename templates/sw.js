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