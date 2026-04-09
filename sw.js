// Easy House PWA — Service Worker
const CACHE_NAME = 'easyhouse-v1';
const ASSETS = [
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/lucide/0.263.1/lucide.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js'
];

// Install — pré-cache dos assets
self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(ASSETS).catch(function(err) {
        console.log('[SW] Alguns assets não foram cacheados:', err);
      });
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

// Activate — limpa caches antigos
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});

// Fetch — serve do cache, atualiza em background (stale-while-revalidate)
self.addEventListener('fetch', function(e) {
  // Não interceptar chamadas à API (Firebase, VTEX, Anymarket)
  var url = e.request.url;
  if (url.includes('firebaseio.com') ||
      url.includes('vtexcommercestable') ||
      url.includes('anymarket.com.br') ||
      url.includes('script.google.com') ||
      url.includes('googleapis.com/identitytoolkit')) {
    return;
  }

  e.respondWith(
    caches.match(e.request).then(function(cached) {
      var network = fetch(e.request).then(function(response) {
        if (response && response.status === 200 && response.type === 'basic') {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(e.request, clone);
          });
        }
        return response;
      }).catch(function() { return cached; });

      return cached || network;
    })
  );
});
