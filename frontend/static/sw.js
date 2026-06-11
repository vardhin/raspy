/* Raspy service worker — background Web Push.
 *
 * Served at /sw.js (root scope) so it controls the whole app. Its only job is to
 * turn incoming push messages into OS notifications, even when no tab is open,
 * and to focus/open the app when one is clicked.
 *
 * The push payload is the JSON the spine sends in core/notifications.py
 * (_fan_out_push): { title, body, icon, url, data }.
 */

self.addEventListener('install', (event) => {
	// Activate immediately so a freshly-registered worker can receive pushes
	// without waiting for a navigation.
	self.skipWaiting();
});

self.addEventListener('activate', (event) => {
	event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
	let data = {};
	try {
		data = event.data ? event.data.json() : {};
	} catch (e) {
		data = { title: 'Raspy', body: event.data ? event.data.text() : '' };
	}

	const title = data.title || 'Raspy';
	const options = {
		body: data.body || '',
		icon: data.icon || '/favicon.svg',
		badge: '/favicon.svg',
		tag: data.data && data.data.id ? `raspy-${data.data.id}` : undefined,
		data: { url: data.url || '/', ...(data.data || {}) }
	};

	event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const target = (event.notification.data && event.notification.data.url) || '/';

	event.waitUntil(
		self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
			// Focus an existing tab if we have one; otherwise open a new one.
			for (const client of clients) {
				if ('focus' in client) {
					client.navigate(target).catch(() => {});
					return client.focus();
				}
			}
			if (self.clients.openWindow) return self.clients.openWindow(target);
		})
	);
});
