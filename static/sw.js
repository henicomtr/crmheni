// HENİ CRM — Service Worker v2
// Push bildirimlerini alır, gösterir ve uygulama ikonuna badge yazar.

self.addEventListener('push', function (event) {
    var data = {};
    try { data = event.data.json(); } catch (e) {}

    var title   = data.title   || 'Yeni Talep';
    var body    = data.body    || 'Yeni bir talep geldi.';
    var url     = data.url     || '/esk/requests';
    var icon    = data.icon    || '/static/img/icon-192.png';
    var badge   = data.badge   || '/static/img/icon-192.png';
    var count   = data.count   || 0;

    // Uygulama ikonuna sayı yaz (destekleyen tarayıcılarda)
    if (count > 0 && navigator.setAppBadge) {
        navigator.setAppBadge(count).catch(function () {});
    }

    event.waitUntil(
        self.registration.showNotification(title, {
            body:      body,
            icon:      icon,
            badge:     badge,   // Android bildirim çubuğundaki küçük ikon
            tag:       'heni-request',
            renotify:  true,
            vibrate:   [200, 100, 200],
            data:      { url: url },
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    // Badge'i sıfırla
    if (navigator.clearAppBadge) {
        navigator.clearAppBadge().catch(function () {});
    }

    var target = (event.notification.data && event.notification.data.url)
        ? event.notification.data.url
        : '/esk/requests';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
            for (var i = 0; i < list.length; i++) {
                var c = list[i];
                if (c.url.includes('/esk/') && 'focus' in c) {
                    c.focus();
                    return c.navigate(target);
                }
            }
            if (clients.openWindow) return clients.openWindow(target);
        })
    );
});

// Badge'i unread-count endpoint'inden çek ve güncelle
function syncBadge() {
    fetch('/esk/requests/unread-count')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var count = data.count || 0;
            if (navigator.setAppBadge) {
                if (count > 0) {
                    navigator.setAppBadge(count).catch(function () {});
                } else {
                    navigator.clearAppBadge().catch(function () {});
                }
            }
        })
        .catch(function () {});
}

// Periyodik badge sync (arka planda da çalışır)
self.addEventListener('periodicsync', function (event) {
    if (event.tag === 'badge-sync') {
        event.waitUntil(syncBadge());
    }
});

self.addEventListener('install',  function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
    e.waitUntil(
        clients.claim().then(function () { syncBadge(); })
    );
});
