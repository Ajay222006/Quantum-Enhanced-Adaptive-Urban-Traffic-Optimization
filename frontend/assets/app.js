const pageStyles = document.createElement('link'); pageStyles.rel = 'stylesheet'; pageStyles.href = 'assets/pages.css'; document.head.appendChild(pageStyles);
const nav = `<div class="brand"><span class="brand-mark">Q</span><span><strong>Quantum Traffic</strong><small>Urban operations center</small></span></div><div class="workspace-picker"><span class="status-dot"></span><span><small>Workspace</small><strong>City Grid / Alpha</strong></span><span class="chevron">⌄</span></div><nav class="nav-group"><span class="nav-label">Monitor</span><a href="index.html" data-route="overview">⌂ <span>Overview</span></a><a href="live-map.html" data-route="network">⌁ <span>Live network</span></a><a href="events.html" data-route="events">! <span>Events</span><b>2</b></a><span class="nav-label">Optimize</span><a href="optimization.html" data-route="optimizer">◈ <span>Signal optimizer</span></a><a href="emergency.html" data-route="emergency">✚ <span>Emergency corridor</span></a><a href="comparison.html" data-route="comparison">↗ <span>Controller comparison</span></a><span class="nav-label">Workspace</span><a href="settings.html" data-route="settings">⚙ <span>Settings</span></a></nav><div class="sidebar-footer"><span class="mini-signal"><i></i><i></i><i></i></span><div><small>System health</small><strong>All services nominal</strong></div></div>`;
document.querySelectorAll('[data-sidebar]').forEach((el) => { el.innerHTML = nav; const page = document.body.dataset.page; el.querySelector(`[data-route="${page}"]`)?.classList.add('active'); });
document.querySelectorAll('[data-menu]').forEach((button) => button.addEventListener('click', () => document.querySelector('[data-sidebar]').classList.toggle('open')));
document.querySelectorAll('[data-toast]').forEach((button) => button.addEventListener('click', () => { const toast = document.querySelector('[data-toast-box]'); toast.textContent = button.dataset.toast; toast.classList.add('show'); window.setTimeout(() => toast.classList.remove('show'), 2400); }));
const additionalPages = [{ group: 'Analyze', items: [['metrics.html', 'metrics', '◉', 'Traffic metrics'], ['prediction.html', 'prediction', '⌁', 'Traffic prediction'], ['what-if.html', 'whatif', '◇', 'What-if analysis'], ['environment.html', 'environment', '◒', 'Environmental impact'], ['reports.html', 'reports', '▤', 'Reports']] }, { group: 'System', items: [['signal-control.html', 'signals', '◫', 'Signal control'], ['alerts.html', 'alerts', '!', 'Alerts'], ['about.html', 'about', 'i', 'About system']] }];
document.querySelectorAll('[data-sidebar] .nav-group').forEach((group) => { additionalPages.forEach((section) => { const label = document.createElement('span'); label.className = 'nav-label'; label.textContent = section.group; group.appendChild(label); section.items.forEach(([href, route, icon, text]) => { const link = document.createElement('a'); link.href = href; link.dataset.route = route; link.innerHTML = `${icon} <span>${text}</span>`; if (document.body.dataset.page === route) link.classList.add('active'); group.appendChild(link); }); }); });

const liveApi = window.location.protocol === 'file:' ? 'http://127.0.0.1:8002' : '';
const liveValue = (value, suffix = '') => value === null || value === undefined ? '--' : `${value}${suffix}`;
const setLiveText = (label, value) => {
	document.querySelectorAll('.metric-card p').forEach((node) => {
		if (node.textContent.trim().toLowerCase() === label.toLowerCase()) {
			const strong = node.parentElement.querySelector('strong');
			if (strong) strong.textContent = value;
		}
	});
};
const renderLiveSnapshot = (snapshot) => {
	const connected = snapshot.status === 'CONNECTED';
	document.querySelectorAll('.live-indicator').forEach((node) => {
		node.innerHTML = `<i></i> ${connected ? 'SUMO live' : snapshot.status || 'SUMO offline'}`;
	});
	const intersections = snapshot.intersections || [];
	const metrics = snapshot.metrics || {};
	setLiveText('Active queue length', connected ? liveValue(metrics.queue_vehicles, ' veh') : '--');
	setLiveText('Average wait time', connected ? liveValue(metrics.average_wait_seconds, ' sec') : '--');
	setLiveText('Traffic throughput', connected ? liveValue(metrics.throughput_vehicles_per_hour, ' veh / h') : '--');
	setLiveText('CO₂ emissions', connected ? liveValue(metrics.estimated_co2_kg, ' kg') : '--');
	const updateLabeledValue = (label, value) => {
		document.querySelectorAll('p, span, b').forEach((node) => {
			if (node.textContent.trim().toLowerCase() !== label.toLowerCase()) return;
			const parent = node.parentElement;
			const target = parent?.querySelector('strong, b');
			if (target && target !== node) target.textContent = value;
		});
	};
	updateLabeledValue('Fuel consumption', connected ? liveValue(metrics.estimated_fuel_litres, ' L') : '--');
	updateLabeledValue('CO₂ emissions', connected ? liveValue(metrics.estimated_co2_kg, ' kg') : '--');
	updateLabeledValue('Average speed', connected ? liveValue(metrics.average_speed_mps, ' m/s') : '--');
	updateLabeledValue('Simulation time', liveValue(snapshot.simulation_time, ' s'));
	const signalTable = document.querySelector('.signal-table');
	if (signalTable) {
		const rows = intersections.map((item) => {
			const signal = item.signal || {};
			const optimized = item.optimized_timing || {};
			const optimizedGreen = signal.phase === 0 ? optimized.NS : optimized.EW;
			return `<div class="table-row"><span><b>${item.id}</b><small>${liveValue(item.vehicle_count)} vehicles</small></span><span><i class="signal ${signal.label?.includes('GREEN') ? 'green' : 'amber'}"></i> Phase ${liveValue(signal.phase)}<small>${signal.label || 'UNKNOWN'}</small></span><span class="mono">${liveValue(signal.current_green_seconds, 's')}<small>opt ${liveValue(optimizedGreen, 's')}</small></span><span class="${connected ? 'good' : ''}">${connected ? 'LIVE' : 'OFFLINE'}</span></div>`;
		}).join('');
		signalTable.innerHTML = `<div class="table-row header"><span>Node</span><span>Phase</span><span>Green</span><span>State</span></div>${rows || '<div class="table-row"><span><b>SUMO</b><small>Waiting for live network</small></span><span>-</span><span>-</span><span>Disconnected</span></div>'}`;
	}
	document.querySelectorAll('.lede').forEach((node) => {
		if (node.textContent.includes('Adaptive signals') || node.textContent.includes('Inspect density')) {
			node.textContent = connected ? `Live SUMO state at ${liveValue(snapshot.simulation_time, 's')}. ${intersections.length} intersections reporting.` : 'SUMO is disconnected. Start the backend simulation to view live traffic.';
		}
	});
	document.querySelectorAll('.map-node').forEach((node, index) => {
		const item = intersections[index];
		if (item) node.innerHTML = `${item.id}<small>${Math.round((item.density || 0) * 100)}%</small>`;
		else node.innerHTML = `--<small>--</small>`;
	});
	document.querySelectorAll('.clock').forEach((node) => { node.textContent = connected ? `SUMO ${liveValue(snapshot.simulation_time, 's')}` : 'SUMO disconnected'; });
	const events = snapshot.events || [];
	const eventList = document.querySelector('.event-list');
	if (eventList && events.length) {
		eventList.innerHTML = events.slice().reverse().map((event) => `<article class="event-card warning-card"><div class="event-marker warning">!</div><div class="event-content"><div class="event-title"><div><span class="eyebrow">${event.time}s · AUTOMATED DETECTION</span><h2>${event.kind}</h2></div><span class="status-badge watch">ACTIVE</span></div><p>${event.message}</p><div class="event-meta"><span>Location <b>${event.location}</b></span><span>Response <b>Signal re-optimization</b></span></div></div></article>`).join('');
	}
	const predictionNote = document.querySelector('[data-prediction-status]');
	if (predictionNote) predictionNote.textContent = Object.keys(snapshot.prediction || {}).length ? 'LIVE PREDICTION ACTIVE' : 'MODEL NOT CONFIGURED';
	const page = document.body.dataset.page;
	const pagePill = document.querySelector('.page-heading .pill');
	if (pagePill) {
		if (page === 'prediction') pagePill.textContent = Object.keys(snapshot.prediction || {}).length ? 'LIVE MODEL' : 'MODEL NOT CONFIGURED';
		if (page === 'emergency') pagePill.textContent = 'EMERGENCY MODULE READY';
		if (page === 'comparison') pagePill.textContent = connected ? 'LIVE SNAPSHOT' : 'WAITING FOR SUMO';
		if (page === 'optimizer') pagePill.textContent = snapshot.optimization ? 'OPTIMIZATION READY' : 'WAITING FOR OPTIMIZATION';
	}
};
const connectLiveTraffic = () => {
	let pollingTimer = null;
	const poll = () => fetch(`${liveApi}/api/snapshot`).then((response) => response.json()).then(renderLiveSnapshot).catch(() => renderLiveSnapshot({ status: 'BACKEND OFFLINE', intersections: [] }));
	const startFallbackPolling = () => {
		if (!pollingTimer) {
			poll();
			pollingTimer = window.setInterval(poll, 2000);
		}
	};
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const socketUrl = `${window.location.protocol === 'file:' ? 'ws://127.0.0.1:8002' : `${protocol}//${window.location.host}`}/ws/live`;
	try {
		const socket = new WebSocket(socketUrl);
		socket.onmessage = (event) => renderLiveSnapshot(JSON.parse(event.data));
		socket.onerror = () => socket.close();
		socket.onclose = startFallbackPolling;
	} catch (_) {
		startFallbackPolling();
	}
};
connectLiveTraffic();