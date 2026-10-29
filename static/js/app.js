/* app.js — application controllers. All data comes from the JSON API. */

const state = {
    user: null,
    config: null,
    activeTab: 'dashboard',
    charts: {},
    // Servants eligible for weighing: both work types may collect leaf.
    weightWorkers: null,
    salary: null,
    payslip: null,
    rainyTimer: null,
    paymentMethod: null,
    paymentRef: '',
    historyServants: null,
    includeInactiveSupervisors: false,
    includeInactiveServants: false,
};

const $ = (id) => document.getElementById(id);

const TAB_TITLES = {
    dashboard: 'Dashboard Overview',
    supervisors: 'Field Supervisors',
    servants: 'Servant Registry',
    attendance: 'Attendance Timecards',
    weights: 'Tea Weight Entry',
    assignments: 'Work Area Assignments',
    salary: 'Salary Center',
    reports: 'Analytics Reports',
    'servant-records': 'My Activity Log',
};

const WORK_TYPE_BADGE = {
    'Tea Collector': 'badge-success',
    'Retail Worker': 'badge-warning',
};

/* ------------------------------------------------------------------ utils */
function emptyRow(colspan, message) {
    return `<tr><td colspan="${colspan}" style="text-align:center;color:var(--text-secondary);padding:24px;">${esc(message)}</td></tr>`;
}

function recordNote(shown, total) {
    if (total === undefined || total === null) return '';
    if (total > shown) return `Showing the latest ${shown} of ${total} records.`;
    return `All ${total} record${total === 1 ? '' : 's'}.`;
}

function pctBadge(pct) {
    const cls = pct > 80 ? 'badge-success' : pct >= 70 ? 'badge-warning' : 'badge-danger';
    return `<span class="badge ${cls}">${pct}%</span>`;
}

function statusBadge(status) {
    if (status === 'Paid' || status === 'Present') return `<span class="badge badge-success">${status}</span>`;
    if (status === 'Absent') return '<span class="badge badge-danger">Absent</span>';
    if (status === 'Pending') return '<span class="badge badge-warning">Pending</span>';
    if (status === 'draft') return '<span class="badge badge-warning">Draft</span>';
    if (status === 'finalized') return '<span class="badge badge-success">Finalized</span>';
    return `<span class="badge badge-info">${esc(status)}</span>`;
}

function workTypeBadge(workType) {
    return `<span class="badge ${WORK_TYPE_BADGE[workType] || 'badge-info'}">${esc(workType)}</span>`;
}

function statCard(title, value, caption, icon, tone) {
    const tones = {
        primary: 'rgba(16, 185, 129, 0.1); color: var(--primary);',
        secondary: 'rgba(6, 182, 212, 0.1); color: var(--secondary);',
        warning: 'rgba(245, 158, 11, 0.1); color: var(--warning);',
        info: 'rgba(59, 130, 246, 0.1); color: var(--info);',
    };
    return `
        <div class="glass-card stat-card">
            <div class="stat-details">
                <h4>${esc(title)}</h4>
                <div class="value">${value}</div>
                <div class="trend positive">${esc(caption)}</div>
            </div>
            <div class="stat-icon" style="background: ${tones[tone] || tones.primary}">
                <i data-feather="${icon}"></i>
            </div>
        </div>`;
}

function fmtMoneyCompact(value) {
    const amount = Math.round(Number(value) || 0);
    if (amount >= 1000000) return `Rs. ${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 1000) return `Rs. ${(amount / 1000).toFixed(1)}k`;
    return `Rs. ${amount}`;
}

function ringSvg({ percent, radius, center, label, small, gauge }) {
    const circumference = 2 * Math.PI * radius;
    const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
    const offset = circumference - (clamped / 100) * circumference;
    const size = radius * 2 + 20;
    const c = size / 2;
    return `
        <div class="attendance-ring-container ${small ? 'ring-sm' : ''}">
            <svg class="attendance-ring" viewBox="0 0 ${size} ${size}">
                <circle class="ring-circle-bg" cx="${c}" cy="${c}" r="${radius}"></circle>
                <circle class="ring-circle-val ${gauge ? 'ring-gauge' : ''}" cx="${c}" cy="${c}" r="${radius}"
                        style="stroke-dasharray:${circumference};stroke-dashoffset:${offset};"></circle>
            </svg>
            <div class="attendance-text">
                <div class="attendance-pct">${center}</div>
                <div class="attendance-label">${label}</div>
            </div>
        </div>`;
}

function renderChart(canvasId, config) {
    const canvas = $(canvasId);
    if (!canvas || !window.Chart) return;
    if (state.charts[canvasId]) state.charts[canvasId].destroy();
    state.charts[canvasId] = new Chart(canvas.getContext('2d'), config);
}

/* ------------------------------------------------------------------- boot */
async function boot() {
    bindEvents();
    startClock();

    if (window.Chart) {
        Chart.defaults.color = 'rgba(226, 232, 240, 0.75)';
        Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.08)';
        Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
    }

    window.addEventListener('auth:required', () => {
        if (state.user) {
            resetClientState();
            showAuthView();
            showToast('Your session has ended. Please sign in again.', 'info');
        }
    });

    // Back/forward cache can restore this document with its previous DOM after
    // the session was cleared (logout here or in another tab). Revalidate or
    // fall back to the sign-in view instead of repainting protected content.
    window.addEventListener('pageshow', (event) => {
        if (!event.persisted) return;
        if (!state.user) {
            resetClientState();
            showAuthView();
            return;
        }
        api.get('/api/auth/me').catch(() => {
            resetClientState();
            showAuthView();
        });
    });

    try {
        const { user } = await api.get('/api/auth/me');
        state.user = user;
        await enterApp();
    } catch (error) {
        showAuthView();
    }
    refreshIcons();
}

function showAuthView() {
    closeAllModals();
    closeSidebar();
    $('app-shell').style.display = 'none';
    $('auth-view').style.display = 'flex';
}

function resetClientState() {
    state.user = null;
    state.config = null;
    state.salary = null;
    state.payslip = null;
    state.weightWorkers = null;
    state.historyServants = null;
    state.paymentMethod = null;
    state.paymentRef = '';
    userCache.clear();
    Object.values(state.charts).forEach((chart) => {
        if (chart && typeof chart.destroy === 'function') chart.destroy();
    });
    state.charts = {};
    const loginForm = $('login-form');
    if (loginForm) loginForm.reset();
    const passwordForm = $('password-form');
    if (passwordForm) passwordForm.reset();
    $('password-modal').classList.remove('force-change');
}

async function enterApp() {
    $('auth-view').style.display = 'none';
    $('app-shell').style.display = 'grid';

    applyRoleNavigation();
    renderUserBadge();

    if (state.user.must_change_password) {
        // Other API calls are blocked server-side until this is resolved, so
        // do not fetch config/dashboard yet. The modal is not dismissible.
        $('password-modal').classList.add('force-change');
        openModal('password-modal');
        showToast('Your password was reset. Please choose a new one.', 'info');
        return;
    }

    await initializeApp();
}

async function initializeApp() {
    try {
        state.config = await api.get('/api/config');
    } catch (error) {
        state.config = null;
    }
    applyConfigDefaults();
    switchTab('dashboard');
}

function applyRoleNavigation() {
    document.querySelectorAll('.menu-item').forEach((item) => {
        const roles = (item.dataset.roles || '').split(',');
        item.style.display = roles.includes(state.user.role) ? '' : 'none';
    });
}

function renderUserBadge() {
    const user = state.user;
    const initials = user.name.split(' ').map((part) => part[0]).join('').substring(0, 2).toUpperCase();
    $('user-avatar').textContent = initials;
    $('user-display-name').textContent = user.name;
    $('user-display-role').textContent = user.role.charAt(0).toUpperCase() + user.role.slice(1);
}

function applyConfigDefaults() {
    const areas = (state.config && state.config.areas) || [];

    const areaSelect = $('weight-area-select');
    if (areaSelect && !areaSelect.options.length) {
        areaSelect.innerHTML =
            '<option value="" selected disabled>Select area</option>' +
            areas.map((area) => `<option value="${esc(area)}">${esc(area)}</option>`).join('');
    }
    const sectionGroup = $('user-sections');
    if (sectionGroup && !sectionGroup.children.length) {
        sectionGroup.innerHTML = areas
            .map((area) => `
                <label class="checkbox-option">
                    <input type="checkbox" value="${esc(area)}">
                    <span>${esc(area)}</span>
                </label>`)
            .join('');
    }

    // Seed the payment method from the first configured option. Without this the
    // run-actions select *displays* "Cash" while state.paymentMethod stays null,
    // so paying would silently record no method at all -- the visible selection
    // would not match what gets sent.
    const methods = (state.config && state.config.payment_methods) || [];
    if (!state.paymentMethod && methods.length) {
        state.paymentMethod = methods[0];
    }
}

function startClock() {
    const el = $('live-time');
    const tick = () => {
        el.textContent = new Date().toLocaleString('en-GB', {
            weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    };
    tick();
    setInterval(tick, 30000);
}

/* -------------------------------------------------------------- navigation */
function setSidebarOpen(open) {
    const sidebar = $('sidebar-nav');
    const toggle = $('mobile-toggle');
    if (!sidebar || !toggle) return;
    sidebar.classList.toggle('mobile-open', open);
    document.body.classList.toggle('drawer-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    const label = open ? 'Close navigation menu' : 'Open navigation menu';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
    // Swap the hamburger for a close icon while the drawer is open.
    toggle.innerHTML = `<i data-feather="${open ? 'x' : 'menu'}"></i>`;
    refreshIcons();
}

function closeSidebar() {
    setSidebarOpen(false);
}

function toggleSidebar() {
    setSidebarOpen(!$('sidebar-nav').classList.contains('mobile-open'));
}

function switchTab(tab) {
    if (state.user && state.user.must_change_password) {
        openModal('password-modal');
        return;
    }
    state.activeTab = tab;

    document.querySelectorAll('.dashboard-view').forEach((view) => view.classList.remove('active'));
    document.querySelectorAll('.menu-item').forEach((item) => item.classList.remove('active'));

    const view = $(`view-${tab}`);
    const menu = $(`menu-${tab}`);
    if (view) view.classList.add('active');
    if (menu) menu.classList.add('active');

    $('current-tab-title').textContent = TAB_TITLES[tab] || 'Dashboard';
    closeSidebar();

    const loader = VIEW_LOADERS[tab];
    if (loader) loader().catch(reportError);
}

const VIEW_LOADERS = {
    dashboard: loadDashboard,
    supervisors: loadSupervisors,
    servants: loadServants,
    attendance: loadAttendanceView,
    weights: loadWeights,
    assignments: loadAssignments,
    salary: loadSalary,
    reports: loadReports,
    'servant-records': loadServantRecords,
};

/* --------------------------------------------------------------- dashboard */
async function loadDashboard() {
    const data = await api.get('/api/dashboard');
    if (data.role === 'servant') {
        renderServantDashboard(data);
    } else {
        renderStaffDashboard(data);
    }
    refreshIcons();
}

function renderStaffDashboard(data) {
    const s = data.stats;
    // Supervisors receive no payroll figures: their dashboard is operational only.
    const hasPayroll = s.estimated_payroll !== undefined && s.estimated_payroll !== null;

    $('hero-welcome').textContent = `Welcome back, ${state.user.name}!`;
    $('hero-desc').textContent = state.user.role === 'owner'
        ? 'Oversee collection, payroll, and analytics across the estate — all in one place.'
        : 'Record attendance, assign daily work areas, and log tea weights with rainy-day deductions.';
    $('panel-main-title').textContent = hasPayroll ? 'Harvest & Payroll Cost' : 'Harvest Overview';
    $('panel-main-badge').textContent = `${data.period.start} → ${data.period.end}`;

    $('dashboard-stats').innerHTML = [
        statCard('Active Servants', s.servants, `${s.collectors} collectors · ${s.retail_workers} retail`, 'users', 'primary'),
        statCard('Present Today', s.present_today, `${s.absent_today} absent today`, 'user-check', 'info'),
        statCard('Harvest (cycle)', fmtKg(s.harvest_kg), `${fmtNumber(s.rainy_deduction_kg)} kg rain deduction`, 'package', 'warning'),
        hasPayroll
            ? statCard('Est. Payroll (cycle)', fmtMoney(s.estimated_payroll), 'At current rates', 'credit-card', 'secondary')
            : statCard('Rainy Deduction', fmtKg(s.rainy_deduction_kg), 'Moisture adjustment this cycle', 'cloud-rain', 'secondary'),
    ].join('');

    const datasets = [
        {
            type: 'bar',
            label: 'Harvest (kg)',
            data: data.series.map((row) => row.harvest_kg),
            backgroundColor: 'rgba(16, 185, 129, 0.55)',
            borderRadius: 6,
            yAxisID: 'y',
        },
    ];
    const scales = {
        y: { position: 'left', ticks: { callback: (v) => `${v} kg` } },
    };
    if (hasPayroll) {
        datasets.push({
            type: 'line',
            label: 'Payroll cost (Rs.)',
            data: data.series.map((row) => row.cost_rs),
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.15)',
            tension: 0.35,
            fill: true,
            yAxisID: 'y1',
        });
        scales.y1 = {
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { callback: (v) => `Rs. ${v}` },
        };
    }

    renderChart('dashboardMainChart', {
        data: {
            labels: data.series.map((row) => row.date.slice(5)),
            datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales,
        },
    });

    $('panel-side-title').textContent = 'Work Area Allocations';
    const max = Math.max(...data.area_distribution.map((row) => row.kg), 1);
    $('panel-side-body').innerHTML = data.area_distribution.map((row) => `
        <div style="margin-bottom:14px;">
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:6px;">
                <span>${esc(row.area)}</span><strong>${fmtKg(row.kg)}</strong>
            </div>
            <div style="height:8px;background:rgba(255,255,255,0.05);border-radius:4px;overflow:hidden;">
                <div style="height:100%;width:${((row.kg / max) * 100).toFixed(1)}%;background:var(--primary);border-radius:4px;"></div>
            </div>
        </div>`).join('');
}

function renderServantDashboard(data) {
    const g = data.gauge;
    const rates = data.rates || {};
    const isCollector = g.rate_unit === 'kg';

    $('hero-welcome').textContent = `Hello, ${state.user.name}!`;
    $('hero-desc').textContent = `Current payroll cycle: ${g.cycle_start} → ${g.cycle_end} · Day ${g.day_of_cycle} of ${g.cycle_days}.`;
    $('panel-main-title').textContent = 'My Daily Collection';
    $('panel-main-badge').textContent = `Day ${g.day_of_cycle} of ${g.cycle_days}`;

    $('dashboard-stats').innerHTML = [
        statCard('Cycle Output', isCollector ? fmtKg(data.stats.total_weight) : `${data.stats.present_days} days`, `Day ${g.day_of_cycle} of ${g.cycle_days}`, 'package', 'primary'),
        statCard('Present Days', g.present_days, `of ${g.elapsed_days} elapsed days`, 'user-check', 'info'),
        statCard('Attendance', `${g.attendance_pct}%`, g.bracket, 'activity', 'warning'),
        statCard('Earned So Far', fmtMoney(g.earned_to_date), `Projected ${fmtMoney(g.projected_total)}`, 'credit-card', 'secondary'),
    ].join('');

    renderChart('dashboardMainChart', {
        type: 'bar',
        data: {
            labels: data.series.map((row) => row.date.slice(5)),
            datasets: [{
                label: 'Adjusted weight (kg)',
                data: data.series.map((row) => row.kg),
                backgroundColor: 'rgba(16, 185, 129, 0.55)',
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { callback: (v) => `${v} kg` } } },
        },
    });

    $('panel-side-title').textContent = 'Attendance Bracket Tracker';

    const attendanceRing = ringSvg({
        percent: g.attendance_pct,
        radius: 50,
        center: `${g.attendance_pct}%`,
        label: 'Attendance',
        small: true,
    });
    const salaryRing = ringSvg({
        percent: g.progress_pct,
        radius: 50,
        center: fmtMoneyCompact(g.earned_to_date),
        label: 'of ' + fmtMoneyCompact(g.projected_total),
        small: true,
        gauge: true,
    });

    let bracketHtml;
    if (isCollector) {
        const pct = g.attendance_pct;
        bracketHtml = `
            <div class="salary-brackets">
                <div class="bracket-item ${pct > 80 ? 'highlight' : ''}">
                    <span class="bracket-range">&gt; 80% Attendance</span>
                    <span class="bracket-rate">Rs. ${fmtNumber(rates.above_80, 0)} / kg</span>
                </div>
                <div class="bracket-item ${pct >= 70 && pct <= 80 ? 'highlight' : ''}">
                    <span class="bracket-range">70% - 80% Attendance</span>
                    <span class="bracket-rate">Rs. ${fmtNumber(rates.between_70_80, 0)} / kg</span>
                </div>
                <div class="bracket-item ${pct < 70 ? 'highlight' : ''}">
                    <span class="bracket-range">&lt; 70% Attendance</span>
                    <span class="bracket-rate">Rs. ${fmtNumber(rates.below_70, 0)} / kg</span>
                </div>
            </div>`;
    } else {
        bracketHtml = `
            <div class="bracket-item highlight" style="margin-top:16px;">
                <span class="bracket-range">${esc(state.user.gender)} daily wage</span>
                <span class="bracket-rate">Rs. ${fmtNumber(g.rate, 0)} / day</span>
            </div>`;
    }

    $('panel-side-body').innerHTML = `
        <div class="gauge-row">${attendanceRing}${salaryRing}</div>
        <div class="gauge-caption">Day ${g.day_of_cycle} of ${g.cycle_days} · ${esc(g.bracket)}</div>
        ${bracketHtml}
    `;
}

/* ------------------------------------------------------------- supervisors */
function sectionBadges(user) {
    const sections = Array.isArray(user.sections) && user.sections.length
        ? user.sections
        : (user.area ? [user.area] : []);
    if (!sections.length) {
        return '<span class="badge badge-info">All Sections</span>';
    }
    return sections
        .map((area) => `<span class="badge badge-info">${esc(area)}</span>`)
        .join('');
}

async function loadSupervisors() {
    const filter = state.includeInactiveSupervisors ? '' : '&active=1';
    const data = await api.get(`/api/users?role=supervisor${filter}`);
    const tbody = $('supervisors-table-body');
    tbody.innerHTML = data.users.length ? data.users.map((user) => `
        <tr>
            <td><strong>SUP-${user.user_id}</strong></td>
            <td>${esc(user.name)}</td>
            <td>${esc(user.gender)}</td>
            <td>${esc(user.phone)}</td>
            <td><div class="section-badges">${sectionBadges(user)}</div></td>
            <td>${user.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Inactive</span>'}</td>
            <td>
                <button class="btn btn-secondary btn-sm" data-action="edit-user" data-id="${user.user_id}"><i data-feather="edit-2"></i> Edit</button>
                <button class="btn btn-secondary btn-sm" data-action="reset-password" data-id="${user.user_id}" style="margin-left:6px;"><i data-feather="key"></i> Reset</button>
                <button class="btn ${user.is_active ? 'btn-secondary' : 'btn-primary'} btn-sm" data-action="toggle-user-active" data-id="${user.user_id}" data-active="${user.is_active ? '0' : '1'}" style="margin-left:6px;">
                    <i data-feather="${user.is_active ? 'user-x' : 'user-check'}"></i> ${user.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button class="btn btn-danger btn-sm" data-action="delete-user" data-id="${user.user_id}" style="margin-left:6px;"><i data-feather="trash-2"></i> Delete</button>
            </td>
        </tr>`).join('') : emptyRow(7, 'No supervisors yet. Add the first one.');
    refreshIcons();
}

/* ---------------------------------------------------------------- servants */
async function loadServants() {
    const filter = state.includeInactiveServants ? '' : '&active=1';
    const data = await api.get(`/api/users?role=servant${filter}`);
    const tbody = $('servants-table-body');
    const isOwner = state.user.role === 'owner';

    tbody.innerHTML = data.users.length ? data.users.map((user) => `
        <tr>
            <td><strong>SRV-${user.user_id}</strong></td>
            <td>${esc(user.name)}</td>
            <td>${esc(user.gender)}</td>
            <td>${workTypeBadge(user.work_type)}</td>
            <td>${esc(user.phone)}</td>
            <td>${user.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Inactive</span>'}</td>
            <td>
                <button class="btn btn-secondary btn-sm" data-action="edit-user" data-id="${user.user_id}"><i data-feather="edit-2"></i> Edit</button>
                ${isOwner ? `<button class="btn btn-secondary btn-sm" data-action="reset-password" data-id="${user.user_id}" style="margin-left:6px;"><i data-feather="key"></i> Reset</button>` : ''}
                ${isOwner ? `<button class="btn ${user.is_active ? 'btn-secondary' : 'btn-primary'} btn-sm" data-action="toggle-user-active" data-id="${user.user_id}" data-active="${user.is_active ? '0' : '1'}" style="margin-left:6px;"><i data-feather="${user.is_active ? 'user-x' : 'user-check'}"></i> ${user.is_active ? 'Deactivate' : 'Activate'}</button>` : ''}
                ${isOwner ? `<button class="btn btn-danger btn-sm" data-action="delete-user" data-id="${user.user_id}" style="margin-left:6px;"><i data-feather="trash-2"></i> Delete</button>` : ''}
            </td>
        </tr>`).join('') : emptyRow(7, 'No servants registered yet.');
    refreshIcons();
}

/* -------------------------------------------------------------- attendance */
async function loadAttendance() {
    const dateInput = $('attendance-date');
    if (!dateInput.value) dateInput.value = serverToday();
    dateInput.max = serverToday();

    const data = await api.get(`/api/attendance?date=${encodeURIComponent(dateInput.value)}`);
    const tbody = $('attendance-table-body');

    tbody.innerHTML = data.rows.length ? data.rows.map((row) => `
        <tr id="att-row-${row.servant_id}">
            <td>
                <div style="font-weight:600;">${esc(row.name)}</div>
                <span style="font-size:0.75rem;color:var(--text-secondary);">SRV-${row.servant_id}</span>
            </td>
            <td>${workTypeBadge(row.work_type)}</td>
            <td>${esc(row.gender)}</td>
            <td><span id="att-status-${row.servant_id}" class="badge ${row.status === 'Present' ? 'badge-success' : 'badge-danger'}">${row.status}</span></td>
            <td><input type="time" id="time-in-${row.servant_id}" class="glass-input" style="padding:6px 12px;width:120px;" value="${esc(row.check_in || '')}" data-change="attendance-time" data-servant="${row.servant_id}"></td>
            <td><input type="time" id="time-out-${row.servant_id}" class="glass-input" style="padding:6px 12px;width:120px;" value="${esc(row.check_out || '')}" data-change="attendance-time" data-servant="${row.servant_id}"></td>
            <td>
                <button class="btn btn-secondary btn-sm" data-action="quick-present" data-servant="${row.servant_id}"><i data-feather="check"></i> Present</button>
                <button class="btn btn-danger btn-sm" data-action="quick-absent" data-servant="${row.servant_id}" style="margin-left:6px;"><i data-feather="x"></i> Absent</button>
            </td>
        </tr>`).join('') : emptyRow(7, 'No servants registered yet.');
    refreshIcons();
}

/* The attendance tab holds two independent cards; the day sheet reloads on every
 * date change, so the history card is loaded once per visit rather than from
 * loadAttendance(). */
async function loadAttendanceView() {
    await loadAttendance();
    await loadAttendanceHistory();
}

async function loadAttendanceHistory() {
    const startInput = $('history-start-date');
    const endInput = $('history-end-date');
    const cycle = state.config && state.config.current_cycle;
    const range = clampCycleRange(cycle);
    const today = serverToday();

    if (!startInput.value) startInput.value = range.start;
    if (!endInput.value) endInput.value = range.end;
    startInput.max = today;
    endInput.max = today;
    if (endInput.value > today) endInput.value = today;
    if (startInput.value > endInput.value) startInput.value = endInput.value;

    // state.weightWorkers only holds active servants (both work types), while
    // history also needs inactive ones, so it must not be reused here.
    if (!state.historyServants) {
        const data = await api.get('/api/users?role=servant&active=1');
        state.historyServants = data.users;
    }
    const select = $('history-servant');
    const previous = select.value;
    select.innerHTML =
        '<option value="">All servants</option>' +
        state.historyServants
            .map((user) => `<option value="${user.user_id}">${esc(user.name)}</option>`)
            .join('');
    if (previous && state.historyServants.some((user) => String(user.user_id) === previous)) {
        select.value = previous;
    }

    // The endpoint applies no row limit, so a bounded range is always sent.
    const params = new URLSearchParams({ start: startInput.value, end: endInput.value });
    if (select.value) params.set('servant_id', select.value);

    const data = await api.get(`/api/attendance/history?${params}`);
    const tbody = $('history-table-body');
    tbody.innerHTML = data.rows.length ? data.rows.map((row) => `
        <tr>
            <td>${esc(row.work_date)}</td>
            <td>
                <div style="font-weight:600;">${esc(row.servant_name)}</div>
                <span style="font-size:0.75rem;color:var(--text-secondary);">SRV-${row.servant_id}</span>
            </td>
            <td>${esc(row.check_in || '--:--')}</td>
            <td>${esc(row.check_out || '--:--')}</td>
            <td>${statusBadge(row.status)}</td>
        </tr>`).join('') : emptyRow(5, 'No attendance records for this range.');

    await renderHistorySummary(params);
    refreshIcons();
}

/* One servant selected -> show the server-computed attendance percentage. It comes
 * from /api/attendance/summary so the bracket maths is never re-derived in JS. */
async function renderHistorySummary(params) {
    const container = $('history-summary');
    if (!params.get('servant_id')) {
        container.innerHTML = '';
        return;
    }

    const summary = await api.get(`/api/attendance/summary?${params}`);
    const row = summary.rows[0];
    container.innerHTML = row
        ? `<span class="badge badge-info" style="font-size:0.85rem;padding:6px 12px;">
               Present ${row.present_days} of ${row.period_days} · ${row.attendance_pct}%
           </span>`
        : '';
}

async function saveAttendanceTime(servantId) {
    const date = $('attendance-date').value;
    const checkIn = $(`time-in-${servantId}`).value || null;
    const checkOut = $(`time-out-${servantId}`).value || null;
    const result = await api.put(`/api/attendance/${servantId}/${date}`, {
        check_in: checkIn,
        check_out: checkOut,
    });
    const badge = $(`att-status-${servantId}`);
    if (badge) {
        badge.className = `badge ${result.status === 'Present' ? 'badge-success' : 'badge-danger'}`;
        badge.textContent = result.status;
    }
}

/* ------------------------------------------------------------------ weights */
async function loadWeights() {
    const dateInput = $('weight-date');
    if (!dateInput.value) dateInput.value = serverToday();
    dateInput.max = serverToday();

    if (!state.weightWorkers) {
        const users = await api.get('/api/users?role=servant&active=1');
        // Retail workers also collect leaf when needed; their registered work
        // type is never changed by recording a weight.
        state.weightWorkers = users.users.filter(
            (user) => user.work_type === 'Tea Collector' || user.work_type === 'Retail Worker'
        );
    }

    const select = $('weight-servant-select');
    const previous = select.value;
    select.innerHTML = state.weightWorkers.length
        ? state.weightWorkers
            .map((user) => `<option value="${user.user_id}">${esc(user.name)} · ${esc(user.work_type)}</option>`)
            .join('')
        : '<option value="">No servants registered</option>';
    if (previous && state.weightWorkers.some((user) => String(user.user_id) === previous)) {
        select.value = previous;
    }

    await prefillWeightArea();
    await loadWeightLog();
}

async function prefillWeightArea() {
    const date = $('weight-date').value || serverToday();
    const servantId = $('weight-servant-select').value;
    const areaSelect = $('weight-area-select');
    // Never carry an area over from the previously selected servant/day.
    areaSelect.value = '';
    if (!servantId) return;
    try {
        const data = await api.get(`/api/assignments?date=${encodeURIComponent(date)}`);
        const row = data.rows.find((entry) => String(entry.servant_id) === String(servantId));
        if (row && row.area) areaSelect.value = row.area;
    } catch (error) {
        /* prefill is best-effort only */
    }
}

async function loadWeightLog() {
    const date = $('weight-date').value || todayISO();
    const data = await api.get(`/api/weights?date=${encodeURIComponent(date)}`);
    const tbody = $('daily-weights-table-body');

    tbody.innerHTML = data.rows.length ? data.rows.map((row) => `
        <tr>
            <td>${esc(row.work_date)}</td>
            <td>${esc(row.servant_name)}</td>
            <td><span class="badge badge-info">${esc(row.area)}</span></td>
            <td>${fmtNumber(row.original_weight)} kg</td>
            <td>${row.rainy_day ? '<span class="badge badge-danger">Rainy</span>' : '<span class="badge badge-success">Dry</span>'}</td>
            <td style="font-weight:700;color:var(--primary-light);">${fmtNumber(row.adjusted_weight)} kg</td>
            <td><button class="btn btn-danger btn-sm" data-action="delete-weight" data-id="${row.weight_id}"><i data-feather="trash-2"></i></button></td>
        </tr>`).join('') : emptyRow(7, 'No weighings recorded for this day.');

    const total = data.rows.reduce((sum, row) => sum + row.adjusted_weight, 0);
    $('today-total-weight-badge').textContent = `Total: ${fmtNumber(total)} kg`;
    refreshIcons();
}

function scheduleRainyPreview() {
    clearTimeout(state.rainyTimer);
    state.rainyTimer = setTimeout(updateRainyPreview, 250);
}

async function updateRainyPreview() {
    const original = parseFloat($('weight-original').value);
    const rainy = $('weight-rainy-toggle').checked;
    const preview = $('rainy-preview');

    if (!original || original <= 0) {
        preview.style.display = 'none';
        return;
    }
    try {
        const data = await api.post('/api/weights/preview', {
            original_weight: original,
            rainy_day: rainy,
        });
        preview.style.display = 'flex';
        $('preview-original').textContent = `${fmtNumber(data.original_weight)} kg`;
        $('preview-deduction').textContent = `${fmtNumber(data.deduction)} kg`;
        $('preview-final').textContent = `${fmtNumber(data.adjusted_weight)} kg`;
    } catch (error) {
        preview.style.display = 'none';
    }
}

async function submitWeight(event) {
    event.preventDefault();
    const servantId = parseInt($('weight-servant-select').value, 10);
    if (!servantId) {
        showToast('Register a servant first.', 'error');
        return;
    }
    const payload = {
        servant_id: servantId,
        date: $('weight-date').value,
        original_weight: parseFloat($('weight-original').value),
        rainy_day: $('weight-rainy-toggle').checked,
        area: $('weight-area-select').value,
    };
    try {
        await api.post('/api/weights', payload);
        showToast('Weighing record saved.', 'success');
        $('weight-original').value = '';
        $('weight-rainy-toggle').checked = false;
        $('rainy-preview').style.display = 'none';
        await loadWeightLog();
    } catch (error) {
        reportError(error);
    }
}

/* -------------------------------------------------------------- assignments */
async function loadAssignments() {
    const dateInput = $('assignment-date');
    if (!dateInput.value) dateInput.value = serverToday();
    dateInput.max = serverToday();

    const data = await api.get(`/api/assignments?date=${encodeURIComponent(dateInput.value)}`);
    const areas = (state.config && state.config.areas) || data.areas || [];
    const tbody = $('assignments-table-body');

    tbody.innerHTML = data.rows.length ? data.rows.map((row) => `
        <tr>
            <td>
                <div style="font-weight:600;">${esc(row.name)}</div>
                <span style="font-size:0.75rem;color:var(--text-secondary);">SRV-${row.servant_id}</span>
            </td>
            <td>${workTypeBadge(row.work_type)}</td>
            <td>
                <select class="glass-input" style="width:220px;" data-servant="${row.servant_id}">
                    <option value="">— Unassigned —</option>
                    ${areas.map((area) => `<option value="${esc(area)}" ${row.area === area ? 'selected' : ''}>${esc(area)}</option>`).join('')}
                </select>
            </td>
        </tr>`).join('') : emptyRow(3, 'No servants registered yet.');
    refreshIcons();
}

async function saveAssignments() {
    const date = $('assignment-date').value;
    const entries = [...document.querySelectorAll('#assignments-table-body select')].map((select) => ({
        servant_id: parseInt(select.dataset.servant, 10),
        area: select.value || null,
    }));
    if (!entries.length) {
        showToast('Nothing to save.', 'error');
        return;
    }
    await api.post('/api/assignments/bulk', { date, entries });
    showToast('Work-area assignments saved.', 'success');
}

/* ------------------------------------------------------------------- salary */
async function loadSalary() {
    const rates = await api.get('/api/rates');
    $('rate-above-80').value = rates.rates.above_80;
    $('rate-70-80').value = rates.rates.between_70_80;
    $('rate-below-70').value = rates.rates.below_70;
    $('rate-male-daily').value = rates.rates.male_daily;
    $('rate-female-daily').value = rates.rates.female_daily;

    const start = $('salary-start-date');
    const end = $('salary-end-date');
    const range = clampCycleRange(state.config && state.config.suggested_next_cycle);
    if (!start.value || !end.value) {
        start.value = range.start;
        end.value = range.end;
    }
    start.max = serverToday();
    end.max = serverToday();

    await previewSalary();
    await loadRuns();
    refreshIcons();
}

async function previewSalary() {
    let start = $('salary-start-date').value;
    let end = $('salary-end-date').value;
    if (!start || !end) return;

    // Future days are not counted by the server; keep the inputs honest.
    const today = serverToday();
    if (end > today) {
        end = today;
        $('salary-end-date').value = end;
    }
    if (start > end) {
        showToast('Start date must not be after end date.', 'error');
        return;
    }

    const data = await api.get(`/api/payroll/preview?start=${start}&end=${end}`);
    state.salary = data;
    renderSalaryTable(data);
}

function renderSalaryTable(data) {
    const hint = $('salary-period-hint');
    const today = serverToday();
    const completeCycle = data.is_cycle && data.period_end < today;
    const compileButton = $('compile-run-btn');
    if (compileButton) compileButton.disabled = !completeCycle;

    if (!data.is_cycle) {
        hint.textContent = `${data.period_days} days selected — a payroll run must cover exactly 10 days. Compiling is disabled.`;
    } else if (data.period_end >= today) {
        hint.textContent = `Cycle ${data.period_start} → ${data.period_end} is still in progress. It can be compiled from ${addDaysISO(data.period_end, 1)}, once every day has been recorded.`;
    } else {
        hint.textContent = `10-day cycle selected (${data.period_start} → ${data.period_end}) — expected total ${fmtMoney(data.totals.total_salary)}.`;
    }

    const runLines = new Map();
    if (data.existing_run) {
        data.existing_run.lines.forEach((line) => runLines.set(line.servant_id, line));
    }

    const tbody = $('salary-table-body');
    tbody.innerHTML = data.lines.length ? data.lines.map((line) => {
        const runLine = runLines.get(line.servant_id);
        let statusCell = '<span class="badge badge-info">Not compiled</span>';
        let actionCell = '<span style="color:var(--text-secondary);">—</span>';

        if (runLine) {
            statusCell = statusBadge(runLine.status);
            actionCell = `
                ${runLine.status === 'Pending'
                    ? `<button class="btn btn-primary btn-sm" data-action="pay-line" data-run="${data.existing_run.run_id}" data-salary="${runLine.salary_id}"><i data-feather="check"></i> Pay</button>`
                    : ''}
                <button class="btn btn-secondary btn-sm" data-action="view-payslip" data-id="${runLine.salary_id}" style="margin-left:6px;"><i data-feather="file-text"></i> Payslip</button>`;
        } else if (data.is_cycle) {
            actionCell = '<span style="color:var(--text-secondary);font-size:0.8rem;">Compile the run to pay</span>';
        }

        return `
            <tr>
                <td><strong>SRV-${line.servant_id}</strong></td>
                <td>${esc(line.name)}</td>
                <td>${workTypeBadge(line.work_type)}</td>
                <td>${pctBadge(line.attendance_pct)}</td>
                <td style="font-weight:600;">${esc(line.output_label)}</td>
                <td style="color:var(--secondary);font-weight:500;">${esc(line.rate_label)}</td>
                <td style="font-weight:700;color:var(--primary-light);font-size:1.05rem;">${fmtMoney(line.total_salary)}</td>
                <td>${statusCell}</td>
                <td>${actionCell}</td>
            </tr>`;
    }).join('') : emptyRow(9, 'No servants registered yet.');

    renderRunActions(data);
    refreshIcons();
}

function renderRunActions(data) {
    const bar = $('salary-run-actions');
    const run = data.existing_run;

    if (!run) {
        bar.style.display = 'flex';
        bar.innerHTML = data.is_cycle
            ? '<span style="color:var(--text-secondary);font-size:0.85rem;">Preview only — press “Compile 10-Day Run” to create the draft run.</span>'
            : '';
        return;
    }

    // The bar is re-rendered on every load, so the chosen method lives in state
    // and is re-marked `selected` here rather than being read back off the DOM.
    const methods = (state.config && state.config.payment_methods) || ['Cash'];
    const methodOptions = methods
        .map((method) => `<option value="${esc(method)}"${state.paymentMethod === method ? ' selected' : ''}>${esc(method)}</option>`)
        .join('');
    const pendingCount = (run.lines || []).filter((line) => line.status === 'Pending').length;

    bar.style.display = 'flex';
    bar.innerHTML = `
        <span class="badge ${run.status === 'finalized' ? 'badge-success' : 'badge-warning'}" style="align-self:center;">Run #${run.run_id} · ${run.status}</span>
        <select id="salary-payment-method" class="glass-input" data-change="payment-method"
                title="How the payment is being made. Recorded against each line you pay."
                style="width:auto;padding:6px 10px;font-size:0.85rem;">
            ${methodOptions}
        </select>
        <input id="salary-payment-ref" type="text" class="glass-input" maxlength="60" data-input="payment-ref"
               value="${esc(state.paymentRef)}" placeholder="Reference (cheque no., etc.)"
               style="width:220px;padding:6px 10px;font-size:0.85rem;">
        ${run.status === 'draft'
            ? `<button class="btn btn-secondary btn-sm" data-action="finalize-run" data-run="${run.run_id}"><i data-feather="lock"></i> Finalize</button>`
            : ''}
        ${pendingCount
            ? `<button class="btn btn-primary btn-sm" data-action="pay-run" data-run="${run.run_id}"><i data-feather="check-circle"></i> Pay All Pending (${pendingCount})</button>`
            : '<span style="color:var(--text-secondary);font-size:0.85rem;align-self:center;">All lines paid.</span>'}
        <button class="btn btn-secondary btn-sm" data-action="export-run" data-run="${run.run_id}"><i data-feather="download"></i> Export CSV</button>
        ${run.status === 'draft'
            ? `<button class="btn btn-danger btn-sm" data-action="delete-run" data-run="${run.run_id}"><i data-feather="trash-2"></i> Delete Draft</button>`
            : ''}
    `;
    refreshIcons();
}

async function loadRuns() {
    const data = await api.get('/api/payroll/runs?limit=25');
    const tbody = $('runs-table-body');

    tbody.innerHTML = data.runs.length ? data.runs.map((run) => `
        <tr>
            <td><strong>#${run.run_id}</strong></td>
            <td>${esc(run.period_start)} → ${esc(run.period_end)}</td>
            <td>${statusBadge(run.status)}</td>
            <td>${run.servant_count}</td>
            <td>${run.paid_count} / ${run.servant_count}</td>
            <td style="font-weight:700;color:var(--primary-light);">${fmtMoney(run.total_salary)}</td>
            <td>
                <button class="btn btn-secondary btn-sm" data-action="view-run" data-run="${run.run_id}"><i data-feather="eye"></i> View</button>
                <button class="btn btn-secondary btn-sm" data-action="export-run" data-run="${run.run_id}" style="margin-left:6px;"><i data-feather="download"></i> CSV</button>
                ${run.status === 'draft'
                    ? `<button class="btn btn-danger btn-sm" data-action="delete-run" data-run="${run.run_id}" style="margin-left:6px;"><i data-feather="trash-2"></i> Delete</button>`
                    : ''}
            </td>
        </tr>`).join('') : emptyRow(7, 'No payroll runs yet.');
    refreshIcons();
}

/* Every line of a single run, with the admin actions that apply to it. */
async function openRunDetail(runId) {
    const { run, lines } = await api.get(`/api/payroll/runs/${runId}`);

    // The detail endpoint selects from payroll_runs alone, so unlike the listing
    // it carries no servant_count / paid_count / total_salary. Derive them here.
    const paidCount = lines.filter((line) => line.status === 'Paid').length;
    const total = lines.reduce((sum, line) => sum + (Number(line.total_salary) || 0), 0);
    const rateRows = Object.entries(run.rates || {})
        .map(([key, value]) => `<span class="badge badge-info" style="margin-right:6px;">${esc(key)}: ${fmtNumber(value)}</span>`)
        .join('');
    const methods = (state.config && state.config.payment_methods) || ['Cash'];
    const methodOptions = methods
        .map((method) => `<option value="${esc(method)}"${state.paymentMethod === method ? ' selected' : ''}>${esc(method)}</option>`)
        .join('');

    $('run-modal-body').innerHTML = `
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:14px;">
            <span class="badge badge-info">Run #${run.run_id}</span>
            ${statusBadge(run.status)}
            <span style="color:var(--text-secondary);font-size:0.9rem;">
                ${esc(run.period_start)} → ${esc(run.period_end)} (${run.period_days} days)
            </span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:14px;">
            <div><span style="color:var(--text-secondary);font-size:0.8rem;">Servants</span>
                 <div style="font-weight:700;">${lines.length}</div></div>
            <div><span style="color:var(--text-secondary);font-size:0.8rem;">Paid</span>
                 <div style="font-weight:700;">${paidCount} / ${lines.length}</div></div>
            <div><span style="color:var(--text-secondary);font-size:0.8rem;">Total</span>
                 <div style="font-weight:700;color:var(--primary-light);">${fmtMoney(total)}</div></div>
            <div><span style="color:var(--text-secondary);font-size:0.8rem;">Compiled</span>
                 <div style="font-size:0.85rem;">${esc(run.compiled_at || '—')}
                     ${run.compiled_by_name ? `· ${esc(run.compiled_by_name)}` : ''}</div></div>
            ${run.finalized_at ? `<div><span style="color:var(--text-secondary);font-size:0.8rem;">Finalized</span>
                 <div style="font-size:0.85rem;">${esc(run.finalized_at)}</div></div>` : ''}
        </div>
        <div style="margin-bottom:14px;">${rateRows}</div>
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px;">
            <span style="color:var(--text-secondary);font-size:0.85rem;">Payment details for lines paid here:</span>
            <select id="run-modal-payment-method" class="glass-input" data-change="payment-method"
                    style="width:auto;padding:6px 10px;font-size:0.85rem;">
                ${methodOptions}
            </select>
            <input id="run-modal-payment-ref" type="text" class="glass-input" maxlength="60" data-input="payment-ref"
                   value="${esc(state.paymentRef)}" placeholder="Reference (cheque no., etc.)"
                   style="width:230px;padding:6px 10px;font-size:0.85rem;">
        </div>
        <div class="data-table-container">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Servant</th><th>Type</th><th>Attendance</th><th>Output</th>
                        <th>Rate</th><th>Salary</th><th>Status</th><th>Paid via</th><th></th>
                    </tr>
                </thead>
                <tbody>
                    ${lines.length ? lines.map((line) => `
                        <tr>
                            <td><strong>SRV-${line.servant_id}</strong><br><span style="color:var(--text-secondary);font-size:0.8rem;">${esc(line.name)}</span></td>
                            <td>${workTypeBadge(line.work_type)}</td>
                            <td>${pctBadge(line.attendance_pct)}</td>
                            <td style="font-weight:600;">${esc(line.output_label)}</td>
                            <td style="color:var(--secondary);font-weight:500;">${esc(line.rate_label)}</td>
                            <td style="font-weight:700;color:var(--primary-light);">${fmtMoney(line.total_salary)}</td>
                            <td>${statusBadge(line.status)}</td>
                            <td>${line.payment_method
                                ? `${esc(line.payment_method)}${line.payment_ref ? `<br><span style="color:var(--text-secondary);font-size:0.75rem;">${esc(line.payment_ref)}</span>` : ''}`
                                : '—'}</td>
                            <td style="white-space:nowrap;">
                                <button class="btn btn-secondary btn-sm" data-action="view-payslip" data-id="${line.salary_id}"><i data-feather="file-text"></i> Slip</button>
                                ${line.status === 'Pending'
                                    ? `<button class="btn btn-primary btn-sm" data-action="run-detail-pay" data-run="${run.run_id}" data-salary="${line.salary_id}" style="margin-left:6px;"><i data-feather="check"></i> Pay</button>`
                                    : ''}
                            </td>
                        </tr>`).join('') : emptyRow(9, 'This run has no lines.')}
                </tbody>
            </table>
        </div>
    `;
    openModal('run-modal');
    refreshIcons();
}

/* ------------------------------------------------------------------ reports */
async function loadReports() {
    const start = $('report-start-date');
    const end = $('report-end-date');
    const range = clampCycleRange(state.config && state.config.current_cycle);
    if (!start.value || !end.value) {
        start.value = range.start;
        end.value = range.end;
    }
    const today = serverToday();
    start.max = today;
    end.max = today;
    if (end.value > today) end.value = today;
    if (start.value > end.value) start.value = end.value;

    const [overview, leaderboard] = await Promise.all([
        api.get(`/api/reports/overview?start=${start.value}&end=${end.value}`),
        api.get(`/api/reports/leaderboard?start=${start.value}&end=${end.value}`),
    ]);

    renderChart('reportChartSalaryWeight', {
        data: {
            labels: overview.series.map((row) => row.date.slice(5)),
            datasets: [
                {
                    type: 'bar',
                    label: 'Harvest (kg)',
                    data: overview.series.map((row) => row.harvest_kg),
                    backgroundColor: 'rgba(16, 185, 129, 0.55)',
                    borderRadius: 6,
                    yAxisID: 'y',
                },
                {
                    type: 'line',
                    label: 'Real payroll cost (Rs.)',
                    data: overview.series.map((row) => row.cost_rs),
                    borderColor: '#06b6d4',
                    backgroundColor: 'rgba(6, 182, 212, 0.15)',
                    tension: 0.35,
                    fill: true,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: { position: 'left', ticks: { callback: (v) => `${v} kg` } },
                y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { callback: (v) => `Rs. ${v}` } },
            },
        },
    });

    renderChart('reportChartRainyDeduction', {
        type: 'doughnut',
        data: {
            labels: ['Dry leaf (kg)', 'Rainy leaf after deduction (kg)', 'Rain deduction (kg)'],
            datasets: [{
                data: [
                    overview.rainy.dry_weight,
                    overview.rainy.rainy_adjusted,
                    overview.rainy.rainy_deduction,
                ],
                backgroundColor: ['rgba(16, 185, 129, 0.7)', 'rgba(6, 182, 212, 0.7)', 'rgba(239, 68, 68, 0.7)'],
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: { legend: { position: 'bottom' } },
        },
    });

    const tbody = $('leaderboard-table-body');
    const medals = { 1: '🥇', 2: '🥈', 3: '🥉' };
    tbody.innerHTML = leaderboard.rows.length ? leaderboard.rows.map((row) => `
        <tr>
            <td style="font-weight:700;">${medals[row.rank] || `#${row.rank}`}</td>
            <td>${esc(row.name)}</td>
            <td>${row.days_worked}</td>
            <td>${fmtNumber(row.original_weight)} kg</td>
            <td style="color:var(--danger);">-${fmtNumber(row.deducted)} kg</td>
            <td style="font-weight:700;color:var(--primary-light);">${fmtNumber(row.adjusted_weight)} kg</td>
            <td>${pctBadge(row.attendance_pct)}</td>
            <td><span class="badge ${row.efficiency === 'Harvest Master' ? 'badge-success' : row.efficiency === 'Consistent' ? 'badge-info' : 'badge-warning'}">${esc(row.efficiency)}</span></td>
        </tr>`).join('') : emptyRow(8, 'No collector data for this range.');
    refreshIcons();
}

/* -------------------------------------------------------- servant records */
async function loadServantRecords() {
    const data = await api.get('/api/servant/records');

    $('servant-my-weighings').innerHTML = data.weights.length ? data.weights.map((row) => {
        const deduction = row.original_weight - row.adjusted_weight;
        return `
            <tr>
                <td>${esc(row.work_date)}</td>
                <td><strong>${esc(row.area)}</strong></td>
                <td>${fmtNumber(row.original_weight)} kg</td>
                <td>${row.rainy_day ? '<span class="badge badge-danger">Rainy</span>' : '<span class="badge badge-success">Dry</span>'}</td>
                <td style="color:var(--danger);font-weight:500;">-${fmtNumber(deduction)} kg</td>
                <td style="font-weight:700;color:var(--primary-light);">${fmtNumber(row.adjusted_weight)} kg</td>
            </tr>`;
    }).join('') : emptyRow(6, 'No tea weight records logged for you yet.');

    $('servant-my-attendance').innerHTML = data.attendance.length ? data.attendance.map((row) => `
        <tr>
            <td>${esc(row.work_date)}</td>
            <td>${esc(row.check_in || '--:--')}</td>
            <td>${esc(row.check_out || '--:--')}</td>
            <td>${statusBadge(row.status)}</td>
        </tr>`).join('') : emptyRow(4, 'No attendance logs recorded for you.');

    $('servant-my-salary').innerHTML = data.history.length ? data.history.map((row) => `
        <tr>
            <td>${esc(row.period_start)} → ${esc(row.period_end)}</td>
            <td>${pctBadge(row.attendance_pct)}</td>
            <td>${row.total_weight > 0 ? `${fmtNumber(row.total_weight)} kg` : `${row.present_days} days`}</td>
            <td style="font-weight:700;color:var(--primary-light);">${fmtMoney(row.total_salary)}</td>
            <td>${statusBadge(row.status)}</td>
            <td><button class="btn btn-secondary btn-sm" data-action="view-payslip" data-id="${row.salary_id}"><i data-feather="file-text"></i> View</button></td>
        </tr>`).join('') : emptyRow(6, 'No salary runs have included you yet.');

    const totals = data.totals || {};
    $('servant-my-weighings-note').textContent = recordNote(data.weights.length, totals.weights);
    $('servant-my-attendance-note').textContent = recordNote(data.attendance.length, totals.attendance);
    $('servant-my-salary-note').textContent = recordNote(data.history.length, totals.salary_history);
    refreshIcons();
}

/* ----------------------------------------------------------------- payslip */
async function openPayslip(salaryId) {
    const { payslip } = await api.get(`/api/payroll/payslips/${salaryId}`);
    state.payslip = payslip;

    const rows = [
        ['Servant', `SRV-${payslip.servant_id} · ${payslip.name}`],
        ['Work type', payslip.work_type],
        ['Period', `${payslip.period_start} → ${payslip.period_end} (${payslip.period_days} days)`],
        ['Days present', `${payslip.present_days} of ${payslip.period_days}`],
        ['Attendance', `${payslip.attendance_pct}%`],
        ['Output', payslip.output_label],
        ['Rate applied', payslip.rate_label],
        ['Status', payslip.status],
        ['Paid at', payslip.paid_at || '—'],
        ['Paid via', payslip.payment_method
            ? `${payslip.payment_method}${payslip.payment_ref ? ` (${payslip.payment_ref})` : ''}`
            : '—'],
    ];

    $('payslip-body').innerHTML = `
        <div class="payslip-header">
            <div>
                <h2>Ceylon Tea Factory</h2>
                <p>Salary Payslip</p>
            </div>
            <div class="payslip-ref">
                <div><strong>Slip #${payslip.salary_id}</strong></div>
                <div>Run #${payslip.run_id}</div>
            </div>
        </div>
        <table class="data-table payslip-table">
            <tbody>
                ${rows.map(([label, value]) => `<tr><th style="width:38%;">${esc(label)}</th><td>${esc(value)}</td></tr>`).join('')}
            </tbody>
        </table>
        <div class="payslip-total">
            <span>Gross Salary</span>
            <strong>${fmtMoney(payslip.total_salary)}</strong>
        </div>
    `;
    openModal('payslip-modal');
    refreshIcons();
}

/* ----------------------------------------------------------------- actions */
function bindEvents() {
    $('login-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const phone = $('login-phone').value.trim();
        const password = $('login-password').value;
        try {
            const { user } = await api.post('/api/auth/login', { phone, password });
            state.user = user;
            $('login-phone').value = '';
            $('login-password').value = '';
            showToast(`Welcome back, ${user.name}!`, 'success');
            await enterApp();
        } catch (error) {
            reportError(error);
        }
    });

    $('weight-entry-form').addEventListener('submit', submitWeight);
    $('user-form').addEventListener('submit', saveUser);
    $('password-form').addEventListener('submit', changePassword);

    document.querySelectorAll('.menu-item').forEach((item) => {
        item.addEventListener('click', () => switchTab(item.dataset.tab));
    });

    /* ---- navigation & generic ---- */
    registerAction('toggle-sidebar', toggleSidebar);
    registerAction('close-sidebar', closeSidebar);
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        // A modal owns Escape while it is open; ui.js closes it first.
        if (document.querySelector('.modal-overlay.active')) return;
        if ($('sidebar-nav').classList.contains('mobile-open')) closeSidebar();
    });
    registerAction('logout', handleLogout);
    registerAction('close-modal', ({ target }) => closeModal(target));
    registerAction('open-password-modal', () => {
        $('password-form').reset();
        openModal('password-modal');
    });
    registerAction('date-today', ({ target }) => {
        const input = $(target);
        if (input) {
            input.value = serverToday();
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });

    /* ---- users ---- */
    registerAction('add-user', ({ role }) => openUserModal({ role }));
    registerAction('edit-user', ({ id }) => openUserModal({ userId: parseInt(id, 10) }));
    registerAction('delete-user', ({ id }) => removeUser(parseInt(id, 10)));
    registerAction('reset-password', ({ id }) => resetPassword(parseInt(id, 10)));
    registerAction('toggle-user-active', ({ id, active }) =>
        setUserActive(parseInt(id, 10), active === '1').catch(reportError));
    registerChange('user-filter', (_dataset, el) => {
        if (el.id === 'supervisors-include-inactive') {
            state.includeInactiveSupervisors = el.checked;
            loadSupervisors().catch(reportError);
        } else {
            state.includeInactiveServants = el.checked;
            loadServants().catch(reportError);
        }
    });

    /* ---- attendance ---- */
    registerChange('attendance-history', () => loadAttendanceHistory().catch(reportError));
    registerAction('attendance-history-cycle', () => {
        const range = clampCycleRange(state.config && state.config.current_cycle);
        $('history-start-date').value = range.start;
        $('history-end-date').value = range.end;
        loadAttendanceHistory().catch(reportError);
    });
    registerChange('attendance-date', () => loadAttendance().catch(reportError));
    registerChange('attendance-time', ({ servant }) => {
        saveAttendanceTime(parseInt(servant, 10)).catch((error) => {
            reportError(error);
            loadAttendance().catch(reportError);
        });
    });
    registerAction('quick-present', async ({ servant }) => {
        const id = parseInt(servant, 10);
        $(`time-in-${id}`).value = '07:30';
        $(`time-out-${id}`).value = '17:00';
        try {
            await saveAttendanceTime(id);
            showToast('Attendance logged: Present', 'success');
        } catch (error) {
            reportError(error);
        }
    });
    registerAction('quick-absent', async ({ servant }) => {
        const id = parseInt(servant, 10);
        $(`time-in-${id}`).value = '';
        $(`time-out-${id}`).value = '';
        try {
            await saveAttendanceTime(id);
            showToast('Attendance logged: Absent', 'info');
        } catch (error) {
            reportError(error);
        }
    });

    /* ---- weights ---- */
    registerChange('weight-date', () => loadWeights().catch(reportError));
    registerChange('rainy-preview', () => updateRainyPreview());
    registerInput('rainy-preview', () => scheduleRainyPreview());
    $('weight-servant-select').addEventListener('change', () => prefillWeightArea());
    registerAction('delete-weight', async ({ id }) => {
        if (!window.confirm('Delete this weighing record?')) return;
        try {
            await api.del(`/api/weights/${id}`);
            showToast('Weighing record deleted.', 'success');
            await loadWeightLog();
        } catch (error) {
            reportError(error);
        }
    });

    /* ---- assignments ---- */
    registerChange('assignment-date', () => loadAssignments().catch(reportError));
    registerAction('save-assignments', () => saveAssignments().catch(reportError));

    /* ---- salary ---- */
    registerChange('salary-period', () => previewSalary().catch(reportError));
    registerAction('preview-salary', () => previewSalary().catch(reportError));
    registerAction('save-rates', saveRates);
    registerAction('compile-run', compileRun);
    registerAction('pay-line', payLine);
    registerAction('pay-run', payRun);
    registerChange('payment-method', (_dataset, el) => {
        state.paymentMethod = el.value;
    });
    registerInput('payment-ref', (_dataset, el) => {
        state.paymentRef = el.value;
    });
    registerAction('finalize-run', finalizeRun);
    registerAction('delete-run', deleteRun);
    registerAction('export-run', ({ run }) => {
        window.location.href = `/api/payroll/runs/${run}/export?format=csv`;
    });

    /* ---- reports ---- */
    registerChange('report-period', () => loadReports().catch(reportError));
    registerAction('report-current-cycle', () => {
        const range = clampCycleRange(state.config && state.config.current_cycle);
        $('report-start-date').value = range.start;
        $('report-end-date').value = range.end;
        loadReports().catch(reportError);
    });

    /* ---- payroll run detail ---- */
    registerAction('view-run', ({ run }) => openRunDetail(parseInt(run, 10)).catch(reportError));
    registerAction('run-detail-pay', async ({ run, salary }) => {
        await payLine({ run: parseInt(run, 10), salary });
        // payLine() refreshes the salary table, not this modal, so the row would
        // otherwise still read "Pending" until the modal is reopened.
        await openRunDetail(parseInt(run, 10)).catch(reportError);
    });

    /* ---- payslip ---- */
    registerAction('view-payslip', ({ id }) => openPayslip(parseInt(id, 10)).catch(reportError));
    registerAction('print-payslip', () => window.print());
    registerAction('download-payslip-csv', () => {
        if (state.payslip) {
            window.location.href = `/api/payroll/payslips/${state.payslip.salary_id}/export?format=csv`;
        }
    });
}

async function handleLogout() {
    try {
        await api.post('/api/auth/logout');
    } catch (error) {
        /* signing out locally is fine even if the request failed */
    }
    resetClientState();
    showAuthView();
    showToast('Signed out successfully.', 'info');
}

async function changePassword(event) {
    event.preventDefault();
    const currentPassword = $('password-current').value;
    const newPassword = $('password-new').value;
    const confirmPassword = $('password-confirm').value;
    const wasForced = $('password-modal').classList.contains('force-change');

    if (newPassword !== confirmPassword) {
        showToast('New passwords do not match.', 'error');
        return;
    }
    try {
        await api.post('/api/auth/password', {
            current_password: currentPassword,
            new_password: newPassword,
        });
        $('password-form').reset();
        $('password-modal').classList.remove('force-change');
        closeModal('password-modal');
        showToast('Password updated.', 'success');
        if (state.user) state.user.must_change_password = false;
        if (wasForced) await initializeApp();
    } catch (error) {
        reportError(error);
    }
}

/* ------------------------------------------------------------ user modals */
const userCache = new Map();

function setSectionSelection(sections) {
    const chosen = new Set(sections || []);
    document.querySelectorAll('#user-sections input[type="checkbox"]').forEach((box) => {
        box.checked = chosen.has(box.value);
    });
}

function selectedSections() {
    return [...document.querySelectorAll('#user-sections input[type="checkbox"]:checked')]
        .map((box) => box.value);
}

async function openUserModal({ role, userId }) {
    const title = $('user-modal-title');
    const idInput = $('user-modal-id');
    const roleInput = $('user-modal-role');
    const workTypeContainer = $('user-work-type-container');
    const areaContainer = $('user-area-container');
    const passwordInput = $('user-password');
    const passwordHint = $('user-password-hint');

    if (userId) {
        const { user } = await api.get(`/api/users/${userId}`);
        userCache.set(userId, user);
        title.textContent = `Edit ${user.role === 'servant' ? 'Servant' : 'Supervisor'}`;
        idInput.value = user.user_id;
        roleInput.value = user.role;
        $('user-name').value = user.name;
        $('user-gender').value = user.gender;
        $('user-phone').value = user.phone;
        passwordInput.value = '';
        passwordInput.required = false;
        passwordHint.style.display = 'block';

        workTypeContainer.style.display = user.role === 'servant' ? 'block' : 'none';
        areaContainer.style.display = user.role === 'supervisor' ? 'block' : 'none';
        if (user.role === 'servant') $('user-work-type').value = user.work_type;
        if (user.role === 'supervisor') {
            const assigned = Array.isArray(user.sections) && user.sections.length
                ? user.sections
                : (user.area ? [user.area] : []);
            setSectionSelection(assigned);
        }
    } else {
        title.textContent = role === 'servant' ? 'Add Servant' : 'Add Supervisor';
        $('user-form').reset();
        setSectionSelection([]);
        idInput.value = '';
        roleInput.value = role;
        passwordInput.required = true;
        passwordHint.style.display = 'none';
        workTypeContainer.style.display = role === 'servant' ? 'block' : 'none';
        areaContainer.style.display = role === 'supervisor' ? 'block' : 'none';
    }
    openModal('user-modal');
    refreshIcons();
}

async function saveUser(event) {
    event.preventDefault();
    const userId = $('user-modal-id').value;
    const role = $('user-modal-role').value;

    const payload = {
        name: $('user-name').value.trim(),
        gender: $('user-gender').value,
        phone: $('user-phone').value.trim(),
    };
    if (role === 'servant') payload.work_type = $('user-work-type').value;
    if (role === 'supervisor') payload.sections = selectedSections();

    const password = $('user-password').value;
    if (password) payload.password = password;

    try {
        if (userId) {
            await api.put(`/api/users/${userId}`, payload);
            showToast('User updated.', 'success');
        } else {
            payload.role = role;
            if (!password) {
                showToast('A password is required for a new account.', 'error');
                return;
            }
            await api.post('/api/users', payload);
            showToast('User registered.', 'success');
        }
        invalidateUserCaches();
        closeModal('user-modal');
        if (state.activeTab === 'supervisors') await loadSupervisors();
        if (state.activeTab === 'servants') await loadServants();
    } catch (error) {
        reportError(error);
    }
}

function invalidateUserCaches() {
    state.weightWorkers = null;
    state.historyServants = null;
    userCache.clear();
}

async function setUserActive(userId, active, confirmFirst = true) {
    const cached = userCache.get(userId);
    const label = cached ? cached.name : `user #${userId}`;
    if (!active && confirmFirst && !window.confirm(`Deactivate ${label}? They will not be able to sign in.`)) {
        return;
    }
    try {
        await api.put(`/api/users/${userId}`, { is_active: active });
        invalidateUserCaches();
        showToast(active ? 'Account activated.' : 'Account deactivated.', 'success');
        if (state.activeTab === 'supervisors') await loadSupervisors();
        if (state.activeTab === 'servants') await loadServants();
    } catch (error) {
        reportError(error);
    }
}

async function removeUser(userId) {
    const cached = userCache.get(userId);
    const label = cached ? cached.name : `user #${userId}`;
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;

    try {
        await api.del(`/api/users/${userId}`);
        invalidateUserCaches();
        showToast('User deleted.', 'success');
        if (state.activeTab === 'supervisors') await loadSupervisors();
        if (state.activeTab === 'servants') await loadServants();
    } catch (error) {
        if (error.code === 'has_payroll_history') {
            if (window.confirm(`${label} has payroll history and cannot be deleted.\n\nDeactivate the account instead?`)) {
                await setUserActive(userId, false, false);
            }
            return;
        }
        reportError(error);
    }
}

async function resetPassword(userId) {
    if (!window.confirm('Generate a new temporary password for this user?')) return;
    try {
        const data = await api.post(`/api/users/${userId}/reset-password`);
        $('temp-password-value').textContent = data.temp_password;
        openModal('temp-password-modal');
        refreshIcons();
    } catch (error) {
        reportError(error);
    }
}

/* ----------------------------------------------------------- salary actions */
async function saveRates() {
    const payload = {
        above_80: parseFloat($('rate-above-80').value),
        between_70_80: parseFloat($('rate-70-80').value),
        below_70: parseFloat($('rate-below-70').value),
        male_daily: parseFloat($('rate-male-daily').value),
        female_daily: parseFloat($('rate-female-daily').value),
    };
    try {
        await api.put('/api/rates', payload);
        showToast('Payment rates updated.', 'success');
        await previewSalary();
    } catch (error) {
        reportError(error);
    }
}

async function compileRun() {
    const start = $('salary-start-date').value;
    const end = $('salary-end-date').value;
    if (!start || !end) {
        showToast('Select a date range first.', 'error');
        return;
    }
    if (end >= serverToday()) {
        showToast('This cycle has not finished yet. Compile it on the day after its final day.', 'error');
        return;
    }
    try {
        await api.post('/api/payroll/runs', { start, end });
        showToast('Payroll run compiled.', 'success');
        await previewSalary();
        await loadRuns();
    } catch (error) {
        reportError(error);
    }
}

async function payLine({ run, salary }) {
    try {
        await api.post(`/api/payroll/runs/${run}/pay`, {
            salary_ids: [parseInt(salary, 10)],
            payment_method: state.paymentMethod || null,
            payment_ref: state.paymentRef.trim() || null,
        });
        showToast('Payment recorded.', 'success');
        await previewSalary();
        await loadRuns();
    } catch (error) {
        reportError(error);
    }
}

async function payRun({ run }) {
    if (!window.confirm('Mark every pending line in this run as paid?')) return;
    try {
        await api.post(`/api/payroll/runs/${run}/pay`, {
            payment_method: state.paymentMethod || null,
            payment_ref: state.paymentRef.trim() || null,
        });
        showToast('All pending lines paid.', 'success');
        await previewSalary();
        await loadRuns();
    } catch (error) {
        reportError(error);
    }
}

async function finalizeRun({ run }) {
    try {
        await api.post(`/api/payroll/runs/${run}/finalize`, {});
        showToast('Run finalized.', 'success');
        await previewSalary();
        await loadRuns();
    } catch (error) {
        reportError(error);
    }
}

async function deleteRun({ run }) {
    if (!window.confirm('Delete this draft run? The payslip lines will be removed.')) return;
    try {
        await api.del(`/api/payroll/runs/${run}`);
        showToast('Draft run deleted.', 'success');
        await previewSalary();
        await loadRuns();
    } catch (error) {
        reportError(error);
    }
}

/* -------------------------------------------------------------------- init */
boot();
