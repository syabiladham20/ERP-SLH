const CACHE_NAME = 'slh-erp-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/offline',
  '/offline_mirror',
  '/static/js/offline_sync.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler.min.css',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-flags.min.css',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-payments.min.css',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/css/tabler-vendors.min.css',
  'https://cdn.jsdelivr.net/npm/@tabler/core@latest/dist/js/tabler.min.js'
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