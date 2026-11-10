// Service Worker for Expense Tracker Pro 2.0 (Fast Live App Shell PWA v3.2)
const CACHE_NAME = 'expense-pro-v3.2-cache';
const STATIC_ASSETS = [
  '/mobile',
  '/static/manifest.json',
  '/static/icons/icon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(err => {
        console.warn('[ServiceWorker] Pre-cache note:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: 'window', includeUncontrolled: true }))
      .then((clientList) => {
        clientList.forEach((client) => {
          try { client.postMessage({ type: 'SW_ACTIVATED', cache: CACHE_NAME }); } catch (e) {}
        });
      })
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // 1. API endpoints: Strictly Network-Only (never serve stale API responses from SW cache)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req).catch(() => {
        return new Response(
          JSON.stringify({ error: 'Device is offline. Changes stored in local queue.', offline: true }),
          { headers: { 'Content-Type': 'application/json' }, status: 503 }
        );
      })
    );
    return;
  }

  // 2. HTML App Shell (/mobile, /app, /): Fast Network-First (850ms timeout -> cache fallback)
  //    Ensures latest code updates apply immediately on open/refresh while staying resilient offline.
  if (req.mode === 'navigate' || url.pathname === '/mobile' || url.pathname === '/app' || url.pathname === '/') {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(req, { ignoreSearch: true }).then((cachedResponse) => {
          const networkFetch = fetch(req).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(req, networkResponse.clone());
            }
            return networkResponse;
          });

          if (!cachedResponse) {
            return networkFetch.catch(() => caches.match('/mobile'));
          }

          return new Promise((resolve) => {
            let settled = false;
            const fallbackTimer = setTimeout(() => {
              if (!settled) {
                settled = true;
                resolve(cachedResponse);
              }
            }, 850);

            networkFetch.then((res) => {
              if (!settled) {
                settled = true;
                clearTimeout(fallbackTimer);
                resolve(res);
              }
            }).catch(() => {
              if (!settled) {
                settled = true;
                clearTimeout(fallbackTimer);
                resolve(cachedResponse);
              }
            });
          });
        });
      })
    );
    return;
  }

  // 3. Static Assets, Google Fonts & Category Thumbnails: Stale-While-Revalidate
  event.respondWith(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.match(req).then((cachedResponse) => {
        const isCacheableExternal =
          url.hostname.includes('fonts.googleapis.com') ||
          url.hostname.includes('fonts.gstatic.com') ||
          url.hostname.includes('images.unsplash.com');

        const fetchPromise = fetch(req).then((networkResponse) => {
          if (networkResponse && (networkResponse.status === 200 || networkResponse.type === 'opaque')) {
            if (networkResponse.type === 'basic' || isCacheableExternal) {
              cache.put(req, networkResponse.clone());
            }
          }
          return networkResponse;
        }).catch(() => cachedResponse);

        return cachedResponse || fetchPromise;
      });
    })
  );
});

// ==============================================
// Web Push Notification Listeners
// ==============================================

self.addEventListener('push', (event) => {
  let data = { title: 'Expense Tracker Pro', body: 'New financial alert received.', url: '/mobile' };
  try {
    if (event.data) {
      data = event.data.json();
    }
  } catch (e) {
    if (event.data) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/static/icons/icon.svg',
    badge: '/static/icons/icon.svg',
    vibrate: [100, 50, 100],
    data: {
      url: data.url || '/mobile'
    }
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Expense Tracker Pro', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/mobile';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes('/mobile') && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
