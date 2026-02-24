// ── State ─────────────────────────────────────────────────────────────────────
const State = {
  currentPage: 'dashboard',
  currentUser: null,
  campaigns: [],
  currentCampaign: null,
  currentWizardStep: 1,
  contacts: [],
  filteredContacts: [],
  drafts: [],
  currentDraftIdx: 0,
  templates: [],
  currentTemplate: null,
  resumePath: null,
  chartInstance: null,
  chartRange: 30,
  tags: { companies: [], titles: [], locations: [], schools: [] },
  switches: { regenerate: false, 'avoid-dups': true },
};

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',
  };
  const r = await fetch(path, opts);
  if (r.status === 401) {
    window.location.href = '/login';
    return null;
  }
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || 'Request failed');
  }
  if (r.status === 204) return null;
  return r.json();
}

// ── Toast notifications ───────────────────────────────────────────────────────
function toast(msg, type = 'default') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  // Trigger animation
  requestAnimationFrame(() => el.classList.add('toast-show'));
  setTimeout(() => {
    el.classList.remove('toast-show');
    el.classList.add('toast-hide');
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ── Loading overlay ───────────────────────────────────────────────────────────
function showLoading(text = 'Loading...') {
  const overlay = document.getElementById('loading-overlay');
  const textEl = document.getElementById('loading-text');
  if (overlay) overlay.classList.remove('hidden');
  if (textEl) textEl.textContent = text;
}

function hideLoading() {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.classList.add('hidden');
}

// ── Page navigation ───────────────────────────────────────────────────────────
function showPage(page) {
  // Hide all page sections
  document.querySelectorAll('.page-section').forEach(el => el.classList.add('hidden'));

  // Show target page
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.remove('hidden');

  // Update nav active state
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const navBtn = document.getElementById(`nav-${page}`);
  if (navBtn) navBtn.classList.add('active');

  State.currentPage = page;

  // Load page-specific data
  switch (page) {
    case 'dashboard':   loadDashboard();   break;
    case 'campaigns':   loadCampaigns();   break;
    case 'templates':   loadTemplates();   break;
    case 'billing':     loadBilling();     break;
    case 'account':     loadAccountInfo(); break;
    case 'help':        break;
    default: break;
  }
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  // Welcome message
  const hour = new Date().getHours();
  let greeting = 'Good evening 🌙';
  if (hour < 12) greeting = 'Good morning 👋';
  else if (hour < 17) greeting = 'Good afternoon ☀️';
  const welcomeEl = document.getElementById('welcome-msg');
  if (welcomeEl) welcomeEl.textContent = greeting;
  if (State.currentUser) {
    const sub = document.getElementById('welcome-sub');
    if (sub) sub.textContent = `Welcome back, ${State.currentUser.email || 'there'}. Here's your outreach overview.`;
  }

  try {
    const stats = await api('GET', '/api/campaigns/stats');
    if (!stats) return;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('stat-campaigns', stats.total_campaigns ?? 0);
    set('stat-selected',  stats.total_selected  ?? 0);
    set('stat-approved',  stats.total_approved  ?? 0);
    set('stat-sent',      stats.total_sent      ?? 0);
    set('stat-queued',    stats.total_queued    ?? 0);
    set('stat-avg-fit',   stats.avg_fit_score   ? stats.avg_fit_score.toFixed(1) : '—');

    // Update badge
    const badge = document.getElementById('campaigns-badge');
    if (badge) badge.textContent = stats.total_campaigns ?? 0;

    // Render chart
    renderEmailChart(stats.chart_data || [], State.chartRange);

    // Recent campaigns
    const recent = stats.recent_campaigns || [];
    renderRecentCampaigns(recent);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderRecentCampaigns(campaigns) {
  const tbody = document.getElementById('recent-campaigns-tbody');
  if (!tbody) return;
  if (!campaigns.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:32px;">No campaigns yet. <a href="#" onclick="openNewCampaign()" style="color:var(--amber);">Create your first one →</a></td></tr>';
    return;
  }
  tbody.innerHTML = campaigns.map(c => `
    <tr onclick="openCampaign('${c.id}')" style="cursor:pointer;">
      <td><span style="font-weight:600;">${escHtml(c.name)}</span></td>
      <td>${c.sent_count ?? 0}</td>
      <td>${statusBadge(c.status)}</td>
      <td style="color:var(--gray-400);font-size:12px;">${formatDate(c.created_at)}</td>
    </tr>
  `).join('');
}

function renderEmailChart(chartData, range) {
  const ctx = document.getElementById('emailChart');
  if (!ctx) return;

  // Build labels/data: last `range` days
  const labels = [];
  const data = [];
  const today = new Date();
  const dataMap = {};
  (chartData || []).forEach(pt => { dataMap[pt.date] = pt.count; });

  for (let i = range - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    labels.push(range <= 7 ? key.slice(5) : key.slice(5));
    data.push(dataMap[key] || 0);
  }

  if (State.chartInstance) {
    State.chartInstance.destroy();
    State.chartInstance = null;
  }

  State.chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Emails Sent',
        data,
        backgroundColor: 'rgba(245, 158, 11, 0.7)',
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
        y: { beginAtZero: true, ticks: { precision: 0, font: { size: 11 } } },
      },
    },
  });

  // Highlight active range button
  ['7', '30', '90'].forEach(d => {
    const btn = document.getElementById(`chart-${d}d`);
    if (btn) btn.classList.toggle('active', Number(d) === range);
  });
}

function setChartRange(days) {
  State.chartRange = days;
  loadDashboard();
}

// ── Campaigns List ────────────────────────────────────────────────────────────
async function loadCampaigns() {
  try {
    const data = await api('GET', '/api/campaigns');
    if (!data) return;
    State.campaigns = data.campaigns || data || [];
    filterCampaigns();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function filterCampaigns(status) {
  // Track active tab
  if (status !== undefined) {
    ['all', 'active', 'draft', 'ended'].forEach(s => {
      const btn = document.getElementById(`tab-${s}`);
      if (btn) {
        btn.className = s === status ? 'btn btn-black' : 'btn btn-ghost';
      }
    });
    State._campaignFilter = status;
  }
  const activeFilter = State._campaignFilter || 'all';
  const search = (document.getElementById('campaign-search')?.value || '').toLowerCase();

  let list = State.campaigns;
  if (activeFilter !== 'all') {
    list = list.filter(c => c.status === activeFilter);
  }
  if (search) {
    list = list.filter(c => c.name.toLowerCase().includes(search));
  }

  const tbody = document.getElementById('campaigns-tbody');
  if (!tbody) return;
  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--gray-400);padding:40px;">No campaigns found.</td></tr>';
    return;
  }
  tbody.innerHTML = list.map(c => renderCampaignRow(c)).join('');
}

function renderCampaignRow(c) {
  return `
    <tr>
      <td>
        <span style="font-weight:600;cursor:pointer;color:var(--black);" onclick="openCampaign('${c.id}')">${escHtml(c.name)}</span>
      </td>
      <td>${c.contact_count ?? 0}</td>
      <td>${c.sent_count ?? 0}</td>
      <td>${statusBadge(c.status)}</td>
      <td style="color:var(--gray-400);font-size:12px;">${formatDate(c.created_at)}</td>
      <td style="text-align:right;">
        <button class="btn btn-ghost" style="height:28px;font-size:11px;" onclick="openCampaign('${c.id}')">Open</button>
        <button class="btn btn-danger" style="height:28px;font-size:11px;margin-left:4px;" onclick="deleteCampaign('${c.id}')">Delete</button>
      </td>
    </tr>
  `;
}

async function deleteCampaign(id) {
  if (!confirm('Delete this campaign? This cannot be undone.')) return;
  try {
    await api('DELETE', `/api/campaigns/${id}`);
    toast('Campaign deleted', 'success');
    State.campaigns = State.campaigns.filter(c => c.id !== id);
    filterCampaigns();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function openCampaign(id) {
  const campaign = State.campaigns.find(c => c.id === id || c.id === String(id));
  if (campaign) {
    State.currentCampaign = campaign;
  } else {
    State.currentCampaign = { id };
  }
  resetWizardForm();
  if (State.currentCampaign.name) {
    const nameEl = document.getElementById('w-name');
    if (nameEl) {
      nameEl.value = State.currentCampaign.name;
      const counter = document.getElementById('w-name-count');
      if (counter) counter.textContent = `${nameEl.value.length}/100`;
    }
  }
  goToStep(1);
  showPage('wizard');
  // Load existing contacts if any
  loadExistingCampaignData(id);
}

async function loadExistingCampaignData(id) {
  try {
    const data = await api('GET', `/api/campaigns/${id}`);
    if (!data) return;
    State.currentCampaign = data;
    const nameEl = document.getElementById('w-name');
    if (nameEl) {
      nameEl.value = data.name || '';
      const counter = document.getElementById('w-name-count');
      if (counter) counter.textContent = `${nameEl.value.length}/100`;
    }
    // Load existing contacts
    const contactData = await api('GET', `/api/campaigns/${id}/contacts`);
    if (contactData && contactData.contacts && contactData.contacts.length) {
      State.contacts = contactData.contacts.map(c => ({ ...c, selected: c.selected || false }));
      State.filteredContacts = [...State.contacts];
      renderContactsTable(State.contacts);
      document.getElementById('contacts-table-section')?.classList.remove('hidden');
      updateSelectionCount();
    }
  } catch (e) {
    // Silently ignore — new campaign
  }
}

function openNewCampaign() {
  State.currentCampaign = null;
  State.contacts = [];
  State.filteredContacts = [];
  State.drafts = [];
  State.tags = { companies: [], titles: [], locations: [], schools: [] };
  resetWizardForm();
  goToStep(1);
  showPage('wizard');
}

function resetWizardForm() {
  const nameEl = document.getElementById('w-name');
  if (nameEl) nameEl.value = '';
  const countEl = document.getElementById('w-target-count');
  if (countEl) countEl.value = '10';
  // Clear tags
  ['companies', 'titles', 'locations', 'schools'].forEach(f => {
    State.tags[f] = [];
    renderTags(f);
  });
  // Reset seniority
  document.querySelectorAll('.seniority-chip').forEach((chip, i) => {
    chip.classList.toggle('selected', i < 2); // Analyst + Associate default
  });
  // Hide contacts table
  document.getElementById('contacts-table-section')?.classList.add('hidden');
  // Reset stats
  ['w-stat-contacts', 'w-stat-selected', 'w-stat-companies'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '0';
  });
  const fitEl = document.getElementById('w-stat-fit');
  if (fitEl) fitEl.textContent = '—';
}

// ── Tag inputs ────────────────────────────────────────────────────────────────
function addTag(field, value) {
  const v = value.trim();
  if (!v) return;
  if (State.tags[field].includes(v)) return;
  State.tags[field].push(v);
  renderTags(field);
  // Clear input
  const inp = document.getElementById(`${field}-input`);
  if (inp) inp.value = '';
}

function removeTag(field, value) {
  State.tags[field] = State.tags[field].filter(t => t !== value);
  renderTags(field);
}

function renderTags(field) {
  const container = document.getElementById(`${field}-chips`);
  if (!container) return;
  container.innerHTML = State.tags[field].map(t => `
    <span class="tag-chip">
      ${escHtml(t)}
      <button class="tag-chip-remove" onclick="removeTag('${field}','${escHtml(t)}')" type="button">×</button>
    </span>
  `).join('');
}

function setupTagInput(field, inputId) {
  const inp = document.getElementById(inputId);
  if (!inp) return;
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag(field, inp.value);
    } else if (e.key === 'Backspace' && inp.value === '' && State.tags[field].length) {
      State.tags[field].pop();
      renderTags(field);
    }
  });
}

// ── Seniority / toggle ────────────────────────────────────────────────────────
function toggleSeniority(el) {
  el.classList.toggle('selected');
}

function toggleSwitch(name) {
  State.switches[name] = !State.switches[name];
  const el = document.getElementById(`toggle-${name}`);
  if (el) el.classList.toggle('on', State.switches[name]);
}

// ── Contact Generation (Step 1) ───────────────────────────────────────────────
async function generateContacts() {
  const name = document.getElementById('w-name')?.value.trim();
  if (!name) {
    toast('Campaign name is required', 'error');
    document.getElementById('w-name')?.focus();
    return;
  }

  const targetCount = parseInt(document.getElementById('w-target-count')?.value || '10');
  const seniority = [...document.querySelectorAll('.seniority-chip.selected')].map(el => el.textContent.trim());

  const payload = {
    campaign_name: name,
    target_count: targetCount,
    companies: State.tags.companies,
    title_keywords: State.tags.titles,
    locations: State.tags.locations,
    schools: State.tags.schools,
    seniority_levels: seniority,
    regenerate: State.switches.regenerate,
    avoid_duplicates: State.switches['avoid-dups'],
  };

  showLoading('Finding contacts...');
  const btn = document.getElementById('btn-generate');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating...'; }

  try {
    let result;
    if (State.currentCampaign?.id) {
      result = await api('POST', `/api/campaigns/${State.currentCampaign.id}/contacts/generate`, payload);
    } else {
      result = await api('POST', '/api/contacts/generate', payload);
    }
    if (!result) return;

    // Save campaign reference
    if (result.campaign_id || result.campaign) {
      State.currentCampaign = result.campaign || { id: result.campaign_id, name };
    }

    const contacts = result.contacts || result || [];
    State.contacts = contacts.map(c => ({ ...c, selected: c.selected || false }));
    State.filteredContacts = [...State.contacts];

    renderContactsTable(State.contacts);
    document.getElementById('contacts-table-section')?.classList.remove('hidden');
    updateSelectionCount();

    const n = State.contacts.length;
    toast(`Found ${n} contact${n !== 1 ? 's' : ''}`, 'success');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
    if (btn) { btn.disabled = false; btn.innerHTML = '🔍&nbsp; Generate Contacts'; }
  }
}

function renderContactsTable(contacts) {
  const tbody = document.getElementById('contacts-tbody');
  if (!tbody) return;

  // Update subtitle
  const subtitle = document.getElementById('contacts-subtitle');
  if (subtitle) subtitle.textContent = `${contacts.length} contacts found`;

  // Update wizard stats
  const companies = new Set(contacts.map(c => c.company).filter(Boolean));
  const selected = contacts.filter(c => c.selected);
  const avgFit = selected.length
    ? (selected.reduce((s, c) => s + (c.fit_score || 0), 0) / selected.length).toFixed(1)
    : contacts.length
      ? (contacts.reduce((s, c) => s + (c.fit_score || 0), 0) / contacts.length).toFixed(1)
      : '—';

  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('w-stat-contacts', contacts.length);
  set('w-stat-selected', selected.length);
  set('w-stat-companies', companies.size);
  set('w-stat-fit', avgFit);

  if (!contacts.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--gray-400);padding:32px;">No contacts found. Try adjusting your filters.</td></tr>';
    return;
  }

  tbody.innerHTML = contacts.map((c, i) => {
    const fit = c.fit_score || 0;
    const fitClass = getFitClass(fit);
    const avatar = getAvatarInitials(c.name || c.first_name || '?');
    const avatarColor = getAvatarColor(c.company || '');
    return `
      <tr id="contact-row-${c.id}" class="${c.selected ? 'row-selected' : ''}">
        <td><input type="checkbox" class="checkbox-amber" ${c.selected ? 'checked' : ''} onchange="toggleContactSelection('${c.id}', this.checked)"></td>
        <td style="color:var(--gray-400);font-size:12px;">${i + 1}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="avatar" style="background:${avatarColor};">${avatar}</div>
            <div>
              <div style="font-weight:600;font-size:13px;">${escHtml(c.name || `${c.first_name || ''} ${c.last_name || ''}`.trim())}</div>
              ${c.school ? `<div style="font-size:11px;color:var(--gray-400);">${escHtml(c.school)}</div>` : ''}
            </div>
          </div>
        </td>
        <td style="font-size:13px;">${escHtml(c.title || c.job_title || '')}</td>
        <td style="font-size:13px;font-weight:500;">${escHtml(c.company || '')}</td>
        <td style="font-size:12px;color:var(--gray-500);">${escHtml(c.location || c.city || '')}</td>
        <td>
          ${c.linkedin_url
            ? `<a href="${escHtml(c.linkedin_url)}" target="_blank" style="color:var(--blue);font-size:12px;" onclick="event.stopPropagation()">🔗 LinkedIn</a>`
            : '<span style="color:var(--gray-300);font-size:12px;">—</span>'}
        </td>
        <td style="font-size:12px;font-family:var(--font-mono);">${escHtml(c.email || '')}</td>
        <td>
          <span class="fit-badge ${fitClass}">${fit}</span>
        </td>
      </tr>
    `;
  }).join('');

  // Update select-all checkbox state
  const allCb = document.getElementById('select-all-cb');
  if (allCb) {
    const allSelected = contacts.every(c => c.selected);
    const someSelected = contacts.some(c => c.selected);
    allCb.checked = allSelected;
    allCb.indeterminate = someSelected && !allSelected;
  }
}

function applyContactFilters() {
  const titleF   = (document.getElementById('filter-title')?.value   || '').toLowerCase();
  const companyF = (document.getElementById('filter-company')?.value || '').toLowerCase();
  const cityF    = (document.getElementById('filter-city')?.value    || '').toLowerCase();
  const minFit   = parseInt(document.getElementById('filter-fit')?.value || '0') || 0;

  State.filteredContacts = State.contacts.filter(c => {
    const title   = (c.title || c.job_title || '').toLowerCase();
    const company = (c.company || '').toLowerCase();
    const city    = (c.location || c.city || '').toLowerCase();
    const fit     = c.fit_score || 0;
    return (
      (!titleF   || title.includes(titleF))   &&
      (!companyF || company.includes(companyF)) &&
      (!cityF    || city.includes(cityF))     &&
      fit >= minFit
    );
  });

  renderContactsTable(State.filteredContacts);
}

function toggleSelectAll(cb) {
  const list = State.filteredContacts.length ? State.filteredContacts : State.contacts;
  list.forEach(c => {
    c.selected = cb.checked;
    // Also update in main list
    const main = State.contacts.find(m => m.id === c.id);
    if (main) main.selected = cb.checked;
  });
  renderContactsTable(State.filteredContacts.length ? State.filteredContacts : State.contacts);
  updateSelectionCount();
}

function toggleContactSelection(id, checked) {
  const c = State.contacts.find(c => c.id === id || String(c.id) === String(id));
  if (c) c.selected = checked;
  const cf = State.filteredContacts.find(c => c.id === id || String(c.id) === String(id));
  if (cf) cf.selected = checked;
  updateSelectionCount();

  // Update row highlight
  const row = document.getElementById(`contact-row-${id}`);
  if (row) row.classList.toggle('row-selected', checked);
}

function selectTop(n) {
  const sorted = [...State.contacts].sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0));
  State.contacts.forEach(c => { c.selected = false; });
  sorted.slice(0, n).forEach(c => {
    const main = State.contacts.find(m => m.id === c.id);
    if (main) main.selected = true;
  });
  State.filteredContacts = [...State.contacts];
  renderContactsTable(State.contacts);
  updateSelectionCount();
  toast(`Selected top ${Math.min(n, State.contacts.length)} contacts`, 'success');
}

function clearSelections() {
  State.contacts.forEach(c => { c.selected = false; });
  State.filteredContacts.forEach(c => { c.selected = false; });
  renderContactsTable(State.filteredContacts.length ? State.filteredContacts : State.contacts);
  updateSelectionCount();
}

function updateSelectionCount() {
  const count = State.contacts.filter(c => c.selected).length;
  const el = document.getElementById('selected-count');
  if (el) el.textContent = count;

  // Update wizard stats
  const selEl = document.getElementById('w-stat-selected');
  if (selEl) selEl.textContent = count;

  // Enable/disable draft button
  const btn = document.getElementById('btn-draft-emails');
  if (btn) btn.disabled = count === 0;

  // Update avg fit
  const selected = State.contacts.filter(c => c.selected);
  if (selected.length) {
    const avg = (selected.reduce((s, c) => s + (c.fit_score || 0), 0) / selected.length).toFixed(1);
    const fitEl = document.getElementById('w-stat-fit');
    if (fitEl) fitEl.textContent = avg;
  }
}

function getFitClass(score) {
  if (score >= 70) return 'fit-green';
  if (score >= 50) return 'fit-amber';
  return 'fit-red';
}

function getAvatarInitials(name) {
  const parts = name.trim().split(' ');
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function getAvatarColor(company) {
  const colors = ['#3B82F6', '#8B5CF6', '#EC4899', '#10B981', '#F59E0B', '#EF4444', '#6366F1'];
  let hash = 0;
  for (let i = 0; i < company.length; i++) hash = company.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

function exportCSV() {
  if (!State.currentCampaign?.id) {
    toast('No active campaign', 'error');
    return;
  }
  window.location.href = `/api/campaigns/${State.currentCampaign.id}/contacts/export`;
}

async function saveContactSelections() {
  if (!State.currentCampaign?.id) return;
  const ids = State.contacts.filter(c => c.selected).map(c => c.id);
  await api('POST', `/api/campaigns/${State.currentCampaign.id}/contacts/select`, { contact_ids: ids });
}

// ── Wizard navigation ─────────────────────────────────────────────────────────
function goToStep(n) {
  [1, 2, 3, 4].forEach(i => {
    const el = document.getElementById(`wizard-step-${i}`);
    if (el) {
      if (i === n) {
        el.classList.remove('hidden');
        // Step 3 has flex display
        if (i === 3) el.style.display = 'flex';
      } else {
        el.classList.add('hidden');
        if (i === 3) el.style.display = 'none';
      }
    }
  });
  State.currentWizardStep = n;
  updateStepBar(n);

  if (n === 3) loadDrafts();
  if (n === 4) loadStep4();
}

function updateStepBar(n) {
  [1, 2, 3, 4].forEach(i => {
    const circle = document.getElementById(`step-circle-${i}`);
    const text   = document.getElementById(`step-text-${i}`);
    if (!circle || !text) return;
    circle.className = 'step-circle ' + (i < n ? 'done' : i === n ? 'current' : 'pending');
    text.className   = 'step-text'   + (i === n ? ' current' : '');
    if (i < n) circle.textContent = '✓';
    else circle.textContent = String(i);
  });
}

async function goToStep2() {
  const selectedCount = State.contacts.filter(c => c.selected).length;
  if (selectedCount === 0) {
    toast('Select at least one contact first', 'error');
    return;
  }
  showLoading('Saving contacts...');
  try {
    await saveContactSelections();
    goToStep(2);
    loadTemplatesForStep2();
    // Update step 2 stats
    const s2Sel = document.getElementById('s2-selected');
    if (s2Sel) s2Sel.textContent = selectedCount;
    // Show success banner
    const banner = document.getElementById('step2-success-banner');
    if (banner) banner.classList.remove('hidden');
    setTimeout(() => banner?.classList.add('hidden'), 4000);
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── Step 2: Resume + Draft ────────────────────────────────────────────────────
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('upload-zone')?.classList.add('drag-over');
}

function handleDragLeave(e) {
  document.getElementById('upload-zone')?.classList.remove('drag-over');
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone')?.classList.remove('drag-over');
  handleFileSelect({ target: { files: e.dataTransfer.files } });
}

async function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;

  const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  const allowedExt = ['.pdf', '.docx'];
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!allowedExt.includes(ext)) {
    toast('Only PDF or DOCX files are allowed', 'error');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    toast('File must be under 10MB', 'error');
    return;
  }
  if (!State.currentCampaign?.id) {
    toast('No active campaign — please generate contacts first', 'error');
    return;
  }

  showLoading('Uploading resume...');
  try {
    const formData = new FormData();
    formData.append('file', file);

    const r = await fetch(`/api/campaigns/${State.currentCampaign.id}/resume`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    const result = await r.json();
    State.resumePath = result.path || result.resume_path || file.name;

    // Show success UI
    document.getElementById('upload-zone')?.classList.add('hidden');
    const successEl = document.getElementById('upload-success');
    if (successEl) successEl.classList.remove('hidden');
    const filenameEl = document.getElementById('resume-filename');
    if (filenameEl) filenameEl.textContent = file.name;
    const metaEl = document.getElementById('resume-meta');
    if (metaEl) metaEl.textContent = `${(file.size / 1024).toFixed(0)} KB · Uploaded ✓`;

    // Update status
    const statusEl = document.getElementById('s2-resume-status');
    if (statusEl) {
      statusEl.textContent = 'Attached ✓';
      statusEl.className = 'stat-value text-teal';
    }
    toast('Resume uploaded', 'success');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

function removeResume() {
  State.resumePath = null;
  document.getElementById('upload-zone')?.classList.remove('hidden');
  document.getElementById('upload-success')?.classList.add('hidden');
  const statusEl = document.getElementById('s2-resume-status');
  if (statusEl) {
    statusEl.textContent = 'Not Attached';
    statusEl.className = 'stat-value text-red';
  }
  const fileInput = document.getElementById('resume-file-input');
  if (fileInput) fileInput.value = '';
}

function updateTemplateSection() {
  const source = document.getElementById('template-source-select')?.value;
  const group = document.getElementById('template-select-group');
  if (group) group.style.display = source === 'custom' ? 'none' : '';
}

async function loadTemplatesForStep2() {
  try {
    const data = await api('GET', '/api/templates');
    if (!data) return;
    State.templates = data.templates || data || [];
    const sel = document.getElementById('template-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">— No template —</option>' +
      State.templates.map(t => `<option value="${t.id}">${escHtml(t.name)}</option>`).join('');
    // Update draft count
    if (State.currentCampaign?.id) {
      const draftsData = await api('GET', `/api/campaigns/${State.currentCampaign.id}/drafts`).catch(() => null);
      if (draftsData) {
        const cnt = (draftsData.drafts || draftsData || []).length;
        const el = document.getElementById('s2-drafts');
        if (el) el.textContent = cnt;
      }
    }
  } catch (e) {
    // Non-fatal
  }
}

async function generateDrafts() {
  if (!State.currentCampaign?.id) {
    toast('No active campaign', 'error');
    return;
  }
  if (!State.resumePath && !document.getElementById('upload-success')?.classList.contains('hidden') === false) {
    // Allow proceeding without resume for custom
  }

  const templateId = document.getElementById('template-select')?.value || null;
  const source = document.getElementById('template-source-select')?.value;

  showLoading('Generating drafts...');
  try {
    const payload = {
      template_id: templateId || null,
      use_template: source !== 'custom',
      resume_path: State.resumePath,
    };
    const result = await api('POST', `/api/campaigns/${State.currentCampaign.id}/drafts/generate`, payload);
    if (!result) return;

    const drafts = result.drafts || result || [];
    State.drafts = drafts;
    toast(`Generated ${drafts.length} draft${drafts.length !== 1 ? 's' : ''}`, 'success');
    goToStep(3);

    // Show success banner
    const banner = document.getElementById('step3-success-banner');
    if (banner) {
      banner.classList.remove('hidden');
      setTimeout(() => banner.classList.add('hidden'), 4000);
    }
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── Step 3: Draft editor ──────────────────────────────────────────────────────
async function loadDrafts() {
  if (!State.currentCampaign?.id) return;
  try {
    const data = await api('GET', `/api/campaigns/${State.currentCampaign.id}/drafts`);
    if (!data) return;
    State.drafts = data.drafts || data || [];
    State.currentDraftIdx = 0;
    renderDraftCards();
    updateDraftStats();
    if (State.drafts.length) loadDraft(0);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderDraftCards() {
  const container = document.getElementById('draft-cards-list');
  if (!container) return;
  const count = document.getElementById('draft-list-count');
  if (count) count.textContent = State.drafts.length;

  if (!State.drafts.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray-400);font-size:13px;">No drafts yet.</div>';
    return;
  }

  container.innerHTML = State.drafts.map((d, i) => {
    const isActive = i === State.currentDraftIdx;
    const statusColor = d.status === 'approved' ? 'var(--green)' : d.status === 'sent' ? 'var(--blue)' : 'var(--amber)';
    const name = d.contact_name || d.contact?.name || `Contact ${i + 1}`;
    const company = d.contact_company || d.contact?.company || '';
    return `
      <div class="draft-card ${isActive ? 'active' : ''}" onclick="loadDraft(${i})">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
          <span style="font-weight:600;font-size:13px;">${escHtml(name)}</span>
          <span style="font-size:11px;color:${statusColor};font-weight:600;">${(d.status || 'pending').toUpperCase()}</span>
        </div>
        <div style="font-size:11px;color:var(--gray-400);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          ${escHtml(company)} · ${escHtml((d.subject || '').slice(0, 40))}
        </div>
      </div>
    `;
  }).join('');
}

function loadDraft(idx) {
  if (idx < 0 || idx >= State.drafts.length) return;
  State.currentDraftIdx = idx;
  const d = State.drafts[idx];

  // Show editor, hide empty
  document.getElementById('draft-editor-empty')?.classList.add('hidden');
  const content = document.getElementById('draft-editor-content');
  if (content) content.classList.remove('hidden');

  // Nav label
  const navLabel = document.getElementById('draft-nav-label');
  if (navLabel) navLabel.textContent = `${idx + 1} of ${State.drafts.length}`;

  // Meta row
  const metaRow = document.getElementById('editor-meta-row');
  if (metaRow) {
    const name    = d.contact_name    || d.contact?.name    || '';
    const company = d.contact_company || d.contact?.company || '';
    const email   = d.contact_email   || d.contact?.email   || '';
    const status  = d.status || 'pending';
    const statusColor = status === 'approved' ? 'var(--green)' : status === 'sent' ? 'var(--blue)' : 'var(--amber)';
    metaRow.innerHTML = `
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <div>
          <div style="font-weight:700;font-size:14px;">${escHtml(name)}</div>
          <div style="font-size:12px;color:var(--gray-400);">${escHtml(company)} · ${escHtml(email)}</div>
        </div>
        <span style="font-size:11px;font-weight:700;color:${statusColor};padding:3px 8px;border:1px solid ${statusColor};border-radius:4px;">${status.toUpperCase()}</span>
        ${status !== 'approved' && status !== 'sent'
          ? `<button class="btn btn-teal" style="height:28px;font-size:11px;" onclick="approveSingleDraft(${idx})">✓ Approve</button>`
          : ''}
      </div>
    `;
  }

  // Subject + body
  const subjEl = document.getElementById('editor-subject');
  if (subjEl) subjEl.value = d.subject || '';
  const bodyEl = document.getElementById('editor-body');
  if (bodyEl) bodyEl.value = d.body || '';

  // Update active card highlight
  renderDraftCards();
}

function navigateDraft(delta) {
  const newIdx = State.currentDraftIdx + delta;
  if (newIdx >= 0 && newIdx < State.drafts.length) {
    loadDraft(newIdx);
  }
}

async function saveDraftField(field) {
  const d = State.drafts[State.currentDraftIdx];
  if (!d?.id) return;
  const val = document.getElementById(`editor-${field}`)?.value;
  if (val === undefined) return;
  try {
    await api('PATCH', `/api/drafts/${d.id}`, { [field]: val });
    d[field] = val;
  } catch (e) {
    toast('Failed to save: ' + e.message, 'error');
  }
}

async function approveSingleDraft(idx) {
  const d = State.drafts[idx];
  if (!d?.id) return;
  try {
    await api('POST', `/api/drafts/${d.id}/approve`, { approved: true });
    d.status = 'approved';
    renderDraftCards();
    updateDraftStats();
    loadDraft(idx);
    toast('Draft approved', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function approveAll() {
  showLoading('Approving all drafts...');
  try {
    for (const d of State.drafts) {
      if (d.status !== 'sent') {
        await api('POST', `/api/drafts/${d.id}/approve`, { approved: true });
        d.status = 'approved';
      }
    }
    renderDraftCards();
    updateDraftStats();
    if (State.drafts.length) loadDraft(State.currentDraftIdx);
    toast('All drafts approved', 'success');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function approveSelected() {
  const selectedDrafts = State.drafts.filter((d, i) => {
    const card = document.querySelector(`.draft-card:nth-child(${i + 1})`);
    return card && card.classList.contains('active');
  });
  // If nothing "selected" in multi-select sense, approve current
  const current = State.drafts[State.currentDraftIdx];
  if (current && current.status !== 'sent') {
    try {
      await api('POST', `/api/drafts/${current.id}/approve`, { approved: true });
      current.status = 'approved';
      renderDraftCards();
      updateDraftStats();
      loadDraft(State.currentDraftIdx);
      toast('Draft approved', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  } else {
    toast('No draft selected', 'error');
  }
}

function updateDraftStats() {
  const total    = State.drafts.length;
  const approved = State.drafts.filter(d => d.status === 'approved').length;
  const pending  = State.drafts.filter(d => d.status !== 'approved' && d.status !== 'sent').length;

  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('s3-total', total);
  set('s3-approved', approved);
  set('s3-pending', pending);
}

async function sendTestEmail() {
  const d = State.drafts[State.currentDraftIdx];
  if (!d?.id) { toast('No draft selected', 'error'); return; }
  const email = prompt('Send test to:', State.currentUser?.email || '');
  if (!email) return;
  try {
    await api('POST', `/api/drafts/${d.id}/test`, { to: email });
    toast('Test email sent to ' + email, 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── Step 4: Send ──────────────────────────────────────────────────────────────
async function loadStep4() {
  if (!State.currentCampaign?.id) return;
  try {
    const data = await api('GET', `/api/campaigns/${State.currentCampaign.id}`);
    if (!data) return;

    const approvedCount = State.drafts.filter(d => d.status === 'approved').length;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('s4-approved', approvedCount);
    set('s4-queued',   data.queued_count || 0);
    set('s4-status',   data.status       || '—');

    // Summary
    set('summary-approved', approvedCount);
    updateSendSummary();

    // Show/hide warning
    const warning = document.getElementById('send-warning');
    if (warning) warning.classList.toggle('hidden', approvedCount > 0);
    const sendBtn = document.getElementById('btn-send-now');
    if (sendBtn) sendBtn.disabled = approvedCount === 0;
  } catch (e) {
    // Non-fatal
  }
}

function updateSendSummary() {
  const days = getDayChips().join(', ') || 'None';
  const start = document.getElementById('window-start')?.value || '09:30';
  const end   = document.getElementById('window-end')?.value   || '17:00';
  const cap   = document.getElementById('daily-cap')?.value    || '20';

  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('summary-days',   days);
  set('summary-window', `${start} – ${end}`);
  set('summary-cap',    cap);
}

async function sendCampaign() {
  const approvedCount = State.drafts.filter(d => d.status === 'approved').length;
  if (approvedCount === 0) {
    toast('No approved drafts to send', 'error');
    return;
  }
  if (!confirm(`Send ${approvedCount} email${approvedCount !== 1 ? 's' : ''}? This cannot be undone.`)) return;

  const payload = {
    campaign_id:   State.currentCampaign.id,
    send_mode:     document.getElementById('send-mode')?.value || 'now',
    allowed_days:  getDayChips(),
    window_start:  document.getElementById('window-start')?.value  || '09:30',
    window_end:    document.getElementById('window-end')?.value    || '17:00',
    daily_cap:     parseInt(document.getElementById('daily-cap')?.value    || '20'),
    hourly_cap:    parseInt(document.getElementById('hourly-cap')?.value   || '15'),
    interval_min:  parseInt(document.getElementById('interval-min')?.value || '1'),
    interval_max:  parseInt(document.getElementById('interval-max')?.value || '15'),
  };

  showLoading('Sending campaign...');
  try {
    const result = await api('POST', '/api/send', payload);
    if (!result) return;
    toast(`Campaign launched! ${approvedCount} emails queued.`, 'success');
    State.currentCampaign = null;
    State.drafts = [];
    State.contacts = [];
    showPage('dashboard');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

function getDayChips() {
  return [...document.querySelectorAll('.day-chip.selected')].map(d => d.dataset.day);
}

// ── Templates ─────────────────────────────────────────────────────────────────
async function loadTemplates() {
  try {
    const data = await api('GET', '/api/templates');
    if (!data) return;
    State.templates = data.templates || data || [];
    renderTemplateList();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderTemplateList() {
  const container = document.getElementById('template-list-items');
  if (!container) return;
  if (!State.templates.length) {
    container.innerHTML = '<div style="padding:16px;font-size:13px;color:var(--gray-400);">No templates yet.</div>';
    return;
  }
  container.innerHTML = State.templates.map(t => `
    <div class="template-card ${State.currentTemplate?.id === t.id ? 'active' : ''}" onclick="loadTemplate(${JSON.stringify(t).replace(/"/g, '&quot;')})">
      <div class="template-card-name">${escHtml(t.name)}</div>
      <div class="template-card-preview">${escHtml((t.subject_template || '').slice(0, 50))}</div>
      <div style="display:flex;gap:6px;margin-top:8px;">
        <button class="btn btn-ghost" style="height:24px;font-size:11px;" onclick="event.stopPropagation();deleteTemplate('${t.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function loadTemplate(t) {
  State.currentTemplate = t;
  const nameEl = document.getElementById('template-name-input');
  const subjEl = document.getElementById('template-subject-input');
  const bodyEl = document.getElementById('template-body-input');
  if (nameEl) nameEl.value = t.name || '';
  if (subjEl) subjEl.value = t.subject_template || '';
  if (bodyEl) bodyEl.value = t.body_template || '';
  renderTemplateList();
}

function newTemplate() {
  State.currentTemplate = null;
  const nameEl = document.getElementById('template-name-input');
  const subjEl = document.getElementById('template-subject-input');
  const bodyEl = document.getElementById('template-body-input');
  if (nameEl) nameEl.value = '';
  if (subjEl) subjEl.value = '';
  if (bodyEl) bodyEl.value = '';
  renderTemplateList();
}

async function saveTemplate() {
  const name    = document.getElementById('template-name-input')?.value.trim();
  const subject = document.getElementById('template-subject-input')?.value || '';
  const body    = document.getElementById('template-body-input')?.value || '';
  if (!name) { toast('Template name is required', 'error'); return; }

  try {
    if (State.currentTemplate?.id) {
      const result = await api('PUT', `/api/templates/${State.currentTemplate.id}`, {
        name, subject_template: subject, body_template: body,
      });
      const idx = State.templates.findIndex(t => t.id === State.currentTemplate.id);
      if (idx !== -1) State.templates[idx] = result || { ...State.currentTemplate, name, subject_template: subject, body_template: body };
      State.currentTemplate = State.templates[idx];
    } else {
      const result = await api('POST', '/api/templates', {
        name, subject_template: subject, body_template: body,
      });
      if (result) {
        State.templates.push(result);
        State.currentTemplate = result;
      }
    }
    toast('Template saved', 'success');
    renderTemplateList();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteTemplate(id) {
  if (!confirm('Delete this template?')) return;
  try {
    await api('DELETE', `/api/templates/${id}`);
    State.templates = State.templates.filter(t => t.id !== id);
    if (State.currentTemplate?.id === id) newTemplate();
    renderTemplateList();
    toast('Template deleted', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function resetTemplate() {
  if (!State.currentTemplate) {
    newTemplate();
    return;
  }
  loadTemplate(State.currentTemplate);
}

function insertMergeTag(inputId, tag) {
  const el = document.getElementById(inputId);
  if (!el) return;
  const start = el.selectionStart;
  const end   = el.selectionEnd;
  const val   = el.value;
  el.value = val.slice(0, start) + tag + val.slice(end);
  el.selectionStart = el.selectionEnd = start + tag.length;
  el.focus();
}

const STARTER_TEMPLATES = {
  cold: {
    name: 'Cold Outreach (Basic)',
    subject_template: 'Interest in {{ Company }} — {{ First Name }}',
    body_template: `Hi {{ First Name }},

I hope this message finds you well. My name is [Your Name], and I'm a [Your Year] student at [Your School] studying [Your Major].

I came across your profile and was really impressed by your work at {{ Company }} as a {{ Title }}. I'm very interested in learning more about your career path and what it's like working in [relevant area] at {{ Company }}.

Would you be open to a 20-minute call at your convenience? I'd love to hear about your experience and any advice you might have for someone looking to break into this field.

Thank you so much for your time — I look forward to hearing from you.

Best regards,
[Your Name]
[Your School] | [Your Year]
[Your Email] | [Your LinkedIn]`,
  },
  coffee: {
    name: 'Coffee Chat Request',
    subject_template: 'Quick Chat — {{ Company }} | {{ First Name }}',
    body_template: `Hi {{ First Name }},

I'm reaching out because I've been following {{ Company }}'s work in [relevant area] and found your background particularly interesting.

I'm a [Your Year] at [Your School] and am actively exploring opportunities in [sector/role]. I'd love to get your perspective on the industry and any advice you'd share with someone earlier in their career.

Would you have 15–20 minutes for a quick call or virtual coffee chat over the next few weeks? I'm happy to work around your schedule.

Really appreciate you taking the time — looking forward to connecting!

Best,
[Your Name]`,
  },
  followup: {
    name: 'Follow-Up Email',
    subject_template: 'Following up — {{ Company }} | {{ First Name }}',
    body_template: `Hi {{ First Name }},

I wanted to follow up on my previous message. I know you're incredibly busy, so I just wanted to make sure it didn't get lost in your inbox.

I remain very interested in learning from your experience at {{ Company }} and would truly appreciate even a brief conversation.

If now isn't a good time, please don't hesitate to let me know — I'm happy to reconnect when things are less hectic.

Thank you again for your time.

Best,
[Your Name]`,
  },
};

function loadStarterTemplate(type) {
  const t = STARTER_TEMPLATES[type];
  if (!t) return;
  State.currentTemplate = null;
  const nameEl = document.getElementById('template-name-input');
  const subjEl = document.getElementById('template-subject-input');
  const bodyEl = document.getElementById('template-body-input');
  if (nameEl) nameEl.value = t.name;
  if (subjEl) subjEl.value = t.subject_template;
  if (bodyEl) bodyEl.value = t.body_template;
}

// ── Billing ───────────────────────────────────────────────────────────────────
async function loadBilling() {
  try {
    const stats = await api('GET', '/api/campaigns/stats');
    if (!stats) return;
    const el1 = document.getElementById('billing-campaigns');
    const el2 = document.getElementById('billing-sent');
    if (el1) el1.textContent = stats.total_campaigns || 0;
    if (el2) el2.textContent = stats.total_sent || 0;
  } catch (e) {
    // Non-fatal
  }
}

// ── Account ───────────────────────────────────────────────────────────────────
async function loadAccountInfo() {
  try {
    const data = await api('GET', '/api/auth/me');
    if (!data) return;
    State.currentUser = data;
    const emailEl = document.getElementById('account-email');
    if (emailEl) emailEl.value = data.email || '';

    // Gmail status
    const gmailDot  = document.getElementById('gmail-status-dot');
    const gmailText = document.getElementById('gmail-status-text');
    const gmailAt   = document.getElementById('gmail-connected-at');
    if (data.gmail_connected) {
      if (gmailDot)  { gmailDot.style.background = 'var(--green)'; }
      if (gmailText) gmailText.textContent = 'Connected';
      if (gmailAt && data.gmail_connected_at) {
        gmailAt.textContent = 'Connected ' + formatDate(data.gmail_connected_at);
      }
    } else {
      if (gmailDot)  { gmailDot.style.background = 'var(--red)'; }
      if (gmailText) gmailText.textContent = 'Not connected';
      if (gmailAt)   gmailAt.textContent = '';
    }
  } catch (e) {
    // Non-fatal
  }
}

async function connectGmail() {
  try {
    const data = await api('GET', '/api/auth/gmail/authorize');
    if (data?.auth_url) window.location.href = data.auth_url;
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function disconnectGmail() {
  if (!confirm('Disconnect Gmail?')) return;
  try {
    await api('POST', '/api/auth/gmail/disconnect');
    toast('Gmail disconnected', 'success');
    loadAccountInfo();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function checkApiHealth() {
  const dot = document.getElementById('api-health-dot');
  try {
    const r = await fetch('/api/health', { credentials: 'include' });
    if (r.ok) {
      if (dot) dot.style.background = 'var(--green)';
      toast('API is healthy', 'success');
    } else {
      if (dot) dot.style.background = 'var(--red)';
      toast('API returned error ' + r.status, 'error');
    }
  } catch (e) {
    if (dot) dot.style.background = 'var(--red)';
    toast('API unreachable', 'error');
  }
}

async function logout() {
  try {
    await api('POST', '/api/auth/logout');
  } catch (e) {
    // Continue regardless
  }
  window.location.href = '/';
}

async function confirmDeleteAll() {
  const confirmation = prompt('Type DELETE to confirm removing all campaigns:');
  if (confirmation !== 'DELETE') { toast('Cancelled', 'default'); return; }
  showLoading('Deleting all campaigns...');
  try {
    await api('DELETE', '/api/campaigns/all');
    State.campaigns = [];
    toast('All campaigns deleted', 'success');
    showPage('dashboard');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── Utility helpers ───────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (e) { return iso; }
}

function statusBadge(status) {
  const map = {
    draft:   { color: '#888',           label: 'Draft' },
    active:  { color: 'var(--blue)',    label: 'Active' },
    running: { color: 'var(--teal)',    label: 'Running' },
    ended:   { color: 'var(--gray-400)',label: 'Ended' },
    sent:    { color: 'var(--green)',   label: 'Sent' },
    paused:  { color: 'var(--amber)',   label: 'Paused' },
    error:   { color: 'var(--red)',     label: 'Error' },
  };
  const s = (status || 'draft').toLowerCase();
  const { color, label } = map[s] || { color: '#888', label: s };
  return `<span style="font-size:11px;font-weight:700;color:${color};padding:2px 7px;background:${color}18;border-radius:4px;">${label}</span>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  // Setup tag inputs
  ['companies', 'titles', 'locations', 'schools'].forEach(field => {
    setupTagInput(field, `${field}-input`);
  });

  // Day chip clicks
  document.querySelectorAll('.day-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      chip.classList.toggle('selected');
      updateSendSummary();
    });
  });

  // Name counter
  const nameInput = document.getElementById('w-name');
  if (nameInput) {
    nameInput.addEventListener('input', function() {
      const counter = document.getElementById('w-name-count');
      if (counter) counter.textContent = `${this.value.length}/100`;
    });
  }

  // Check auth
  try {
    const user = await api('GET', '/api/auth/me');
    if (!user) return; // api() will redirect to /login on 401
    State.currentUser = user;
  } catch (e) {
    // If API not available, continue anyway for dev purposes
  }

  // Load dashboard
  showPage('dashboard');
}

window.addEventListener('DOMContentLoaded', init);
