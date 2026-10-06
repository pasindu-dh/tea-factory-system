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
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('active');
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('active');
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

/* Escape-key closes any open modal. */
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach((modal) => {
            modal.classList.remove('active');
        });
    }
});
