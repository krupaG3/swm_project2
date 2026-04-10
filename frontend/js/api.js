// const API_BASE = "http://127.0.0.1:8000/api";
const API_BASE = 'https://swm-project2.onrender.com/api';

// ── Token helpers ──────────────────────────────
function getToken() {
    return localStorage.getItem('access_token');
}

function getUser() {
    const u = localStorage.getItem('user');
    return u ? JSON.parse(u) : null;
}

function logout() {
    localStorage.clear();
    window.location.href = 'pages/login.html';
}

// ── Core fetch wrapper ─────────────────────────
async function apiFetch(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
    });

    if (response.status === 401) {
        logout();
        return;
    }

    const data = await response.json();

    if (!response.ok) {
        throw data;
    }

    return data;
}

// ── Auth ───────────────────────────────────────
async function login(username, password) {
    const data = await apiFetch('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    });
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);

    const user = await apiFetch('/auth/me/');
    localStorage.setItem('user', JSON.stringify(user));
    return user;
}

// ── Projects ───────────────────────────────────
async function getProjects() {
    return apiFetch('/projects/');
}

// ── Households ─────────────────────────────────
async function getHouseholds(projectId, search = '') {
    return apiFetch(`/households/?project=${projectId}&search=${search}`);
}

// ── Collections ────────────────────────────────
async function submitCollection(data) {
    return apiFetch('/collections/', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

async function getDailyCollections(projectId, date) {
    return apiFetch(`/collections/daily/?project=${projectId}&date=${date}`);
}

// ── Alerts ─────────────────────────────────────
async function getMissingHouseholds(projectId, date) {
    return apiFetch(`/alerts/missing/?project=${projectId}&date=${date}`);
}

// ── Dashboard ──────────────────────────────────
async function getDailyDashboard(projectId, date) {
    return apiFetch(`/dashboard/daily/?project=${projectId}&date=${date}`);
}

async function getWeeklyDashboard(projectId) {
    return apiFetch(`/dashboard/weekly/?project=${projectId}`);
}