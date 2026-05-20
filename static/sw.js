// HENİ CRM — Service Worker v1
// Push bildirimlerini alır ve gösterir.

self.addEventListener('push', function (event) {
    var data = {};
    try { data = event.data.json(); } catch (e) {}

    var title   = data.title   || 'Yeni Talep';
    var body    = data.body    || 'Yeni bir talep geldi.';
    var url     = data.url     || '/esk/requests';
    var icon    = data.icon    || '/static/img/icon-192.png';

    event.waitUntil(
        self.registration.showNotification(title, {
            body:  body,
            icon:  icon,
            badge: icon,
            tag:   'heni-request',          // Aynı tag → eski bildirimi replace eder
            renotify: true,
            data:  { url: url },
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var target = (event.notification.data && event.notification.data.url)
        ? event.notification.data.url
        : '/esk/requests';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
            // Zaten açık sekme varsa fokusla
            for (var i = 0; i < list.length; i++) {
                var c = list[i];
                if (c.url.includes('/esk/') && 'focus' in c) {
                    c.focus();
                    return c.navigate(target);
                }
            }
            // Yoksa yeni sekme aç
            if (clients.openWindow) return clients.openWindow(target);
        })
    );
});

// Install & activate — cache kullanmıyoruz, sade tut
self.addEventListener('install',  function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });
