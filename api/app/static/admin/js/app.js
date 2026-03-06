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
// Navigation
// ---------------------------------------------------------------------------

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    const page = item.dataset.page;
    document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
    const target = document.getElementById(`page-${page}`);
    if (target) target.classList.add('active');
    const titles = {
      dashboard: 'Global Overview',
      map: 'Map View',
      grievances: 'Grievances',
      'ward-performance': 'Ward Performance',
      departments: 'Departments',
      wards: 'Wards & Zones',
      workers: 'Officer Management',
      logs: 'System Logs',
    };
    document.getElementById('page-title').textContent = titles[page] || 'Admin';
    if (page === 'dashboard') loadDashboard();
    if (page === 'map') initCommandCenter();
    if (page === 'grievances') {
      populateGrievanceFilters();
      loadGrievances();
    }
    if (page === 'ward-performance') loadWardPerformance();
    if (page === 'departments') {
      loadDepartments();
      loadCategories();
    }
    if (page === 'wards') {
      populateWardZoneFilter();
      loadWardsAndZones();
    }
    if (page === 'workers') {
      workersSkip = 0;
      populateWorkerFilters();
      loadWorkers();
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
  if (token && user) {
    loginForm.classList.add('hidden');
    userInfo.classList.remove('hidden');
    userName.textContent = user.name || user.phone || 'Admin';
  } else {
    loginForm.classList.remove('hidden');
    userInfo.classList.add('hidden');
  }
}

document.getElementById('btn-login').addEventListener('click', async () => {
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

document.getElementById('btn-logout').addEventListener('click', () => {
  clearAuth();
  renderAuth();
  showToast('Logged out');
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function loadDashboard() {
  try {
    const [gResp, dResp, wResp, wardsResp, pendingResp, resolvedResp, assignedResp, inprogressResp, recentResp] = await Promise.all([
      api('/grievances?limit=1'),
      api('/departments'),
      api('/workers?limit=1'),
      api('/wards'),
      api('/grievances?status=pending&limit=1'),
      api('/grievances?status=resolved&limit=1'),
      api('/grievances?status=assigned&limit=1'),
      api('/grievances?status=inprogress&limit=1'),
      api('/grievances?limit=8'),
    ]);
    const total = gResp?.total ?? 0;
    const pending   = pendingResp?.total    ?? 0;
    const resolved  = resolvedResp?.total   ?? 0;
    const assigned  = assignedResp?.total   ?? 0;
    const inprogress= inprogressResp?.total ?? 0;

    document.getElementById('stat-grievances').textContent  = total;
    document.getElementById('stat-pending').textContent     = pending;
    document.getElementById('stat-resolved').textContent    = resolved;
    document.getElementById('stat-assigned').textContent    = assigned;
    document.getElementById('stat-inprogress').textContent  = inprogress;
    document.getElementById('stat-departments').textContent = (dResp && dResp.length) || 0;
    document.getElementById('stat-workers').textContent     = wResp?.total ?? 0;
    document.getElementById('stat-wards').textContent       = (wardsResp && wardsResp.length) || 0;

    // Recent activity feed
    const recentEl = document.getElementById('recent-grievances-list');
    if (recentEl) {
      const items = recentResp?.items || [];
      if (!items.length) {
        recentEl.innerHTML = '<div class="activity-empty">No grievances yet.</div>';
      } else {
        recentEl.innerHTML = items.map((g) => `
          <div class="activity-item">
            <div class="activity-title">${escapeHtml(g.title || '–')}</div>
            <div class="activity-badge">
              <span class="status-badge status-${(g.status || '').toLowerCase()}">${escapeHtml(g.status || '')}</span>
            </div>
            <div class="activity-meta">${escapeHtml(g.ward_name || 'No ward')} · ${formatDate(g.created_at)}</div>
            <div class="activity-meta priority-${(g.priority || 'medium').toLowerCase()}">${escapeHtml(g.priority || '')}</div>
          </div>
        `).join('');
      }
    }

    // Status breakdown bars
    const bdEl = document.getElementById('status-breakdown');
    if (bdEl && total > 0) {
      const statuses = [
        { label: 'Pending',    count: pending,    color: '#f59e0b' },
        { label: 'Assigned',   count: assigned,   color: '#3b82f6' },
        { label: 'In Progress',count: inprogress, color: '#8b5cf6' },
        { label: 'Resolved',   count: resolved,   color: '#16a34a' },
      ];
      bdEl.innerHTML = statuses.map(({ label, count, color }) => {
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        return `
          <div class="breakdown-row">
            <span class="breakdown-label">${escapeHtml(label)}</span>
            <div class="breakdown-bar-bg">
              <div class="breakdown-bar-fill" style="width:${pct}%;background:${color};"></div>
            </div>
            <span class="breakdown-count">${count}</span>
          </div>
        `;
      }).join('');
    }
  } catch (e) {
    ['stat-grievances','stat-pending','stat-resolved','stat-assigned','stat-inprogress','stat-departments','stat-workers','stat-wards']
      .forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = '–'; });
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

// ---------------------------------------------------------------------------
// Ward Performance Ranking
// ---------------------------------------------------------------------------

async function fetchAllGrievancesForPerf() {
  const limit = 100;
  let skip = 0;
  let out = [];
  while (true) {
    const resp = await api(`/grievances?skip=${skip}&limit=${limit}`);
    const items = resp?.items ?? [];
    out = out.concat(items);
    if (items.length < limit) break;
    skip += limit;
    if (skip >= 5000) break;
  }
  return out;
}

function loadWardPerformance() {
  const tbody = document.getElementById('ward-perf-tbody');
  const noteEl = document.getElementById('ward-perf-note');
  if (tbody) tbody.innerHTML = '<tr><td colspan="8"><span class="spinner"></span> Loading…</td></tr>';
  if (noteEl) noteEl.textContent = '';

  (async () => {
    try {
      const [grievances, wards, zones] = await Promise.all([
        fetchAllGrievancesForPerf(),
        api('/wards').catch(() => []),
        api('/zones').catch(() => []),
      ]);
      const wardList = Array.isArray(wards) ? wards : [];
      const zoneList = Array.isArray(zones) ? zones : [];
      const zoneById = Object.fromEntries(zoneList.map((z) => [z.id, z]));

      const zoneSel = document.getElementById('perf-zone-filter');
      if (zoneSel && zoneList.length > 0) {
        const current = zoneSel.value;
        zoneSel.innerHTML = '<option value="">All zones</option>';
        zoneList.forEach((z) => zoneSel.appendChild(new Option(z.name, z.id)));
        if (current) zoneSel.value = current;
      }

      const byWard = {};
      wardList.forEach((w) => {
        byWard[w.id] = {
          ward_id: w.id,
          name: w.name,
          number: w.number,
          zone_id: w.zone_id,
          zone_name: (zoneById[w.zone_id] && zoneById[w.zone_id].name) || w.zone_name || '–',
          total: 0,
          pending: 0,
          assigned: 0,
          inprogress: 0,
          resolved: 0,
        };
      });

      grievances.forEach((g) => {
        const wid = g.ward_id || `_${(g.ward_name || '').trim()}_${g.ward_number ?? ''}`;
        if (!byWard[wid]) {
          byWard[wid] = {
            ward_id: g.ward_id,
            name: g.ward_name || 'Unknown',
            number: g.ward_number,
            zone_id: null,
            zone_name: '–',
            total: 0,
            pending: 0,
            assigned: 0,
            inprogress: 0,
            resolved: 0,
          };
        }
        const row = byWard[wid];
        row.total += 1;
        const st = (g.status || '').toLowerCase();
        if (st === 'pending') row.pending += 1;
        else if (st === 'assigned') row.assigned += 1;
        else if (st === 'inprogress') row.inprogress += 1;
        else if (st === 'resolved') row.resolved += 1;
      });

      let rows = Object.values(byWard);
      const zoneFilter = document.getElementById('perf-zone-filter')?.value || '';
      if (zoneFilter) {
        rows = rows.filter((r) => String(r.zone_id) === String(zoneFilter));
      }

      const sortBy = document.getElementById('perf-sort')?.value || 'resolution_desc';
      rows.sort((a, b) => {
        const rateA = a.total > 0 ? (a.resolved / a.total) * 100 : 0;
        const rateB = b.total > 0 ? (b.resolved / b.total) * 100 : 0;
        const openA = a.pending + a.assigned + a.inprogress;
        const openB = b.pending + b.assigned + b.inprogress;
        switch (sortBy) {
          case 'resolution_asc':
            return rateA - rateB || b.resolved - a.resolved;
          case 'resolved_desc':
            return b.resolved - a.resolved || rateB - rateA;
          case 'open_desc':
            return openB - openA || rateA - rateB;
          case 'total_desc':
            return b.total - a.total || rateB - rateA;
          default:
            return rateB - rateA || b.resolved - a.resolved;
        }
      });

      const wardLabel = (r) => (r.number != null ? `#${r.number} ${r.name || ''}` : (r.name || '–').trim());
      tbody.innerHTML = rows
        .map((r, i) => {
          const pct = r.total > 0 ? Math.round((r.resolved / r.total) * 100) : 0;
          const openCount = r.pending + r.assigned + r.inprogress;
          const pctClass = pct >= 75 ? 'perf-good' : pct >= 50 ? 'perf-mid' : pct > 0 ? 'perf-low' : 'perf-zero';
          return `
        <tr>
          <td><strong>${i + 1}</strong></td>
          <td>${escapeHtml(wardLabel(r))}</td>
          <td>${escapeHtml(r.zone_name)}</td>
          <td>${r.total}</td>
          <td>${r.resolved}</td>
          <td>${r.pending}</td>
          <td>${r.assigned + r.inprogress}</td>
          <td><span class="perf-pct ${pctClass}">${pct}%</span></td>
        </tr>`;
        })
        .join('') || '<tr><td colspan="8">No wards to display.</td></tr>';

      if (noteEl) {
        noteEl.textContent = `Ranking based on ${grievances.length} grievance(s) across ${rows.length} ward(s).`;
      }
    } catch (e) {
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8">Failed to load performance data.</td></tr>';
      }
      if (noteEl) noteEl.textContent = '';
      showToast(e.data?.detail || e.message || 'Failed to load ward performance', 'error');
    }
  })();
}

document.getElementById('btn-refresh-perf')?.addEventListener('click', () => loadWardPerformance());
document.getElementById('perf-zone-filter')?.addEventListener('change', () => loadWardPerformance());
document.getElementById('perf-sort')?.addEventListener('change', () => loadWardPerformance());

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
      <td>${escapeHtml(g.reporter_name || '–')}</td>
      <td>${formatDate(g.created_at)}</td>
      <td>
        <button type="button" class="btn btn-sm btn-update-status" data-id="${g.id}" data-priority="${(g.priority || 'medium').toLowerCase()}">Status</button>
        <button type="button" class="btn btn-sm btn-assign-worker" data-id="${g.id}">Assign</button>
      </td>
    </tr>
  `;
      }
    )
    .join('');

  tbody.querySelectorAll('.btn-update-status').forEach((btn) => {
    btn.addEventListener('click', () => openStatusModal(btn.dataset.id, btn.dataset.priority));
  });
  tbody.querySelectorAll('.btn-assign-worker').forEach((btn) => {
    btn.addEventListener('click', () => openAssignWorkerModal(btn.dataset.id));
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

function openStatusModal(grievanceId, priority) {
  const token = getToken();
  if (!token) {
    showToast('Please log in to update status', 'error');
    return;
  }
  document.getElementById('modal-grievance-id').value = grievanceId;
  const priSelect = document.getElementById('modal-priority-select');
  if (priSelect && (priority || 'medium')) priSelect.value = (priority || 'medium').toLowerCase();
  document.getElementById('modal-status').classList.remove('hidden');
}

function closeStatusModal() {
  document.getElementById('modal-status').classList.add('hidden');
}

document.querySelector('.modal-backdrop').addEventListener('click', closeStatusModal);
document.querySelector('.modal-close').addEventListener('click', closeStatusModal);

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
    loadDashboard();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

function openAssignWorkerModal(grievanceId) {
  if (!getToken()) {
    showToast('Please log in to assign workers', 'error');
    return;
  }
  document.getElementById('modal-assign-grievance-id').value = grievanceId;
  const sel = document.getElementById('modal-assign-worker-select');
  sel.innerHTML = '<option value="">Loading…</option>';
  document.getElementById('modal-assign-worker').classList.remove('hidden');
  api('/workers?limit=500')
    .then((data) => {
      const list = data?.items ?? (Array.isArray(data) ? data : []);
      sel.innerHTML = '<option value="">Select worker</option>';
      list.forEach((w) => sel.appendChild(new Option(`${w.name} (${w.designation})`, w.id)));
    })
    .catch(() => {
      sel.innerHTML = '<option value="">Failed to load workers</option>';
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
    showToast('Select a worker', 'error');
    return;
  }
  try {
    await api(`/grievances/${grievanceId}/assign`, {
      method: 'POST',
      body: JSON.stringify({ worker_id: workerId }),
    });
    closeAssignWorkerModal();
    showToast('Worker assigned', 'success');
    loadGrievances();
    loadDashboard();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Assign failed', 'error');
  }
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

async function loadDepartments() {
  try {
    const data = await api('/departments');
    const list = Array.isArray(data) ? data : [];
    const tbody = document.getElementById('departments-tbody');
    tbody.innerHTML = list
      .map(
        (d) => `
      <tr data-id="${d.id}">
        <td>${escapeHtml(d.name)}</td>
        <td>${escapeHtml(d.short_code)}</td>
        <td>${escapeHtml(d.jurisdiction_label)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-edit-dept" data-id="${d.id}">Edit</button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-dept" data-id="${d.id}">Delete</button>
        </td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="4">No departments</td></tr>';
    tbody.querySelectorAll('.btn-edit-dept').forEach((btn) => btn.addEventListener('click', () => openEditDepartment(btn.dataset.id)));
    tbody.querySelectorAll('.btn-delete-dept').forEach((btn) => btn.addEventListener('click', () => deleteDepartment(btn.dataset.id)));
  } catch (e) {
    document.getElementById('departments-tbody').innerHTML =
      '<tr><td colspan="4">Failed to load departments.</td></tr>';
  }
}

async function loadCategories() {
  try {
    const data = await api('/categories');
    const list = Array.isArray(data) ? data : [];
    const tbody = document.getElementById('categories-tbody');
    tbody.innerHTML = list
      .map(
        (c) => `
      <tr data-id="${c.id}">
        <td>${escapeHtml(c.name)}</td>
        <td>${escapeHtml(c.dept_name)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-edit-cat" data-id="${c.id}">Edit</button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-cat" data-id="${c.id}">Delete</button>
        </td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="3">No grievance categories</td></tr>';
    tbody.querySelectorAll('.btn-edit-cat').forEach((btn) => btn.addEventListener('click', () => openEditCategory(btn.dataset.id)));
    tbody.querySelectorAll('.btn-delete-cat').forEach((btn) => btn.addEventListener('click', () => deleteCategory(btn.dataset.id)));
  } catch (e) {
    const tbody = document.getElementById('categories-tbody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="3">Failed to load categories.</td></tr>';
  }
}

// ---------------------------------------------------------------------------
// Wards & Zones
// ---------------------------------------------------------------------------

async function populateWardZoneFilter() {
  const sel = document.getElementById('filter-ward-zone');
  if (!sel) return;
  try {
    const list = await api('/zones');
    sel.innerHTML = '<option value="">All zones</option>';
    (Array.isArray(list) ? list : []).forEach((z) => sel.appendChild(new Option(z.name, z.id)));
  } catch (_) {}
}

document.getElementById('filter-ward-zone')?.addEventListener('change', loadWardsAndZones);

document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    const t = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('wards-table-wrap').classList.toggle('hidden', t !== 'wards');
    document.getElementById('zones-table-wrap').classList.toggle('hidden', t !== 'zones');
    document.getElementById('wards-toolbar').classList.toggle('hidden', t !== 'wards');
    document.getElementById('add-zone-section').classList.add('hidden');
    document.getElementById('add-ward-section').classList.add('hidden');
    document.getElementById('btn-add-zone').classList.toggle('hidden', t !== 'zones');
    document.getElementById('btn-add-ward').classList.toggle('hidden', t !== 'wards');
    if (t === 'zones') loadZones();
    if (t === 'wards') loadWardsAndZones();
  });
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

document.getElementById('btn-add-zone').addEventListener('click', () => showAddSection('add-zone-section'));
document.getElementById('btn-add-ward').addEventListener('click', () => {
  populateZoneDropdown('add-ward-zone');
  showAddSection('add-ward-section');
});
document.getElementById('btn-add-worker').addEventListener('click', () => {
  populateDepartmentDropdown('add-worker-department');
  populateZoneDropdown('add-worker-zone');
  populateWardDropdown('add-worker-ward');
  showAddSection('add-worker-section');
});
document.getElementById('btn-add-department').addEventListener('click', () => showAddSection('add-department-section'));
document.getElementById('btn-add-category').addEventListener('click', () => {
  populateDepartmentDropdown('add-category-department', 'Select department');
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

async function loadWardsAndZones() {
  const zoneFilter = document.getElementById('filter-ward-zone');
  const zoneId = (zoneFilter && zoneFilter.value) || '';
  try {
    const path = zoneId ? `/wards?zone_id=${encodeURIComponent(zoneId)}` : '/wards';
    const wards = await api(path);
    const list = Array.isArray(wards) ? wards : [];
    const tbody = document.getElementById('wards-tbody');
    tbody.innerHTML = list
      .map(
        (w) => `
      <tr data-id="${w.id}">
        <td>${escapeHtml(w.name)}</td>
        <td>${w.number != null ? w.number : '–'}</td>
        <td>${escapeHtml(w.zone_name)}</td>
        <td>${escapeHtml(w.representative_name)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-edit-ward" data-id="${w.id}">Edit</button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-ward" data-id="${w.id}">Delete</button>
        </td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="5">No wards</td></tr>';
    tbody.querySelectorAll('.btn-edit-ward').forEach((btn) => btn.addEventListener('click', () => openEditWard(btn.dataset.id)));
    tbody.querySelectorAll('.btn-delete-ward').forEach((btn) => btn.addEventListener('click', () => deleteWard(btn.dataset.id)));
  } catch (e) {
    document.getElementById('wards-tbody').innerHTML =
      '<tr><td colspan="5">Failed to load wards.</td></tr>';
  }
}

async function loadZones() {
  try {
    const data = await api('/zones');
    const list = Array.isArray(data) ? data : [];
    const tbody = document.getElementById('zones-tbody');
    tbody.innerHTML = list
      .map(
        (z) => `
      <tr data-id="${z.id}">
        <td>${escapeHtml(z.name)}</td>
        <td>${escapeHtml(z.code)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-edit-zone" data-id="${z.id}">Edit</button>
          <button type="button" class="btn btn-sm btn-danger btn-delete-zone" data-id="${z.id}">Delete</button>
        </td>
      </tr>
    `
      )
      .join('') || '<tr><td colspan="3">No zones</td></tr>';
    tbody.querySelectorAll('.btn-edit-zone').forEach((btn) => btn.addEventListener('click', () => openEditZone(btn.dataset.id)));
    tbody.querySelectorAll('.btn-delete-zone').forEach((btn) => btn.addEventListener('click', () => deleteZone(btn.dataset.id)));
  } catch (e) {
    document.getElementById('zones-tbody').innerHTML =
      '<tr><td colspan="3">Failed to load zones.</td></tr>';
  }
}

document.getElementById('form-add-zone').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create zones', 'error');
    return;
  }
  const form = e.target;
  const name = form.name.value.trim();
  const code = form.code.value.trim();
  if (!name || !code) return;
  try {
    await api('/zones', { method: 'POST', body: JSON.stringify({ name, code }) });
    showToast('Zone created', 'success');
    form.reset();
    document.getElementById('add-zone-section').classList.add('hidden');
    loadZones();
    loadWardsAndZones();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

document.getElementById('form-add-ward').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create wards', 'error');
    return;
  }
  const form = e.target;
  const zone_id = form.zone_id.value;
  const name = form.name.value.trim();
  const number = parseInt(form.number.value, 10);
  const representative_name = form.representative_name.value.trim() || null;
  if (!zone_id || !name || !number) return;
  try {
    await api('/wards', {
      method: 'POST',
      body: JSON.stringify({ zone_id, name, number, representative_name }),
    });
    showToast('Ward created', 'success');
    form.reset();
    document.getElementById('add-ward-section').classList.add('hidden');
    loadWardsAndZones();
  } catch (err) {
    showToast(err.data?.detail || err.message || 'Failed', 'error');
  }
});

document.getElementById('form-add-worker').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!getToken()) {
    showToast('Please log in to create workers', 'error');
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
    showToast('Worker created', 'success');
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
  const body = {
    name: form.name.value.trim(),
    short_code: form.short_code.value.trim(),
    primary_color: form.primary_color.value.trim() || '#1976D2',
    icon: form.icon.value.trim() || 'assignment',
    manager_title: form.manager_title.value.trim() || 'Manager',
    assistant_title: form.assistant_title.value.trim() || 'Assistant',
    jurisdiction_label: form.jurisdiction_label.value.trim() || 'Ward',
  };
  if (!body.name || !body.short_code) return;
  try {
    await api('/departments', { method: 'POST', body: JSON.stringify(body) });
    showToast('Department created', 'success');
    form.reset();
    document.getElementById('add-department-section').classList.add('hidden');
    loadDepartments();
    loadCategories();
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
  const dept_id = form.dept_id.value;
  const name = form.name.value.trim();
  if (!dept_id || !name) return;
  try {
    await api(`/departments/${dept_id}/categories`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    showToast('Grievance category created', 'success');
    form.reset();
    document.getElementById('add-category-section').classList.add('hidden');
    loadCategories();
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
document.querySelectorAll('#modal-edit-zone .modal-backdrop, #modal-edit-ward .modal-backdrop, #modal-edit-department .modal-backdrop, #modal-edit-category .modal-backdrop, #modal-edit-worker .modal-backdrop').forEach((el) => {
  el.addEventListener('click', () => {
    const modal = el.closest('.modal');
    if (modal) modal.classList.add('hidden');
  });
});

async function openEditZone(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  try {
    const z = await api(`/zones/${id}`);
    document.getElementById('edit-zone-id').value = z.id;
    document.getElementById('edit-zone-name').value = z.name || '';
    document.getElementById('edit-zone-code').value = z.code || '';
    document.getElementById('modal-edit-zone').classList.remove('hidden');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load zone', 'error');
  }
}

document.getElementById('btn-save-zone').addEventListener('click', async () => {
  const id = document.getElementById('edit-zone-id').value;
  const name = document.getElementById('edit-zone-name').value.trim();
  const code = document.getElementById('edit-zone-code').value.trim();
  if (!id || !name || !code) return showToast('Name and code required', 'error');
  try {
    await api(`/zones/${id}`, { method: 'PATCH', body: JSON.stringify({ name, code }) });
    document.getElementById('modal-edit-zone').classList.add('hidden');
    showToast('Zone updated', 'success');
    loadZones();
    loadWardsAndZones();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteZone(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this zone? It will fail if it has wards.')) return;
  try {
    await api(`/zones/${id}`, { method: 'DELETE' });
    showToast('Zone deleted', 'success');
    loadZones();
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
    await populateZoneDropdown('edit-ward-zone', true);
    const zoneSel = document.getElementById('edit-ward-zone');
    if (w.zone_id) zoneSel.value = w.zone_id;
    document.getElementById('edit-ward-id').value = w.id;
    document.getElementById('edit-ward-name').value = w.name || '';
    document.getElementById('edit-ward-number').value = w.number != null ? w.number : '';
    document.getElementById('edit-ward-rep').value = w.representative_name || '';
    document.getElementById('modal-edit-ward').classList.remove('hidden');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load ward', 'error');
  }
}

document.getElementById('btn-save-ward').addEventListener('click', async () => {
  const id = document.getElementById('edit-ward-id').value;
  const zone_id = document.getElementById('edit-ward-zone').value;
  const name = document.getElementById('edit-ward-name').value.trim();
  const number = parseInt(document.getElementById('edit-ward-number').value, 10);
  const representative_name = document.getElementById('edit-ward-rep').value.trim() || null;
  if (!id || !zone_id || !name || !number) return showToast('Zone, name and number required', 'error');
  try {
    await api(`/wards/${id}`, { method: 'PATCH', body: JSON.stringify({ zone_id, name, number, representative_name }) });
    document.getElementById('modal-edit-ward').classList.add('hidden');
    showToast('Ward updated', 'success');
    loadWardsAndZones();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteWard(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this ward? Grievances/workers will have ward cleared.')) return;
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
    document.getElementById('edit-dept-id').value = d.id;
    document.getElementById('edit-dept-name').value = d.name || '';
    document.getElementById('edit-dept-short-code').value = d.short_code || '';
    document.getElementById('edit-dept-color').value = d.primary_color || '#1976D2';
    document.getElementById('edit-dept-icon').value = d.icon || 'assignment';
    document.getElementById('edit-dept-manager-title').value = d.manager_title || 'Manager';
    document.getElementById('edit-dept-assistant-title').value = d.assistant_title || 'Assistant';
    document.getElementById('edit-dept-jurisdiction').value = d.jurisdiction_label || 'Ward';
    document.getElementById('modal-edit-department').classList.remove('hidden');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load department', 'error');
  }
}

document.getElementById('btn-save-department').addEventListener('click', async () => {
  const id = document.getElementById('edit-dept-id').value;
  const name = document.getElementById('edit-dept-name').value.trim();
  const short_code = document.getElementById('edit-dept-short-code').value.trim();
  const primary_color = document.getElementById('edit-dept-color').value.trim() || null;
  const icon = document.getElementById('edit-dept-icon').value.trim() || null;
  const manager_title = document.getElementById('edit-dept-manager-title').value.trim() || null;
  const assistant_title = document.getElementById('edit-dept-assistant-title').value.trim() || null;
  const jurisdiction_label = document.getElementById('edit-dept-jurisdiction').value.trim() || null;
  if (!id || !name || !short_code) return showToast('Name and short code required', 'error');
  const body = { name, short_code };
  if (primary_color) body.primary_color = primary_color;
  if (icon) body.icon = icon;
  if (manager_title) body.manager_title = manager_title;
  if (assistant_title) body.assistant_title = assistant_title;
  if (jurisdiction_label) body.jurisdiction_label = jurisdiction_label;
  try {
    await api(`/departments/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    document.getElementById('modal-edit-department').classList.add('hidden');
    showToast('Department updated', 'success');
    loadDepartments();
    loadCategories();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteDepartment(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this department? It will fail if it has categories or workers.')) return;
  try {
    await api(`/departments/${id}`, { method: 'DELETE' });
    showToast('Department deleted', 'success');
    loadDepartments();
    loadCategories();
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
    document.getElementById('edit-cat-id').value = c.id;
    document.getElementById('edit-cat-name').value = c.name || '';
    document.getElementById('modal-edit-category').classList.remove('hidden');
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Failed to load category', 'error');
  }
}

document.getElementById('btn-save-category').addEventListener('click', async () => {
  const id = document.getElementById('edit-cat-id').value;
  const name = document.getElementById('edit-cat-name').value.trim();
  if (!id || !name) return showToast('Name required', 'error');
  try {
    await api(`/categories/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) });
    document.getElementById('modal-edit-category').classList.add('hidden');
    showToast('Category updated', 'success');
    loadCategories();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteCategory(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this category? Grievances will have category cleared.')) return;
  try {
    await api(`/categories/${id}`, { method: 'DELETE' });
    showToast('Category deleted', 'success');
    loadCategories();
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
    showToast(e.data?.detail || e.message || 'Failed to load worker', 'error');
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
    showToast('Worker updated', 'success');
    loadWorkers();
  } catch (e) {
    showToast(e.data?.detail || e.message || 'Update failed', 'error');
  }
});

async function deleteWorker(id) {
  if (!getToken()) return showToast('Please log in', 'error');
  if (!confirm('Delete this worker? This cannot be undone.')) return;
  try {
    await api(`/workers/${id}`, { method: 'DELETE' });
    showToast('Worker deleted', 'success');
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
      .join('') || '<tr><td colspan="9">No workers</td></tr>';
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
      '<tr><td colspan="9">Failed to load workers.</td></tr>';
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
let commandGridSort = { key: 'created_at', dir: 'desc' };

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

function createStatusMarker(status) {
  const s = normalizeText(status);
  const color = s === 'resolved' ? '#16a34a' : (s === 'assigned' || s === 'inprogress' ? '#f59e0b' : '#dc2626');
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
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(commandMap);
  }
  // Wait for the browser to finish layout before invalidating size,
  // so the heatmap canvas is never 0-height when it renders.
  await new Promise((resolve) => setTimeout(() => { commandMap.invalidateSize(); resolve(); }, 80));
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
  if (!wSel) return;
  const selected = wSel.value;
  const list = zoneId
    ? commandWards.filter((w) => String(w.zone_id) === String(zoneId))
    : commandWards;
  wSel.innerHTML = '<option value="">All wards</option>';
  list.forEach((w) => wSel.appendChild(new Option(getWardLabel(w), w.id)));
  if (selected && list.some((w) => String(w.id) === String(selected))) {
    wSel.value = selected;
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

function renderWardBoundaries() {
  if (!commandMap || !commandGeoJson) return;
  if (wardGeoJsonLayer) commandMap.removeLayer(wardGeoJsonLayer);
  wardGeoJsonLayer = L.geoJSON(commandGeoJson, {
    style: {
      color: '#0f766e',
      weight: 1,
      fillOpacity: 0.03,
    },
    onEachFeature: (feature, layer) => {
      const props = feature.properties || {};
      const wardName = getWardFeatureName(props) || 'Unknown ward';
      const wardNo = getWardFeatureNumber(props);
      const label = wardNo ? `#${wardNo} ${wardName}` : wardName;
      layer.bindTooltip(label);
      layer.on('click', () => {
        updateWardInfoCardByFeature(feature);
        commandMap.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 14 });
      });
    },
  }).addTo(commandMap);
}

function wardInfoRow(label, value) {
  return `<div class="ward-info-row"><span class="ward-info-label">${escapeHtml(label)}</span><span>${escapeHtml(String(value ?? 'N/A'))}</span></div>`;
}

async function updateWardInfoCardByFeature(feature) {
  const props = feature?.properties || {};
  const name = getWardFeatureName(props);
  const number = getWardFeatureNumber(props);
  const ward = commandWards.find((w) => normalizeText(w.name) === normalizeText(name) || String(w.number) === String(number));
  const councillor = ward?.representative_name || props.councillor || props.COUNCILLOR || 'N/A';
  const party = props.party || props.PARTY || 'N/A';
  const population = props.population || props.POPULATION || 'N/A';
  const box = document.getElementById('ward-info-content');
  if (!box) return;
  box.innerHTML = [
    wardInfoRow('Ward', name || ward?.name || 'Unknown'),
    wardInfoRow('Ward No', number || String(ward?.number || 'N/A')),
    wardInfoRow('Zone', ward?.zone_name || 'N/A'),
    wardInfoRow('Councillor', councillor),
    wardInfoRow('Party', party),
    wardInfoRow('Population', population),
  ].join('');

  // Fetch live grievance counts for this ward
  if (ward?.id) {
    try {
      const [open, closed] = await Promise.all([
        api(`/grievances?ward_id=${ward.id}&status=pending&limit=1`).catch(() => null),
        api(`/grievances?ward_id=${ward.id}&status=resolved&limit=1`).catch(() => null),
      ]);
      box.innerHTML += `<div class="ward-grievance-counts">
        <div class="wgc-title">Live Grievances</div>
        ${wardInfoRow('Open (pending)', open?.total ?? '–')}
        ${wardInfoRow('Resolved', closed?.total ?? '–')}
      </div>`;
    } catch (_) {}
  }
}

async function fetchAllGrievancesForCommand() {
  const status = document.getElementById('cc-status-filter')?.value || '';
  const wardId = document.getElementById('cc-ward-filter')?.value || '';
  const zoneId = document.getElementById('cc-zone-filter')?.value || '';
  const dateFrom = document.getElementById('cc-date-from')?.value || '';
  const dateTo = document.getElementById('cc-date-to')?.value || '';

  const limit = 100;
  let skip = 0;
  let done = false;
  let out = [];
  while (!done && skip < 5000) {
    let q = `/grievances?skip=${skip}&limit=${limit}`;
    if (status) q += `&status=${encodeURIComponent(status)}`;
    if (wardId) q += `&ward_id=${encodeURIComponent(wardId)}`;
    const resp = await api(q);
    const items = Array.isArray(resp?.items) ? resp.items : [];
    out = out.concat(items);
    if (items.length < limit) done = true;
    skip += limit;
  }

  if (zoneId && !wardId) {
    const names = new Set(
      commandWards
        .filter((w) => String(w.zone_id) === String(zoneId))
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
  // Guard: leaflet-heat throws "source height is 0" when the map container
  // hasn't been laid out yet. Bail out and let refreshCommandCenter retry.
  const mapEl = document.getElementById('command-map');
  if (!mapEl || mapEl.offsetHeight === 0) return;

  if (grievanceClusterLayer) { commandMap.removeLayer(grievanceClusterLayer); grievanceClusterLayer = null; }
  if (grievanceHeatLayer)    { commandMap.removeLayer(grievanceHeatLayer);    grievanceHeatLayer    = null; }

  const heatPts = [];
  grievanceClusterLayer = L.markerClusterGroup({ disableClusteringAtZoom: 16, maxClusterRadius: 50 });

  let plotted = 0;
  items.forEach((g) => {
    const lat = Number(g.lat);
    const lng = Number(g.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat === 0 || lng === 0) return;
    plotted++;

    // Marker with rich popup
    const st = (g.status || 'pending').toLowerCase();
    const marker = L.marker([lat, lng], { icon: createStatusMarker(st) });
    marker.bindPopup(
      `<div style="min-width:180px;font-size:13px">` +
      `<strong style="display:block;margin-bottom:4px">${escapeHtml(g.title || 'Grievance')}</strong>` +
      `<div><b>Status:</b> <span style="text-transform:capitalize">${escapeHtml(st)}</span></div>` +
      `<div><b>Ward:</b> ${escapeHtml(g.ward_name || 'N/A')}</div>` +
      `<div><b>Category:</b> ${escapeHtml(g.category_name || 'N/A')}</div>` +
      `<div><b>Officer:</b> ${escapeHtml(g.assigned_to_name || 'Unassigned')}</div>` +
      `<div style="color:#64748b;font-size:11px;margin-top:4px">${formatDate(g.created_at)}</div>` +
      `</div>`
    );
    grievanceClusterLayer.addLayer(marker);

    // Heatmap weight: pending = hottest, resolved = coolest
    const w = st === 'pending' ? 1.0 : (st === 'assigned' || st === 'inprogress') ? 0.65 : 0.25;
    heatPts.push([lat, lng, w]);
  });

  // Heatmap is ALWAYS rendered (mandatory layer)
  if (heatPts.length > 0) {
    grievanceHeatLayer = L.heatLayer(heatPts, {
      radius: 28,
      blur: 22,
      maxZoom: 17,
      gradient: { 0.2: '#ffffb2', 0.45: '#fecc5c', 0.65: '#fd8d3c', 0.85: '#f03b20', 1.0: '#bd0026' },
    });
    grievanceHeatLayer.addTo(commandMap);
  }

  // Markers shown when "Show Markers" toggle is checked (default: checked)
  const showMarkers = document.getElementById('cc-heatmap-toggle')?.checked !== false;
  if (showMarkers && plotted > 0) {
    grievanceClusterLayer.addTo(commandMap);
  }

  // Update map subtitle with counts
  const counts = { pending: 0, assigned: 0, inprogress: 0, resolved: 0 };
  items.forEach((g) => {
    const st = (g.status || 'pending').toLowerCase();
    if (st in counts) counts[st]++;
  });
  const subtitleEl = document.getElementById('map-stat-bar');
  if (subtitleEl) {
    subtitleEl.innerHTML =
      `<span class="mstat mstat-pending">${counts.pending} Pending</span>` +
      `<span class="mstat mstat-assigned">${counts.assigned} Assigned</span>` +
      `<span class="mstat mstat-inprogress">${counts.inprogress} In Progress</span>` +
      `<span class="mstat mstat-resolved">${counts.resolved} Resolved</span>` +
      `<span class="mstat mstat-total">${plotted} plotted on map</span>`;
  }
}

function renderCommandGrid() {
  const tbody = document.getElementById('cc-grid-tbody');
  if (!tbody) return;
  const q = normalizeText(document.getElementById('cc-grid-search')?.value || '');
  let list = !q ? [...commandCenterData] : commandCenterData.filter((g) => {
    const hay = `${g.title} ${g.ward_name} ${g.category_name} ${g.assigned_to_name} ${g.status}`;
    return normalizeText(hay).includes(q);
  });
  if (commandGridSort?.key) {
    const { key, dir } = commandGridSort;
    list.sort((a, b) => {
      const av = normalizeText(String(a[key] ?? ''));
      const bv = normalizeText(String(b[key] ?? ''));
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    });
  }
  // Update sort indicators on headers
  document.querySelectorAll('#cc-grid thead th[data-sort]').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === commandGridSort.key) {
      th.classList.add(commandGridSort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
  tbody.innerHTML = list.map((g) => {
    const proof = g.image_url || g.resolution_image_url || '';
    const wardCell = g.ward_number != null
      ? `#${g.ward_number} ${escapeHtml(g.ward_name || '')}`
      : escapeHtml(g.ward_name || '–');
    return `
      <tr>
        <td title="${escapeHtml(String(g.id || ''))}">
          <span style="font-size:0.82rem;color:var(--secondary)">${escapeHtml(String(g.id || '').slice(0, 8))}…</span>
          <div style="font-weight:500">${escapeHtml(g.title || '–')}</div>
        </td>
        <td>${wardCell}</td>
        <td>${escapeHtml(g.category_name || '–')}</td>
        <td>${escapeHtml(g.assigned_to_name || 'Unassigned')}</td>
        <td><span class="status-badge status-${(g.status || '').toLowerCase()}">${escapeHtml(g.status || '–')}</span></td>
        <td>
          ${proof ? `<button type="button" class="btn btn-sm btn-proof" data-url="${escapeHtml(proof)}">View Proof</button>` : '–'}
        </td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="6">No records</td></tr>';
  tbody.querySelectorAll('.btn-proof').forEach((btn) => {
    btn.addEventListener('click', () => {
      const url = btn.dataset.url;
      if (url) window.open(url, '_blank', 'noopener');
    });
  });
}

async function refreshCommandCenter() {
  await ensureCommandMap();
  if (!commandMap) return;
  setMapLoading(true);
  try {
    commandGeoJson = await fetchCommandGeoJson();
    renderWardBoundaries();
    commandCenterData = await fetchAllGrievancesForCommand();
    renderCommandMapData(commandCenterData);
    renderCommandGrid();
    const wardId = document.getElementById('cc-ward-filter')?.value || '';
    if (wardId) {
      const ward = commandWards.find((w) => String(w.id) === String(wardId));
      const feature = findWardFeature(ward);
      if (feature) {
        const temp = L.geoJSON(feature);
        commandMap.fitBounds(temp.getBounds(), { padding: [20, 20], maxZoom: 14 });
        await updateWardInfoCardByFeature(feature);
      }
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
  const table = document.getElementById('cc-grid')?.outerHTML || '<p>No data</p>';
  win.document.write(`<html><head><title>Command Export</title></head><body><h2>CivicCare Command Export</h2>${table}</body></html>`);
  win.document.close();
  win.focus();
  win.print();
}

let logsAllRows = [];
let logsPage = 0;
const LOGS_PAGE_SIZE = 50;

async function loadSystemLogs() {
  const tbody = document.getElementById('system-logs-tbody');
  if (!tbody) return;
  logsPage = 0;
  tbody.innerHTML = '<tr><td colspan="5"><span class="spinner"></span> Loading logs…</td></tr>';
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
        const text = `${ev.title || ''} ${ev.note || ''}`;
        const geoBad = /outside|10\s?-?\s?meter|10m|geofence/i.test(text);
        logsAllRows.push({
          when: ev.created_at || d.updated_at || d.created_at,
          grievance: d.title || String(d.id).slice(0, 8),
          ward: d.ward_name || '–',
          event: ev.title || ev.note || 'Update',
          geofence: geoBad ? 'Potential violation' : 'OK',
          isBad: geoBad,
        });
      });
    });
    logsAllRows.sort((a, b) => new Date(b.when) - new Date(a.when));
    renderSystemLogs();
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="5">Failed to load logs.</td></tr>';
  }
}

function renderSystemLogs() {
  const tbody = document.getElementById('system-logs-tbody');
  const searchQ = normalizeText(document.getElementById('logs-search')?.value || '');
  const dateFrom = document.getElementById('logs-date-from')?.value || '';
  const dateTo   = document.getElementById('logs-date-to')?.value   || '';
  const geoFilter= document.getElementById('logs-geo-filter')?.value || '';

  let rows = logsAllRows.filter((r) => {
    if (searchQ && !normalizeText(r.grievance).includes(searchQ) && !normalizeText(r.event).includes(searchQ)) return false;
    if (dateFrom && new Date(r.when) < new Date(`${dateFrom}T00:00:00`)) return false;
    if (dateTo   && new Date(r.when) > new Date(`${dateTo}T23:59:59`))   return false;
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
      <td class="${r.isBad ? 'geo-flag-bad' : 'geo-flag-good'}">${r.isBad ? '⚠ ' : ''}${escapeHtml(r.geofence)}</td>
    </tr>
  `).join('') || '<tr><td colspan="5">No matching events.</td></tr>';

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
    refreshCommandCenter();
  });
  // Ward/status/date changes → full refresh (re-fetch data)
  const ids = ['cc-ward-filter', 'cc-status-filter', 'cc-date-from', 'cc-date-to'];
  ids.forEach((id) => document.getElementById(id)?.addEventListener('change', refreshCommandCenter));

  // Marker toggle → just re-render layers without re-fetching
  document.getElementById('cc-heatmap-toggle')?.addEventListener('change', () => {
    if (commandCenterData.length > 0) renderCommandMapData(commandCenterData);
  });
  document.getElementById('btn-cc-refresh')?.addEventListener('click', refreshCommandCenter);
  document.getElementById('cc-grid-search')?.addEventListener('input', renderCommandGrid);
  document.querySelectorAll('#cc-grid thead th[data-sort]').forEach((th) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (commandGridSort.key === key) {
        commandGridSort.dir = commandGridSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        commandGridSort = { key, dir: 'asc' };
      }
      renderCommandGrid();
    });
  });
  document.getElementById('btn-export-csv')?.addEventListener('click', exportCommandCsv);
  document.getElementById('btn-export-pdf')?.addEventListener('click', exportCommandPdf);
}

async function initCommandCenter() {
  if (!commandCenterReady) {
    wireCommandCenterEvents();
    await populateCommandFilters();
    syncCommandWardOptions();
    await ensureCommandMap();
    commandCenterReady = true;
  }
  await refreshCommandCenter();
}

// System Logs filter listeners (wired once, not inside wireCommandCenterEvents)
document.getElementById('btn-refresh-logs')?.addEventListener('click', loadSystemLogs);
['logs-search', 'logs-date-from', 'logs-date-to', 'logs-geo-filter'].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  const evtType = el.tagName === 'SELECT' ? 'change' : 'input';
  el.addEventListener(evtType, () => { logsPage = 0; renderSystemLogs(); });
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

renderAuth();
loadDashboard();
