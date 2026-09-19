const pageStyles = document.createElement('link'); pageStyles.rel = 'stylesheet'; pageStyles.href = 'assets/pages.css'; document.head.appendChild(pageStyles);
const nav = `<div class="brand"><span class="brand-mark">Q</span><span><strong>Quantum Traffic</strong><small>Urban operations center</small></span></div><div class="workspace-picker"><span class="status-dot"></span><span><small>Workspace</small><strong>City Grid / Alpha</strong></span><span class="chevron">⌄</span></div><nav class="nav-group"><span class="nav-label">Monitor</span><a href="index.html" data-route="overview">⌂ <span>Overview</span></a><a href="live-map.html" data-route="network">⌁ <span>Live network</span></a><a href="events.html" data-route="events">! <span>Events</span><b>2</b></a><span class="nav-label">Optimize</span><a href="optimization.html" data-route="optimizer">◈ <span>Signal optimizer</span></a><a href="emergency.html" data-route="emergency">✚ <span>Emergency corridor</span></a><a href="comparison.html" data-route="comparison">↗ <span>Controller comparison</span></a><span class="nav-label">Workspace</span><a href="settings.html" data-route="settings">⚙ <span>Settings</span></a></nav><div class="sidebar-footer"><span class="mini-signal"><i></i><i></i><i></i></span><div><small>System health</small><strong>All services nominal</strong></div></div>`;
document.querySelectorAll('[data-sidebar]').forEach((el) => { el.innerHTML = nav; const page = document.body.dataset.page; el.querySelector(`[data-route="${page}"]`)?.classList.add('active'); });
document.querySelectorAll('[data-menu]').forEach((button) => button.addEventListener('click', () => document.querySelector('[data-sidebar]').classList.toggle('open')));
document.querySelectorAll('[data-toast]').forEach((button) => button.addEventListener('click', () => { const toast = document.querySelector('[data-toast-box]'); toast.textContent = button.dataset.toast; toast.classList.add('show'); window.setTimeout(() => toast.classList.remove('show'), 2400); }));
const additionalPages = [{ group: 'Analyze', items: [['metrics.html', 'metrics', '◉', 'Traffic metrics'], ['prediction.html', 'prediction', '⌁', 'Traffic prediction'], ['what-if.html', 'whatif', '◇', 'What-if analysis'], ['environment.html', 'environment', '◒', 'Environmental impact'], ['reports.html', 'reports', '▤', 'Reports']] }, { group: 'System', items: [['signal-control.html', 'signals', '◫', 'Signal control'], ['alerts.html', 'alerts', '!', 'Alerts'], ['about.html', 'about', 'i', 'About system']] }];
document.querySelectorAll('[data-sidebar] .nav-group').forEach((group) => { additionalPages.forEach((section) => { const label = document.createElement('span'); label.className = 'nav-label'; label.textContent = section.group; group.appendChild(label); section.items.forEach(([href, route, icon, text]) => { const link = document.createElement('a'); link.href = href; link.dataset.route = route; link.innerHTML = `${icon} <span>${text}</span>`; if (document.body.dataset.page === route) link.classList.add('active'); group.appendChild(link); }); }); });

const liveApi = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
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
		node.innerHTML = `<i></i> ${connected ? 'SUMO live' : snapshot.status}`;
	});
	const intersections = snapshot.intersections || [];
	const queue = intersections.reduce((sum, item) => sum + (item.queue || 0), 0);
	const vehicles = intersections.reduce((sum, item) => sum + (item.vehicle_count || 0), 0);
	const speedValues = intersections.map((item) => item.average_speed || 0);
	const averageSpeed = speedValues.length ? (speedValues.reduce((sum, value) => sum + value, 0) / speedValues.length).toFixed(1) : null;
	setLiveText('Active queue length', connected ? liveValue(queue, ' veh') : '--');
	setLiveText('Average wait time', connected ? liveValue(snapshot.optimization?.current_state?.wait, ' sec') : '--');
	setLiveText('Traffic throughput', connected ? liveValue(vehicles, ' veh') : '--');
	setLiveText('CO₂ emissions', '--');
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
};
const connectLiveTraffic = () => {
	const poll = () => fetch(`${liveApi}/api/snapshot`).then((response) => response.json()).then(renderLiveSnapshot).catch(() => renderLiveSnapshot({ status: 'DISCONNECTED', intersections: [] }));
	poll();
	window.setInterval(poll, 1000);
};
connectLiveTraffic();