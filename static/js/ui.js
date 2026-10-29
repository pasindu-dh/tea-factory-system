/* ui.js — escaping, formatting, toasts, modals, and delegated event wiring. */

/* Escape any value before putting it inside an innerHTML template. */
function esc(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/* Local-time YYYY-MM-DD. Never use toISOString(): it is UTC and can be a day
 * off after midnight. */
function todayISO() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
}

function addDaysISO(iso, days) {
    const [year, month, day] = iso.split('-').map(Number);
    const shifted = new Date(year, month - 1, day + days);
    const m = String(shifted.getMonth() + 1).padStart(2, '0');
    const d = String(shifted.getDate()).padStart(2, '0');
    return `${shifted.getFullYear()}-${m}-${d}`;
}

/* The factory's date, from /api/config, so a browser in another timezone
 * cannot shift "today" and its date limits. Falls back to local time. */
function serverToday() {
    if (typeof state !== 'undefined' && state.config && state.config.today) {
        return state.config.today;
    }
    return todayISO();
}

/* Clip a cycle range to today. If the whole cycle is still in the future,
 * fall back to the trailing ten days. */
function clampCycleRange(cycle) {
    const today = serverToday();
    const start = (cycle && cycle.start) || addDaysISO(today, -9);
    let end = (cycle && cycle.end) || today;
    if (start > today) return { start: addDaysISO(today, -9), end: today };
    if (end > today) end = today;
    return { start, end };
}

const fmtMoney = (value) => `Rs. ${Math.round(Number(value) || 0).toLocaleString('en-LK')}`;
const fmtNumber = (value, digits = 2) =>
    (Number(value) || 0).toLocaleString('en-LK', { maximumFractionDigits: digits });
const fmtKg = (value) => `${fmtNumber(value)} kg`;

function refreshIcons() {
    if (window.feather) feather.replace();
}

/* ------------------------------------------------------------------ toasts */
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = 'info';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'alert-triangle';

    toast.innerHTML = `<i data-feather="${icon}" style="width: 18px; height: 18px;"></i> <span>${esc(message)}</span>`;
    container.appendChild(toast);
    refreshIcons();

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function reportError(error) {
    showToast(error && error.message ? error.message : 'Something went wrong.', 'error');
}

/* ------------------------------------------------------------------ modals */
/* A stack so the payslip opened from the run-detail modal paints above it.
 * Escape closes only the top-most modal. */
const modalStack = [];
let modalZ = 100;

function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    const existing = modalStack.indexOf(id);
    if (existing !== -1) modalStack.splice(existing, 1);
    modalZ += 1;
    modal.style.zIndex = String(modalZ);
    modal.classList.add('active');
    modalStack.push(id);
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('active');
    const index = modalStack.indexOf(id);
    if (index !== -1) modalStack.splice(index, 1);
}

function closeAllModals() {
    document.querySelectorAll('.modal-overlay.active').forEach((modal) => {
        modal.classList.remove('active');
        modal.style.zIndex = '';
    });
    modalStack.length = 0;
    modalZ = 100;
}

/* ----------------------------------------------------- delegated listeners */
const delegatedActions = {};
const delegatedChanges = {};
const delegatedInputs = {};

function registerAction(name, handler) {
    delegatedActions[name] = handler;
}

function registerChange(name, handler) {
    delegatedChanges[name] = handler;
}

function registerInput(name, handler) {
    delegatedInputs[name] = handler;
}

document.addEventListener('click', (event) => {
    const el = event.target.closest('[data-action]');
    if (!el) return;
    const handler = delegatedActions[el.dataset.action];
    if (!handler) return;
    event.preventDefault();
    handler(el.dataset, el);
});

document.addEventListener('change', (event) => {
    const el = event.target.closest('[data-change]');
    if (!el) return;
    const handler = delegatedChanges[el.dataset.change];
    if (!handler) return;
    handler(el.dataset, el);
});

document.addEventListener('input', (event) => {
    const el = event.target.closest('[data-input]');
    if (!el) return;
    const handler = delegatedInputs[el.dataset.input];
    if (!handler) return;
    handler(el.dataset, el);
});

/* Escape-key closes the top-most modal only. A forced password change cannot
 * be dismissed at all. */
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    for (let i = modalStack.length - 1; i >= 0; i -= 1) {
        const id = modalStack[i];
        const modal = document.getElementById(id);
        if (!modal || !modal.classList.contains('active')) {
            modalStack.splice(i, 1);
            continue;
        }
        if (modal.classList.contains('force-change')) return;
        closeModal(id);
        return;
    }
});
