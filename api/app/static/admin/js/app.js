const API_BASE = '/api/v1';
const AUTH_STORAGE_KEY = 'civiccare_admin_token';
const USER_STORAGE_KEY = 'civiccare_admin_user';

function getToken() {
  return sessionStorage.getItem(AUTH_STORAGE_KEY);
}

function setAuth(token, user) {
  if (token) sessionStorage.setItem(AUTH_STORAGE_KEY, token);
  if (user) sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

function clearAuth() {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  sessionStorage.removeItem(USER_STORAGE_KEY);
}

function authHeaders() {
  const token = getToken();
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

async function api(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...options.headers },
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {}
  if (!res.ok) {
    const err = new Error(data?.detail || data?.message || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function showToast(message, type = '') {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = 'toast ' + (type ? type : '');
  el.classList.remove('hidden');
  setTimeout(() => {
    el.classList.add('hidden');
  }, 3000);
}

// ---------------------------------------------------------------------------
// Hamburger menu (responsive sidebar)
// ---------------------------------------------------------------------------

function isSidebarOverlayMode() {
  return window.matchMedia('(max-width: 992px)').matches;
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const btn = document.getElementById('btn-hamburger');
  if (sidebar) sidebar.classList.remove('sidebar-open');
  if (overlay) {
    overlay.classList.remove('sidebar-overlay-visible');
    overlay.setAttribute('aria-hidden', 'true');
  }
  if (btn) {
    btn.setAttribute('aria-expanded', 'false');
  }
  document.body.style.overflow = '';
}

function openSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const btn = document.getElementById('btn-hamburger');
  if (sidebar) sidebar.classList.add('sidebar-open');
  if (overlay) {
    overlay.classList.add('sidebar-overlay-visible');
    overlay.setAttribute('aria-hidden', 'false');
  }
  if (btn) btn.setAttribute('aria-expanded', 'true');
  document.body.style.overflow = 'hidden';
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar?.classList.contains('sidebar-open')) {
    closeSidebar();
  } else {
    openSidebar();
  }
}

document.getElementById('btn-hamburger')?.addEventListener('click', () => {
  if (isSidebarOverlayMode()) toggleSidebar();
});

document.getElementById('sidebar-overlay')?.addEventListener('click', () => {
  if (isSidebarOverlayMode()) closeSidebar();
});

window.addEventListener('resize', () => {
  if (!isSidebarOverlayMode()) closeSidebar();
});

const SIDEBAR_COLLAPSED_KEY = 'civiccare-sidebar-collapsed';
function isSidebarCollapsed() {
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
}
function setSidebarCollapsed(collapsed) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  if (collapsed) {
    sidebar.classList.add('sidebar-collapsed');
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, '1');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('title', 'Expand sidebar');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('aria-label', 'Expand sidebar');
  } else {
    sidebar.classList.remove('sidebar-collapsed');
    localStorage.removeItem(SIDEBAR_COLLAPSED_KEY);
    document.getElementById('sidebar-collapse-btn')?.setAttribute('title', 'Collapse sidebar');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('aria-label', 'Collapse sidebar');
  }
}
function toggleSidebarCollapse() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  const collapsed = sidebar.classList.toggle('sidebar-collapsed');
  if (collapsed) {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, '1');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('title', 'Expand sidebar');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('aria-label', 'Expand sidebar');
  } else {
    localStorage.removeItem(SIDEBAR_COLLAPSED_KEY);
    document.getElementById('sidebar-collapse-btn')?.setAttribute('title', 'Collapse sidebar');
    document.getElementById('sidebar-collapse-btn')?.setAttribute('aria-label', 'Collapse sidebar');
  }
}
document.getElementById('sidebar-collapse-btn')?.addEventListener('click', toggleSidebarCollapse);
function initSidebarCollapsed() {
  const sidebar = document.getElementById('sidebar');
  const btn = document.getElementById('sidebar-collapse-btn');
  if (isSidebarCollapsed()) {
    sidebar?.classList.add('sidebar-collapsed');
    btn?.setAttribute('title', 'Expand sidebar');
    btn?.setAttribute('aria-label', 'Expand sidebar');
  }
}
if (document.readyState !== 'loading') {
  initSidebarCollapsed();
} else {
  document.addEventListener('DOMContentLoaded', initSidebarCollapsed);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && isSidebarOverlayMode()) {
    const sidebar = document.getElementById('sidebar');
    if (sidebar?.classList.contains('sidebar-open')) closeSidebar();
  }
});

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    if (isSidebarOverlayMode()) closeSidebar();
    const page = item.dataset.page;
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
    const target = document.getElementById(`page-${page}`);
    if (target) target.classList.add('active');
    const title = PAGE_TITLES[page] || 'Admin';
    document.getElementById('page-title').textContent = title;
    document.title =
      page === 'command-center'
        ? 'Command Center · CivicCare Admin'
        : `${title} · CivicCare Admin`;
    updateHeaderActions(page);
    if (page === 'command-center' || page === 'map') initCommandCenter();
    if (page === 'dashboard') loadDashboard();
    if (page === 'analytics') {
      populateAnalyticsFilters();
      loadDepartmentAnalytics();
    }
    if (page === 'escalations') {
      populateEscalationFilters();
      loadEscalations();
    }
    if (page === 'grievances') {
      populateGrievanceFilters();
      loadGrievances();
    }
    if (page === 'departments') {
      loadDepartmentsAndCategories();
    }
    if (page === 'parties') {
      loadParties();
    }
    if (page === 'party-map') initPartyMap();
    if (page === 'wards') {
      populateWardZoneFilter();
      loadWardsAndZones();
    }
    if (page === 'workers') {
      workersSkip = 0;
      populateWorkerFilters();
      loadWorkers();
    }
    if (page === 'citizens') {
      citizensSkip = 0;
      loadCitizens();
    }
    if (page === 'logs') loadSystemLogs();
  });
});

function onWorkersFilterChange() {
  workersSkip = 0;
  loadWorkers();
}
document.getElementById('filter-worker-department')?.addEventListener('change', onWorkersFilterChange);
document.getElementById('filter-worker-ward')?.addEventListener('change', onWorkersFilterChange);
document.getElementById('filter-worker-role')?.addEventListener('change', onWorkersFilterChange);
document.getElementById('filter-worker-status')?.addEventListener('change', onWorkersFilterChange);
document.getElementById('filter-worker-limit')?.addEventListener('change', onWorkersFilterChange);

function updateHeaderActions(page) {
  const el = document.getElementById('header-quick-actions');
  if (!el) return;
  const actions = {
    grievances: () => { grievancesSkip = 0; loadGrievances(); },
    escalations: () => { escalationsSkip = 0; loadEscalations(); },
    workers: () => { workersSkip = 0; loadWorkers(); },
    'command-center': () => refreshCommandCenter?.(),
    map: undefined,
    analytics: undefined,
    'party-map': () => loadPartyMapData(),
    departments: () => loadDepartmentsAndCategories(),
    parties: () => loadParties(),
    wards: () => loadWardsAndZones(),
    citizens: () => loadCitizens(),
    logs: () => loadSystemLogs(),
  };
  const fn = actions[page];
  if (fn) {
    el.innerHTML = '<button type="button" class="btn btn-primary btn-sm" id="header-refresh-btn">Refresh</button>';
    el.querySelector('#header-refresh-btn')?.addEventListener('click', fn);
  } else {
    el.innerHTML = '';
  }
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function renderAuth() {
  const token = getToken();
  const userJson = sessionStorage.getItem(USER_STORAGE_KEY);
  const user = userJson ? JSON.parse(userJson) : null;
  const loginForm = document.getElementById('login-form');
  const userInfo = document.getElementById('user-info');
  const userName = document.getElementById('user-name');
  const userInfoHeader = document.getElementById('user-info-header');
  const userNameHeader = document.getElementById('user-name-header');
  const displayName = user?.name || user?.phone || 'Admin';
  if (token && user) {
    loginForm.classList.add('hidden');
    userInfo.classList.remove('hidden');
    userInfoHeader?.classList.remove('hidden');
    if (userName) userName.textContent = displayName;
    if (userNameHeader) userNameHeader.textContent = displayName;
  } else {
    loginForm.classList.remove('hidden');
    userInfo.classList.add('hidden');
    userInfoHeader?.classList.add('hidden');
  }
  const btnUpdateCis = document.getElementById('btn-update-cis');
  if (btnUpdateCis) {
    const isAdmin = (user?.role || '').toLowerCase() === 'admin';
    btnUpdateCis.classList.toggle('hidden', !(token && user && isAdmin));
  }
}

document.getElementById('btn-login')?.addEventListener('click', async () => {
  const userIdRaw = document.getElementById('login-user-id').value.trim();
  const password = document.getElementById('login-password').value;
  if (!userIdRaw || !password) {
    showToast('Enter User ID or phone and password', 'error');
    return;
  }
  try {
    // Allow either staff User ID (UUID) or phone for department portal login.
    const isUuid = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
      userIdRaw
    );
    const body = isUuid
      ? { user_id: userIdRaw, password }
      : { phone: userIdRaw, password };

    const data = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const token = data?.tokens?.access_token;
    const user = data?.user;
    const role = (user?.role || '').toLowerCase();
    if (role === 'citizen') {
      // Citizens can use the mobile/web citizen portal, but not this department dashboard.
      clearAuth();
      showToast('Citizens cannot access the department portal.', 'error');
      return;
    }
    if (token) {
      setAuth(token, user);
      renderAuth();
      showToast('Logged in', 'success');
    }
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Login failed', 'error');
  }
});

document.getElementById('btn-logout')?.addEventListener('click', () => {
  clearAuth();
  renderAuth();
  showToast('Logged out');
});
document.getElementById('btn-logout-header')?.addEventListener('click', () => {
  clearAuth();
  renderAuth();
  showToast('Logged out');
});

document.querySelectorAll('.quick-action-btn, .dnav-link').forEach((btn) => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const page = btn.dataset.page;
    const navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (navItem) navItem.click();
  });
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

let dashboardTrendChart = null;

function apiWithTimeout(path, ms = 15000) {
  return Promise.race([
    api(path),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Request timeout')), ms)),
  ]);
}

async function loadDashboard() {
  const setStat = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const recentEl = document.getElementById('recent-grievances-list');
  const trendCanvas = document.getElementById('chart-escalation-trend');
  try {
    const results = await Promise.allSettled([
      apiWithTimeout('/grievances?limit=1'),
      apiWithTimeout('/departments'),
      apiWithTimeout('/workers?limit=1'),
      apiWithTimeout('/wards'),
      apiWithTimeout('/grievances?status=pending&limit=1'),
      apiWithTimeout('/grievances?status=resolved&limit=1'),
      apiWithTimeout('/grievances?status=assigned&limit=1'),
      apiWithTimeout('/grievances?status=inprogress&limit=1'),
      apiWithTimeout('/grievances?status=escalated&limit=1'),
      apiWithTimeout('/analytics/grievances/escalation-priority'),
      apiWithTimeout('/grievances?status=escalated&limit=50'),
    ]);
    const fulfilled = (r) => (r.status === 'fulfilled' ? r.value : null);
    const gResp = fulfilled(results[0]);
    const dResp = fulfilled(results[1]);
    const wResp = fulfilled(results[2]);
    const wardsResp = fulfilled(results[3]);
    const pendingResp = fulfilled(results[4]);
    const resolvedResp = fulfilled(results[5]);
    const assignedResp = fulfilled(results[6]);
    const inprogressResp = fulfilled(results[7]);
    const escalatedResp = fulfilled(results[8]);
    const escalationsListResp = fulfilled(results[9]);
    const escalationsTrendResp = fulfilled(results[10]);
    const total = gResp?.total ?? 0;
    const pending   = pendingResp?.total    ?? 0;
    const resolved  = resolvedResp?.total   ?? 0;
    const assigned  = assignedResp?.total   ?? 0;
    const inprogress= inprogressResp?.total ?? 0;
    const escalated = escalatedResp?.total ?? 0;

    setStat('stat-grievances', total);
    setStat('stat-escalated', escalated);
    setStat('stat-pending', pending);
    setStat('stat-resolved', resolved);
    setStat('stat-assigned', assigned);
    setStat('stat-inprogress', inprogress);
    setStat('stat-departments', (dResp && dResp.length) || 0);
    setStat('stat-workers', wResp?.total ?? 0);
    setStat('stat-wards', (wardsResp && wardsResp.length) || 0);

    // Staff-to-ward alarm: ratio < 1 staff per 50 wards = critical
    const workersCount = wResp?.total ?? 0;
    const wardsCount = (wardsResp && wardsResp.length) || 0;
    const workersEl = document.getElementById('dmeta-workers');
    const alarmEl = document.getElementById('dmeta-workers-alarm');
    if (workersEl && alarmEl && wardsCount > 0) {
      const ratio = workersCount / wardsCount;
      workersEl.classList.remove('dmeta-alarm-critical', 'dmeta-alarm-warning');
      alarmEl.textContent = '';
      alarmEl.setAttribute('aria-hidden', 'true');
      if (ratio < 0.02) {
        workersEl.classList.add('dmeta-alarm-critical');
      } else if (ratio < 0.04) {
        workersEl.classList.add('dmeta-alarm-warning');
      }
    }

    // Top 10 EPS grievances — command center priority view
    if (recentEl) {
      const items = Array.isArray(escalationsListResp) ? escalationsListResp.slice(0, 10) : [];
      if (escalationsListResp === null) {
        recentEl.innerHTML = '<div class="activity-empty">Could not load. <a href="#" id="dashboard-retry">Retry</a></div>';
        setTimeout(() => {
          document.getElementById('dashboard-retry')?.addEventListener('click', (ev) => {
            ev.preventDefault();
            recentEl.innerHTML = '<div class="activity-empty">Loading…</div>';
            loadDashboard();
          });
        }, 0);
      } else if (!items.length) {
        recentEl.innerHTML = '<div class="activity-empty">No escalation priority data.</div>';
      } else {
        recentEl.innerHTML = items.map((g) => {
          const eps = Number(g?.eps?.total ?? 0).toFixed(1);
          const level = escapeHtml(g?.escalation_level || 'Low');
          const dept = escapeHtml(g?.department || '–');
          const ward = escapeHtml(g?.ward || '–');
          const zone = escapeHtml(g?.zone || '–');
          const worker = escapeHtml(g?.worker || 'Unassigned');
          return `
          <div class="activity-item activity-item-compact" data-id="${g.id}">
            <div class="activity-row-main">
              <span class="activity-dot activity-dot-escalated" aria-label="escalated"></span>
              <div class="activity-content">
                <div class="activity-title">${escapeHtml(g.title || '–')}</div>
                <div class="activity-meta">
                  EPS ${eps} (${level}) · ${dept} · ${ward} · ${zone} · ${worker}
                </div>
              </div>
              <div class="activity-actions">
                <button type="button" class="btn btn-sm btn-secondary btn-view-grievance" data-id="${g.id}" title="Open details">View</button>
              </div>
            </div>
          </div>
        `;
        }).join('');

        recentEl.querySelectorAll('.btn-view-grievance').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openGrievanceDetailModal(btn.dataset.id);
          });
        });
      }
    }

    // Escalation trend chart (replaces status breakdown)
    const trendItems = escalationsTrendResp?.items || [];
    const last7Days = [];
    const now = new Date();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      d.setHours(0, 0, 0, 0);
      last7Days.push(d);
    }
    const bucket = {};
    last7Days.forEach((d) => { bucket[d.toISOString().slice(0, 10)] = 0; });
    trendItems.forEach((g) => {
      if (g.created_at) {
        const key = new Date(g.created_at).toISOString().slice(0, 10);
        if (bucket[key] !== undefined) bucket[key]++;
      }
    });
    const labels = last7Days.map((d) => d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }));
    const data = last7Days.map((d) => bucket[d.toISOString().slice(0, 10)] || 0);

    if (dashboardTrendChart) { dashboardTrendChart.destroy(); dashboardTrendChart = null; }
    if (trendCanvas && typeof Chart !== 'undefined') {
      const ctx = trendCanvas.getContext('2d');
      dashboardTrendChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Escalations',
            data,
            backgroundColor: data.map((v) => (v > 0 ? 'rgba(209, 50, 18, 0.7)' : 'rgba(213, 219, 219, 0.5)')),
            borderColor: '#d13212',
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { stepSize: 1 } },
            x: { grid: { display: false } },
          },
        },
      });
    }
  } catch (e) {
    ['stat-grievances','stat-pending','stat-resolved','stat-assigned','stat-inprogress','stat-escalated','stat-departments','stat-workers','stat-wards']
      .forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = '–'; });
    const recentEl = document.getElementById('recent-grievances-list');
    if (recentEl) {
      const msg = (e?.message || 'Unknown error').toString().slice(0, 80);
      recentEl.innerHTML = `<div class="activity-empty">Unable to load data. <a href="#" id="dashboard-retry">Retry</a><br><small>${escapeHtml(msg)}</small></div>`;
      setTimeout(() => {
        document.getElementById('dashboard-retry')?.addEventListener('click', (ev) => {
          ev.preventDefault();
          recentEl.innerHTML = '<div class="activity-empty">Loading…</div>';
          loadDashboard();
        });
      }, 0);
    }
    const trendCanvas = document.getElementById('chart-escalation-trend');
    if (trendCanvas && dashboardTrendChart) {
      dashboardTrendChart.destroy();
      dashboardTrendChart = null;
    }
  }
}

// Dashboard clickable cards → navigate to page
document.querySelectorAll('.card-clickable[data-page]').forEach((card) => {
  card.addEventListener('click', () => {
    const page = card.dataset.page;
    const nav = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (nav) nav.click();
  });
});
document.querySelector('.nav-to-grievances')?.addEventListener('click', (e) => {
  e.preventDefault();
  document.querySelector('.nav-item[data-page="grievances"]')?.click();
});
document.querySelectorAll('a.panel-link[data-page]').forEach((a) => {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    const page = a.dataset.page;
    document.querySelector(`.nav-item[data-page="${page}"]`)?.click();
  });
});
document.getElementById('cmd-view-all-escalations')?.addEventListener('click', (e) => {
  e.preventDefault();
  document.querySelector('.nav-item[data-page="escalations"]')?.click();
});

// ---------------------------------------------------------------------------
// Grievances
// ---------------------------------------------------------------------------

let grievancesSkip = 0;

async function populateGrievanceFilters() {
  const wardSel = document.getElementById('filter-ward-id');
  const deptSel = document.getElementById('filter-category-dept');
  try {
    const [wards, depts] = await Promise.all([api('/wards').catch(() => []), api('/departments').catch(() => [])]);
    const wardList = Array.isArray(wards) ? wards : [];
    const deptList = Array.isArray(depts) ? depts : [];
    if (wardSel) {
      wardSel.innerHTML = '<option value="">All wards</option>';
      wardList.forEach((w) => wardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    }
    if (deptSel) {
      deptSel.innerHTML = '<option value="">All departments (category)</option>';
      deptList.forEach((d) => deptSel.appendChild(new Option(d.name, d.id)));
    }
  } catch (_) {}
}

function getGrievancesLimit() {
  const el = document.getElementById('filter-limit');
  const v = el && el.value;
  return v ? Math.max(1, Math.min(100, parseInt(v, 10))) : 10;
}

function formatDate(d) {
  if (!d) return '–';
  const dt = typeof d === 'string' ? new Date(d) : d;
  return dt.toLocaleString();
}

function renderGrievances(data) {
  const tbody = document.getElementById('grievances-tbody');
  const items = data?.items || [];
  tbody.innerHTML = items
    .map(
      (g) => {
        const wardCell = g.ward_number != null
          ? `#${g.ward_number} ${escapeHtml(g.ward_name || '')}`
          : escapeHtml(g.ward_name || '–');
        return `
    <tr>
      <td>${escapeHtml(g.title || '–')}</td>
      <td><span class="status-badge status-${(g.status || '').toLowerCase()}">${escapeHtml(g.status || '')}</span></td>
      <td><span class="priority-${(g.priority || 'medium').toLowerCase()}">${escapeHtml(g.priority || '–')}</span></td>
      <td>${escapeHtml(g.category_name || '–')}</td>
      <td>${wardCell}</td>
      <td>${escapeHtml(g.assigned_to_name || 'Unassigned')}</td>
      <td>${escapeHtml(g.assigned_to_phone || '–')}</td>
      <td>${escapeHtml(g.reporter_name || '–')}</td>
      <td>${escapeHtml(g.reporter_phone || '–')}</td>
      <td>${formatDate(g.created_at)}</td>
      <td>
        <button type="button" class="btn btn-sm btn-view-grievance" data-id="${g.id}">View</button>
        <button type="button" class="btn btn-sm btn-update-status" data-id="${g.id}" data-priority="${(g.priority || 'medium').toLowerCase()}" data-status="${escapeHtml(g.status || '')}">Status</button>
        <button type="button" class="btn btn-sm btn-assign-worker" data-id="${g.id}">Assign</button>
      </td>
    </tr>
  `;
      }
    )
    .join('');

  tbody.querySelectorAll('.btn-update-status').forEach((btn) => {
    btn.addEventListener('click', () => openStatusModal(btn.dataset.id, btn.dataset.priority, btn.dataset.status));
  });
  tbody.querySelectorAll('.btn-assign-worker').forEach((btn) => {
    btn.addEventListener('click', () => openAssignWorkerModal(btn.dataset.id));
  });
  tbody.querySelectorAll('.btn-view-grievance').forEach((btn) => {
    btn.addEventListener('click', () => openGrievanceDetailModal(btn.dataset.id));
  });

  const total = data?.total ?? 0;
  const limit = getGrievancesLimit();
  const pagination = document.getElementById('grievances-pagination');
  const prev = grievancesSkip > 0;
  const next = grievancesSkip + items.length < total;
  pagination.innerHTML = `
    <span>${grievancesSkip + 1}–${Math.min(grievancesSkip + items.length, total)} of ${total}</span>
    <button type="button" class="btn btn-sm" data-action="prev" ${prev ? '' : 'disabled'}>Previous</button>
    <button type="button" class="btn btn-sm" data-action="next" ${next ? '' : 'disabled'}>Next</button>
  `;
  pagination.querySelector('[data-action="prev"]')?.addEventListener('click', () => {
    grievancesSkip = Math.max(0, grievancesSkip - limit);
    loadGrievances();
  });
  pagination.querySelector('[data-action="next"]')?.addEventListener('click', () => {
    grievancesSkip += limit;
    loadGrievances();
  });
}

async function loadGrievances() {
  const statusFilter = document.getElementById('filter-status')?.value || '';
  const priorityFilter = document.getElementById('filter-priority')?.value || '';
  const wardIdEl = document.getElementById('filter-ward-id');
  const wardId = (wardIdEl && wardIdEl.value && wardIdEl.value.trim()) || '';
  const wardNameEl = document.getElementById('filter-ward-name');
  const wardName = (wardNameEl && wardNameEl.value.trim()) || '';
  const categoryDeptEl = document.getElementById('filter-category-dept');
  const categoryDept = (categoryDeptEl && categoryDeptEl.value && categoryDeptEl.value.trim()) || '';
  const reporterIdEl = document.getElementById('filter-reporter-id');
  const reporterId = (reporterIdEl && reporterIdEl.value.trim()) || '';
  const limit = getGrievancesLimit();
  let path = `/grievances?skip=${grievancesSkip}&limit=${limit}`;
  if (statusFilter) path += `&status=${encodeURIComponent(statusFilter)}`;
  if (priorityFilter) path += `&priority=${encodeURIComponent(priorityFilter)}`;
  if (wardId) path += `&ward_id=${encodeURIComponent(wardId)}`;
  if (wardName) path += `&ward_name=${encodeURIComponent(wardName)}`;
  if (categoryDept) path += `&category_dept=${encodeURIComponent(categoryDept)}`;
  if (reporterId) path += `&reporter_id=${encodeURIComponent(reporterId)}`;
  try {
    const data = await api(path);
    renderGrievances(data);
  } catch (e) {
    document.getElementById('grievances-tbody').innerHTML =
      '<tr><td colspan="9">Failed to load grievances.</td></tr>';
  }
}

document.getElementById('btn-refresh-grievances').addEventListener('click', () => {
  grievancesSkip = 0;
  loadGrievances();
});

document.getElementById('filter-status').addEventListener('change', () => {
  grievancesSkip = 0;
  loadGrievances();
});
document.getElementById('filter-priority').addEventListener('change', () => {
  grievancesSkip = 0;
  loadGrievances();
});
document.getElementById('filter-limit').addEventListener('change', () => {
  grievancesSkip = 0;
  loadGrievances();
});
document.getElementById('filter-ward-name').addEventListener('input', () => {
  const el = document.getElementById('filter-ward-name');
  if (el._applyTimeout) clearTimeout(el._applyTimeout);
  el._applyTimeout = setTimeout(() => {
    grievancesSkip = 0;
    loadGrievances();
  }, 400);
});
document.getElementById('filter-ward-id')?.addEventListener('change', () => {
  grievancesSkip = 0;
  loadGrievances();
});
document.getElementById('filter-category-dept')?.addEventListener('change', () => {
  grievancesSkip = 0;
  loadGrievances();
});
document.getElementById('filter-reporter-id')?.addEventListener('input', () => {
  const el = document.getElementById('filter-reporter-id');
  if (el._reporterTimeout) clearTimeout(el._reporterTimeout);
  el._reporterTimeout = setTimeout(() => {
    grievancesSkip = 0;
    loadGrievances();
  }, 500);
});

// ---------------------------------------------------------------------------
// Status modal
// ---------------------------------------------------------------------------

function openStatusModal(grievanceId, priority, status) {
  const token = getToken();
  if (!token) {
    showToast('Please log in to update status', 'error');
    return;
  }
  document.getElementById('modal-grievance-id').value = grievanceId;
  const priSelect = document.getElementById('modal-priority-select');
  if (priSelect && (priority || 'medium')) priSelect.value = (priority || 'medium').toLowerCase();
  const statusSelect = document.getElementById('modal-status-select');
  if (statusSelect && status) statusSelect.value = status.toLowerCase();
  document.getElementById('modal-status').classList.remove('hidden');
}

function closeStatusModal() {
  document.getElementById('modal-status').classList.add('hidden');
}

document.querySelector('.modal-backdrop')?.addEventListener('click', closeStatusModal);
document.querySelector('.modal-close')?.addEventListener('click', closeStatusModal);

document.getElementById('btn-save-status').addEventListener('click', async () => {
  const id = document.getElementById('modal-grievance-id').value;
  const status = document.getElementById('modal-status-select').value;
  const priority = document.getElementById('modal-priority-select').value;
  const body = { status };
  if (priority) body.priority = priority;
  try {
    await api(`/grievances/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    closeStatusModal();
    showToast('Status updated', 'success');
    loadGrievances();
    loadEscalations?.();
    loadDashboard();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

function openAssignWorkerModal(grievanceId) {
  if (!getToken()) {
    showToast('Please log in to assign officers', 'error');
    return;
  }
  document.getElementById('modal-assign-grievance-id').value = grievanceId;
  const sel = document.getElementById('modal-assign-worker-select');
  sel.innerHTML = '<option value="">Loading…</option>';
  document.getElementById('modal-assign-worker').classList.remove('hidden');
  api('/workers?limit=500')
    .then((data) => {
      const list = data?.items ?? (Array.isArray(data) ? data : []);
      sel.innerHTML = '<option value="">Select officer</option>';
      list.forEach((w) => sel.appendChild(new Option(`${w.name} (${w.designation})${w.phone ? ' · ' + w.phone : ''}`, w.id)));
    })
    .catch(() => {
      sel.innerHTML = '<option value="">Failed to load officers</option>';
    });
}

function closeAssignWorkerModal() {
  document.getElementById('modal-assign-worker').classList.add('hidden');
}

document.querySelector('#modal-assign-worker .modal-backdrop').addEventListener('click', closeAssignWorkerModal);
document.querySelector('.modal-close-assign').addEventListener('click', closeAssignWorkerModal);

document.getElementById('btn-save-assign').addEventListener('click', async () => {
  const grievanceId = document.getElementById('modal-assign-grievance-id').value;
  const workerId = document.getElementById('modal-assign-worker-select').value;
  if (!workerId) {
    showToast('Select an officer', 'error');
    return;
  }
  try {
    await api(`/grievances/${grievanceId}/assign`, {
      method: 'POST',
      body: JSON.stringify({ worker_id: workerId }),
    });
    closeAssignWorkerModal();
      showToast('Officer assigned', 'success');
    loadGrievances();
    loadEscalations?.();
    loadDashboard();
    if (document.getElementById('page-command-center')?.classList.contains('active')) {
      refreshCommandCenter?.();
    }
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Assign failed', 'error');
  }
});

// ---------------------------------------------------------------------------
// Escalations
// ---------------------------------------------------------------------------

let escalationsSkip = 0;
let escalationCharts = { zone: null, ward: null, priority: null, dept: null };

async function populateEscalationFilters() {
  const zoneSel = document.getElementById('escalations-filter-zone');
  const wardSel = document.getElementById('escalations-filter-ward');
  const deptSel = document.getElementById('escalations-filter-dept');
  try {
    const [zones, wards, depts] = await Promise.all([
      api('/zones').catch(() => []),
      api('/wards').catch(() => []),
      api('/departments').catch(() => []),
    ]);
    const zoneList = Array.isArray(zones) ? zones : [];
    const wardList = Array.isArray(wards) ? wards : [];
    const deptList = Array.isArray(depts) ? depts : [];
    if (zoneSel) {
      zoneSel.innerHTML = '<option value="">All zones</option>';
      zoneList.forEach((z) => zoneSel.appendChild(new Option(z.name + (z.code ? ` (${z.code})` : ''), z.id)));
    }
    if (wardSel) {
      wardSel.innerHTML = '<option value="">All wards</option>';
      wardList.forEach((w) => wardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    }
    if (deptSel) {
      deptSel.innerHTML = '<option value="">All departments</option>';
      deptList.forEach((d) => deptSel.appendChild(new Option(d.name, d.id)));
    }
  } catch (_) {}
}

function getEscalationsLimit() {
  return 20;
}

async function loadEscalations() {
  const zoneId = document.getElementById('escalations-filter-zone')?.value || '';
  const wardId = document.getElementById('escalations-filter-ward')?.value || '';
  const deptId = document.getElementById('escalations-filter-dept')?.value || '';
  const priority = document.getElementById('escalations-filter-priority')?.value || '';
  
  // KPI/Chart Analytics still uses the existing summary endpoint
  // Summary Analytics and Triage Table use all 4 filters
  const filterParams = new URLSearchParams();
  if (zoneId) filterParams.set('zone_id', zoneId);
  if (wardId) filterParams.set('ward_id', wardId);
  if (deptId) filterParams.set('category_dept', deptId);
  if (priority) filterParams.set('priority', priority);

  try {
    const [analyticsData, grievancesData] = await Promise.all([
      api('/analytics/escalations?' + filterParams.toString()),
      api('/analytics/grievances/escalation-priority?' + filterParams.toString()),
    ]);

    document.getElementById('escalations-total').textContent = analyticsData?.total ?? 0;
    document.getElementById('escalations-high').textContent = analyticsData?.by_priority?.high ?? 0;
    document.getElementById('escalations-reopened').textContent = analyticsData?.reopened_count ?? 0;
    const oldest = analyticsData?.oldest_days;
    document.getElementById('escalations-oldest').textContent = oldest != null ? oldest : '–';

    renderEscalationCharts(analyticsData);
    renderEscalationsTable(grievancesData);
    renderEPSFormula();
  } catch (e) {
    document.getElementById('escalations-total').textContent = '–';
    document.getElementById('escalations-high').textContent = '–';
    document.getElementById('escalations-reopened').textContent = '–';
    document.getElementById('escalations-oldest').textContent = '–';
    document.getElementById('escalations-tbody').innerHTML =
      '<tr><td colspan="7">Failed to load escalations.</td></tr>';
    renderEscalationCharts(null);
  }
}

function renderEscalationCharts(data) {
  if (typeof Chart === 'undefined') return;
  Object.keys(escalationCharts).forEach((k) => {
    if (escalationCharts[k]) {
      escalationCharts[k].destroy();
      escalationCharts[k] = null;
    }
  });

  if (!data) return;

  const themePrimary = 'rgba(13, 148, 136, 0.85)';
  const zoneCtx = document.getElementById('chart-escalations-zone')?.getContext('2d');
  if (zoneCtx && data.by_zone?.length) {
    escalationCharts.zone = new Chart(zoneCtx, {
      type: 'bar',
      data: {
        labels: data.by_zone.map((z) => z.name || z.code || '–'),
        datasets: [{ label: 'Escalations', data: data.by_zone.map((z) => z.count), backgroundColor: themePrimary }],
      },
      options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  const wardCtx = document.getElementById('chart-escalations-ward')?.getContext('2d');
  if (wardCtx && data.by_ward?.length) {
    const topWards = data.by_ward.slice(0, 10);
    escalationCharts.ward = new Chart(wardCtx, {
      type: 'bar',
      data: {
        labels: topWards.map((w) => (w.number ? `#${w.number}` : '') + ' ' + (w.name || '–')),
        datasets: [{ label: 'Escalations', data: topWards.map((w) => w.count), backgroundColor: themePrimary }],
      },
      options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  const epsDistCtx = document.getElementById('chart-escalations-eps-dist')?.getContext('2d');
  if (epsDistCtx && data.eps_distribution) {
    const ed = data.eps_distribution;
    const total = ed.Critical + ed.High + ed.Moderate + ed.Low;
    if (total > 0) {
      escalationCharts.epsDist = new Chart(epsDistCtx, {
        type: 'doughnut',
        data: {
          labels: ['Critical', 'High', 'Moderate', 'Low'],
          datasets: [{
            data: [ed.Critical, ed.High, ed.Moderate, ed.Low],
            backgroundColor: ['#d13212', '#ea580c', '#0d9488', '#4a6b6b'],
          }],
        },
        options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { position: 'bottom' } } },
      });
    }
  }

  const topRiskCtx = document.getElementById('chart-escalations-top-risk-wards')?.getContext('2d');
  if (topRiskCtx && data.top_risk_wards?.length) {
    escalationCharts.topRisk = new Chart(topRiskCtx, {
      type: 'bar',
      data: {
        labels: data.top_risk_wards.map((w) => w.name || '–'),
        datasets: [{ label: 'Avg EPS', data: data.top_risk_wards.map((w) => w.avg_eps), backgroundColor: '#ea580c' }],
      },
      options: { 
        indexAxis: 'y',
        responsive: true, 
        maintainAspectRatio: true, 
        plugins: { legend: { display: false } }, 
        scales: { x: { beginAtZero: true, max: 100 } } 
      },
    });
  }
}

// ---------------------------------------------------------------------------
// Escalation Priority Score (EPS) Helpers
// ---------------------------------------------------------------------------

function getEpsLevel(total) {
  if (total >= 75) return { label: 'Critical', class: 'critical' };
  if (total >= 50) return { label: 'High', class: 'high' };
  if (total >= 25) return { label: 'Moderate', class: 'moderate' };
  return { label: 'Low', class: 'low' };
}

function renderEpsBadge(score) {
  if (score === null || score === undefined) return '<span class="text-muted">—</span>';
  const level = getEpsLevel(score);
  return `<span class="eps-badge ${level.class}" title="EPS: ${score}">${Math.round(score)}</span>`;
}

function renderEpsBreakdownBar(eps) {
  if (!eps || !eps.breakdown) return '';
  const b = eps.breakdown;
  return `
    <div class="eps-bar-wrap">
      <div class="eps-bar-segment segment-age" style="width: ${b.age}%" title="Age: ${b.age} pts"></div>
      <div class="eps-bar-segment segment-reopen" style="width: ${b.reopen}%" title="Reopens: ${b.reopen} pts"></div>
      <div class="eps-bar-segment segment-votes" style="width: ${b.votes}%" title="Votes: ${b.votes} pts"></div>
      <div class="eps-bar-segment segment-severity" style="width: ${b.severity}%" title="Severity: ${b.severity} pts"></div>
    </div>
    <div class="eps-breakdown-legend">
      <span class="legend-item"><i class="legend-dot segment-age"></i> Age</span>
      <span class="legend-item"><i class="legend-dot segment-reopen"></i> Reopens</span>
      <span class="legend-item"><i class="legend-dot segment-votes"></i> Votes</span>
      <span class="legend-item"><i class="legend-dot segment-severity"></i> Severity</span>
    </div>
  `;
}

function renderEPSFormula() {
  const display = document.getElementById('eps-formula-display');
  const composite = document.querySelector('.dpi-formula');
  
  if (typeof katex === 'undefined') {
    setTimeout(renderEPSFormula, 200);
    return;
  }
  
  const formula = 'EPS = (30\\% \\cdot \\text{Age}_{\\text{norm}}) + (25\\% \\cdot \\text{Reopen}_{\\text{norm}}) + (25\\% \\cdot \\text{Votes}_{\\text{norm}}) + (20\\% \\cdot \\text{Severity})';
  
  const options = {
    throwOnError: false,
    displayMode: true
  };

  if (display) katex.render(formula, display, options);
  if (composite) katex.render(formula, composite, options);
}

function renderEscalationsTable(data) {
  const tbody = document.getElementById('escalations-tbody');
  if (!tbody) return;

  if (!data || data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="text-center">No escalated grievances found.</td></tr>';
    return;
  }

  tbody.innerHTML = data.map((g, index) => {
    const level = getEpsLevel(g.eps.total);
    return `
      <tr>
        <td class="text-center"><strong>${index + 1}</strong></td>
        <td>
          <div class="grievance-mini-info">
            <strong>${escapeHtml(g.title || 'Untitled')}</strong><br/>
            <small class="text-muted">${escapeHtml(g.category || '–')}</small>
          </div>
        </td>
        <td>${escapeHtml(g.department || '–')}</td>
        <td>
          <div>${escapeHtml(g.ward || '–')}</div>
          <small class="text-muted">${escapeHtml(g.zone || '–')}</small>
        </td>
        <td>
          <div class="worker-pill">
            <i class="ri-user-follow-line"></i> ${escapeHtml(g.worker || 'Unassigned')}
          </div>
        </td>
        <td>
          <div class="manager-info">
             ${escapeHtml(g.manager || '–')}
          </div>
        </td>
        <td class="text-center">
          <div class="eps-score-text ${level.class}">${Math.round(g.eps.total)}</div>
        </td>
        <td>
          ${renderEpsBreakdownBar(g.eps)}
        </td>
        <td class="text-center">
          <span class="eps-level-pill level-${level.class}">${level.label}</span>
        </td>
        <td class="text-right">
          <button type="button" class="btn btn-sm btn-view-grievance" data-id="${g.id}">View</button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-view-grievance').forEach((btn) => {
    btn.addEventListener('click', () => {
      openGrievanceDetailModal(btn.dataset.id);
    });
  });

  // Hide pagination as this is a ranked top-list
  const pagination = document.getElementById('escalations-pagination');
  if (pagination) pagination.innerHTML = '';
}

document.getElementById('btn-refresh-escalations')?.addEventListener('click', () => {
  escalationsSkip = 0;
  loadEscalations();
});
document.getElementById('escalations-filter-zone')?.addEventListener('change', () => {
  escalationsSkip = 0;
  loadEscalations();
});
document.getElementById('escalations-filter-ward')?.addEventListener('change', () => {
  escalationsSkip = 0;
  loadEscalations();
});
document.getElementById('escalations-filter-dept')?.addEventListener('change', () => {
  escalationsSkip = 0;
  loadEscalations();
});
document.getElementById('escalations-filter-priority')?.addEventListener('change', () => {
  escalationsSkip = 0;
  loadEscalations();
});

// ---------------------------------------------------------------------------
// Citizens
// ---------------------------------------------------------------------------

let citizensSkip = 0;

async function loadCitizens() {
  if (!getToken()) {
    document.getElementById('citizens-tbody').innerHTML =
      '<tr><td colspan="7">Please log in (sidebar) to view citizens.</td></tr>';
    const pagEl = document.getElementById('citizens-pagination');
    if (pagEl) pagEl.innerHTML = '';
    return;
  }
  const limit = parseInt(document.getElementById('citizens-limit')?.value || '20', 10) || 20;
  try {
    const data = await api(`/auth/users?role=citizen&skip=${citizensSkip}&limit=${limit}`);
    const items = data?.items || [];
    const total = data?.total ?? 0;
    const tbody = document.getElementById('citizens-tbody');
    tbody.innerHTML = items.map((c) => {
      const cis =
        c.cis_total_score != null && c.cis_total_score !== undefined
          ? Number(c.cis_total_score).toFixed(1)
          : '–';
      const cisTitle =
        c.cis_week_start && c.cis_week_end
          ? `CIS snapshot (IST ${c.cis_week_start} – ${c.cis_week_end})`
          : 'No CIS snapshot yet — use Update CIS';
      return `
      <tr>
        <td>${escapeHtml(c.name || '–')}</td>
        <td>${escapeHtml(c.phone || '–')}</td>
        <td>${escapeHtml(c.email || '–')}</td>
        <td>${escapeHtml(c.ward || '–')}</td>
        <td>${escapeHtml(c.zone || '–')}</td>
        <td title="${escapeHtml(cisTitle)}">${cis}</td>
        <td>${formatDate(c.created_at)}</td>
      </tr>
    `;
    }).join('');
    if (!items.length) tbody.innerHTML = '<tr><td colspan="7">No citizens found.</td></tr>';
    const pagination = document.getElementById('citizens-pagination');
    const prev = citizensSkip > 0;
    const next = citizensSkip + items.length < total;
    pagination.innerHTML = `
      <span>${citizensSkip + 1}–${Math.min(citizensSkip + items.length, total)} of ${total}</span>
      <button type="button" class="btn btn-sm" data-action="prev" ${prev ? '' : 'disabled'}>Previous</button>
      <button type="button" class="btn btn-sm" data-action="next" ${next ? '' : 'disabled'}>Next</button>
    `;
    pagination.querySelector('[data-action="prev"]')?.addEventListener('click', () => {
      citizensSkip = Math.max(0, citizensSkip - limit);
      loadCitizens();
    });
    pagination.querySelector('[data-action="next"]')?.addEventListener('click', () => {
      citizensSkip += limit;
      loadCitizens();
    });
  } catch (e) {
    const msg = e.status === 401 ? 'Please log in to view citizens.'
      : e.status === 403 ? 'Admin or Manager role required.'
      : (e.data?.detail || e.message || 'Failed to load citizens.');
    document.getElementById('citizens-tbody').innerHTML =
      `<tr><td colspan="7">${escapeHtml(msg)}</td></tr>`;
    const pagEl = document.getElementById('citizens-pagination');
    if (pagEl) pagEl.innerHTML = '';
  }
}

document.getElementById('btn-refresh-citizens')?.addEventListener('click', () => {
  citizensSkip = 0;
  loadCitizens();
});

document.getElementById('btn-update-cis')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-update-cis');
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = 'Updating…';
  try {
    const data = await api('/analytics/cis/recompute-weekly', { method: 'POST' });
    const nextHint = data.next_scheduled_run_display
      ? ` · next auto: ${data.next_scheduled_run_display}`
      : '';
    showToast(
      `CIS updated: ${data.processed} citizens · IST ${data.week_start}–${data.week_end}${nextHint}`,
      'success'
    );
    if (document.getElementById('page-citizens')?.classList.contains('active')) {
      loadCitizens();
    }
  } catch (e) {
    const msg =
      e.status === 403
        ? 'Admin role required to update CIS.'
        : e.data?.detail || e.message || 'Failed to update CIS.';
    showToast(msg, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
});
document.getElementById('citizens-limit')?.addEventListener('change', () => {
  citizensSkip = 0;
  loadCitizens();
});

// ---------------------------------------------------------------------------
// Departments
// ---------------------------------------------------------------------------

function escapeHtml(s) {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

let deptCategoriesData = { departments: [], categories: [] };
let selectedDeptId = null;

function getSelectedDeptIds() {
  return Array.from(document.querySelectorAll('#dept-categories-list .dept-check:checked')).map((cb) => cb.value);
}

function renderDepartmentsList(departments, search, selectedId) {
  const listEl = document.getElementById('dept-categories-list');
  if (!listEl) return;
  const filtered = filterBySearch(departments, search, (d) => `${d.name} ${d.short_code || ''} ${d.jurisdiction_label || ''}`);
  listEl.innerHTML = filtered
    .map(
      (d) => `
    <div class="wards-zone-item ${d.id === selectedId ? 'active' : ''}" data-dept-id="${d.id}" role="button" tabindex="0">
      <input type="checkbox" class="item-checkbox dept-check" value="${d.id}" aria-label="Select ${escapeHtml(d.name)}" />
      <span class="zone-name">${escapeHtml(d.name)}</span>
      <span class="zone-code">${escapeHtml(d.short_code || '')}</span>
    </div>`
    )
    .join('') || '<div class="wards-select-hint" style="padding:1rem">No departments match</div>';
  listEl.querySelectorAll('.wards-zone-item[data-dept-id]').forEach((el) => {
    const deptId = el.dataset.deptId;
    el.addEventListener('click', (e) => {
      if (e.target.closest('.item-checkbox')) return;
      selectDepartment(deptId);
    });
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (!e.target.closest('.item-checkbox')) selectDepartment(deptId);
      }
    });
  });
  listEl.querySelectorAll('.dept-check').forEach((cb) => {
    cb.addEventListener('change', () => updateDeptSelectionButtons());
  });
  updateDeptSelectionButtons();
}

function updateDeptSelectionButtons() {
  const ids = getSelectedDeptIds();
  const editBtn = document.getElementById('btn-edit-dept-selected');
  const delBtn = document.getElementById('btn-delete-dept-selected');
  if (editBtn) editBtn.disabled = ids.length !== 1;
  if (delBtn) delBtn.disabled = ids.length === 0;
}

function selectDepartment(deptId) {
  selectedDeptId = deptId || null;
  const labelEl = document.getElementById('dept-categories-label');
  const wrapEl = document.getElementById('dept-categories-table-wrap');
  const dept = deptCategoriesData.departments.find((d) => d.id === deptId);
  if (labelEl) labelEl.textContent = dept ? `– ${dept.name}` : '';
  renderDepartmentsList(deptCategoriesData.departments, document.getElementById('dept-categories-search')?.value || '', selectedDeptId);
  loadCategoriesForSelectedDept();
  if (wrapEl) wrapEl.classList.toggle('has-categories', !!deptId);
}

async function loadCategoriesForSelectedDept() {
  const search = document.getElementById('dept-categories-search')?.value || '';
  const tbody = document.getElementById('categories-tbody');
  if (!tbody) return;
  if (!selectedDeptId) {
    tbody.innerHTML = '';
    document.getElementById('dept-categories-table-wrap')?.classList.remove('has-categories');
    return;
  }
  try {
    const categories = await api(`/departments/${selectedDeptId}/categories`);
    const list = Array.isArray(categories) ? categories : [];
    const filtered = filterBySearch(list, search, (c) => c.name || '');
    tbody.innerHTML = filtered
      .map(
        (c) => `
      <tr data-id="${c.id}">
        <td class="col-checkbox"><input type="checkbox" class="cat-check" value="${c.id}" aria-label="Select category" /></td>
        <td>${escapeHtml(c.name)}</td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="2">No categories</td></tr>';
    tbody.querySelectorAll('.cat-check').forEach((cb) => cb.addEventListener('change', () => updateCatSelectionButtons()));
    updateCatSelectionButtons();
    document.getElementById('dept-categories-table-wrap')?.classList.add('has-categories');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="2">Failed to load categories</td></tr>';
    document.getElementById('dept-categories-table-wrap')?.classList.remove('has-categories');
  }
}

async function loadDepartmentsAndCategories() {
  try {
    const departments = await api('/departments').catch(() => []);
    deptCategoriesData = { departments: Array.isArray(departments) ? departments : [], categories: [] };
    const search = document.getElementById('dept-categories-search')?.value || '';
    renderDepartmentsList(deptCategoriesData.departments, search, selectedDeptId);
    loadCategoriesForSelectedDept();
    document.getElementById('dept-categories-table-wrap')?.classList.toggle('has-categories', !!selectedDeptId);
  } catch (e) {
    renderDepartmentsList([], '', null);
  }
}

document.getElementById('dept-categories-search')?.addEventListener('input', () => {
  renderDepartmentsList(deptCategoriesData.departments, document.getElementById('dept-categories-search')?.value || '', selectedDeptId);
  loadCategoriesForSelectedDept();
});

function getSelectedCatIds() {
  return Array.from(document.querySelectorAll('#categories-tbody .cat-check:checked')).map((cb) => cb.value);
}

function updateCatSelectionButtons() {
  const ids = getSelectedCatIds();
  const allCheck = document.getElementById('dept-cat-select-all');
  const checks = document.querySelectorAll('#categories-tbody .cat-check');
  if (allCheck && checks.length) {
    allCheck.checked = checks.length === ids.length;
    allCheck.indeterminate = ids.length > 0 && ids.length < checks.length;
  }
  const editBtn = document.getElementById('btn-edit-cat-selected');
  const delBtn = document.getElementById('btn-delete-cat-selected');
  if (editBtn) editBtn.disabled = ids.length !== 1;
  if (delBtn) delBtn.disabled = ids.length === 0;
}

document.getElementById('dept-cat-select-all')?.addEventListener('change', function () {
  document.querySelectorAll('#categories-tbody .cat-check').forEach((c) => { c.checked = this.checked; });
  updateCatSelectionButtons();
});

document.getElementById('btn-edit-dept-selected')?.addEventListener('click', () => {
  const ids = getSelectedDeptIds();
  if (ids.length === 1) openEditDepartment(ids[0]);
});
document.getElementById('btn-delete-dept-selected')?.addEventListener('click', async () => {
  const ids = getSelectedDeptIds();
  if (ids.length && confirm(`Delete ${ids.length} department(s)?`)) {
    for (const id of ids) await deleteDepartment(id, true);
    updateDeptSelectionButtons();
  }
});
document.getElementById('btn-edit-cat-selected')?.addEventListener('click', () => {
  const ids = getSelectedCatIds();
  if (ids.length === 1) openEditCategory(ids[0]);
});
document.getElementById('btn-delete-cat-selected')?.addEventListener('click', async () => {
  const ids = getSelectedCatIds();
  if (ids.length && confirm(`Delete ${ids.length} categor(y/ies)?`)) {
    for (const id of ids) await deleteCategory(id, true);
    updateCatSelectionButtons();
  }
});

// ---------------------------------------------------------------------------
// Wards & Zones
// ---------------------------------------------------------------------------

let wardsZonesData = { zones: [], wards: [] };
let selectedZoneId = null;

async function populateWardZoneFilter() {
  // No longer used; kept for compatibility with header refresh
}

function normalizeSearch(t) {
  return (t || '').toLowerCase().trim();
}

function filterBySearch(items, search, getText) {
  if (!search) return items;
  const q = normalizeSearch(search);
  if (!q) return items;
  return items.filter((x) => getText(x).toLowerCase().includes(q));
}

function getSelectedZoneIds() {
  return Array.from(document.querySelectorAll('#wards-zones-list .zone-check:checked')).map((cb) => cb.value);
}

function renderZonesList(zones, search, selectedId) {
  const listEl = document.getElementById('wards-zones-list');
  if (!listEl) return;
  const filtered = filterBySearch(zones, search, (z) => `${z.name} ${z.code || ''}`);
  listEl.innerHTML = filtered
    .map(
      (z) => `
    <div class="wards-zone-item ${z.id === selectedId ? 'active' : ''}" data-zone-id="${z.id}" role="button" tabindex="0">
      <input type="checkbox" class="item-checkbox zone-check" value="${z.id}" aria-label="Select zone" />
      <span class="zone-name">${escapeHtml(z.name)}</span>
      <span class="zone-code">${escapeHtml(z.code || '')}</span>
    </div>`
    )
    .join('') || '<div class="wards-select-hint" style="padding:1rem">No zones match</div>';
  listEl.querySelectorAll('.wards-zone-item').forEach((el) => {
    const zoneId = el.dataset.zoneId;
    el.addEventListener('click', (e) => {
      if (e.target.closest('.item-checkbox')) return;
      selectZone(zoneId);
    });
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (!e.target.closest('.item-checkbox')) selectZone(zoneId);
      }
    });
  });
  listEl.querySelectorAll('.zone-check').forEach((cb) => cb.addEventListener('change', () => updateZoneSelectionButtons()));
  updateZoneSelectionButtons();
}

function updateZoneSelectionButtons() {
  const ids = getSelectedZoneIds();
  const editBtn = document.getElementById('btn-edit-zone-selected');
  const delBtn = document.getElementById('btn-delete-zone-selected');
  if (editBtn) editBtn.disabled = ids.length !== 1;
  if (delBtn) delBtn.disabled = ids.length === 0;
}

function selectZone(zoneId) {
  selectedZoneId = zoneId || null;
  const labelEl = document.getElementById('wards-zone-label');
  const wrapEl = document.getElementById('wards-table-wrap');
  if (labelEl) labelEl.textContent = zoneId ? '' : '';
  const zone = wardsZonesData.zones.find((z) => z.id === zoneId);
  if (zone && labelEl) labelEl.textContent = `– ${zone.name}`;
  renderZonesList(wardsZonesData.zones, document.getElementById('wards-zones-search')?.value || '', selectedZoneId);
  loadWardsForSelectedZone();
  if (wrapEl) wrapEl.classList.toggle('has-wards', !!zoneId);
}

async function loadWardsForSelectedZone() {
  const search = document.getElementById('wards-zones-search')?.value || '';
  const tbody = document.getElementById('wards-tbody');
  if (!tbody) return;
  if (!selectedZoneId) {
    tbody.innerHTML = '';
    document.getElementById('wards-table-wrap')?.classList.remove('has-wards');
    return;
  }
  try {
    const wards = await api(`/wards?zone_id=${encodeURIComponent(selectedZoneId)}`);
    const list = Array.isArray(wards) ? wards : [];
    const filtered = filterBySearch(list, search, (w) => `${w.name} ${w.number} ${w.representative_name || ''}`);
    tbody.innerHTML = filtered
      .map(
        (w) => `
      <tr data-id="${w.id}">
        <td class="col-checkbox"><input type="checkbox" class="ward-check" value="${w.id}" aria-label="Select ward" /></td>
        <td>${escapeHtml(w.name)}</td>
        <td>${w.number != null ? w.number : '–'}</td>
        <td>${escapeHtml(w.representative_name)}</td>
        <td>${escapeHtml(Array.isArray(w.representative_phone) ? w.representative_phone.join(', ') : (w.representative_phone || '–'))}</td>
        <td>${escapeHtml(w.representative_party || '–')}</td>
        <td>${escapeHtml(w.representative_email || '–')}</td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="8">No wards</td></tr>';
    tbody.querySelectorAll('.ward-check').forEach((cb) => cb.addEventListener('change', () => updateWardSelectionButtons()));
    updateWardSelectionButtons();
    document.getElementById('wards-table-wrap')?.classList.add('has-wards');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="8">Failed to load wards</td></tr>';
    document.getElementById('wards-table-wrap')?.classList.remove('has-wards');
  }
}

async function loadWardsAndZones() {
  try {
    const [zones, wards] = await Promise.all([api('/zones').catch(() => []), api('/wards').catch(() => [])]);
    wardsZonesData = { zones: Array.isArray(zones) ? zones : [], wards: Array.isArray(wards) ? wards : [] };
    const search = document.getElementById('wards-zones-search')?.value || '';
    renderZonesList(wardsZonesData.zones, search, selectedZoneId);
    loadWardsForSelectedZone();
    document.getElementById('wards-table-wrap')?.classList.toggle('has-wards', !!selectedZoneId);
  } catch (e) {
    renderZonesList([], '', null);
  }
}

document.getElementById('wards-zones-search')?.addEventListener('input', () => {
  renderZonesList(wardsZonesData.zones, document.getElementById('wards-zones-search')?.value || '', selectedZoneId);
  loadWardsForSelectedZone();
});

function getSelectedWardIds() {
  return Array.from(document.querySelectorAll('#wards-tbody .ward-check:checked')).map((cb) => cb.value);
}

function updateWardSelectionButtons() {
  const ids = getSelectedWardIds();
  const allCheck = document.getElementById('wards-select-all');
  const checks = document.querySelectorAll('#wards-tbody .ward-check');
  if (allCheck && checks.length) {
    allCheck.checked = checks.length === ids.length;
    allCheck.indeterminate = ids.length > 0 && ids.length < checks.length;
  }
  const editBtn = document.getElementById('btn-edit-ward-selected');
  const delBtn = document.getElementById('btn-delete-ward-selected');
  if (editBtn) editBtn.disabled = ids.length !== 1;
  if (delBtn) delBtn.disabled = ids.length === 0;
}

document.getElementById('wards-select-all')?.addEventListener('change', function () {
  document.querySelectorAll('#wards-tbody .ward-check').forEach((c) => { c.checked = this.checked; });
  updateWardSelectionButtons();
});

document.getElementById('btn-edit-zone-selected')?.addEventListener('click', () => {
  const ids = getSelectedZoneIds();
  if (ids.length === 1) openEditZone(ids[0]);
});
document.getElementById('btn-delete-zone-selected')?.addEventListener('click', async () => {
  const ids = getSelectedZoneIds();
  if (ids.length && confirm(`Delete ${ids.length} zone(s)?`)) {
    for (const id of ids) await deleteZone(id, true);
    updateZoneSelectionButtons();
  }
});
document.getElementById('btn-edit-ward-selected')?.addEventListener('click', () => {
  const ids = getSelectedWardIds();
  if (ids.length === 1) openEditWard(ids[0]);
});
document.getElementById('btn-delete-ward-selected')?.addEventListener('click', async () => {
  const ids = getSelectedWardIds();
  if (ids.length && confirm(`Delete ${ids.length} ward(s)?`)) {
    for (const id of ids) await deleteWard(id, true);
    updateWardSelectionButtons();
  }
});

function showAddSection(sectionId) {
  document.querySelectorAll('.add-section').forEach((el) => el.classList.add('hidden'));
  const section = document.getElementById(sectionId);
  if (section) section.classList.remove('hidden');
}

document.querySelectorAll('.btn-cancel-add').forEach((btn) => {
  btn.addEventListener('click', () => {
    const id = btn.dataset.cancel;
    if (id) document.getElementById(id).classList.add('hidden');
  });
});

document.getElementById('btn-add-zone').addEventListener('click', () => {
  document.getElementById('edit-id-zone').value = '';
  document.getElementById('add-zone-heading').textContent = 'Add zone';
  document.getElementById('btn-submit-zone').textContent = 'Add zone';
  showAddSection('add-zone-section');
});
document.getElementById('btn-add-ward').addEventListener('click', async () => {
  document.getElementById('edit-id-ward').value = '';
  document.getElementById('add-ward-heading').textContent = 'Add ward';
  document.getElementById('btn-submit-ward').textContent = 'Add ward';
  await Promise.all([populateZoneDropdown('add-ward-zone'), populatePartyDropdown('add-ward-party')]);
  if (selectedZoneId) document.getElementById('add-ward-zone').value = selectedZoneId;
  showAddSection('add-ward-section');
});
document.getElementById('btn-add-worker').addEventListener('click', () => {
  populateDepartmentDropdown('add-worker-department');
  populateZoneDropdown('add-worker-zone');
  populateWardDropdown('add-worker-ward');
  showAddSection('add-worker-section');
});
document.getElementById('btn-add-department').addEventListener('click', () => {
  document.getElementById('edit-id-department').value = '';
  document.getElementById('add-department-heading').textContent = 'Add department';
  document.getElementById('btn-submit-department').textContent = 'Add department';
  showAddSection('add-department-section');
});
document.getElementById('btn-add-category').addEventListener('click', async () => {
  document.getElementById('edit-id-category').value = '';
  document.getElementById('add-category-heading').textContent = 'Add grievance category';
  document.getElementById('btn-submit-category').textContent = 'Add category';
  await populateDepartmentDropdown('add-category-department', 'Select department');
  if (selectedDeptId) document.getElementById('add-category-department').value = selectedDeptId;
  showAddSection('add-category-section');
});

async function populateZoneDropdown(selectId, optional = true) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const first = sel.options[0];
  try {
    const list = await api('/zones');
    sel.innerHTML = '';
    if (optional) sel.appendChild(new Option('Select zone', ''));
    (Array.isArray(list) ? list : []).forEach((z) => sel.appendChild(new Option(z.name, z.id)));
  } catch (_) {
    sel.innerHTML = '';
    if (first) sel.appendChild(first);
  }
}

async function populateDepartmentDropdown(selectId, firstOptionText = 'Department (optional)') {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  try {
    const list = await api('/departments');
    sel.innerHTML = `<option value="">${escapeHtml(firstOptionText)}</option>`;
    (Array.isArray(list) ? list : []).forEach((d) => sel.appendChild(new Option(d.name, d.id)));
  } catch (_) {}
}

async function populateWardDropdown(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  try {
    const list = await api('/wards');
    sel.innerHTML = '<option value="">Ward (optional)</option>';
    (Array.isArray(list) ? list : []).forEach((w) => sel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
  } catch (_) {}
}

async function populatePartyDropdown(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  try {
    const list = await api('/parties').catch(() => []);
    sel.innerHTML = '<option value="">No party</option>';
    (Array.isArray(list) ? list : []).forEach((p) => sel.appendChild(new Option(p.short_code ? `${p.name} (${p.short_code})` : p.name, p.id)));
  } catch (_) {}
}

let partiesData = [];

async function loadParties() {
  try {
    const [list, control] = await Promise.all([
      api('/parties').catch(() => []),
      api('/analytics/parties/control').catch(() => null),
    ]);
    partiesData = Array.isArray(list) ? list : [];
    renderPartiesTable();
    updatePartiesKPIs(control);
  } catch (_) {
    partiesData = [];
    renderPartiesTable();
    updatePartiesKPIs(null);
  }
}

function updatePartiesKPIs(control) {
  const totalEl = document.getElementById('parties-stat-total');
  const assignedEl = document.getElementById('parties-stat-wards-assigned');
  const totalWardsEl = document.getElementById('parties-stat-total-wards');
  if (totalEl) totalEl.textContent = partiesData.length;
  if (control) {
    const assigned = (control.total_wards ?? 0) - (control.wards_without_party ?? 0);
    if (assignedEl) assignedEl.textContent = assigned;
    if (totalWardsEl) totalWardsEl.textContent = control.total_wards ?? '–';
  } else {
    if (assignedEl) assignedEl.textContent = '–';
    if (totalWardsEl) totalWardsEl.textContent = '–';
  }
}

function renderPartiesTable() {
  const tbody = document.getElementById('parties-tbody');
  if (!tbody) return;
  tbody.innerHTML = partiesData.length
    ? partiesData
        .map(
          (p) => `
      <tr data-id="${p.id}">
        <td>${escapeHtml(p.name || '–')}</td>
        <td><code class="parties-code">${escapeHtml(p.short_code || '–')}</code></td>
        <td><div class="party-color-cell">${p.color ? `<span class="party-color-swatch" style="background:${escapeHtml(p.color)}" title="${escapeHtml(p.color)}"></span><span>${escapeHtml(p.color)}</span>` : '<span class="parties-no-color">–</span>'}</div></td>
        <td class="col-actions">
          <button type="button" class="btn btn-sm btn-secondary btn-edit-party" data-id="${p.id}" title="Edit">Edit</button>
          <button type="button" class="btn btn-sm btn-danger-outline btn-delete-party" data-id="${p.id}" title="Delete">Delete</button>
        </td>
      </tr>
    `
        )
        .join('')
    : '<tr class="parties-empty-row"><td colspan="4">No parties yet. Add one to assign to wards.</td></tr>';
  tbody.querySelectorAll('.btn-edit-party').forEach((btn) => {
    btn.addEventListener('click', () => openEditParty(btn.dataset.id));
  });
  tbody.querySelectorAll('.btn-delete-party').forEach((btn) => {
    btn.addEventListener('click', () => deleteParty(btn.dataset.id));
  });
}

document.getElementById('btn-add-party')?.addEventListener('click', () => {
  const form = document.getElementById('form-add-party');
  form.edit_id.value = '';
  form.reset();
  document.getElementById('edit-id-party').value = '';
  document.getElementById('add-party-heading').textContent = 'Add political party';
  document.getElementById('btn-submit-party').textContent = 'Add party';
  showAddSection('add-party-section');
});

document.getElementById('form-add-party')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to manage parties', 'error');
    return;
  }
  const form = e.target;
  const editId = document.getElementById('edit-id-party')?.value?.trim() || '';
  const name = form.name.value.trim();
  const short_code = form.short_code?.value?.trim() || null;
  const color = form.color?.value?.trim() || null;
  if (!name) return showToast('Party name is required', 'error');
  try {
    if (editId) {
      await api(`/parties/${editId}`, { method: 'PATCH', body: JSON.stringify({ name, short_code, color }) });
      showToast('Party updated', 'success');
    } else {
      await api('/parties', { method: 'POST', body: JSON.stringify({ name, short_code, color }) });
      showToast('Party created', 'success');
    }
    form.reset();
    document.getElementById('edit-id-party').value = '';
    document.getElementById('add-party-section').classList.add('hidden');
    loadParties();
    populatePartyDropdown('add-ward-party');
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

async function openEditParty(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const p = await api(`/parties/${id}`);
    const form = document.getElementById('form-add-party');
    const editInput = document.getElementById('edit-id-party');
    if (editInput) editInput.value = p.id;
    form.name.value = p.name || '';
    form.short_code.value = p.short_code || '';
    form.color.value = p.color && /^#[0-9a-fA-F]{6}$/.test(p.color) ? p.color : '#9ca3af';
    document.getElementById('add-party-heading').textContent = 'Edit political party';
    document.getElementById('btn-submit-party').textContent = 'Save';
    showAddSection('add-party-section');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load party', 'error');
  }
}

async function deleteParty(id, skipConfirm = false) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!skipConfirm && !confirm('Delete this party? Wards using it will have their party cleared.')) return;
  try {
    await api(`/parties/${id}`, { method: 'DELETE' });
    showToast('Party deleted', 'success');
    loadParties();
    populatePartyDropdown('add-ward-party');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

document.getElementById('form-add-zone').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create zones', 'error');
    return;
  }
  const form = e.target;
  const editId = form.edit_id?.value?.trim() || '';
  const name = form.name.value.trim();
  const code = form.code.value.trim();
  if (!name || !code) return;
  try {
    if (editId) {
      await api(`/zones/${editId}`, { method: 'PATCH', body: JSON.stringify({ name, code }) });
      showToast('Zone updated', 'success');
    } else {
      await api('/zones', { method: 'POST', body: JSON.stringify({ name, code }) });
      showToast('Zone created', 'success');
    }
    form.reset();
    form.edit_id.value = '';
    document.getElementById('add-zone-heading').textContent = 'Add zone';
    document.getElementById('btn-submit-zone').textContent = 'Add zone';
    document.getElementById('add-zone-section').classList.add('hidden');
    loadWardsAndZones();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

function parsePhoneList(str) {
  if (!str || typeof str !== 'string') return [];
  return str.split(/[,\s]+/).map((p) => p.trim()).filter(Boolean);
}

document.getElementById('form-add-ward').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create wards', 'error');
    return;
  }
  const form = e.target;
  const editId = form.edit_id?.value?.trim() || '';
  const zone_id = form.zone_id.value;
  const name = form.name.value.trim();
  const number = parseInt(form.number.value, 10);
  const representative_name = form.representative_name?.value?.trim() || '';
  const representative_phone = parsePhoneList(form.representative_phone?.value || '');
  const party_id = form.party_id?.value?.trim() || null;
  const representative_email = form.representative_email?.value?.trim() || null;
  if (!zone_id || !name || !number) return showToast('Zone, name and number required', 'error');
  if (!representative_name) return showToast('Representative name is required', 'error');
  if (!representative_phone.length) return showToast('At least one representative phone is required', 'error');
  try {
    const body = { zone_id, name, number, representative_name, representative_phone, party_id, representative_email };
    if (editId) {
      await api(`/wards/${editId}`, { method: 'PATCH', body: JSON.stringify(body) });
      showToast('Ward updated', 'success');
    } else {
      await api('/wards', { method: 'POST', body: JSON.stringify(body) });
      showToast('Ward created', 'success');
    }
    form.reset();
    form.edit_id.value = '';
    document.getElementById('add-ward-heading').textContent = 'Add ward';
    document.getElementById('btn-submit-ward').textContent = 'Add ward';
    document.getElementById('add-ward-section').classList.add('hidden');
    loadWardsAndZones();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

document.getElementById('form-add-worker').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create officers', 'error');
    return;
  }
  const form = e.target;
  const password = form.password.value;
  const passwordConfirm = form.password_confirm?.value ?? '';
  if (password !== passwordConfirm) {
    showToast('Password and confirm password do not match', 'error');
    return;
  }
  const body = {
    name: form.name.value.trim(),
    email: (form.email && form.email.value.trim()) || null,
    phone: form.phone.value.trim(),
    address: (form.address && form.address.value.trim()) || null,
    password,
    role: form.role.value,
    designation_title: form.designation_title.value.trim(),
    department_id: form.department_id.value || null,
    zone_id: form.zone_id.value || null,
    ward_id: form.ward_id.value || null,
  };
  if (!body.name || !body.phone || !body.password || !body.designation_title) {
    showToast('Fill required fields: name, phone, password, designation', 'error');
    return;
  }
  try {
    await api('/workers', { method: 'POST', body: JSON.stringify(body) });
    showToast('Officer created', 'success');
    form.reset();
    if (form.password_confirm) form.password_confirm.value = '';
    document.getElementById('add-worker-section').classList.add('hidden');
    loadWorkers();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

document.getElementById('form-add-department').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create departments', 'error');
    return;
  }
  const form = e.target;
  const editId = form.edit_id?.value?.trim() || '';
  const body = {
    name: form.name.value.trim(),
    short_code: form.short_code.value.trim(),
    primary_color: form.primary_color.value.trim() || '#0d9488',
    icon: form.icon.value.trim() || 'assignment',
    manager_title: form.manager_title.value.trim() || 'Manager',
    assistant_title: form.assistant_title.value.trim() || 'Assistant',
    jurisdiction_label: form.jurisdiction_label.value.trim() || 'Ward',
    sdg: form.sdg?.value?.trim() || null,
    description: form.description?.value?.trim() || null,
  };
  if (!body.name || !body.short_code) return;
  try {
    if (editId) {
      await api(`/departments/${editId}`, { method: 'PATCH', body: JSON.stringify(body) });
      showToast('Department updated', 'success');
    } else {
      await api('/departments', { method: 'POST', body: JSON.stringify(body) });
      showToast('Department created', 'success');
    }
    form.reset();
    form.edit_id.value = '';
    document.getElementById('add-department-heading').textContent = 'Add department';
    document.getElementById('btn-submit-department').textContent = 'Add department';
    document.getElementById('add-department-section').classList.add('hidden');
    loadDepartmentsAndCategories();
    populateDepartmentDropdown('add-worker-department');
    populateDepartmentDropdown('add-category-department', 'Select department');
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

document.getElementById('form-add-category').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create categories', 'error');
    return;
  }
  const form = e.target;
  const editId = form.edit_id?.value?.trim() || '';
  const dept_id = form.dept_id.value;
  const name = form.name.value.trim();
  if (!dept_id || !name) return;
  try {
    if (editId) {
      await api(`/categories/${editId}`, { method: 'PATCH', body: JSON.stringify({ name }) });
      showToast('Grievance category updated', 'success');
    } else {
      await api(`/departments/${dept_id}/categories`, {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      showToast('Grievance category created', 'success');
    }
    form.reset();
    form.edit_id.value = '';
    document.getElementById('add-category-heading').textContent = 'Add grievance category';
    document.getElementById('btn-submit-category').textContent = 'Add category';
    document.getElementById('add-category-section').classList.add('hidden');
    loadDepartmentsAndCategories();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

// ---------------------------------------------------------------------------
// Edit/Delete: Zones
// ---------------------------------------------------------------------------

document.querySelectorAll('.modal-close-edit').forEach((btn) => {
  btn.addEventListener('click', () => {
    const mid = btn.dataset.modal;
    if (mid) document.getElementById(mid).classList.add('hidden');
  });
});
document.querySelectorAll('#modal-edit-worker .modal-backdrop, #modal-worker-analytics .modal-backdrop').forEach((el) => {
  el.addEventListener('click', () => {
    const modal = el.closest('.modal');
    if (modal) modal.classList.add('hidden');
  });
});

async function openEditZone(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const z = await api(`/zones/${id}`);
    const form = document.getElementById('form-add-zone');
    form.edit_id.value = z.id;
    form.name.value = z.name || '';
    form.code.value = z.code || '';
    document.getElementById('add-zone-heading').textContent = 'Edit zone';
    document.getElementById('btn-submit-zone').textContent = 'Save';
    showAddSection('add-zone-section');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load zone', 'error');
  }
}

async function deleteZone(id, skipConfirm = false) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!skipConfirm && !confirm('Delete this zone? It will fail if it has wards.')) return;
  try {
    await api(`/zones/${id}`, { method: 'DELETE' });
    showToast('Zone deleted', 'success');
    loadWardsAndZones();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

// ---------------------------------------------------------------------------
// Edit/Delete: Wards
// ---------------------------------------------------------------------------

async function openEditWard(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const w = await api(`/wards/${id}`);
    await Promise.all([populateZoneDropdown('add-ward-zone'), populatePartyDropdown('add-ward-party')]);
    const form = document.getElementById('form-add-ward');
    form.edit_id.value = w.id;
    form.zone_id.value = w.zone_id || '';
    form.name.value = w.name || '';
    form.number.value = w.number != null ? w.number : '';
    form.representative_name.value = w.representative_name || '';
    form.representative_phone.value = Array.isArray(w.representative_phone) ? w.representative_phone.join(', ') : (w.representative_phone || '');
    form.party_id.value = w.party_id || '';
    form.representative_email.value = w.representative_email || '';
    document.getElementById('add-ward-heading').textContent = 'Edit ward';
    document.getElementById('btn-submit-ward').textContent = 'Save';
    showAddSection('add-ward-section');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load ward', 'error');
  }
}

async function deleteWard(id, skipConfirm = false) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!skipConfirm && !confirm('Delete this ward? Grievances/workers will have ward cleared.')) return;
  try {
    await api(`/wards/${id}`, { method: 'DELETE' });
    showToast('Ward deleted', 'success');
    loadWardsAndZones();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

// ---------------------------------------------------------------------------
// Edit/Delete: Departments
// ---------------------------------------------------------------------------

async function openEditDepartment(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const d = await api(`/departments/${id}`);
    const form = document.getElementById('form-add-department');
    form.edit_id.value = d.id;
    form.name.value = d.name || '';
    form.short_code.value = d.short_code || '';
    form.primary_color.value = (d.primary_color && /^#[0-9a-fA-F]{6}$/.test(d.primary_color)) ? d.primary_color : '#0d9488';
    form.icon.value = d.icon || 'assignment';
    form.manager_title.value = d.manager_title || 'Manager';
    form.assistant_title.value = d.assistant_title || 'Assistant';
    form.jurisdiction_label.value = d.jurisdiction_label || 'Ward';
    if (form.sdg) form.sdg.value = d.sdg || '';
    if (form.description) form.description.value = d.description || '';
    document.getElementById('add-department-heading').textContent = 'Edit department';
    document.getElementById('btn-submit-department').textContent = 'Save';
    showAddSection('add-department-section');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load department', 'error');
  }
}

async function deleteDepartment(id, skipConfirm = false) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!skipConfirm && !confirm('Delete this department? It will fail if it has categories or workers.')) return;
  try {
    await api(`/departments/${id}`, { method: 'DELETE' });
    if (id === selectedDeptId) selectedDeptId = null;
    showToast('Department deleted', 'success');
    loadDepartmentsAndCategories();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

// ---------------------------------------------------------------------------
// Edit/Delete: Categories
// ---------------------------------------------------------------------------

async function openEditCategory(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const c = await api(`/categories/${id}`);
    await populateDepartmentDropdown('add-category-department', 'Select department');
    const form = document.getElementById('form-add-category');
    form.edit_id.value = c.id;
    form.dept_id.value = c.dept_id || '';
    form.name.value = c.name || '';
    document.getElementById('add-category-heading').textContent = 'Edit grievance category';
    document.getElementById('btn-submit-category').textContent = 'Save';
    showAddSection('add-category-section');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load category', 'error');
  }
}

async function deleteCategory(id, skipConfirm = false) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!skipConfirm && !confirm('Delete this category? Grievances will have category cleared.')) return;
  try {
    await api(`/categories/${id}`, { method: 'DELETE' });
    showToast('Category deleted', 'success');
    loadDepartmentsAndCategories();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

// ---------------------------------------------------------------------------
// Edit/Delete: Workers
// ---------------------------------------------------------------------------

async function openEditWorker(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const w = await api(`/workers/${id}`);
    await Promise.all([
      populateDepartmentDropdown('edit-worker-department'),
      populateZoneDropdown('edit-worker-zone'),
      populateWardDropdown('edit-worker-ward'),
    ]);
    document.getElementById('edit-worker-id').value = w.id;
    document.getElementById('edit-worker-name').value = w.name || '';
    document.getElementById('edit-worker-email').value = w.email || '';
    document.getElementById('edit-worker-phone').value = w.phone || '';
    document.getElementById('edit-worker-address').value = w.address || '';
    document.getElementById('edit-worker-password').value = '';
    document.getElementById('edit-worker-role').value = w.role || 'fieldAssistant';
    document.getElementById('edit-worker-designation').value = w.designation || '';
    const deptSel = document.getElementById('edit-worker-department');
    const zoneSel = document.getElementById('edit-worker-zone');
    const wardSel = document.getElementById('edit-worker-ward');
    if (w.department_id) deptSel.value = w.department_id;
    if (w.zone_id) zoneSel.value = w.zone_id;
    if (w.ward_id) wardSel.value = w.ward_id;
    document.getElementById('modal-edit-worker').classList.remove('hidden');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load officer', 'error');
  }
}

document.getElementById('btn-save-worker').addEventListener('click', async () => {
  const id = document.getElementById('edit-worker-id').value;
  const name = document.getElementById('edit-worker-name').value.trim();
  const email = (document.getElementById('edit-worker-email').value || '').trim() || null;
  const phone = document.getElementById('edit-worker-phone').value.trim();
  const address = (document.getElementById('edit-worker-address').value || '').trim() || null;
  const password = document.getElementById('edit-worker-password').value;
  const role = document.getElementById('edit-worker-role').value;
  const designation_title = document.getElementById('edit-worker-designation').value.trim();
  const department_id = document.getElementById('edit-worker-department').value || null;
  const zone_id = document.getElementById('edit-worker-zone').value || null;
  const ward_id = document.getElementById('edit-worker-ward').value || null;
  if (!id || !name || !phone || !designation_title) return showToast('Name, phone and designation required', 'error');
  const body = {
    name,
    email,
    phone,
    address,
    role,
    designation_title,
    department_id: department_id || null,
    zone_id: zone_id || null,
    ward_id: ward_id || null,
  };
  if (password) body.password = password;
  try {
    await api(`/workers/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    document.getElementById('modal-edit-worker').classList.add('hidden');
    showToast('Officer updated', 'success');
    loadWorkers();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteWorker(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this officer? This cannot be undone.')) return;
  try {
    await api(`/workers/${id}`, { method: 'DELETE' });
    showToast('Officer deleted', 'success');
    loadWorkers();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Delete failed', 'error');
  }
}

// ---------------------------------------------------------------------------
// Workers
// ---------------------------------------------------------------------------

let workersSkip = 0;

function getWorkersLimit() {
  const el = document.getElementById('filter-worker-limit');
  const v = el && el.value;
  return v ? Math.max(1, Math.min(100, parseInt(v, 10))) : 20;
}

async function loadWorkers() {
  const deptFilter = document.getElementById('filter-worker-department');
  const wardFilter = document.getElementById('filter-worker-ward');
  const roleFilter = document.getElementById('filter-worker-role');
  const statusFilter = document.getElementById('filter-worker-status');
  const limit = getWorkersLimit();
  const params = [`skip=${workersSkip}`, `limit=${limit}`];
  if (deptFilter && deptFilter.value) params.push(`department=${encodeURIComponent(deptFilter.value)}`);
  if (wardFilter && wardFilter.value) params.push(`ward_id=${encodeURIComponent(wardFilter.value)}`);
  if (statusFilter && statusFilter.value) params.push(`status=${encodeURIComponent(statusFilter.value)}`);
  const path = '/workers?' + params.join('&');
  try {
    const data = await api(path);
    let list = data?.items ?? (Array.isArray(data) ? data : []);
    const total = data?.total ?? list.length;
    const roleVal = roleFilter && roleFilter.value;
    if (roleVal) list = list.filter((w) => (w.role || '').toLowerCase() === roleVal.toLowerCase());
    const tbody = document.getElementById('workers-tbody');
    tbody.innerHTML = list
      .map((w) => {
        const st = (w.status || '').toLowerCase();
        const stLabel = st === 'onduty' ? 'On Duty' : st === 'offduty' ? 'Off Duty' : (w.status || '–');
        const stClass = st === 'onduty' ? 'status-onduty' : st === 'offduty' ? 'status-offduty' : '';
        return `
      <tr data-id="${w.id}">
        <td>${escapeHtml(w.name)}</td>
        <td>${escapeHtml(w.email || '–')}</td>
        <td>${escapeHtml(w.phone)}</td>
        <td>${escapeHtml(w.role || '–')}</td>
        <td>${escapeHtml(w.designation || '–')}</td>
        <td>${escapeHtml(w.department_name || '–')}</td>
        <td>${escapeHtml(w.last_active_ward || '–')}</td>
        <td><span class="status-badge ${stClass}">${escapeHtml(stLabel)}</span></td>
        <td>
          <button type="button" class="btn btn-sm btn-edit-worker" data-id="${w.id}">Edit</button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-worker" data-id="${w.id}">Delete</button>
        </td>
      </tr>
    `;
      })
      .join('') || '<tr><td colspan="9">No officers</td></tr>';
    tbody.querySelectorAll('.btn-edit-worker').forEach((btn) => btn.addEventListener('click', () => openEditWorker(btn.dataset.id)));
    tbody.querySelectorAll('.btn-delete-worker').forEach((btn) => btn.addEventListener('click', () => deleteWorker(btn.dataset.id)));

    const pagination = document.getElementById('workers-pagination');
    if (pagination) {
      const pageLimit = getWorkersLimit();
      const prev = workersSkip > 0;
      const next = workersSkip + list.length < total;
      pagination.innerHTML = `
        <span>${workersSkip + 1}–${workersSkip + list.length} of ${total}</span>
        <button type="button" class="btn btn-sm" data-action="prev" ${prev ? '' : 'disabled'}>Previous</button>
        <button type="button" class="btn btn-sm" data-action="next" ${next ? '' : 'disabled'}>Next</button>
      `;
      pagination.querySelector('[data-action="prev"]')?.addEventListener('click', () => {
        workersSkip = Math.max(0, workersSkip - pageLimit);
        loadWorkers();
      });
      pagination.querySelector('[data-action="next"]')?.addEventListener('click', () => {
        workersSkip += pageLimit;
        loadWorkers();
      });
    }
  } catch (e) {
    document.getElementById('workers-tbody').innerHTML =
      '<tr><td colspan="9">Failed to load officers.</td></tr>';
    const pagination = document.getElementById('workers-pagination');
    if (pagination) pagination.innerHTML = '';
  }
}

function populateWorkerFilters() {
  const deptSel = document.getElementById('filter-worker-department');
  const wardSel = document.getElementById('filter-worker-ward');
  Promise.all([
    api('/departments').catch(() => []),
    api('/wards').catch(() => []),
  ]).then(([deptList, wardList]) => {
    const depts = Array.isArray(deptList) ? deptList : [];
    const wards = Array.isArray(wardList) ? wardList : [];
    if (deptSel) {
      deptSel.innerHTML = '<option value="">All departments</option>';
      depts.forEach((d) => deptSel.appendChild(new Option(d.name, d.id)));
    }
    if (wardSel) {
      wardSel.innerHTML = '<option value="">All wards</option>';
      wards.forEach((w) => wardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    }
  });
}

// ---------------------------------------------------------------------------
// Command Center (Map + Smart Filters + Unified Grid + Logs)
// ---------------------------------------------------------------------------

let commandCenterReady = false;
let commandMap = null;
let wardGeoJsonLayer = null;
let grievanceClusterLayer = null;
let grievanceHeatLayer = null;
let commandCenterData = [];
let commandGeoJson = null;
let commandWards = [];
let wardFeatureToLayer = new Map();
let wardHighlightedLayer = null;

// Status badge toggles – control which markers show on map (single source of truth)
let commandCenterStatusFilters = {
  escalated: true, pending: true, assigned: true, inprogress: true, resolved: true,
};

function normalizeText(v) {
  return String(v || '').trim().toLowerCase();
}

function getWardLabel(ward) {
  if (!ward) return '–';
  return `${ward.name || ''}${ward.number != null ? ` (#${ward.number})` : ''}`;
}

function getWardFeatureName(props) {
  const keys = ['WardName', 'ward_name', 'WARD_NAME', 'name', 'NAME', 'ward', 'WARD', 'NW2022'];
  for (const k of keys) {
    if (props && props[k] != null) {
      const v = String(props[k]).trim();
      if (v) return v;
    }
  }
  return '';
}

function getWardFeatureNumber(props) {
  const keys = ['Ward_No', 'ward_no', 'WARD_NO', 'number', 'NUMBER', 'ward_number', 'WARD_NUMBER'];
  for (const k of keys) {
    if (props && props[k] != null) return String(props[k]);
  }
  return '';
}

function hexToRgba(hex, alpha) {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!m) return hex;
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${alpha})`;
}

/** Status severity: higher = worse. Used for cluster color (worst in cluster wins). */
function statusSeverity(s) {
  const t = normalizeText(s);
  if (t === 'escalated') return 4;
  if (t === 'pending') return 3;
  if (t === 'assigned' || t === 'inprogress') return 2;
  if (t === 'resolved') return 1;
  return 3; // unknown -> treat as pending
}

function getStatusColor(status) {
  const s = normalizeText(status);
  if (s === 'escalated') return '#d13212';      // AWS red – urgent
  if (s === 'resolved') return '#1d8102';       // AWS green – done
  if (s === 'assigned' || s === 'inprogress') return '#14b8a6';  // teal – in progress
  return '#0d9488';  // teal – pending
}

function createStatusMarker(status) {
  const color = getStatusColor(status);
  return L.divIcon({
    className: 'grievance-marker',
    html: `<span style="display:block;width:12px;height:12px;border-radius:999px;background:${color};border:2px solid #ffffff;box-shadow:0 1px 2px rgba(0,0,0,0.35);"></span>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });
}

function setMapLoading(on) {
  const el = document.getElementById('map-loading');
  if (el) el.classList.toggle('hidden', !on);
}

async function ensureCommandMap() {
  const mapEl = document.getElementById('command-map');
  if (!mapEl || typeof L === 'undefined') return;
  if (!commandMap) {
    commandMap = L.map('command-map', { preferCanvas: true }).setView([28.6139, 77.209], 10);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png', {
      maxZoom: 20,
      subdomains: 'abcd',
      detectRetina: true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(commandMap);
  }
  // Wait for the browser to finish layout before invalidating size,
  // so the heatmap canvas is never 0-height when it renders.
  await new Promise((resolve) => setTimeout(() => { commandMap.invalidateSize(); resolve(); }, 80));

  // Hover anywhere on map to show ward
  const tooltipEl = document.getElementById('cc-ward-hover-tooltip');
  const mapWrap = document.querySelector('.cc-map-wrap');
  commandMap.on('mousemove', (e) => {
    if (!tooltipEl || !mapWrap) return;
    const feature = findWardFeatureAtPoint(e.latlng);
    if (feature) {
      const props = feature?.properties || {};
      const name = getWardFeatureName(props) || 'Unknown';
      const num = getWardFeatureNumber(props);
      const label = num ? `#${num} ${name}` : name;
      tooltipEl.textContent = label;
      tooltipEl.classList.remove('hidden');
      const rect = mapWrap.getBoundingClientRect();
      tooltipEl.style.left = `${e.originalEvent.clientX - rect.left + 12}px`;
      tooltipEl.style.top = `${e.originalEvent.clientY - rect.top + 8}px`;
    } else {
      tooltipEl.classList.add('hidden');
    }
  });
  commandMap.on('mouseout', () => {
    if (tooltipEl) tooltipEl.classList.add('hidden');
  });
}

async function populateCommandFilters() {
  const [zones, wards] = await Promise.all([
    api('/zones').catch(() => []),
    api('/wards').catch(() => []),
  ]);
  const zSel = document.getElementById('cc-zone-filter');
  const wSel = document.getElementById('cc-ward-filter');
  const zList = Array.isArray(zones) ? zones : [];
  const wList = Array.isArray(wards) ? wards : [];
  commandWards = wList;
  if (zSel) {
    zSel.innerHTML = '<option value="">All zones</option>';
    zList.forEach((z) => zSel.appendChild(new Option(z.name, z.id)));
  }
  if (wSel) {
    wSel.innerHTML = '<option value="">All wards</option>';
    wList.forEach((w) => wSel.appendChild(new Option(getWardLabel(w), w.id)));
  }
}

function syncCommandWardOptions() {
  const zoneId = document.getElementById('cc-zone-filter')?.value || '';
  const wSel = document.getElementById('cc-ward-filter');
  const list = zoneId
    ? commandWards.filter((w) => String(w.zone_id) === String(zoneId))
    : commandWards;
  if (wSel) {
    const selected = wSel.value;
    wSel.innerHTML = '<option value="">All wards</option>';
    list.forEach((w) => wSel.appendChild(new Option(getWardLabel(w), w.id)));
    if (selected && list.some((w) => String(w.id) === String(selected))) wSel.value = selected;
  }
}

async function fetchCommandGeoJson() {
  if (commandGeoJson) return commandGeoJson;
  commandGeoJson = await api('/wards/geojson');
  return commandGeoJson;
}

function findWardFeature(ward) {
  if (!commandGeoJson || !Array.isArray(commandGeoJson.features) || !ward) return null;
  const targetName = normalizeText(ward.name);
  const targetNum = String(ward.number ?? '').trim();
  return commandGeoJson.features.find((f) => {
    const props = f?.properties || {};
    const n = normalizeText(getWardFeatureName(props));
    const num = String(getWardFeatureNumber(props)).trim();
    const nameMatch = targetName && n.includes(targetName);
    const numMatch = targetNum && num === targetNum;
    return nameMatch || (nameMatch && numMatch) || numMatch;
  }) || null;
}

function getWardForFeature(feature) {
  if (!feature || !commandWards.length) return null;
  const props = feature?.properties || {};
  const name = normalizeText(getWardFeatureName(props));
  const num = String(getWardFeatureNumber(props)).trim();
  return commandWards.find((w) => {
    const wn = normalizeText(w.name);
    const wnum = String(w.number ?? '').trim();
    return (name && wn && wn.includes(name)) || (num && wnum && wnum === num);
  }) || null;
}

function pointInPolygonRing(lng, lat, ring) {
  let inside = false;
  const n = ring.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (((yi > lat) !== (yj > lat)) && (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

function findWardFeatureAtPoint(latlng) {
  if (!commandGeoJson?.features?.length || !latlng) return null;
  const lng = latlng.lng;
  const lat = latlng.lat;
  for (const f of commandGeoJson.features) {
    const coords = f?.geometry?.coordinates;
    if (!coords) continue;
    if (f.geometry.type === 'Polygon' && Array.isArray(coords[0])) {
      if (pointInPolygonRing(lng, lat, coords[0])) return f;
    } else if (f.geometry.type === 'MultiPolygon' && Array.isArray(coords)) {
      for (const ring of coords) {
        if (Array.isArray(ring?.[0]) && pointInPolygonRing(lng, lat, ring[0])) return f;
      }
    }
  }
  return null;
}

function getSearchableWardList() {
  if (!commandGeoJson || !Array.isArray(commandGeoJson.features)) return [];
  return commandGeoJson.features.map((f) => {
    const props = f?.properties || {};
    const name = getWardFeatureName(props) || 'Unknown';
    const num = getWardFeatureNumber(props);
    const searchText = normalizeText(`${num} ${name}`);
    return { feature: f, name, num, searchText };
  });
}

function showWardSearchResults(query) {
  const q = normalizeText(query);
  const dropdown = document.getElementById('cc-ward-search-results');
  if (!dropdown) return;
  if (!q || q.length < 2) {
    dropdown.classList.add('hidden');
    dropdown.innerHTML = '';
    return;
  }
  const list = getSearchableWardList();
  const matches = list.filter((w) => w.searchText.includes(q)).slice(0, 12);
  if (matches.length === 0) {
    dropdown.classList.remove('hidden');
    dropdown.innerHTML = '<div class="ward-search-item" style="cursor:default;color:var(--secondary)">No wards found</div>';
    return;
  }
  dropdown.innerHTML = matches.map((w, i) => {
    const label = w.num ? `#${w.num} ${escapeHtml(w.name)}` : escapeHtml(w.name);
    return `<div class="ward-search-item" role="option" data-match-index="${i}">${label}</div>`;
  }).join('');
  dropdown.classList.remove('hidden');
  dropdown.querySelectorAll('.ward-search-item[data-match-index]').forEach((el) => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.matchIndex, 10);
      const item = matches[idx];
      if (item?.feature) {
        zoomToWardFeature(item.feature);
        updateWardInfoCardByFeature(item.feature);
        document.getElementById('cc-ward-search').value = item.num ? `#${item.num} ${item.name}` : item.name;
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
      }
    });
  });
}

function getFeatureKey(feature) {
  const props = feature?.properties || {};
  return `${getWardFeatureNumber(props)}_${normalizeText(getWardFeatureName(props))}`;
}

function zoomToWardFeature(feature) {
  if (!commandMap || !feature) return;
  const temp = L.geoJSON(feature);
  commandMap.fitBounds(temp.getBounds(), { padding: [20, 20], maxZoom: 14 });
  // Highlight selected ward with thicker boundary
  const key = getFeatureKey(feature);
  const layer = wardFeatureToLayer.get(key);
  if (layer) {
    if (wardHighlightedLayer) wardHighlightedLayer.setStyle({ color: '#9ca3af', weight: 0.8, fillOpacity: 0.02 });
    layer.setStyle({ color: '#0d9488', weight: 3, fillOpacity: 0.1 });
    layer.bringToFront();
    wardHighlightedLayer = layer;
  }
}

function renderWardBoundaries() {
  if (!commandMap || !commandGeoJson) return;
  if (wardGeoJsonLayer) commandMap.removeLayer(wardGeoJsonLayer);
  wardFeatureToLayer.clear();
  wardHighlightedLayer = null;
  // Thin light grey by default — only highlight when selected (not a green spiderweb)
  const defaultStyle = { color: '#9ca3af', weight: 0.8, fillOpacity: 0.02 };
  const hoverStyle = { color: '#6b7280', weight: 1.5, fillOpacity: 0.06 };
  const highlightStyle = { color: '#0d9488', weight: 3, fillOpacity: 0.1 };
  const geoOpts = { style: defaultStyle, onEachFeature: (feature, layer) => {
      layer.feature = feature;
      wardFeatureToLayer.set(getFeatureKey(feature), layer);
      /* Tooltip shown by map mousemove (cc-ward-hover-tooltip) - no bindTooltip to avoid duplicates */
      layer.on('mouseover', function () {
        if (this !== wardHighlightedLayer) this.setStyle(hoverStyle);
        this.bringToFront();
      });
      layer.on('mouseout', function () {
        if (this !== wardHighlightedLayer) this.setStyle(defaultStyle);
      });
      layer.on('click', () => {
        if (wardHighlightedLayer) wardHighlightedLayer.setStyle(defaultStyle);
        layer.setStyle(highlightStyle);
        layer.bringToFront();
        wardHighlightedLayer = layer;
        showWardPanelAndUpdate(feature);
        commandMap.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 14 });
      });
    },
  };
  if (typeof L.canvas === 'function') geoOpts.renderer = L.canvas();
  wardGeoJsonLayer = L.geoJSON(commandGeoJson, geoOpts).addTo(commandMap);
  applyFilterHighlighting();
}

function applyFilterHighlighting() {
  if (!wardGeoJsonLayer || wardFeatureToLayer.size === 0) return;
  const zoneId = document.getElementById('cc-zone-filter')?.value || '';
  const wardId = document.getElementById('cc-ward-filter')?.value || '';
  const defaultStyle = { color: '#9ca3af', weight: 0.8, fillOpacity: 0.02 };
  const zoneOutlineStyle = { color: '#0d9488', weight: 2, fillOpacity: 0.06 };
  const wardHighlightStyle = { color: '#0d9488', weight: 3, fillOpacity: 0.15 };

  wardFeatureToLayer.forEach((layer) => {
    const feature = layer?.feature;
    if (!feature) return;
    const ward = getWardForFeature(feature);
    const isInZone = zoneId && ward && String(ward.zone_id) === String(zoneId);
    const isSelectedWard = wardId && ward && String(ward.id) === String(wardId);

    if (isSelectedWard) {
      layer.setStyle(wardHighlightStyle);
      layer.bringToFront();
    } else if (isInZone) {
      layer.setStyle(zoneOutlineStyle);
    } else {
      layer.setStyle(defaultStyle);
    }
  });
}

function wardInfoRow(label, value) {
  return `<div class="ward-info-row"><span class="ward-info-label">${escapeHtml(label)}</span><span class="ward-info-value">${escapeHtml(String(value ?? 'N/A'))}</span></div>`;
}

function showWardPanelAndUpdate(feature) {
  updateWardInfoCardByFeature(feature);
}
function hideWardPanel() {
  updateWardInfoDefault(commandCenterData || []);
}

function updateWardInfoDefault(items) {
  const box = document.getElementById('ward-info-content');
  if (!box) return;
  const counts = { escalated: 0, pending: 0, assigned: 0, inprogress: 0, resolved: 0 };
  items.forEach((g) => {
    const st = (g.status || 'pending').toLowerCase();
    if (st in counts) counts[st]++;
  });
  const total = items.length;
  const wardCounts = {};
  items.forEach((g) => {
    const wn = g.ward_name || 'Unknown';
    wardCounts[wn] = (wardCounts[wn] || 0) + 1;
  });
  const sortedWards = Object.entries(wardCounts).sort((a, b) => b[1] - a[1]);
  const topWard = sortedWards[0];
  const top5 = items
    .slice()
    .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    .slice(0, 5);
  const statusColor = (s) => ({ escalated: 'status-escalated', pending: 'status-pending', assigned: 'status-assigned', inprogress: 'status-inprogress', resolved: 'status-resolved' })[(s || '').toLowerCase()] || '';
  box.innerHTML = `
    <div class="ward-pane ward-pane-overview">
      <div class="ward-pane-header ward-pane-header-overview">
        <h2 class="ward-pane-title">City Overview</h2>
        <p class="ward-pane-subtitle">${total} grievance${total !== 1 ? 's' : ''} in current view</p>
      </div>
      <div class="ward-pane-section">
        <h3 class="ward-pane-section-title">Status breakdown</h3>
        <div class="ward-pane-kpis">
          <div class="ward-pane-kpi ward-pane-kpi-total"><span class="ward-pane-kpi-value">${total}</span><span class="ward-pane-kpi-label">Total</span></div>
          <div class="ward-pane-kpi ward-pane-kpi-escalated"><span class="ward-pane-kpi-value">${counts.escalated}</span><span class="ward-pane-kpi-label">Escalated</span></div>
          <div class="ward-pane-kpi ward-pane-kpi-pending"><span class="ward-pane-kpi-value">${counts.pending}</span><span class="ward-pane-kpi-label">Pending</span></div>
          <div class="ward-pane-kpi ward-pane-kpi-assigned"><span class="ward-pane-kpi-value">${counts.assigned}</span><span class="ward-pane-kpi-label">Assigned</span></div>
          <div class="ward-pane-kpi ward-pane-kpi-inprogress"><span class="ward-pane-kpi-value">${counts.inprogress}</span><span class="ward-pane-kpi-label">In progress</span></div>
          <div class="ward-pane-kpi ward-pane-kpi-resolved"><span class="ward-pane-kpi-value">${counts.resolved}</span><span class="ward-pane-kpi-label">Resolved</span></div>
        </div>
      </div>
      ${topWard ? `<div class="ward-pane-section"><h3 class="ward-pane-section-title">Most active ward</h3><div class="ward-pane-top-ward">${escapeHtml(topWard[0])}<span class="ward-pane-top-ward-count">${topWard[1]} complaints</span></div></div>` : ''}
      <div class="ward-pane-section">
        <h3 class="ward-pane-section-title">Recent activity</h3>
        <div class="ward-pane-recent-list">
          ${top5.length ? top5.map((g) => { const st = (g.status || 'pending').toLowerCase(); return `<div class="ward-pane-recent-item"><span class="ward-pane-recent-title">${escapeHtml((g.title || '–').slice(0, 50))}${(g.title || '').length > 50 ? '…' : ''}</span><div class="ward-pane-recent-meta"><span class="ward-pane-recent-ward">${escapeHtml(g.ward_name || '')}</span><span class="ward-pane-status-pill ${statusColor(st)}">${escapeHtml(st)}</span></div></div>`; }).join('') : '<div class="ward-pane-empty">No complaints in view</div>'}
        </div>
      </div>
      <div class="ward-pane-cta">Click a ward on the map for ward-specific details</div>
    </div>`;
}

async function updateWardInfoCardByFeature(feature) {
  const props = feature?.properties || {};
  const name = getWardFeatureName(props);
  const number = getWardFeatureNumber(props);
  let ward = commandWards.find((w) => normalizeText(w.name) === normalizeText(name) || String(w.number) === String(number));
  const box = document.getElementById('ward-info-content');
  if (!box) return;

  // Fetch full ward from DB to get all fields (representative_phone, representative_email, etc.)
  if (ward?.id) {
    try {
      const fresh = await api(`/wards/${ward.id}`).catch(() => null);
      if (fresh) ward = fresh;
    } catch (_) {}
  }

  const fallback = (v, p) => v ?? props[p] ?? props[p.toUpperCase()] ?? 'N/A';
  const phones = Array.isArray(ward?.representative_phone) ? ward.representative_phone : (ward?.representative_phone ? [ward.representative_phone] : []);
  const phoneStr = phones.filter(Boolean).length ? phones.join(', ') : fallback(null, 'representative_phone');
  const zoneName = ward?.zone_name ?? fallback(null, 'zone');
  const repName = ward?.representative_name ?? fallback(null, 'councillor');
  const repParty = ward?.representative_party ?? fallback(null, 'party');
  const repEmail = ward?.representative_email ?? fallback(null, 'representative_email');
  const wardDisplayName = name || ward?.name || 'Unknown';
  const wardNum = number ?? ward?.number ?? '';

  let grievanceHtml = '';
  let staffCount = 0;
  let openCount = 0;
  const counts = { escalated: '–', pending: '–', assigned: '–', inprogress: '–', resolved: '–' };
  if (ward?.id) {
    try {
      const [staffResp, esc, pend, ass, prog, res] = await Promise.all([
        api(`/workers?ward_id=${ward.id}&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=escalated&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=pending&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=assigned&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=inprogress&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=resolved&limit=1`).catch(() => null),
      ]);
      staffCount = staffResp?.total ?? staffResp?.items?.length ?? 0;
      openCount = (pend?.total ?? 0) + (ass?.total ?? 0) + (prog?.total ?? 0) + (esc?.total ?? 0);
      counts.escalated = esc?.total ?? '–';
      counts.pending = pend?.total ?? '–';
      counts.assigned = ass?.total ?? '–';
      counts.inprogress = prog?.total ?? '–';
      counts.resolved = res?.total ?? '–';
    } catch (_) {}
  }
  const ratioStr = staffCount > 0 ? `${staffCount} staff : ${openCount} open` : openCount > 0 ? `${openCount} open (no staff)` : '–';
  const hasPhone = phoneStr !== 'N/A' && String(phoneStr).replace(/\D/g, '').length > 0;
  const hasEmail = repEmail !== 'N/A';
  const hasContact = hasPhone || hasEmail;
  const pop = props.population ?? props.POPULATION;
  const infoRows = [
    ['Ward', wardDisplayName],
    ['Ward No', wardNum ? String(wardNum) : 'N/A'],
    ['Zone', zoneName],
    ['Representative', repName],
    ['Party', repParty],
    ['Phone', phoneStr],
    ['Email', repEmail],
    ...(pop != null ? [['Population', String(pop)]] : []),
  ];

  box.innerHTML = `
    <div class="ward-pane ward-pane-detail">
      <div class="ward-pane-header ward-pane-header-detail">
        <h2 class="ward-pane-title">${escapeHtml(wardDisplayName)}</h2>
        ${wardNum ? `<span class="ward-pane-badge">Ward #${escapeHtml(String(wardNum))}</span>` : ''}
        ${zoneName !== 'N/A' ? `<span class="ward-pane-zone">${escapeHtml(zoneName)}</span>` : ''}
      </div>
      <div class="ward-pane-info-block">
        <h3 class="ward-pane-block-title">Ward details</h3>
        <div class="ward-pane-rows">
          ${infoRows.map(([lbl, val]) => {
            const isLink = lbl === 'Phone' && hasPhone ? `tel:${String(phoneStr).replace(/\D/g, '')}` : lbl === 'Email' && hasEmail ? `mailto:${encodeURIComponent(repEmail || '')}` : '';
            return `<div class="ward-pane-row"><span class="ward-pane-label">${escapeHtml(lbl)}</span><span class="ward-pane-value">${isLink ? `<a href="${isLink}" class="ward-pane-link">${escapeHtml(val)}</a>` : escapeHtml(val)}</span></div>`;
          }).join('')}
        </div>
      </div>
      <div class="ward-pane-info-block">
        <h3 class="ward-pane-block-title">Staff &amp; workload</h3>
        <div class="ward-pane-rows">
          <div class="ward-pane-row"><span class="ward-pane-label">Field staff</span><span class="ward-pane-value">${staffCount}</span></div>
          <div class="ward-pane-row"><span class="ward-pane-label">Open issues</span><span class="ward-pane-value">${openCount}</span></div>
          <div class="ward-pane-row"><span class="ward-pane-label">Ratio</span><span class="ward-pane-value">${escapeHtml(ratioStr)}</span></div>
        </div>
      </div>
      <div class="ward-pane-info-block">
        <h3 class="ward-pane-block-title">Grievances by status</h3>
        <div class="ward-pane-stats">
          <div class="ward-pane-stat ward-pane-stat-escalated"><span class="ward-pane-stat-val">${counts.escalated}</span><span class="ward-pane-stat-lbl">Escalated</span></div>
          <div class="ward-pane-stat ward-pane-stat-pending"><span class="ward-pane-stat-val">${counts.pending}</span><span class="ward-pane-stat-lbl">Pending</span></div>
          <div class="ward-pane-stat ward-pane-stat-assigned"><span class="ward-pane-stat-val">${counts.assigned}</span><span class="ward-pane-stat-lbl">Assigned</span></div>
          <div class="ward-pane-stat ward-pane-stat-inprogress"><span class="ward-pane-stat-val">${counts.inprogress}</span><span class="ward-pane-stat-lbl">In progress</span></div>
          <div class="ward-pane-stat ward-pane-stat-resolved"><span class="ward-pane-stat-val">${counts.resolved}</span><span class="ward-pane-stat-lbl">Resolved</span></div>
        </div>
      </div>
    </div>`;
}

async function fetchAllGrievancesForCommand() {
  const wardId = document.getElementById('cc-ward-filter')?.value || '';
  const zoneId = document.getElementById('cc-zone-filter')?.value || '';
  const dateFrom = document.getElementById('cc-date-from')?.value || '';
  const dateTo = document.getElementById('cc-date-to')?.value || '';

  const effectiveWardId = wardId;
  const effectiveZoneId = zoneId;

  const limit = 100;
  const maxTotal = 500;
  let skip = 0;
  let done = false;
  let out = [];
  while (!done && skip < maxTotal) {
    let q = `/grievances?skip=${skip}&limit=${limit}`;
    if (effectiveWardId) q += `&ward_id=${encodeURIComponent(effectiveWardId)}`;
    const resp = await api(q);
    const items = Array.isArray(resp?.items) ? resp.items : [];
    out = out.concat(items);
    if (items.length < limit || out.length >= maxTotal) done = true;
    skip += limit;
  }

  if (effectiveZoneId && !effectiveWardId) {
    const names = new Set(
      commandWards
        .filter((w) => String(w.zone_id) === String(effectiveZoneId))
        .map((w) => normalizeText(w.name))
    );
    out = out.filter((g) => names.has(normalizeText(g.ward_name)));
  }

  if (dateFrom) {
    const min = new Date(`${dateFrom}T00:00:00`);
    out = out.filter((g) => new Date(g.created_at) >= min);
  }
  if (dateTo) {
    const max = new Date(`${dateTo}T23:59:59`);
    out = out.filter((g) => new Date(g.created_at) <= max);
  }
  return out;
}

function renderCommandMapData(items) {
  if (!commandMap || typeof L === 'undefined') return;
  const mapEl = document.getElementById('command-map');
  if (!mapEl || mapEl.offsetHeight === 0) return;

  // Filter by status badge toggles – badge counts must match map
  const filtered = items.filter((g) => {
    const st = (g.status || 'pending').toLowerCase();
    return commandCenterStatusFilters[st] !== false;
  });

  // Update HUD counts (single source of truth)
  const counts = { escalated: 0, pending: 0, assigned: 0, inprogress: 0, resolved: 0 };
  items.forEach((g) => {
    const st = (g.status || 'pending').toLowerCase();
    if (st in counts) counts[st]++;
  });
  ['escalated', 'pending', 'assigned', 'inprogress', 'resolved'].forEach((k) => {
    const el = document.getElementById(`cc-hud-${k}`);
    if (el) el.textContent = counts[k] ?? 0;
  });
  const plottedEl = document.getElementById('cc-hud-plotted');
  if (plottedEl) plottedEl.textContent = filtered.length;

  document.querySelectorAll('.cc-map-kpi[data-status]').forEach((btn) => {
    btn.classList.toggle('active', commandCenterStatusFilters[btn.dataset.status] !== false);
  });

  if (grievanceClusterLayer) { commandMap.removeLayer(grievanceClusterLayer); grievanceClusterLayer = null; }
  if (grievanceHeatLayer)    { commandMap.removeLayer(grievanceHeatLayer);    grievanceHeatLayer    = null; }

  const heatPts = [];
  grievanceClusterLayer = L.markerClusterGroup({
    disableClusteringAtZoom: 16,
    maxClusterRadius: 50,
    iconCreateFunction: (cluster) => {
      const markers = cluster.getAllChildMarkers();
      let worst = 0;
      let worstStatus = 'pending';
      markers.forEach((m) => {
        const st = m._grievanceStatus || 'pending';
        const sev = statusSeverity(st);
        if (sev > worst) { worst = sev; worstStatus = st; }
      });
      const color = getStatusColor(worstStatus);
      const count = cluster.getChildCount();
      const rgba = color.startsWith('#') ? hexToRgba(color, 0.6) : color;
      return L.divIcon({
        html: `<div style="background-color:${rgba}"><span>${count}</span></div>`,
        className: 'marker-cluster marker-cluster-status',
        iconSize: L.point(40, 40),
      });
    },
  });

  let plotted = 0;
  filtered.forEach((g) => {
    const lat = Number(g.lat);
    const lng = Number(g.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat === 0 || lng === 0) return;
    plotted++;

    // Marker with rich popup
    const st = (g.status || 'pending').toLowerCase();
    const marker = L.marker([lat, lng], { icon: createStatusMarker(st) });
    marker._grievanceStatus = st;
    marker.bindPopup(
      `<div style="min-width:180px;font-size:13px">` +
      `<strong style="display:block;margin-bottom:4px">${escapeHtml(g.title || 'Grievance')}</strong>` +
      `<div><b>Status:</b> <span style="text-transform:capitalize">${escapeHtml(st)}</span></div>` +
      `<div><b>Ward:</b> ${escapeHtml(g.ward_name || 'N/A')}</div>` +
      `<div><b>Category:</b> ${escapeHtml(g.category_name || 'N/A')}</div>` +
      `<div><b>Officer:</b> ${escapeHtml(g.assigned_to_name || 'Unassigned')}${g.assigned_to_phone ? ' · ' + escapeHtml(g.assigned_to_phone) : ''}</div>` +
      `<div style="color:#4a6b6b;font-size:11px;margin-top:4px">${formatDate(g.created_at)}</div>` +
      `</div>`
    );
    grievanceClusterLayer.addLayer(marker);

    // Heatmap weight: escalated = hottest, pending = hot, in-progress = medium, resolved = coolest
    const w = st === 'escalated' ? 1.0 : st === 'pending' ? 0.85 : (st === 'assigned' || st === 'inprogress') ? 0.55 : 0.2;
    heatPts.push([lat, lng, w]);
  });

  // Heatmap is ALWAYS rendered (mandatory layer); interactive: false so clicks pass through to ward polygons
  if (heatPts.length > 0) {
    grievanceHeatLayer = L.heatLayer(heatPts, {
      radius: 28,
      blur: 22,
      maxZoom: 17,
      gradient: { 0.2: '#ffffb2', 0.45: '#fecc5c', 0.65: '#fd8d3c', 0.85: '#f03b20', 1.0: '#bd0026' },
      interactive: false,
    });
    grievanceHeatLayer.addTo(commandMap);
  }

  // Markers shown when "Show Markers" toggle is checked (default: checked)
  const showMarkers = document.getElementById('cc-heatmap-toggle')?.checked !== false;
  if (showMarkers && plotted > 0) {
    grievanceClusterLayer.addTo(commandMap);
  }

}

function flyToGrievance(g) {
  const lat = Number(g.lat);
  const lng = Number(g.lng);
  if (!commandMap || !Number.isFinite(lat) || !Number.isFinite(lng) || lat === 0 || lng === 0) return;
  commandMap.setView([lat, lng], 14);
}

function populateEscalationFeed() {
  const feedEl = document.getElementById('cc-escalation-feed');
  if (!feedEl) return;
  api('/grievances?status=escalated&limit=20').then((resp) => {
    const items = resp?.items || [];
    if (!items.length) {
      feedEl.innerHTML = '<div class="cc-feed-empty">No escalations.</div>';
      return;
    }
    feedEl.innerHTML = items.map((g) => {
      const phone = g.assigned_to_phone && String(g.assigned_to_phone).replace(/\D/g, '');
      const canCall = !!phone;
      const callBtn = canCall
        ? `<a href="tel:${phone}" class="btn btn-sm" title="Call">Call</a>`
        : '';
      return `
        <div class="cc-feed-item" data-id="${g.id}">
          <div class="cc-feed-item-title">${escapeHtml((g.title || '–').slice(0, 50))}${(g.title || '').length > 50 ? '…' : ''}</div>
          <div class="cc-feed-item-meta">${escapeHtml(g.ward_name || '')} · ${escapeHtml((g.priority || 'medium').toLowerCase())}</div>
          <div class="cc-feed-item-actions">
            <button type="button" class="btn btn-sm btn-primary" data-flyto data-id="${g.id}" data-lat="${g.lat}" data-lng="${g.lng}">Fly-to</button>
            <button type="button" class="btn btn-sm" data-dispatch data-id="${g.id}">Dispatch</button>
            ${callBtn}
          </div>
        </div>`;
    }).join('');
    feedEl.querySelectorAll('[data-flyto]').forEach((btn) => {
      btn.addEventListener('click', () => flyToGrievance({ lat: parseFloat(btn.dataset.lat), lng: parseFloat(btn.dataset.lng) }));
    });
    feedEl.querySelectorAll('[data-dispatch]').forEach((btn) => {
      btn.addEventListener('click', () => openAssignWorkerModal(btn.dataset.id));
    });
  }).catch(() => {
    feedEl.innerHTML = '<div class="cc-feed-empty">Failed to load.</div>';
  });
}

async function refreshCommandCenter() {
  await ensureCommandMap();
  if (!commandMap) return;
  setMapLoading(true);
  try {
    const [geo, data] = await Promise.all([
      fetchCommandGeoJson(),
      fetchAllGrievancesForCommand(),
    ]);
    commandGeoJson = geo;
    commandCenterData = data;
    renderWardBoundaries();
    renderCommandMapData(commandCenterData);
    const wardId = document.getElementById('cc-ward-filter')?.value || '';
    if (wardId) {
      const ward = commandWards.find((w) => String(w.id) === String(wardId));
      const feature = findWardFeature(ward);
      if (feature) {
        const temp = L.geoJSON(feature);
        commandMap.fitBounds(temp.getBounds(), { padding: [20, 20], maxZoom: 14 });
        showWardPanelAndUpdate(feature);
      } else {
        hideWardPanel();
      }
    } else {
      hideWardPanel();
    }
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load map command center', 'error');
  } finally {
    setMapLoading(false);
  }
}

function exportCommandCsv() {
  const headers = ['id', 'ward', 'category', 'assigned_officer', 'status', 'created_at'];
  const rows = [headers.join(',')].concat(
    commandCenterData.map((g) => [
      g.id,
      JSON.stringify(g.ward_name || ''),
      JSON.stringify(g.category_name || ''),
      JSON.stringify(g.assigned_to_name || ''),
      g.status || '',
      g.created_at || '',
    ].join(','))
  );
  const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `civiccare_command_export_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function exportCommandPdf() {
  const win = window.open('', '_blank');
  if (!win) return;
  const rows = (commandCenterData || []).map((g) =>
    `<tr><td>${escapeHtml(g.title || '')}</td><td>${escapeHtml(g.ward_name || '')}</td><td>${escapeHtml(g.category_name || '')}</td><td>${escapeHtml(g.assigned_to_name || '')}</td><td>${escapeHtml(g.status || '')}</td></tr>`
  ).join('');
  const table = `<table style="border-collapse:collapse;width:100%"><thead><tr><th>Title</th><th>Ward</th><th>Category</th><th>Officer</th><th>Status</th></tr></thead><tbody>${rows || '<tr><td colspan="5">No data</td></tr>'}</tbody></table>`;
  win.document.write(`<html><head><title>Command Export</title></head><body><h2>CivicCare Command Export</h2>${table}</body></html>`);
  win.document.close();
  win.focus();
  win.print();
}

// ── Party Map ──
let partyMap = null;
let partyGeoJsonLayer = null;
let partyMapData = null;
let partyMapWards = [];
const PARTY_MAP_NEUTRAL = '#9ca3af';

function getWardForFeaturePartyMap(feature, wardList) {
  if (!feature || !wardList.length) return null;
  const props = feature?.properties || {};
  const name = normalizeText(getWardFeatureName(props));
  const num = String(getWardFeatureNumber(props)).trim();
  return wardList.find((w) => {
    const wn = normalizeText(w.name);
    const wnum = String(w.number ?? '').trim();
    return (name && wn && (wn.includes(name) || name.includes(wn))) || (num && wnum && wnum === num);
  }) || null;
}

async function ensurePartyMap() {
  const mapEl = document.getElementById('party-map');
  if (!mapEl || typeof L === 'undefined') return;
  if (!partyMap) {
    partyMap = L.map('party-map', { preferCanvas: true }).setView([28.6139, 77.209], 10);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png', {
      maxZoom: 20,
      subdomains: 'abcd',
      detectRetina: true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(partyMap);
  }
  const mapWrap = document.querySelector('.party-map-wrap');
  if (mapWrap) {
    partyMap.invalidateSize();
  }
  partyMap.on('mousemove', (e) => {
    const tooltipEl = document.getElementById('party-map-ward-tooltip');
    if (!tooltipEl || !mapWrap) return;
    const feature = findWardFeatureAtPointPartyMap(e.latlng);
    if (feature) {
      const ward = getWardForFeaturePartyMap(feature, partyMapWards);
      const props = feature?.properties || {};
      const name = getWardFeatureName(props) || 'Unknown';
      const num = getWardFeatureNumber(props);
      const label = num ? `#${num} ${name}` : name;
      const partyLabel = ward?.party_short_code ? ` · ${ward.party_short_code}` : ' · Unassigned';
      tooltipEl.textContent = label + partyLabel;
      tooltipEl.classList.remove('hidden');
      const rect = mapWrap.getBoundingClientRect();
      tooltipEl.style.left = `${e.originalEvent.clientX - rect.left + 12}px`;
      tooltipEl.style.top = `${e.originalEvent.clientY - rect.top + 8}px`;
    } else {
      tooltipEl.classList.add('hidden');
    }
  });
  partyMap.on('mouseout', () => {
    const tooltipEl = document.getElementById('party-map-ward-tooltip');
    if (tooltipEl) tooltipEl.classList.add('hidden');
  });
}

function findWardFeatureAtPointPartyMap(latlng) {
  if (!partyMapData?.features?.length || !latlng) return null;
  const lng = latlng.lng;
  const lat = latlng.lat;
  for (const f of partyMapData.features) {
    const coords = f?.geometry?.coordinates;
    if (!coords) continue;
    if (f.geometry.type === 'Polygon' && Array.isArray(coords[0])) {
      const ring = coords[0];
      if (ring && Array.isArray(ring[0]) && pointInPolygonRing(lng, lat, ring)) return f;
    } else if (f.geometry.type === 'MultiPolygon' && Array.isArray(coords)) {
      for (const poly of coords) {
        const ring = Array.isArray(poly?.[0]) ? poly[0] : poly;
        if (ring && Array.isArray(ring[0]) && pointInPolygonRing(lng, lat, ring)) return f;
      }
    }
  }
  return null;
}

function renderPartyMapWards() {
  if (!partyMap || !partyMapData || !partyMapWards.length) return;
  if (partyGeoJsonLayer) partyMap.removeLayer(partyGeoJsonLayer);
  const defaultStyle = { color: '#6b7280', weight: 0.8, fillOpacity: 0.02 };
  const hoverStyle = { color: '#4b5563', weight: 1.5, fillOpacity: 0.12 };
  const geoOpts = {
    style: (feature) => {
      const ward = getWardForFeaturePartyMap(feature, partyMapWards);
      const color = ward?.party_color || PARTY_MAP_NEUTRAL;
      return {
        color: color,
        weight: 1,
        fillColor: color,
        fillOpacity: 0.35,
      };
    },
    onEachFeature: (feature, layer) => {
      layer.feature = feature;
      layer.on('mouseover', function () {
        const ward = getWardForFeaturePartyMap(feature, partyMapWards);
        const color = ward?.party_color || PARTY_MAP_NEUTRAL;
        this.setStyle({ color, weight: 1.5, fillColor: color, fillOpacity: 0.5 });
        this.bringToFront();
      });
      layer.on('mouseout', function () {
        const ward = getWardForFeaturePartyMap(this.feature, partyMapWards);
        const color = ward?.party_color || PARTY_MAP_NEUTRAL;
        this.setStyle({ color, weight: 1, fillColor: color, fillOpacity: 0.35 });
      });
    },
  };
  if (typeof L.canvas === 'function') geoOpts.renderer = L.canvas();
  partyGeoJsonLayer = L.geoJSON(partyMapData, geoOpts).addTo(partyMap);
}

let partyMapControlData = null;

function renderPartyMapAnalytics(data) {
  partyMapControlData = data;
  const listEl = document.getElementById('party-map-list');
  if (!listEl) return;
  const total = data.total_wards || 0;
  const assigned = total - (data.wards_without_party ?? 0);
  const totalEl = document.getElementById('party-map-total-wards');
  const assignedEl = document.getElementById('party-map-assigned');
  const partiesEl = document.getElementById('party-map-parties');
  if (totalEl) totalEl.textContent = total;
  if (assignedEl) assignedEl.textContent = assigned;
  if (partiesEl) partiesEl.textContent = (data.parties || []).length;

  const filterEl = document.getElementById('party-map-filter');
  const sortTop = !filterEl || filterEl.value === 'top';
  let parties = [...(data.parties || [])];
  parties.sort((a, b) => {
    const wpiA = a.avg_wpi != null ? a.avg_wpi : -1;
    const wpiB = b.avg_wpi != null ? b.avg_wpi : -1;
    return sortTop ? wpiB - wpiA : wpiA - wpiB;
  });

  const hasUnassigned = (data.wards_without_party ?? 0) > 0;
  const items = [];

  function renderItem(p, isUnassigned = false) {
    const m = p.metrics || {};
    const grv = m.total ?? 0;
    const resPct = grv > 0 ? (m.resolution_pct ?? 0) : null;
    const slaPct = grv > 0 ? (m.sla_pct ?? 0) : null;
    const wpi = p.avg_wpi != null ? p.avg_wpi : null;
    const resStr = resPct != null ? resPct + '%' : '–';
    const slaStr = slaPct != null ? slaPct + '%' : '–';
    const wpiStr = wpi != null ? (typeof wpi === 'number' ? wpi.toFixed(1) : String(wpi)) : '–';
    const resCls = resStr !== '–' ? ' party-map-res' : '';
    const slaCls = slaStr !== '–' ? ' party-map-sla' : '';
    const wpiCls = wpiStr !== '–' ? ' party-map-wpi' : '';
    const color = p.color || PARTY_MAP_NEUTRAL;
    const name = isUnassigned ? 'Unassigned' : escapeHtml(p.short_code || p.name);
    return `
      <li class="party-map-item ${isUnassigned ? 'party-map-item-unassigned' : ''}">
        <div class="party-map-item-header">
          <span class="party-map-swatch" style="background:${escapeHtml(color)}"></span>
          <strong class="party-map-item-name">${name}</strong>
          <span class="party-map-item-wards">${p.ward_count} (${p.ward_pct}%)</span>
        </div>
        <div class="party-map-item-meta">
          <span>Grv <b>${grv}</b></span>
          <span>Res% <b class="${resCls.trim()}">${resStr}</b></span>
          <span>SLA <b class="${slaCls.trim()}">${slaStr}</b></span>
          <span>WPI <b class="${wpiCls.trim()}">${wpiStr}</b></span>
        </div>
      </li>
    `;
  }

  parties.forEach((p) => { items.push(renderItem(p)); });
  if (hasUnassigned) {
    items.push(renderItem({
      ward_count: data.wards_without_party,
      ward_pct: data.unassigned_pct,
      metrics: data.unassigned_metrics || {},
      avg_wpi: data.unassigned_avg_wpi,
    }, true));
  }
  listEl.innerHTML = items.length ? items.join('') : '<li class="party-map-empty">No parties. Add parties in Admin.</li>';
}

async function loadPartyMapData() {
  const loadingEl = document.getElementById('party-map-loading');
  if (loadingEl) loadingEl.classList.remove('hidden');
  try {
    await ensurePartyMap();
    if (!partyMap) return;
    const [geo, control] = await Promise.all([
      api('/wards/geojson'),
      api('/analytics/parties/control'),
    ]);
    partyMapData = geo;
    partyMapWards = control.wards || [];
    renderPartyMapWards();
    renderPartyMapAnalytics(control);
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load party map', 'error');
    renderPartyMapAnalytics({ total_wards: 0, wards_without_party: 0, parties: [] });
  } finally {
    if (loadingEl) loadingEl.classList.add('hidden');
  }
}

async function initPartyMap() {
  await loadPartyMapData();
}

document.getElementById('btn-party-map-refresh')?.addEventListener('click', () => loadPartyMapData());
document.getElementById('party-map-filter')?.addEventListener('change', () => {
  if (partyMapControlData) renderPartyMapAnalytics(partyMapControlData);
});

let logsAllRows = [];
let logsPage = 0;
const LOGS_PAGE_SIZE = 50;

async function loadSystemLogs() {
  const tbody = document.getElementById('system-logs-tbody');
  if (!tbody) return;
  logsPage = 0;
  tbody.innerHTML = '<tr><td colspan="6"><span class="spinner"></span> Loading logs…</td></tr>';
  try {
    // Fetch up to 50 recent grievances and get their events in parallel batches
    const gResp = await api('/grievances?limit=50&skip=0');
    const gList = Array.isArray(gResp?.items) ? gResp.items : [];
    // Fetch details in parallel (cap at 50 to avoid flooding)
    const BATCH = 10;
    const detailList = [];
    for (let i = 0; i < gList.length; i += BATCH) {
      const batch = await Promise.all(
        gList.slice(i, i + BATCH).map((g) => api(`/grievances/${g.id}`).catch(() => null))
      );
      detailList.push(...batch);
    }
    logsAllRows = [];
    detailList.forEach((d) => {
      if (!d || !Array.isArray(d.events)) return;
      d.events.forEach((ev) => {
        const text = `${ev.title || ''} ${ev.description || ''}`;
        const geoBad = /outside|10\s?-?\s?meter|10m|geofence/i.test(text);
        logsAllRows.push({
          when: ev.created_at || d.updated_at || d.created_at,
          grievance: d.title || String(d.id).slice(0, 8),
          ward: d.ward_name || '–',
          event: ev.title || ev.description || 'Update',
          actor: ev.actor_name || (ev.actor_id ? String(ev.actor_id).slice(0, 8) + '…' : '–'),
          geofence: geoBad ? 'Potential violation' : 'OK',
          isBad: geoBad,
        });
      });
    });
    logsAllRows.sort((a, b) => new Date(b.when) - new Date(a.when));
    populateLogsFilters();
    renderSystemLogs();
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="6">Failed to load logs.</td></tr>';
  }
}

function populateLogsFilters() {
  const wardSel = document.getElementById('logs-ward-filter');
  const actorSel = document.getElementById('logs-actor-filter');
  if (!wardSel || !actorSel) return;
  const wards = [...new Set(logsAllRows.map((r) => (r.ward || '').trim()).filter(Boolean))].sort();
  const actors = [...new Set(logsAllRows.map((r) => (r.actor || '').trim()).filter(Boolean))].sort();
  const selectedWard = wardSel.value;
  const selectedActor = actorSel.value;
  wardSel.innerHTML = '<option value="">All wards</option>' + wards.map((w) => `<option value="${escapeHtml(w)}">${escapeHtml(w)}</option>`).join('');
  actorSel.innerHTML = '<option value="">All actors</option>' + actors.map((a) => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join('');
  if (wards.includes(selectedWard)) wardSel.value = selectedWard;
  if (actors.includes(selectedActor)) actorSel.value = selectedActor;
}

function renderSystemLogs() {
  const tbody = document.getElementById('system-logs-tbody');
  const searchQ = normalizeText(document.getElementById('logs-search')?.value || '');
  const dateFrom = document.getElementById('logs-date-from')?.value || '';
  const dateTo   = document.getElementById('logs-date-to')?.value   || '';
  const wardFilter = (document.getElementById('logs-ward-filter')?.value || '').trim();
  const actorFilter = (document.getElementById('logs-actor-filter')?.value || '').trim();
  const geoFilter = document.getElementById('logs-geo-filter')?.value || '';

  let rows = logsAllRows.filter((r) => {
    if (searchQ && !normalizeText(r.grievance).includes(searchQ) && !normalizeText(r.event).includes(searchQ) && !normalizeText(r.actor || '').includes(searchQ)) return false;
    if (dateFrom && new Date(r.when) < new Date(`${dateFrom}T00:00:00`)) return false;
    if (dateTo   && new Date(r.when) > new Date(`${dateTo}T23:59:59`))   return false;
    if (wardFilter && (r.ward || '').trim() !== wardFilter) return false;
    if (actorFilter && (r.actor || '').trim() !== actorFilter) return false;
    if (geoFilter === 'bad' && !r.isBad)  return false;
    if (geoFilter === 'ok'  &&  r.isBad)  return false;
    return true;
  });

  const total = rows.length;
  const start = logsPage * LOGS_PAGE_SIZE;
  const page  = rows.slice(start, start + LOGS_PAGE_SIZE);

  tbody.innerHTML = page.map((r) => `
    <tr>
      <td>${formatDate(r.when)}</td>
      <td>${escapeHtml(r.grievance)}</td>
      <td>${escapeHtml(r.ward)}</td>
      <td>${escapeHtml(r.event)}</td>
      <td>${escapeHtml(r.actor)}</td>
      <td class="${r.isBad ? 'geo-flag-bad' : 'geo-flag-good'}">${r.isBad ? '⚠ ' : ''}${escapeHtml(r.geofence)}</td>
    </tr>
  `).join('') || '<tr><td colspan="6">No matching events.</td></tr>';

  // Pagination
  const pag = document.getElementById('logs-pagination');
  if (pag) {
    const prev = logsPage > 0;
    const next = start + LOGS_PAGE_SIZE < total;
    pag.innerHTML = `
      <span>${total === 0 ? '0' : start + 1}–${Math.min(start + LOGS_PAGE_SIZE, total)} of ${total}</span>
      <button type="button" class="btn btn-sm" data-action="prev" ${prev ? '' : 'disabled'}>Previous</button>
      <button type="button" class="btn btn-sm" data-action="next" ${next ? '' : 'disabled'}>Next</button>
    `;
    pag.querySelector('[data-action="prev"]')?.addEventListener('click', () => { logsPage--; renderSystemLogs(); });
    pag.querySelector('[data-action="next"]')?.addEventListener('click', () => { logsPage++; renderSystemLogs(); });
  }
}

function wireCommandCenterEvents() {
  document.getElementById('cc-zone-filter')?.addEventListener('change', () => {
    syncCommandWardOptions();
    applyFilterHighlighting();
    refreshCommandCenter();
  });
  document.getElementById('cc-ward-filter')?.addEventListener('change', () => {
    applyFilterHighlighting();
    refreshCommandCenter();
  });
  ['cc-date-from', 'cc-date-to'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', refreshCommandCenter);
  });

  document.getElementById('cc-heatmap-toggle')?.addEventListener('change', () => {
    if (commandCenterData.length > 0) renderCommandMapData(commandCenterData);
  });
  document.getElementById('btn-cc-refresh')?.addEventListener('click', refreshCommandCenter);
  document.getElementById('cc-ward-close')?.addEventListener('click', hideWardPanel);

  document.querySelectorAll('.cc-map-kpi[data-status]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const status = btn.dataset.status;
      commandCenterStatusFilters[status] = !commandCenterStatusFilters[status];
      btn.classList.toggle('active', commandCenterStatusFilters[status]);
      if (commandCenterData.length > 0) renderCommandMapData(commandCenterData);
    });
  });

  document.getElementById('btn-export-csv')?.addEventListener('click', exportCommandCsv);
  document.getElementById('btn-export-pdf')?.addEventListener('click', exportCommandPdf);
}

async function initCommandCenter() {
  if (!commandCenterReady) {
    wireCommandCenterEvents();
    await Promise.all([populateCommandFilters(), ensureCommandMap()]);
    syncCommandWardOptions();
    commandCenterReady = true;
  }
  await refreshCommandCenter();
}

// System Logs filter listeners (wired once, not inside wireCommandCenterEvents)
document.getElementById('btn-refresh-logs')?.addEventListener('click', loadSystemLogs);
['logs-search', 'logs-date-from', 'logs-date-to', 'logs-ward-filter', 'logs-actor-filter', 'logs-geo-filter'].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  const evtType = el.tagName === 'SELECT' ? 'change' : 'input';
  el.addEventListener(evtType, () => { logsPage = 0; renderSystemLogs(); });
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

const PAGE_TITLES = {
  'command-center': 'Command Center',
  dashboard: 'Dashboard',
  map: 'Map View',
  analytics: 'Analytics',
  'party-map': 'Party Map',
  escalations: 'Escalations',
  grievances: 'Grievances',
  departments: 'Departments',
  parties: 'Political Parties',
  wards: 'Wards & Zones',
  workers: 'Officers',
  citizens: 'Citizens',
  logs: 'System Logs',
};

async function initAdmin() {
  try {
    renderAuth();
    const activePage = document.querySelector('.nav-item.active')?.dataset.page || 'command-center';
    const title = PAGE_TITLES[activePage] || 'Admin';
    document.title = activePage === 'command-center' ? 'Command Center - CivicCare Admin' : `Command Center - ${title} - CivicCare Admin`;
    const cmdCenterActive = document.getElementById('page-command-center')?.classList.contains('active');
    if (cmdCenterActive) {
      await initCommandCenter();
    } else {
      await loadDashboard();
    }
  } catch (err) {
    console.error('Admin init error:', err);
    const recentEl = document.getElementById('recent-grievances-list');
    const bdEl = document.getElementById('status-breakdown');
    if (recentEl) recentEl.innerHTML = '<div class="activity-empty">Failed to load. <a href="#" id="dashboard-retry">Retry</a></div>';
    if (bdEl) bdEl.innerHTML = '';
    document.getElementById('dashboard-retry')?.addEventListener('click', (ev) => {
      ev.preventDefault();
      if (recentEl) recentEl.innerHTML = '<div class="activity-empty">Loading…</div>';
      initAdmin();
    });
    ['stat-grievances','stat-pending','stat-resolved','stat-assigned','stat-inprogress','stat-escalated','stat-departments','stat-workers','stat-wards']
      .forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = '–'; });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initAdmin());
} else {
  initAdmin();
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

let deptCharts = { dpi: null, radar: null, scatter: null, pie: null };
let workerCharts = { resolved: null, sla: null, attendance: null, rating: null };
let wardCharts = { wpi: null, pie: null, resolution: null, workload: null };
let zoneCharts = { zpi: null, pie: null, resolution: null, workload: null };
let lastWorkerAnalyticsData = [];

async function populateAnalyticsFilters() {
  const [zones, wards, departments] = await Promise.all([
    api('/zones').catch(() => []),
    api('/wards').catch(() => []),
    api('/departments').catch(() => []),
  ]);
  const zoneList = Array.isArray(zones) ? zones : [];
  const wardList = Array.isArray(wards) ? wards : [];
  const deptList = Array.isArray(departments) ? departments : [];

  const deptZoneSel = document.getElementById('analytics-dept-zone');
  const deptWardSel = document.getElementById('analytics-dept-ward');
  if (deptZoneSel) {
    const v = deptZoneSel.value;
    deptZoneSel.innerHTML = '<option value="">All zones</option>';
    zoneList.forEach((z) => deptZoneSel.appendChild(new Option(z.name, z.id)));
    if (v) deptZoneSel.value = v;
  }
  if (deptWardSel) {
    const v = deptWardSel.value;
    deptWardSel.innerHTML = '<option value="">All wards</option>';
    wardList.forEach((w) => deptWardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    if (v) deptWardSel.value = v;
  }

  const workerDeptSel = document.getElementById('analytics-worker-dept');
  const workerWardSel = document.getElementById('analytics-worker-ward');
  if (workerDeptSel) {
    const v = workerDeptSel.value;
    workerDeptSel.innerHTML = '<option value="">All departments</option>';
    deptList.forEach((d) => workerDeptSel.appendChild(new Option(d.name, d.id)));
    if (v) workerDeptSel.value = v;
  }
  if (workerWardSel) {
    const v = workerWardSel.value;
    workerWardSel.innerHTML = '<option value="">All wards</option>';
    wardList.forEach((w) => workerWardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    if (v) workerWardSel.value = v;
  }

  const wardZoneSel = document.getElementById('analytics-ward-zone');
  if (wardZoneSel) {
    const v = wardZoneSel.value;
    wardZoneSel.innerHTML = '<option value="">All zones</option>';
    zoneList.forEach((z) => wardZoneSel.appendChild(new Option(z.name, z.id)));
    if (v) wardZoneSel.value = v;
  }

  const sustainabilityZoneSel = document.getElementById('analytics-sustainability-zone');
  const sustainabilityWardSel = document.getElementById('analytics-sustainability-ward');
  if (sustainabilityZoneSel) {
    const v = sustainabilityZoneSel.value;
    sustainabilityZoneSel.innerHTML = '<option value="">All zones</option>';
    zoneList.forEach((z) => sustainabilityZoneSel.appendChild(new Option(z.name, z.id)));
    if (v) sustainabilityZoneSel.value = v;
  }
  if (sustainabilityWardSel) {
    const v = sustainabilityWardSel.value;
    sustainabilityWardSel.innerHTML = '<option value="">All wards</option>';
    wardList.forEach((w) => sustainabilityWardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    if (v) sustainabilityWardSel.value = v;
  }

  syncDeptAnalyticsWardOptions(zoneList, wardList);
}

function syncDeptAnalyticsWardOptions(zoneList, wardList) {
  const zoneId = document.getElementById('analytics-dept-zone')?.value || '';
  const wardSel = document.getElementById('analytics-dept-ward');
  if (!wardSel || !Array.isArray(wardList)) return;
  const selected = wardSel.value;
  const list = zoneId
    ? wardList.filter((w) => String(w.zone_id) === String(zoneId))
    : wardList;
  wardSel.innerHTML = '<option value="">All wards</option>';
  list.forEach((w) => wardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
  if (selected && list.some((w) => String(w.id) === String(selected))) wardSel.value = selected;
}

let dpiBarChart = null;
let lastDeptAnalyticsData = [];
let lastWardAnalyticsData = [];
let lastZoneAnalyticsData = [];
let lastSustainabilityAnalyticsData = [];
let analyticsDeptSort = { key: 'dpi', dir: 'desc' };
let analyticsWorkerSort = { key: 'period_resolved', dir: 'desc' };
let analyticsWardSort = { key: 'wpi', dir: 'desc' };
let analyticsZoneSort = { key: 'zpi', dir: 'desc' };
let analyticsSustainabilitySort = { key: 'sustainability_index', dir: 'desc' };

async function loadDepartmentAnalytics() {
  const tbody = document.getElementById('dept-analytics-tbody');
  const zoneSel = document.getElementById('analytics-dept-zone');
  const wardSel = document.getElementById('analytics-dept-ward');

  if (tbody) tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;"><div class="spinner"></div></td></tr>';

  try {
    const zoneId = zoneSel?.value || '';
    const wardId = wardSel?.value || '';
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    if (wardId) params.set('ward_id', wardId);
    const qs = params.toString();
    const data = await api('/analytics/departments' + (qs ? '?' + qs : ''));
    lastDeptAnalyticsData = data;
    renderDeptAnalyticsTable();

    // 4. Render Math Equations (KaTeX)
    if (typeof renderMathInElement === 'function') {
      renderMathInElement(document.getElementById('page-analytics'), {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '$', right: '$', display: false}
        ],
        throwOnError : false
      });
    }

  } catch (e) {
    showToast('Failed to load department analytics', 'error');
  }
}

function getDeptSortValue(d, key) {
  const m = d.metrics || {};
  const s = d.scores || {};
  if (key === 'name' || key === 'performance') return String(d[key] ?? '').toLowerCase();
  if (key === 'total') return m.total ?? 0;
  if (key === 'resolved') return m.resolved ?? 0;
  if (key === 'pending') return m.pending ?? 0;
  if (key === 'sla_resolved') return m.sla_resolved ?? 0;
  if (key === 'total_repeat_count') return m.total_repeat_count ?? 0;
  if (key === 'escalated') return m.escalated ?? 0;
  if (key === 'resolution_rate') return (s.resolution_rate ?? 0) * 100;
  if (key === 'sla_rate') return (s.sla_rate ?? 0) * 100;
  if (key === 'dpi') return s.dpi ?? 0;
  return '';
}

function renderDeptAnalyticsTable() {
  const tbody = document.getElementById('dept-analytics-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('analytics-dept-search')?.value || '');
  let list = !q ? [...lastDeptAnalyticsData] : lastDeptAnalyticsData.filter((d) => {
    const hay = `${d.name} ${d.performance || ''} ${(d.metrics?.total ?? '')} ${(d.metrics?.resolved ?? '')}`;
    return normalizeText(hay).includes(q);
  });
  const { key, dir } = analyticsDeptSort;
  list.sort((a, b) => {
    const av = getDeptSortValue(a, key);
    const bv = getDeptSortValue(b, key);
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  });
  document.querySelectorAll('#dept-analytics-table thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === key) th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
  });
  tbody.innerHTML = list.map(d => `
    <tr>
      <td><strong>${escapeHtml(d.name)}</strong></td>
      <td class="text-center">${d.metrics.total}</td>
      <td class="text-center">${d.metrics.resolved}</td>
      <td class="text-center">${d.metrics.pending}</td>
      <td class="text-center">${d.metrics.sla_resolved}</td>
      <td class="text-center">${d.metrics.total_repeat_count}</td>
      <td class="text-center">${d.metrics.escalated}</td>
      <td class="text-right">${(d.scores.resolution_rate * 100).toFixed(1)}%</td>
      <td class="text-right">${(d.scores.sla_rate * 100).toFixed(1)}%</td>
      <td class="text-center"><strong>${d.scores.dpi}</strong></td>
      <td class="text-center"><span class="perf-badge perf-${(d.performance || '').toLowerCase()}">${d.performance}</span></td>
    </tr>
  `).join('') || '<tr><td colspan="11">No matching departments.</td></tr>';
}

function getDpiColor(dpi) {
  if (dpi >= 90) return '#1d8102'; // Success
  if (dpi >= 80) return '#0d9488'; // Primary teal
  if (dpi >= 70) return '#14b8a6'; // Teal mid
  return '#d13212'; // Danger
}

function renderDepartmentCharts(data) {
  if (!data || !data.length || typeof Chart === 'undefined') return;
  const sorted = [...data].sort((a, b) => (b.scores?.dpi ?? 0) - (a.scores?.dpi ?? 0));
  const colors = ['#0d9488', '#1d8102', '#14b8a6', '#d13212'];

  // 1. DPI Comparison (horizontal bar)
  const dpiCtx = document.getElementById('chart-dept-dpi');
  if (dpiCtx) {
    if (deptCharts.dpi) deptCharts.dpi.destroy();
    deptCharts.dpi = new Chart(dpiCtx, {
      type: 'bar',
      data: {
        labels: sorted.slice(0, 12).map(d => d.name),
        datasets: [{
          label: 'DPI',
          data: sorted.slice(0, 12).map(d => d.scores?.dpi ?? 0),
          backgroundColor: sorted.slice(0, 12).map(d => getDpiColor(d.scores?.dpi ?? 0)),
          borderRadius: 4
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, max: 100 },
          y: { ticks: { font: { size: 11 } } }
        }
      }
    });
  }

  // 2. Radar (metric composition)
  const radarCtx = document.getElementById('chart-dept-radar');
  if (radarCtx) {
    const radarSelect = document.getElementById('radar-dept-select');
    const deptId = radarSelect?.value || '';
    const radarData = deptId ? data.filter(d => String(d.id) === deptId) : data.slice(0, 3);
    if (deptCharts.radar) deptCharts.radar.destroy();
    const radarColors = ['#0d9488', '#4a6b6b', '#5d7a7a'];
    deptCharts.radar = new Chart(radarCtx, {
      type: 'radar',
      data: {
        labels: ['Resolution', 'SLA', 'Caseload', 'Quality', 'Escalation'],
        datasets: radarData.map((d, i) => ({
          label: d.name,
          data: [
            (d.scores?.resolution_rate ?? 0) * 100,
            (d.scores?.sla_rate ?? 0) * 100,
            (d.scores?.pending_score ?? 0) * 100,
            Math.max(0, (d.scores?.recurrence_score ?? 0)) * 100,
            (d.scores?.escalation_score ?? 0) * 100
          ],
          backgroundColor: radarColors[i] + '20',
          borderColor: radarColors[i],
          pointBackgroundColor: radarColors[i],
          borderWidth: 2
        }))
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { r: { beginAtZero: true, max: 100 } },
        plugins: { legend: { position: 'bottom' } }
      }
    });
  }

  // 3. Scatter: Resolution vs SLA
  const scatterCtx = document.getElementById('chart-dept-scatter');
  if (scatterCtx) {
    if (deptCharts.scatter) deptCharts.scatter.destroy();
    const scatterData = data.map(d => ({
      x: (d.scores?.resolution_rate ?? 0) * 100,
      y: (d.scores?.sla_rate ?? 0) * 100,
      label: d.name
    }));
    deptCharts.scatter = new Chart(scatterCtx, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Departments',
          data: scatterData,
          backgroundColor: data.map(d => getDpiColor(d.scores?.dpi ?? 0)),
          borderColor: '#fff',
          borderWidth: 1,
          pointRadius: 10
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const pt = scatterData[ctx.dataIndex];
                return pt ? `${pt.label}: ${ctx.raw.x.toFixed(1)}% res, ${ctx.raw.y.toFixed(1)}% SLA` : '';
              }
            }
          }
        },
        scales: {
          x: { title: { display: true, text: 'Resolution %' }, min: 0, max: 100 },
          y: { title: { display: true, text: 'SLA %' }, min: 0, max: 100 }
        }
      }
    });
  }

  // 4. Performance pie
  const pieCtx = document.getElementById('chart-dept-pie');
  if (pieCtx) {
    if (deptCharts.pie) deptCharts.pie.destroy();
    const byPerf = { Excellent: 0, Good: 0, Average: 0, Poor: 0, Critical: 0 };
    data.forEach(d => { byPerf[d.performance] = (byPerf[d.performance] || 0) + 1; });
    const pieData = Object.entries(byPerf).filter(([, v]) => v > 0);
    deptCharts.pie = new Chart(pieCtx, {
      type: 'doughnut',
      data: {
        labels: pieData.map(([k]) => k),
        datasets: [{
          data: pieData.map(([, v]) => v),
          backgroundColor: ['#1d8102', '#0d9488', '#14b8a6', '#14b8a6', '#d13212'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } }
      }
    });
  }
}

function renderWorkerCharts(data) {
  if (typeof Chart === 'undefined') return;
  const list = Array.isArray(data) ? data : [];
  const top = list.slice(0, 10);

  ['resolved', 'sla', 'attendance', 'rating'].forEach((k) => {
    if (workerCharts[k]) { workerCharts[k].destroy(); workerCharts[k] = null; }
  });

  const resolvedCtx = document.getElementById('chart-worker-resolved');
  if (resolvedCtx && top.length) {
    workerCharts.resolved = new Chart(resolvedCtx, {
      type: 'bar',
      data: {
        labels: top.map(w => w.name?.split(' ')[0] || 'Worker'),
        datasets: [{ label: 'Resolved', data: top.map(w => w.metrics?.period_resolved ?? 0), backgroundColor: '#0d9488', borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
    });
  }

  const slaCtx = document.getElementById('chart-worker-sla');
  if (slaCtx && top.length) {
    workerCharts.sla = new Chart(slaCtx, {
      type: 'bar',
      data: {
        labels: top.map(w => w.name?.split(' ')[0] || 'Worker'),
        datasets: [{ label: 'SLA %', data: top.map(w => (w.metrics?.sla_rate ?? 0) * 100), backgroundColor: '#1d8102', borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } }
    });
  }

  const attCtx = document.getElementById('chart-worker-attendance');
  if (attCtx && top.length) {
    workerCharts.attendance = new Chart(attCtx, {
      type: 'bar',
      data: {
        labels: top.map(w => w.name?.split(' ')[0] || 'Worker'),
        datasets: [{ label: 'Attendance %', data: top.map(w => (w.metrics?.attendance_rate ?? 0) * 100), backgroundColor: '#0d9488', borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } }
    });
  }

  const ratingCtx = document.getElementById('chart-worker-rating');
  if (ratingCtx && list.length) {
    const withRating = list.filter(w => (w.metrics?.period_avg_rating ?? w.metrics?.rating) != null);
    if (withRating.length) {
      const buckets = { '1–2': 0, '2–3': 0, '3–4': 0, '4–5': 0 };
      withRating.forEach(w => {
        const r = w.metrics?.period_avg_rating ?? w.metrics?.rating ?? 0;
        if (r < 2) buckets['1–2']++;
        else if (r < 3) buckets['2–3']++;
        else if (r < 4) buckets['3–4']++;
        else buckets['4–5']++;
      });
      workerCharts.rating = new Chart(ratingCtx, {
        type: 'doughnut',
        data: {
          labels: Object.keys(buckets),
          datasets: [{ data: Object.values(buckets), backgroundColor: ['#d13212', '#14b8a6', '#0d9488', '#1d8102'], borderWidth: 0 }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
      });
    }
  }
}

function renderWardCharts(data) {
  if (typeof Chart === 'undefined') return;
  const list = Array.isArray(data) ? data : [];
  const sorted = [...list].sort((a, b) => (b.scores?.wpi ?? 0) - (a.scores?.wpi ?? 0)).slice(0, 12);

  Object.keys(wardCharts).forEach(k => { if (wardCharts[k]) { wardCharts[k].destroy(); wardCharts[k] = null; } });

  const wpiCtx = document.getElementById('chart-ward-wpi');
  if (wpiCtx && sorted.length) {
    wardCharts.wpi = new Chart(wpiCtx, {
      type: 'bar',
      data: {
        labels: sorted.map(d => `${d.name}${d.number != null ? ' #' + d.number : ''}`),
        datasets: [{ label: 'WPI', data: sorted.map(d => d.scores?.wpi ?? 0), backgroundColor: sorted.map(d => getDpiColor(d.scores?.wpi ?? 0)), borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } }
    });
  }

  const pieCtx = document.getElementById('chart-ward-pie');
  if (pieCtx && list.length) {
    const byPerf = {};
    list.forEach(d => { byPerf[d.performance] = (byPerf[d.performance] || 0) + 1; });
    const pieData = Object.entries(byPerf).filter(([, v]) => v > 0);
    wardCharts.pie = new Chart(pieCtx, {
      type: 'doughnut',
      data: { labels: pieData.map(([k]) => k), datasets: [{ data: pieData.map(([, v]) => v), backgroundColor: ['#1d8102', '#0d9488', '#14b8a6', '#14b8a6', '#d13212'], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
    });
  }

  const resCtx = document.getElementById('chart-ward-resolution');
  if (resCtx && sorted.length) {
    wardCharts.resolution = new Chart(resCtx, {
      type: 'bar',
      data: {
        labels: sorted.map(d => d.name),
        datasets: [
          { label: 'Resolved', data: sorted.map(d => d.metrics?.resolved ?? 0), backgroundColor: '#1d8102', borderRadius: 4 },
          { label: 'Pending', data: sorted.map(d => d.metrics?.pending ?? 0), backgroundColor: '#14b8a6', borderRadius: 4 }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } }
    });
  }

  const workloadCtx = document.getElementById('chart-ward-workload');
  if (workloadCtx && list.length) {
    const byWorkload = [...list].sort((a, b) => (b.metrics?.total ?? 0) - (a.metrics?.total ?? 0)).slice(0, 12);
    wardCharts.workload = new Chart(workloadCtx, {
      type: 'bar',
      data: {
        labels: byWorkload.map(d => `${d.name}${d.number != null ? ' #' + d.number : ''}`),
        datasets: [{ label: 'Total', data: byWorkload.map(d => d.metrics?.total ?? 0), backgroundColor: '#0d9488', borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
    });
  }
}

function renderZoneCharts(data) {
  if (typeof Chart === 'undefined') return;
  const list = Array.isArray(data) ? data : [];
  const sorted = [...list].sort((a, b) => (b.scores?.zpi ?? 0) - (a.scores?.zpi ?? 0));

  Object.keys(zoneCharts).forEach(k => { if (zoneCharts[k]) { zoneCharts[k].destroy(); zoneCharts[k] = null; } });

  const zpiCtx = document.getElementById('chart-zone-zpi');
  if (zpiCtx && sorted.length) {
    zoneCharts.zpi = new Chart(zpiCtx, {
      type: 'bar',
      data: {
        labels: sorted.map(d => `${d.name}${d.code ? ' (' + d.code + ')' : ''}`),
        datasets: [{ label: 'ZPI', data: sorted.map(d => d.scores?.zpi ?? 0), backgroundColor: sorted.map(d => getDpiColor(d.scores?.zpi ?? 0)), borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } }
    });
  }

  const pieCtx = document.getElementById('chart-zone-pie');
  if (pieCtx && list.length) {
    const byPerf = {};
    list.forEach(d => { byPerf[d.performance] = (byPerf[d.performance] || 0) + 1; });
    const pieData = Object.entries(byPerf).filter(([, v]) => v > 0);
    zoneCharts.pie = new Chart(pieCtx, {
      type: 'doughnut',
      data: { labels: pieData.map(([k]) => k), datasets: [{ data: pieData.map(([, v]) => v), backgroundColor: ['#1d8102', '#0d9488', '#14b8a6', '#14b8a6', '#d13212'], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
    });
  }

  const resCtx = document.getElementById('chart-zone-resolution');
  if (resCtx && sorted.length) {
    zoneCharts.resolution = new Chart(resCtx, {
      type: 'bar',
      data: {
        labels: sorted.map(d => d.name),
        datasets: [
          { label: 'Resolved', data: sorted.map(d => d.metrics?.resolved ?? 0), backgroundColor: '#1d8102', borderRadius: 4 },
          { label: 'Pending', data: sorted.map(d => d.metrics?.pending ?? 0), backgroundColor: '#14b8a6', borderRadius: 4 }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } }
    });
  }

  const workloadCtx = document.getElementById('chart-zone-workload');
  if (workloadCtx && list.length) {
    const byWorkload = [...list].sort((a, b) => (b.metrics?.total ?? 0) - (a.metrics?.total ?? 0));
    zoneCharts.workload = new Chart(workloadCtx, {
      type: 'bar',
      data: {
        labels: byWorkload.map(d => `${d.name}${d.code ? ' (' + d.code + ')' : ''}`),
        datasets: [{ label: 'Total', data: byWorkload.map(d => d.metrics?.total ?? 0), backgroundColor: '#0d9488', borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
    });
  }
}

async function loadWorkerAnalytics() {
  const tbody = document.getElementById('worker-analytics-tbody');
  const emptyEl = document.getElementById('worker-analytics-empty');
  const tableWrap = document.querySelector('#analytics-workers-content .table-wrap');

  if (tbody) tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;"><div class="spinner"></div></td></tr>';
  if (emptyEl) emptyEl.classList.add('hidden');
  if (tableWrap) tableWrap.classList.remove('hidden');

  try {
    const deptId = document.getElementById('analytics-worker-dept')?.value || '';
    const wardId = document.getElementById('analytics-worker-ward')?.value || '';
    const period = parseInt(document.getElementById('analytics-worker-period')?.value || '30', 10);
    const toDate = new Date();
    const fromDate = new Date(toDate);
    fromDate.setDate(fromDate.getDate() - period);

    const params = new URLSearchParams();
    params.set('from_date', fromDate.toISOString().slice(0, 10));
    params.set('to_date', toDate.toISOString().slice(0, 10));
    if (deptId) params.set('department_id', deptId);
    if (wardId) params.set('ward_id', wardId);

    const data = await api('/analytics/workers?' + params.toString());
    lastWorkerAnalyticsData = Array.isArray(data) ? data : [];

    if (tbody) {
      renderWorkerAnalyticsTable();
      if (tableWrap) tableWrap.classList.remove('hidden');
      if (emptyEl) emptyEl.classList.add('hidden');
    }
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="10">Failed to load.</td></tr>';
    if (emptyEl) {
      emptyEl.textContent = e.status === 403 || e.status === 401 ? 'Login as admin/manager to view officer analytics.' : 'Failed to load officer analytics.';
      emptyEl.classList.remove('hidden');
    }
    if (tableWrap) tableWrap.classList.add('hidden');
    showToast(e.data?.detail || e.message || 'Failed to load officer analytics', 'error');
  }
}

function formatTime(iso) {
  if (!iso) return '–';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (_) {
    return iso;
  }
}

async function openWorkerDetailModal(workerId, workerName) {
  const modal = document.getElementById('modal-worker-analytics');
  const body = document.getElementById('modal-worker-analytics-body');
  if (!modal || !body) return;
  modal.classList.remove('hidden');
  body.innerHTML = '<div class="activity-empty">Loading…</div>';

  try {
    const period = parseInt(document.getElementById('analytics-worker-period')?.value || '30', 10);
    const toDate = new Date();
    const fromDate = new Date(toDate);
    fromDate.setDate(fromDate.getDate() - period);
    const params = new URLSearchParams();
    params.set('from_date', fromDate.toISOString().slice(0, 10));
    params.set('to_date', toDate.toISOString().slice(0, 10));
    const [data, escalResp, assignedResp, inprogResp] = await Promise.all([
      api(`/analytics/workers/${workerId}?` + params.toString()),
      api(`/grievances?worker_id=${workerId}&status=escalated&limit=50`),
      api(`/grievances?worker_id=${workerId}&status=assigned&limit=50`),
      api(`/grievances?worker_id=${workerId}&status=inprogress&limit=50`),
    ]);

    const m = data.metrics || {};
    const ts = data.time_series || [];
    const att = data.attendance || [];
    const ratingSeries = data.rating_series || [];
    const escalated = Array.isArray(escalResp?.items) ? escalResp.items : [];
    const assigned = Array.isArray(assignedResp?.items) ? assignedResp.items : [];
    const inProgress = Array.isArray(inprogResp?.items) ? inprogResp.items : [];
    const status = (data.status || 'offDuty').toLowerCase();
    const statusLabel = status === 'onduty' ? 'On duty' : 'Off duty';

    const slaPct = ((m.sla_rate ?? 1) * 100).toFixed(0);
    const attPct = ((m.attendance_rate ?? 0) * 100).toFixed(0);
    const daysWithActivity = ts.filter((d) => (d.resolved || 0) > 0).length;
    const daysWithRatings = ratingSeries.filter((r) => r.avg_rating != null).length;

    const parts = [escapeHtml(data.name || workerName)];
    if (data.department_name) parts.push(escapeHtml(data.department_name));
    if (data.ward_name) parts.push(escapeHtml(data.ward_name));
    const profileHtml = `
      <div class="worker-modal-header">
        <strong>${parts.join(' · ')}</strong>
        <span class="status-badge status-${status}">${statusLabel}</span>
        ${data.phone ? `<span class="worker-modal-phone">${escapeHtml(data.phone)}</span>` : ''}
        <div class="worker-modal-period">${data.period?.from || '–'} to ${data.period?.to || '–'} (${data.period?.days || 0} days)</div>
      </div>

      <div class="worker-modal-metrics">
        <div class="worker-modal-metric"><span class="val">${m.period_resolved ?? 0}</span><span class="lbl">Resolved</span></div>
        <div class="worker-modal-metric"><span class="val">${m.tasks_active ?? 0}</span><span class="lbl">Active</span></div>
        <div class="worker-modal-metric"><span class="val">${slaPct}%</span><span class="lbl">SLA</span></div>
        <div class="worker-modal-metric"><span class="val">${m.period_avg_rating != null ? m.period_avg_rating.toFixed(1) : '–'}</span><span class="lbl">Rating</span></div>
        <div class="worker-modal-metric"><span class="val">${attPct}%</span><span class="lbl">Attendance</span></div>
        <div class="worker-modal-metric"><span class="val">${m.avg_resolution_hours != null ? m.avg_resolution_hours + 'h' : '–'}</span><span class="lbl">Avg time</span></div>
        ${(m.reopen_count ?? 0) > 0 ? `<div class="worker-modal-metric warn"><span class="val">${m.reopen_count}</span><span class="lbl">Reopened</span></div>` : ''}
        ${(m.escalated_count ?? 0) > 0 ? `<div class="worker-modal-metric warn"><span class="val">${m.escalated_count}</span><span class="lbl">Escalated</span></div>` : ''}
      </div>`;

    const resolutionContent = ts.length ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Date</th><th class="text-center">Resolved</th></tr></thead>
          <tbody>
            ${ts.filter((d) => (d.resolved || 0) > 0).slice(-14).reverse().map((d) => `
              <tr><td>${d.date}</td><td class="text-center">${d.resolved}</td></tr>
            `).join('')}
          </tbody>
        </table>
      </div>` : '<div class="worker-modal-empty"><p>No resolution data in this period</p></div>';

    const attendanceContent = att.length ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Date</th><th>Clock In</th><th>Clock Out</th><th class="text-right">Duration</th></tr></thead>
          <tbody>
            ${att.slice(0, 20).map((a) => `
              <tr>
                <td>${a.date}</td>
                <td>${formatTime(a.clock_in)}</td>
                <td>${formatTime(a.clock_out)}</td>
                <td class="text-right">${a.duration_hours != null ? a.duration_hours + 'h' : '–'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        ${att.length > 20 ? `<p class="worker-modal-more">Showing 20 of ${att.length} records</p>` : ''}
      </div>` : '<div class="worker-modal-empty"><p>No attendance records in this period</p></div>';

    const ratingsContent = ratingSeries.some((r) => r.avg_rating != null) ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Date</th><th class="text-center">Avg</th><th class="text-center">Count</th></tr></thead>
          <tbody>
            ${ratingSeries.filter((r) => r.avg_rating != null).slice(-14).reverse().map((r) => `
              <tr><td>${r.date}</td><td class="text-center">${r.avg_rating.toFixed(1)}</td><td class="text-center">${r.count}</td></tr>
            `).join('')}
          </tbody>
        </table>
      </div>` : '<div class="worker-modal-empty"><p>No ratings in this period</p></div>';

    const grievanceTableRows = (list) => list.slice(0, 30).map((g) => {
      const proof = g.image_url || g.resolution_image_url || '';
      return `<tr>
        <td>${escapeHtml((g.title || '–').slice(0, 60))}${(g.title || '').length > 60 ? '…' : ''}</td>
        <td>${escapeHtml(g.ward_name || '–')}</td>
        <td>${escapeHtml(g.category_name || '–')}</td>
        <td><span class="status-badge status-${(g.priority || 'medium').toLowerCase()}">${escapeHtml((g.priority || 'medium').toLowerCase())}</span></td>
        <td>${formatDate(g.created_at)}</td>
        <td>${proof ? `<button type="button" class="btn btn-sm btn-proof" data-url="${escapeHtml(proof)}">View</button>` : '–'}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="6">None</td></tr>';

    const escalContent = escalated.length ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Title</th><th>Ward</th><th>Category</th><th>Priority</th><th>Created</th><th>View</th></tr></thead>
          <tbody>${grievanceTableRows(escalated)}</tbody>
        </table>
        ${escalated.length > 30 ? `<p class="worker-modal-more">Showing 30 of ${escalated.length}</p>` : ''}
      </div>` : '<div class="worker-modal-empty"><p>No escalated grievances</p></div>';

    const assignedContent = assigned.length ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Title</th><th>Ward</th><th>Category</th><th>Priority</th><th>Created</th><th>View</th></tr></thead>
          <tbody>${grievanceTableRows(assigned)}</tbody>
        </table>
        ${assigned.length > 30 ? `<p class="worker-modal-more">Showing 30 of ${assigned.length}</p>` : ''}
      </div>` : '<div class="worker-modal-empty"><p>No assigned grievances</p></div>';

    const inProgressContent = inProgress.length ? `
      <div class="worker-modal-table-card">
        <table class="data-table data-table-sm">
          <thead><tr><th>Title</th><th>Ward</th><th>Category</th><th>Priority</th><th>Created</th><th>View</th></tr></thead>
          <tbody>${grievanceTableRows(inProgress)}</tbody>
        </table>
        ${inProgress.length > 30 ? `<p class="worker-modal-more">Showing 30 of ${inProgress.length}</p>` : ''}
      </div>` : '<div class="worker-modal-empty"><p>No in-progress grievances</p></div>';

    const tabsHtml = `
      <div class="worker-modal-tabs">
        <div class="worker-modal-tab-bar">
          <button type="button" class="worker-modal-tab active" data-worker-tab="escalations">Escalations</button>
          <button type="button" class="worker-modal-tab" data-worker-tab="assigned">Assigned</button>
          <button type="button" class="worker-modal-tab" data-worker-tab="inprogress">In Progress</button>
          <button type="button" class="worker-modal-tab" data-worker-tab="resolution">Resolution</button>
          <button type="button" class="worker-modal-tab" data-worker-tab="attendance">Attendance</button>
          <button type="button" class="worker-modal-tab" data-worker-tab="ratings">Ratings</button>
        </div>
        <div class="worker-modal-tab-panels">
          <div id="worker-tab-escalations" class="worker-modal-panel active">${escalContent}</div>
          <div id="worker-tab-assigned" class="worker-modal-panel hidden">${assignedContent}</div>
          <div id="worker-tab-inprogress" class="worker-modal-panel hidden">${inProgressContent}</div>
          <div id="worker-tab-resolution" class="worker-modal-panel hidden">${resolutionContent}</div>
          <div id="worker-tab-attendance" class="worker-modal-panel hidden">${attendanceContent}</div>
          <div id="worker-tab-ratings" class="worker-modal-panel hidden">${ratingsContent}</div>
        </div>
      </div>`;

    body.innerHTML = `<div class="worker-modal">${profileHtml}${tabsHtml}</div>`;

    body.querySelectorAll('.worker-modal-tab[data-worker-tab]').forEach((tab) => {
      tab.addEventListener('click', () => {
        const key = tab.dataset.workerTab;
        body.querySelectorAll('.worker-modal-tab').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        body.querySelectorAll('.worker-modal-panel').forEach((c) => {
          c.classList.add('hidden');
          c.classList.remove('active');
        });
        const panel = document.getElementById(`worker-tab-${key}`);
        if (panel) {
          panel.classList.remove('hidden');
          panel.classList.add('active');
        }
      });
    });
    body.querySelectorAll('.btn-proof').forEach((btn) => {
      btn.addEventListener('click', () => {
        const url = btn.dataset.url;
        if (url) window.open(url, '_blank', 'noopener');
      });
    });
  } catch (err) {
    body.innerHTML = '<div class="activity-empty">Failed to load: ' + escapeHtml(err.message || 'Unknown error') + '</div>';
  }
}

function getWorkerSortValue(w, key) {
  const m = w.metrics || {};
  if (key === 'name' || key === 'phone' || key === 'department_name' || key === 'ward_name' || key === 'status') return String(w[key] ?? '').toLowerCase();
  if (key === 'period_resolved') return m.period_resolved ?? 0;
  if (key === 'sla_rate') return (m.sla_rate ?? 0) * 100;
  if (key === 'rating') return m.period_avg_rating ?? m.rating ?? 0;
  if (key === 'attendance_rate') return (m.attendance_rate ?? 0) * 100;
  return '';
}

function renderWorkerAnalyticsTable() {
  const tbody = document.getElementById('worker-analytics-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('analytics-worker-search')?.value || '');
  let list = !q ? [...lastWorkerAnalyticsData] : lastWorkerAnalyticsData.filter((w) => {
    const hay = `${w.name} ${w.phone || ''} ${w.department_name || ''} ${w.ward_name || ''} ${w.designation || ''} ${w.status || ''}`;
    return normalizeText(hay).includes(q);
  });
  const { key, dir } = analyticsWorkerSort;
  list.sort((a, b) => {
    const av = getWorkerSortValue(a, key);
    const bv = getWorkerSortValue(b, key);
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  });
  document.querySelectorAll('#worker-analytics-table thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === key) th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
  });
  const emptyMsg = lastWorkerAnalyticsData.length === 0 ? 'No officers found.' : 'No matching officers.';
  tbody.innerHTML = list.length ? list.map((w) => {
    const m = w.metrics || {};
    const slaPct = (m.sla_rate ?? 1) * 100;
    const attPct = (m.attendance_rate ?? 0) * 100;
    const rating = m.period_avg_rating ?? m.rating ?? '–';
    const status = (w.status || 'offDuty').toLowerCase();
    return `
    <tr>
      <td><strong>${escapeHtml(w.name)}</strong><br><small class="text-muted">${escapeHtml(w.designation || '')}</small></td>
      <td>${escapeHtml(w.phone || '–')}</td>
      <td>${escapeHtml(w.department_name || '–')}</td>
      <td>${escapeHtml(w.ward_name || '–')}</td>
      <td class="text-center">${m.period_resolved ?? 0}</td>
      <td class="text-center">${slaPct.toFixed(0)}%</td>
      <td class="text-center">${typeof rating === 'number' ? rating.toFixed(1) : rating}</td>
      <td class="text-center">${attPct.toFixed(0)}%</td>
      <td><span class="status-badge status-${status}">${status === 'onduty' ? 'On duty' : 'Off duty'}</span></td>
      <td><button type="button" class="btn btn-sm" data-worker-id="${escapeHtml(w.id)}" data-worker-name="${escapeHtml(w.name)}">View</button></td>
    </tr>`;
  }).join('') : `<tr><td colspan="10" class="activity-empty">${emptyMsg}</td></tr>`;
  tbody.querySelectorAll('[data-worker-id]').forEach((btn) => {
    btn.addEventListener('click', () => openWorkerDetailModal(btn.dataset.workerId, btn.dataset.workerName));
  });
}

document.getElementById('btn-refresh-worker-analytics')?.addEventListener('click', () => loadWorkerAnalytics());
document.getElementById('analytics-worker-dept')?.addEventListener('change', () => loadWorkerAnalytics());
document.getElementById('analytics-worker-ward')?.addEventListener('change', () => loadWorkerAnalytics());
document.getElementById('analytics-worker-period')?.addEventListener('change', () => loadWorkerAnalytics());
document.getElementById('analytics-worker-search')?.addEventListener('input', () => renderWorkerAnalyticsTable());

async function loadWardAnalytics() {
  const tbody = document.getElementById('ward-analytics-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="13" style="text-align:center;"><div class="spinner"></div></td></tr>';

  try {
    const zoneId = document.getElementById('analytics-ward-zone')?.value || '';
    const params = zoneId ? '?zone_id=' + encodeURIComponent(zoneId) : '';
    const data = await api('/analytics/wards' + params);

    lastWardAnalyticsData = Array.isArray(data) ? data : [];
    renderWardAnalyticsTable();
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="13">Failed to load ward analytics.</td></tr>';
    showToast(e.data?.detail || e.message || 'Failed to load ward analytics', 'error');
  }
}

function getWardSortValue(d, key) {
  const m = d.metrics || {};
  const s = d.scores || {};
  if (key === 'name') return `${(d.name || '').toLowerCase()} ${d.number ?? ''}`;
  if (key === 'zone_name') return String(d.zone_name ?? '').toLowerCase();
  if (key === 'rep_name') return String(d.representative_name ?? '').toLowerCase();
  if (key === 'rep_phone') return (Array.isArray(d.representative_phone) ? d.representative_phone.join('') : String(d.representative_phone ?? '')).toLowerCase();
  if (key === 'party_short_code') return String(d.party_short_code ?? '').toLowerCase();
  if (key === 'total') return m.total ?? 0;
  if (key === 'resolved') return m.resolved ?? 0;
  if (key === 'pending') return m.pending ?? 0;
  if (key === 'sla_resolved') return m.sla_resolved ?? 0;
  if (key === 'escalated') return m.escalated ?? 0;
  if (key === 'resolution_rate') return (s.resolution_rate ?? 0) * 100;
  if (key === 'wpi') return s.wpi ?? 0;
  if (key === 'performance') return String(d.performance ?? '').toLowerCase();
  return '';
}

function renderWardAnalyticsTable() {
  const tbody = document.getElementById('ward-analytics-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('analytics-ward-search')?.value || '');
  let list = !q ? [...lastWardAnalyticsData] : lastWardAnalyticsData.filter((d) => {
    const repPhone = Array.isArray(d.representative_phone) ? d.representative_phone.join(' ') : (d.representative_phone || '');
    const hay = `${d.name} ${d.number ?? ''} ${d.zone_name || ''} ${d.representative_name || ''} ${repPhone} ${d.party_short_code || ''} ${d.performance || ''}`;
    return normalizeText(hay).includes(q);
  });
  const { key, dir } = analyticsWardSort;
  list.sort((a, b) => {
    const av = getWardSortValue(a, key);
    const bv = getWardSortValue(b, key);
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  });
  document.querySelectorAll('#ward-analytics-table thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === key) th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
  });
  tbody.innerHTML = list.map((d) => {
    const repPhone = Array.isArray(d.representative_phone) ? d.representative_phone.join(', ') : (d.representative_phone || '–');
    return `
    <tr>
      <td><strong>${escapeHtml(d.name)}</strong> ${d.number != null ? `#${d.number}` : ''}</td>
      <td>${escapeHtml(d.zone_name || '–')}</td>
      <td>${escapeHtml(d.representative_name || '–')}</td>
      <td>${escapeHtml(repPhone)}</td>
      <td>${escapeHtml(d.party_short_code || '–')}</td>
      <td class="text-center">${d.metrics.total}</td>
      <td class="text-center">${d.metrics.resolved}</td>
      <td class="text-center">${d.metrics.pending}</td>
      <td class="text-center">${d.metrics.sla_resolved}</td>
      <td class="text-center">${d.metrics.escalated}</td>
      <td class="text-right">${(d.scores.resolution_rate * 100).toFixed(1)}%</td>
      <td class="text-center"><strong>${d.scores.wpi}</strong></td>
      <td class="text-center"><span class="perf-badge perf-${(d.performance || '').toLowerCase()}">${escapeHtml(d.performance || '')}</span></td>
    </tr>`;
  }).join('') || '<tr><td colspan="13">No matching wards.</td></tr>';
}

document.getElementById('btn-refresh-ward-analytics')?.addEventListener('click', () => loadWardAnalytics());
document.getElementById('analytics-ward-zone')?.addEventListener('change', () => loadWardAnalytics());
document.getElementById('analytics-ward-search')?.addEventListener('input', () => renderWardAnalyticsTable());

async function loadZoneAnalytics() {
  const tbody = document.getElementById('zone-analytics-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;"><div class="spinner"></div></td></tr>';

  try {
    const data = await api('/analytics/zones');
    lastZoneAnalyticsData = Array.isArray(data) ? data : [];
    renderZoneAnalyticsTable();
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="8">Failed to load zone analytics.</td></tr>';
    showToast(e.data?.detail || e.message || 'Failed to load zone analytics', 'error');
  }
}

function getZoneSortValue(d, key) {
  const m = d.metrics || {};
  const s = d.scores || {};
  if (key === 'name') return `${(d.name || '').toLowerCase()} ${d.code || ''}`;
  if (key === 'total') return m.total ?? 0;
  if (key === 'resolved') return m.resolved ?? 0;
  if (key === 'pending') return m.pending ?? 0;
  if (key === 'sla_resolved') return m.sla_resolved ?? 0;
  if (key === 'resolution_rate') return (s.resolution_rate ?? 0) * 100;
  if (key === 'zpi') return s.zpi ?? 0;
  if (key === 'performance') return String(d.performance ?? '').toLowerCase();
  return '';
}

function renderZoneAnalyticsTable() {
  const tbody = document.getElementById('zone-analytics-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('analytics-zone-search')?.value || '');
  let list = !q ? [...lastZoneAnalyticsData] : lastZoneAnalyticsData.filter((d) => {
    const hay = `${d.name} ${d.code || ''} ${d.performance || ''}`;
    return normalizeText(hay).includes(q);
  });
  const { key, dir } = analyticsZoneSort;
  list.sort((a, b) => {
    const av = getZoneSortValue(a, key);
    const bv = getZoneSortValue(b, key);
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  });
  document.querySelectorAll('#zone-analytics-table thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === key) th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
  });
  tbody.innerHTML = list.map((d) => `
    <tr>
      <td><strong>${escapeHtml(d.name)}</strong> ${d.code ? `(${escapeHtml(d.code)})` : ''}</td>
      <td class="text-center">${d.metrics.total}</td>
      <td class="text-center">${d.metrics.resolved}</td>
      <td class="text-center">${d.metrics.pending}</td>
      <td class="text-center">${d.metrics.sla_resolved}</td>
      <td class="text-right">${(d.scores.resolution_rate * 100).toFixed(1)}%</td>
      <td class="text-center"><strong>${d.scores.zpi}</strong></td>
      <td class="text-center"><span class="perf-badge perf-${(d.performance || '').toLowerCase()}">${escapeHtml(d.performance || '')}</span></td>
    </tr>
  `).join('') || '<tr><td colspan="8">No matching zones.</td></tr>';
}

async function loadSustainabilityAnalytics() {
  const tbody = document.getElementById('sustainability-analytics-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;"><div class="spinner"></div></td></tr>';
  try {
    const zoneId = document.getElementById('analytics-sustainability-zone')?.value || '';
    const wardId = document.getElementById('analytics-sustainability-ward')?.value || '';
    const params = new URLSearchParams();
    if (zoneId) params.set('zone_id', zoneId);
    if (wardId) params.set('ward_id', wardId);
    const qs = params.toString();
    const data = await api('/analytics/sustainability' + (qs ? '?' + qs : ''));
    lastSustainabilityAnalyticsData = Array.isArray(data?.rows) ? data.rows : [];
    const totals = data?.totals || {};
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(value ?? '–');
    };
    setText('sustainability-stat-departments', totals.departments ?? 0);
    setText('sustainability-stat-mapped', totals.mapped_departments ?? 0);
    setText('sustainability-stat-unmapped', totals.unmapped_departments ?? 0);
    setText('sustainability-stat-sdg-groups', totals.sdg_groups ?? 0);
    setText('sustainability-stat-avg-si', totals.average_sustainability_index != null ? Number(totals.average_sustainability_index).toFixed(1) : '–');
    renderSustainabilityAnalyticsTable();
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="6">Failed to load sustainability analytics.</td></tr>';
    showToast(e.data?.detail || e.message || 'Failed to load sustainability analytics', 'error');
  }
}

function getSustainabilitySortValue(r, key) {
  if (key === 'sdg') return String(r.sdg || '').toLowerCase();
  if (key === 'description') return String(r.description || '').toLowerCase();
  if (key === 'mapped_departments_text') return String(r.mapped_departments_text || '').toLowerCase();
  if (key === 'department_count') return Number(r.department_count || 0);
  if (key === 'sustainability_index') return Number(r.sustainability_index || 0);
  if (key === 'max_sustainability_index') return Number(r.max_sustainability_index || 0);
  return '';
}

function renderSustainabilityAnalyticsTable() {
  const tbody = document.getElementById('sustainability-analytics-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('analytics-sustainability-search')?.value || '');
  let list = !q ? [...lastSustainabilityAnalyticsData] : lastSustainabilityAnalyticsData.filter((r) => {
    const hay = `${r.sdg || ''} ${r.description || ''} ${r.mapped_departments_text || ''}`;
    return normalizeText(hay).includes(q);
  });
  const { key, dir } = analyticsSustainabilitySort;
  list.sort((a, b) => {
    const av = getSustainabilitySortValue(a, key);
    const bv = getSustainabilitySortValue(b, key);
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return dir === 'asc' ? cmp : -cmp;
  });
  document.querySelectorAll('#sustainability-analytics-table thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === key) th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
  });
  tbody.innerHTML = list.map((r) => `
    <tr>
      <td>${escapeHtml(r.sdg || 'Unmapped')}</td>
      <td>${escapeHtml(r.description || '–')}</td>
      <td>${escapeHtml(r.mapped_departments_text || '–')}</td>
      <td class="text-center"><strong>${Number(r.department_count || 0)}</strong></td>
      <td class="text-center"><strong>${Number(r.sustainability_index || 0).toFixed(2)}</strong></td>
      <td class="text-center"><strong>${Number(r.max_sustainability_index || 0).toFixed(2)}</strong></td>
    </tr>
  `).join('') || '<tr><td colspan="6">No matching records.</td></tr>';
}

document.getElementById('btn-refresh-zone-analytics')?.addEventListener('click', () => loadZoneAnalytics());
document.getElementById('analytics-zone-search')?.addEventListener('input', () => renderZoneAnalyticsTable());
document.getElementById('btn-refresh-sustainability-analytics')?.addEventListener('click', () => loadSustainabilityAnalytics());
document.getElementById('analytics-sustainability-search')?.addEventListener('input', () => renderSustainabilityAnalyticsTable());

function formatCisScore(v) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Number(v).toFixed(1);
}

async function loadCitizenCisAnalytics() {
  const topBody = document.getElementById('citizen-cis-top-tbody');
  const bottomBody = document.getElementById('citizen-cis-bottom-tbody');
  const weekNote = document.getElementById('citizen-cis-week-note');
  const loadingRow = (cols) => `<tr><td colspan="${cols}" style="text-align:center;"><div class="spinner"></div></td></tr>`;
  if (topBody) topBody.innerHTML = loadingRow(6);
  if (bottomBody) bottomBody.innerHTML = loadingRow(6);
  if (weekNote) {
    weekNote.textContent = '';
    weekNote.hidden = true;
  }

  try {
    const data = await api('/analytics/citizens/cis-leaderboard');
    const top = Array.isArray(data?.top) ? data.top : [];
    const bottom = Array.isArray(data?.bottom) ? data.bottom : [];
    if (weekNote) {
      const note = data?.week_note ? String(data.week_note) : '';
      weekNote.textContent = note;
      weekNote.hidden = !note;
    }
    const rowHtml = (rows, startIdx) =>
      rows
        .map((r, i) => {
          const name = escapeHtml(r.name || '—');
          const phone = escapeHtml(String(r.phone || '—'));
          const ward = escapeHtml(r.ward || '—');
          const zone = escapeHtml(r.zone || '—');
          const cis = formatCisScore(r.cis_score);
          return `<tr>
      <td class="text-center">${startIdx + i}</td>
      <td>${name}</td>
      <td>${phone}</td>
      <td>${ward}</td>
      <td>${zone}</td>
      <td class="text-right"><strong>${cis}</strong></td>
    </tr>`;
        })
        .join('') || '<tr><td colspan="6">No data.</td></tr>';

    if (topBody) topBody.innerHTML = rowHtml(top, 1);
    if (bottomBody) bottomBody.innerHTML = rowHtml(bottom, 1);
  } catch (e) {
    if (topBody) topBody.innerHTML = '<tr><td colspan="6">Failed to load CIS leaderboard.</td></tr>';
    if (bottomBody) bottomBody.innerHTML = '<tr><td colspan="6">Failed to load CIS leaderboard.</td></tr>';
    showToast(e.data?.detail || e.message || 'Failed to load CIS leaderboard', 'error');
  }
}

document.getElementById('btn-refresh-citizen-cis')?.addEventListener('click', () => loadCitizenCisAnalytics());
document.getElementById('btn-refresh-dept-analytics')?.addEventListener('click', () => loadDepartmentAnalytics());
document.getElementById('analytics-dept-search')?.addEventListener('input', () => renderDeptAnalyticsTable());

document.querySelectorAll('#dept-analytics-table thead th[data-sort]').forEach((th) => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (analyticsDeptSort.key === k) analyticsDeptSort.dir = analyticsDeptSort.dir === 'asc' ? 'desc' : 'asc';
    else analyticsDeptSort = { key: k, dir: 'asc' };
    renderDeptAnalyticsTable();
  });
});
document.querySelectorAll('#worker-analytics-table thead th[data-sort]').forEach((th) => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (analyticsWorkerSort.key === k) analyticsWorkerSort.dir = analyticsWorkerSort.dir === 'asc' ? 'desc' : 'asc';
    else analyticsWorkerSort = { key: k, dir: 'asc' };
    renderWorkerAnalyticsTable();
  });
});
document.querySelectorAll('#ward-analytics-table thead th[data-sort]').forEach((th) => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (analyticsWardSort.key === k) analyticsWardSort.dir = analyticsWardSort.dir === 'asc' ? 'desc' : 'asc';
    else analyticsWardSort = { key: k, dir: 'asc' };
    renderWardAnalyticsTable();
  });
});
document.querySelectorAll('#zone-analytics-table thead th[data-sort]').forEach((th) => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (analyticsZoneSort.key === k) analyticsZoneSort.dir = analyticsZoneSort.dir === 'asc' ? 'desc' : 'asc';
    else analyticsZoneSort = { key: k, dir: 'asc' };
    renderZoneAnalyticsTable();
  });
});
document.querySelectorAll('#sustainability-analytics-table thead th[data-sort]').forEach((th) => {
  th.style.cursor = 'pointer';
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (analyticsSustainabilitySort.key === k) analyticsSustainabilitySort.dir = analyticsSustainabilitySort.dir === 'asc' ? 'desc' : 'asc';
    else analyticsSustainabilitySort = { key: k, dir: 'asc' };
    renderSustainabilityAnalyticsTable();
  });
});
document.getElementById('analytics-dept-zone')?.addEventListener('change', async () => {
  const [zones, wards] = await Promise.all([api('/zones').catch(() => []), api('/wards').catch(() => [])]);
  syncDeptAnalyticsWardOptions(zones, wards);
  loadDepartmentAnalytics();
});
document.getElementById('analytics-sustainability-zone')?.addEventListener('change', async () => {
  const zoneId = document.getElementById('analytics-sustainability-zone')?.value || '';
  const wardSel = document.getElementById('analytics-sustainability-ward');
  const wards = await api('/wards').catch(() => []);
  if (wardSel) {
    const selectedWard = wardSel.value;
    const filteredWards = (Array.isArray(wards) ? wards : []).filter((w) => !zoneId || String(w.zone_id) === String(zoneId));
    wardSel.innerHTML = '<option value="">All wards</option>';
    filteredWards.forEach((w) => wardSel.appendChild(new Option(`${w.name} (#${w.number})`, w.id)));
    if (selectedWard && filteredWards.some((w) => String(w.id) === String(selectedWard))) wardSel.value = selectedWard;
  }
  loadSustainabilityAnalytics();
});
document.getElementById('analytics-sustainability-ward')?.addEventListener('change', () => loadSustainabilityAnalytics());

// Modal close for worker analytics
document.querySelector('#modal-worker-analytics .modal-backdrop')?.addEventListener('click', () => {
  document.getElementById('modal-worker-analytics')?.classList.add('hidden');
});
document.querySelector('#modal-worker-analytics .modal-close')?.addEventListener('click', () => {
  document.getElementById('modal-worker-analytics')?.classList.add('hidden');
});

async function downloadAnalyticsPdfReport() {
  if (!getToken()) return showToast('Please log in', 'error');
  const downloadBtn = document.getElementById('btn-analytics-pdf-download');
  const emailBtn = document.getElementById('btn-analytics-email-report');
  const restoreDownloadText = downloadBtn?.textContent || 'Download PDF report';
  if (downloadBtn) {
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Preparing PDF...';
  }
  if (emailBtn) emailBtn.disabled = true;
  const params = getAnalyticsReportParams();
  const url = `${API_BASE}/analytics/performance-report.pdf?${params.toString()}`;
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    const res = await fetch(url, { headers });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `civiccare-analytics-report-${new Date().toISOString().slice(0, 10)}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
    showToast('PDF downloaded', 'success');
  } catch (e) {
    showToast(e.message || 'Download failed', 'error');
  } finally {
    if (downloadBtn) {
      downloadBtn.disabled = false;
      downloadBtn.textContent = restoreDownloadText;
    }
    if (emailBtn) emailBtn.disabled = false;
  }
}

function getAnalyticsReportParams() {
  const deptZone = document.getElementById('analytics-dept-zone')?.value || '';
  const deptWard = document.getElementById('analytics-dept-ward')?.value || '';
  const wardZone = document.getElementById('analytics-ward-zone')?.value || '';
  const workerDept = document.getElementById('analytics-worker-dept')?.value || '';
  const workerWard = document.getElementById('analytics-worker-ward')?.value || '';
  const period = parseInt(document.getElementById('analytics-worker-period')?.value || '30', 10);
  const toDate = new Date();
  const fromDate = new Date(toDate);
  fromDate.setDate(fromDate.getDate() - period);

  const params = new URLSearchParams();
  if (deptZone) params.set('dept_zone_id', deptZone);
  if (deptWard) params.set('dept_ward_id', deptWard);
  if (wardZone) params.set('ward_zone_id', wardZone);
  if (workerDept) params.set('department_id', workerDept);
  if (workerWard) params.set('worker_ward_id', workerWard);
  params.set('from_date', fromDate.toISOString().slice(0, 10));
  params.set('to_date', toDate.toISOString().slice(0, 10));
  return params;
}

async function emailAnalyticsPdfReport() {
  if (!getToken()) return showToast('Please log in', 'error');
  const emailBtn = document.getElementById('btn-analytics-email-report');
  const downloadBtn = document.getElementById('btn-analytics-pdf-download');
  const restoreEmailText = emailBtn?.textContent || 'Email Reports';
  if (emailBtn) {
    emailBtn.disabled = true;
    emailBtn.textContent = 'Sending email...';
  }
  if (downloadBtn) downloadBtn.disabled = true;
  const params = getAnalyticsReportParams();
  try {
    const data = await api(`/analytics/performance-report/email?${params.toString()}`, { method: 'POST' });
    showToast(`Report emailed to ${data?.sent_to || 'admin email'}`, 'success');
    if (emailBtn) emailBtn.textContent = 'Sent';
    setTimeout(() => {
      if (emailBtn) emailBtn.textContent = restoreEmailText;
    }, 1500);
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Email report failed', 'error');
  } finally {
    if (emailBtn) emailBtn.disabled = false;
    if (downloadBtn) downloadBtn.disabled = false;
    if (emailBtn && emailBtn.textContent !== 'Sent') {
      emailBtn.textContent = restoreEmailText;
    }
  }
}

document.getElementById('btn-analytics-pdf-download')?.addEventListener('click', () => downloadAnalyticsPdfReport());
document.getElementById('btn-analytics-email-report')?.addEventListener('click', () => emailAnalyticsPdfReport());

// Sub-tab switching for analytics
document.querySelectorAll('#page-analytics .tab[data-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    const t = tab.dataset.tab;
    document.querySelectorAll('#page-analytics .tab').forEach((x) => x.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('#page-analytics .tab-content').forEach((c) => {
        c.classList.add('hidden');
        c.classList.remove('active');
    });
    const target = document.getElementById(`${t}-content`);
    if (target) {
        target.classList.remove('hidden');
        target.classList.add('active');
    }
    if (t === 'analytics-dept') loadDepartmentAnalytics();
    if (t === 'analytics-workers') loadWorkerAnalytics();
    if (t === 'analytics-wards') loadWardAnalytics();
    if (t === 'analytics-zones') loadZoneAnalytics();
    if (t === 'analytics-citizens') loadCitizenCisAnalytics();
    if (t === 'analytics-sustainability') loadSustainabilityAnalytics();
  });
});

function syncPriorityAnalyticsWardOptions(zoneList, wardList) {
  const zSel = document.getElementById('analytics-priority-zone');
  const wSel = document.getElementById('analytics-priority-ward');
  if (!zSel || !wSel) return;
  
  const selectedZone = zSel.value;
  const selectedWard = wSel.value;
  
  // Fill zones
  zSel.innerHTML = '<option value="">All zones</option>';
  zoneList.forEach(z => {
    zSel.innerHTML += `<option value="${z.id}" ${z.id === selectedZone ? 'selected' : ''}>${escapeHtml(z.name)}</option>`;
  });
  
  // Fill wards
  wSel.innerHTML = '<option value="">All wards</option>';
  wardList.filter(w => !selectedZone || w.zone_id === selectedZone).forEach(w => {
    wSel.innerHTML += `<option value="${w.id}" ${w.id === selectedWard ? 'selected' : ''}>${escapeHtml(w.name)}</option>`;
  });
}

document.getElementById('btn-refresh-priority-analytics')?.addEventListener('click', () => loadPriorityAnalytics());

document.getElementById('analytics-priority-zone')?.addEventListener('change', async () => {
  const [zones, wards] = await Promise.all([api('/zones').catch(() => []), api('/wards').catch(() => [])]);
  syncPriorityAnalyticsWardOptions(zones, wards);
  loadPriorityAnalytics();
});

document.getElementById('analytics-priority-ward')?.addEventListener('change', () => loadPriorityAnalytics());

// Inject priority into initial load if needed
(async function() {
  try {
     const [zones, wards] = await Promise.all([api('/zones').catch(() => []), api('/wards').catch(() => [])]);
     syncPriorityAnalyticsWardOptions(zones, wards);
  } catch(e) {}
})();

// ---------------------------------------------------------------------------
// Grievance Detail Modal Logic
// ---------------------------------------------------------------------------

async function openGrievanceDetailModal(id) {
  if (!id) return;
  
  const modal = document.getElementById('modal-grievance-detail');
  if (!modal) return;
  
  modal.classList.remove('hidden');
  // Clear previous state or show loading
  document.getElementById('det-title').textContent = 'Loading...';
  document.getElementById('det-grievance-id').textContent = '#...';
  
  try {
    const g = await api(`/grievances/${id}`);
    renderGrievanceDetail(g);
  } catch (err) {
    showToast('Failed to load grievance details: ' + err.message, 'error');
    modal.classList.add('hidden');
  }
}

function renderGrievanceDetail(g) {
  document.getElementById('det-grievance-id').textContent = '#' + g.id.slice(0, 8);
  document.getElementById('det-title').textContent = escapeHtml(g.title || 'Untitled');
  document.getElementById('det-description').textContent = g.description || 'No description provided.';
  document.getElementById('det-ward').textContent = escapeHtml(g.ward_name || '–');
  document.getElementById('det-category').textContent = escapeHtml(g.category_name || '–');
  document.getElementById('det-dept').textContent = escapeHtml(g.department_name || '–');
  document.getElementById('det-created').textContent = formatDate(g.created_at);
  
  // Status & Priority Pills
  const statusPill = document.getElementById('det-status-pill');
  statusPill.textContent = escapeHtml(g.status || 'Pending');
  statusPill.className = 'status-pill status-' + (g.status || 'pending').toLowerCase();
  
  const priPill = document.getElementById('det-priority-pill');
  priPill.textContent = escapeHtml(g.priority || 'Medium');
  priPill.className = 'priority-pill priority-' + (g.priority || 'medium').toLowerCase();
  
  // EPS Section
  const epsSection = document.getElementById('det-eps-section');
  if (g.eps_score != null || g.eps) {
    epsSection.classList.remove('hidden');
    const score = g.eps_score || (g.eps ? g.eps.total : 0);
    const level = getEpsLevel(score);
    document.getElementById('det-eps-total').textContent = Math.round(score);
    document.getElementById('det-eps-total').className = 'eps-score-text ' + level.class;
    
    const levelBadge = document.getElementById('det-eps-level');
    levelBadge.textContent = level.label;
    levelBadge.className = 'eps-level-pill level-' + level.class;
    
    // Mini breakdown
    const breakdown = document.getElementById('det-eps-breakdown');
    if (g.eps) {
      breakdown.innerHTML = `
        <div class="eps-breakdown-row"><small>Age</small> ${renderEpsBreakdownBar({escalation_age: g.eps.escalation_age})}</div>
        <div class="eps-breakdown-row"><small>Reopen</small> ${renderEpsBreakdownBar({reopen_frequency: g.eps.reopen_frequency})}</div>
        <div class="eps-breakdown-row"><small>Votes</small> ${renderEpsBreakdownBar({net_votes_impact: g.eps.net_votes_impact})}</div>
        <div class="eps-breakdown-row"><small>Severity</small> ${renderEpsBreakdownBar({severity_level: g.eps.severity_level})}</div>
      `;
    } else {
      breakdown.innerHTML = '';
    }
  } else {
    epsSection.classList.add('hidden');
  }
  
  // Media Gallery
  const gallery = document.getElementById('det-media-gallery');
  gallery.innerHTML = '';
  if (g.media && g.media.length > 0) {
    g.media.forEach(m => {
      const container = document.createElement('div');
      container.className = 'det-media-item';
      if (m.type === 'video') {
        container.innerHTML = `<video src="${m.url}" preload="metadata"></video>`;
      } else {
        container.innerHTML = `<img src="${m.url}" alt="Attachment" />`;
      }
      container.onclick = () => window.open(m.url, '_blank');
      gallery.appendChild(container);
    });
  } else {
    gallery.innerHTML = '<div class="activity-empty">No media attached.</div>';
  }
  
  // Comments & Events (Audit Trail)
  const timelineContainer = document.getElementById('det-comments');
  timelineContainer.innerHTML = '';
  
  const comments = (g.comments || []).map(c => ({ ...c, type: 'comment' }));
  const events = (g.events || []).map(e => ({ ...e, type: 'event' }));
  const timeline = [...comments, ...events].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  
  if (timeline.length > 0) {
    timeline.forEach(item => {
      if (item.type === 'comment') {
        timelineContainer.innerHTML += `
          <div class="det-comment-card">
            <div class="det-comment-header">
              <span class="det-comment-author">${escapeHtml(item.user_name || 'User')}</span>
              <span class="det-comment-date">${formatDate(item.created_at)}</span>
            </div>
            <div class="det-comment-body">${escapeHtml(item.text)}</div>
          </div>
        `;
      } else {
        timelineContainer.innerHTML += `
          <div class="det-event-card">
            <div class="det-event-header">
              <span class="det-event-title">${escapeHtml(item.title)}</span>
              <span class="det-comment-date">${formatDate(item.created_at)}</span>
            </div>
            ${item.description ? `<div class="det-event-body">${escapeHtml(item.description)}</div>` : ''}
            <div class="det-comment-header" style="margin-top: 4px; border-top: none; padding-top: 0; opacity: 0.7;">
              <small>By ${escapeHtml(item.actor_name || 'System')}</small>
            </div>
          </div>
        `;
      }
    });
  } else {
    timelineContainer.innerHTML = '<div class="activity-empty">No comments or activity logs.</div>';
  }
  
  // Bind Update Status button
  const upBtn = document.querySelector('.btn-update-status-from-det');
  if (upBtn) {
    upBtn.onclick = () => {
      // modal.classList.add('hidden'); // Optional: hide this one?
      openStatusModal(g.id, g.priority, g.status);
    };
  }
}

document.querySelector('#modal-grievance-detail .modal-backdrop')?.addEventListener('click', () => {
  document.getElementById('modal-grievance-detail').classList.add('hidden');
});

document.querySelector('#modal-grievance-detail .modal-close')?.addEventListener('click', () => {
  document.getElementById('modal-grievance-detail').classList.add('hidden');
});

// ---------------------------------------------------------------------------
// AI Chat Assistant Logic
// ---------------------------------------------------------------------------

const aiChatInput = document.getElementById('ai-chat-input');
const aiChatSend = document.getElementById('ai-chat-send');
const aiChatBody = document.getElementById('ai-chat-body');

let isAiChatStreaming = false;
let aiTypingQueue = [];
let isAiTyping = false;
let currentAiText = '';
let currentAiBubbleId = null;

function processAiTypingQueue() {
  if (aiTypingQueue.length === 0) {
    isAiTyping = false;
    return;
  }
  isAiTyping = true;
  
  // Take one token from the queue
  const token = aiTypingQueue.shift();
  currentAiText += token;
  
  const bubble = document.getElementById(currentAiBubbleId);
  if (bubble) {
    bubble.innerHTML = parseAiMarkdown(currentAiText);
    aiChatBody.scrollTop = aiChatBody.scrollHeight;
  }
  
  // Fast typing effect: 15ms delay per token chunk
  setTimeout(processAiTypingQueue, 15);
}

if (aiChatInput && aiChatSend) {
  aiChatInput.addEventListener('input', () => {
    aiChatInput.style.height = 'auto';
    aiChatInput.style.height = Math.min(aiChatInput.scrollHeight, 200) + 'px';
    aiChatSend.disabled = !aiChatInput.value.trim() || isAiChatStreaming;
  });

  aiChatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!aiChatSend.disabled) {
        sendAiChatMessage();
      }
    }
  });

  aiChatSend.addEventListener('click', () => {
    if (!aiChatSend.disabled) {
      sendAiChatMessage();
    }
  });
}

function appendAiMessage(text, type, id = null) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `ai-message ai-message-${type}`;
  if (id) msgDiv.id = id;
  
  if (type === 'system') {
    // Basic Markdown parser for streaming
    msgDiv.innerHTML = parseAiMarkdown(text);
  } else {
    msgDiv.textContent = text;
  }
  
  aiChatBody.appendChild(msgDiv);
  aiChatBody.scrollTop = aiChatBody.scrollHeight;
  return msgDiv;
}

function parseAiMarkdown(text) {
  if (typeof marked !== 'undefined') {
    // Normal parse
    let html = marked.parse(text || '', {
      breaks: true,
      gfm: true,
      silent: true
    });
    
    // Post-process to wrap tables in scrollable container
    // We can use a simple regex replacing <table> with the wrapper
    html = html.replace(/<table/g, '<div class="ai-table-container"><table');
    html = html.replace(/<\/table>/g, '</table></div>');
    
    return html;
  }
  // Fallback if marked didn't load
  let html = escapeHtml(text || '');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/`(.*?)`/g, '<code>$1</code>');
  html = html.replace(/\n/g, '<br/>');
  return html;
}

async function sendAiChatMessage() {
  if (isAiChatStreaming) return;
  const text = aiChatInput.value.trim();
  if (!text) return;

  aiChatInput.value = '';
  aiChatInput.style.height = 'auto';
  aiChatSend.disabled = true;
  isAiChatStreaming = true;

  appendAiMessage(text, 'user');

  const statusId = 'ai-status-' + Date.now();
  appendAiMessage('Connecting to AI...', 'status', statusId);
  
  const responseId = 'ai-response-' + Date.now();
  currentAiBubbleId = responseId;
  currentAiText = '';
  aiTypingQueue = [];
  
  const responseBubble = appendAiMessage('', 'system', responseId);
  responseBubble.style.display = 'none';

  try {
    const token = getToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message: text })
    });

    if (!res.ok) throw new Error('Failed to connect to AI');

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let statusBubble = document.getElementById(statusId);
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split(/\n+/);
      buffer = parts.pop(); // Keep incomplete chunk in buffer

      for (const ev of parts) {
        if (!ev.trim()) continue;
        try {
          const data = JSON.parse(ev);
          if (data.type === 'status') {
            if (statusBubble) statusBubble.textContent = data.content;
          } else if (data.type === 'token') {
            if (statusBubble) {
              statusBubble.remove();
              statusBubble = null;
            }
            responseBubble.style.display = 'block';
            aiTypingQueue.push(data.content);
            if (!isAiTyping) processAiTypingQueue();
          } else if (data.type === 'error') {
            if (statusBubble) statusBubble.remove();
            appendAiMessage('Error: ' + data.content, 'status');
          } else if (data.type === 'done') {
             // completion inside stream loop
          }
        } catch (err) {
          console.error('SSE parse error', err, ev);
        }
      }
    }
  } catch (err) {
    appendAiMessage('Error: ' + err.message, 'status');
  } finally {
    isAiChatStreaming = false;
    aiChatSend.disabled = !aiChatInput.value.trim();
    const finalStatus = document.getElementById(statusId);
    if (finalStatus) finalStatus.remove();
  }
}

