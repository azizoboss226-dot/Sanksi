const CACHE_NAME = 'sanksi-cache-v6';
const urlsToCache = [
    '/',
    '/historique',
    '/static/style.css',
    '/static/logo.png',
    '/static/manifest.json'
];

// Installation du cache
self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
});

// Intercepter les requêtes
self.addEventListener('fetch', event => {
    // Ne pas cacher les requêtes POST (dépôts, retraits) ni l'admin
    if (event.request.method !== 'GET' || event.request.url.includes('/gestion-sanksi')) {
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Si on a la page en cache, on l'affiche instantanément
                if (response) return response;
                // Sinon, on va sur internet
                return fetch(event.request).then(
                    function(response) {
                        if(!response || response.status !== 200 || response.type !== 'basic') {
                            return response;
                        }
                        var responseToCache = response.clone();
                        caches.open(CACHE_NAME).then(function(cache) {
                            cache.put(event.request, responseToCache);
                        });
                        return response;
                    }
                );
            })
    );
});

// Nettoyage des vieux caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// Notifications Push
self.addEventListener('push', function(event) {
    if (event.data) {
        const data = event.data.json();
        const options = {
            body: data.body,
            icon: '/static/icon-192.png',
            badge: '/static/icon-192.png',
            vibrate: [200, 100, 200, 100, 200],
            data: { url: data.url || '/' }
        };
        event.waitUntil(self.registration.showNotification(data.title, options));
    }
});

// Clic sur la notification
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url));
});
