// API Helper
const api = (action, method = 'GET', body = null, timeout = 30000) => {
  // Handle action with query parameters (e.g., "asset_get&id=123")
  // Split at first & to separate action from additional params
  const parts = action.split('&');
  const baseAction = parts[0];
  const extraParams = parts.slice(1).join('&');
  
  let url = '/api.php?action=' + encodeURIComponent(baseAction);
  if (extraParams) {
    url += '&' + extraParams;
  }
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  return fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null,
    credentials: 'include',
    signal: controller.signal
  }).then(r => {
    clearTimeout(timeoutId);
    if (r.status === 401) {
      document.dispatchEvent(new CustomEvent('app:unauthorized'));
    }
    if (!r.ok && r.status !== 401) {
      throw new Error(`HTTP ${r.status}: ${r.statusText}`);
    }
    return r.json();
  }).catch(err => {
    clearTimeout(timeoutId);
    console.error('API Error:', action, err);
    throw err;
  });
};

const el = sel => document.querySelector(sel);
const elAll = sel => document.querySelectorAll(sel);

const escapeHtml = (value) => {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

const formatDateTime = (value) => {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString();
  } catch (err) {
    return value;
  }
};

const parseChangeValue = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch (err) {
    return value;
  }
};

const formatChangeFieldLabel = (field) => {
  if (!field) return 'Unknown';
  if (field === 'asset') return 'Asset Created';
  return field
    .split(/[_\-]+/)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const renderChangeValue = (field, value) => {
  const sensitiveFields = new Set(['poll_password', 'poll_enable_password']);
  if (sensitiveFields.has(field)) {
    return '<span class="change-redacted">Hidden for security</span>';
  }

  if (value === null || value === undefined) {
    return '<span class="change-null">null</span>';
  }

  if (typeof value === 'object') {
    const pretty = escapeHtml(JSON.stringify(value, null, 2));
    return `<pre class="change-json">${pretty}</pre>`;
  }

  if (typeof value === 'boolean') {
    return `<code>${value}</code>`;
  }

  if (typeof value === 'number') {
    return `<code>${value}</code>`;
  }

  const str = String(value);
  if (str.trim() === '') {
    return '<span class="change-empty">(empty)</span>';
  }

  return escapeHtml(str);
};

const renderChangeHistory = (changes = []) => {
  const safeChanges = Array.isArray(changes) ? changes : [];
  const titleBlock = '<hr><h4>Change History</h4>';
  if (!safeChanges.length) {
    return `<div class="change-history">${titleBlock}<p class="change-empty-state">No changes recorded yet.</p></div>`;
  }

  const items = safeChanges.map(change => {
    const field = change.field || 'unknown';
    const label = formatChangeFieldLabel(field);
    const actor = escapeHtml(change.actor || 'system');
    const source = change.source ? escapeHtml(change.source) : '';
    const sourceSuffix = source ? ` · via ${source}` : '';
    const timestamp = escapeHtml(formatDateTime(change.changed_at));
    const oldVal = renderChangeValue(field, parseChangeValue(change.old_value));
    const newVal = renderChangeValue(field, parseChangeValue(change.new_value));

    return `
      <div class="change-entry">
        <div class="change-timeline-dot"></div>
        <div class="change-meta">
          <span class="change-field">${escapeHtml(label)}</span>
          <span class="change-actor">${actor}</span>
          <span class="change-time">${timestamp}${sourceSuffix}</span>
        </div>
        <div class="change-values">
          <div class="change-block">
            <div class="change-label">Was</div>
            <div class="change-data">${oldVal}</div>
          </div>
          <div class="change-block">
            <div class="change-label">Now</div>
            <div class="change-data">${newVal}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `<div class="change-history">${titleBlock}<div class="change-list">${items}</div></div>`;
};

const getStatusColor = (status) => {
  if (status === 'online') return '#2ba471';
  if (status === 'offline') return '#d64545';
  return '#64748b';
};

const pollTypeRequiresEnablePassword = (type) => (type || '').toLowerCase() === 'ssh_cisco';

const updateEnablePasswordVisibility = () => {
  const pollTypeField = el('#asset-poll-type');
  const wrapper = el('#asset-poll-enable-password-wrapper');
  if (!pollTypeField || !wrapper) return;
  const show = pollTypeRequiresEnablePassword(pollTypeField.value);
  wrapper.style.display = show ? 'block' : 'none';
};

const defaultAssetColumns = ['name','type','ips','mac','owner','status','last_seen'];
const allAssetColumnKeys = ['name','type','ips','mac','owner','status','last_seen','source','created_at','updated_at'];
const assetColumnOrder = ['name','type','ips','mac','owner','status','last_seen','source','created_at','updated_at'];

const defaultAssetTypes = [
  'server',
  'workstation',
  'network',
  'printer',
  'mobile',
  'iot',
  'virtual-machine',
  'storage',
  'appliance',
  'other'
];

const assetColumnDefinitions = {
  name: {
    label: 'Name',
    render: asset => `<strong>${escapeHtml(asset?.name || '-')}</strong>`
  },
  type: {
    label: 'Type',
    render: asset => escapeHtml(asset?.type || '-')
  },
  ips: {
    label: 'IP Addresses',
    render: asset => {
      const ips = Array.isArray(asset?.ips) ? asset.ips.map(x => escapeHtml(x.ip)).filter(Boolean).join(', ') : '';
      return `<span class="monospace">${ips || '-'}</span>`;
    }
  },
  mac: {
    label: 'MAC Address',
    render: asset => `<span class="monospace">${escapeHtml(asset?.mac || '-')}</span>`
  },
  owner: {
    label: 'Owner',
    render: asset => escapeHtml(getOwnerDisplayName(asset) || '-')
  },
  status: {
    label: 'Status',
    render: asset => {
      const status = asset?.online_status || 'unknown';
      const color = getStatusColor(status);
      return `<span style="color: ${color};">● ${escapeHtml(status)}</span>`;
    }
  },
  last_seen: {
    label: 'Last Seen',
    render: asset => escapeHtml(formatDateTime(asset?.updated_at))
  },
  source: {
    label: 'Source',
    render: asset => escapeHtml(asset?.source || '-')
  },
  created_at: {
    label: 'Created',
    render: asset => escapeHtml(formatDateTime(asset?.created_at))
  },
  updated_at: {
    label: 'Updated',
    render: asset => escapeHtml(formatDateTime(asset?.updated_at))
  }
};

let activeAssetColumns = [...defaultAssetColumns];
let columnPrefsLoaded = false;
let lastRenderedAssets = [];
let lastAssetRenderContext = { emptyReason: 'none', total: 0 };

function formatAssetTypeLabel(type) {
  if (!type) return '';
  return type
    .split(/[-_]/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function populateAssetTypeSelect(selectedValue = '') {
  const select = el('#asset-type');
  if (!select) return;
  const normalized = typeof selectedValue === 'string' ? selectedValue.trim() : '';
  const options = [...defaultAssetTypes];
  if (normalized && !options.includes(normalized)) {
    options.push(normalized);
  }
  const placeholder = '<option value="">Select asset type...</option>';
  select.innerHTML = placeholder + options
    .map(type => `<option value="${escapeHtml(type)}">${escapeHtml(formatAssetTypeLabel(type))}</option>`)
    .join('');
  if (normalized) {
    select.value = normalized;
  } else {
    select.value = '';
  }
}

function sanitizeColumns(columns) {
  if (!Array.isArray(columns)) {
    return [...defaultAssetColumns];
  }
  const unique = [];
  columns.forEach(col => {
    if (allAssetColumnKeys.includes(col) && !unique.includes(col)) {
      unique.push(col);
    }
  });
  return unique.length ? unique : [...defaultAssetColumns];
}

function renderAssetActionButtons(asset = {}) {
  const id = asset.id || '';
  const safeId = id.replace(/'/g, "\\'");
  return `
    <div class="action-buttons">
      <button type="button" class="icon-btn" onclick="viewAsset('${safeId}')" title="View asset" aria-label="View asset">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5c-4.97 0-9.16 3.11-11 7 1.84 3.89 6.03 7 11 7s9.16-3.11 11-7c-1.84-3.89-6.03-7-11-7zm0 11a4 4 0 110-8 4 4 0 010 8zm0-2.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" fill="currentColor"/></svg>
      </button>
      <button type="button" class="icon-btn" onclick="editAsset('${safeId}')" title="Edit asset" aria-label="Edit asset">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z" fill="currentColor"/><path d="M20.71 7.04a1.003 1.003 0 000-1.42L18.37 3.29a1.003 1.003 0 00-1.42 0L15.12 5.12l3.75 3.75 1.84-1.83z" fill="currentColor"/></svg>
      </button>
      <button type="button" class="icon-btn danger" onclick="deleteAsset('${safeId}')" title="Delete asset" aria-label="Delete asset">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 19a2 2 0 002 2h8a2 2 0 002-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
      </button>
    </div>
  `;
}

function renderAssetTable(assets) {
  const headRow = el('#asset-table-head');
  const body = el('#asset-list');
  if (!headRow || !body) return;

  const headerHtml = activeAssetColumns
    .map(column => {
      const def = assetColumnDefinitions[column];
      const label = def ? def.label : column;
      return `<th data-column="${column}">${escapeHtml(label)}</th>`;
    })
    .join('') + '<th>Actions</th>';

  headRow.innerHTML = headerHtml;

  if (!Array.isArray(assets) || assets.length === 0) {
    const colspan = activeAssetColumns.length + 1;
    let message = 'No assets found';
    if (lastAssetRenderContext.emptyReason === 'filter') {
      message = 'No assets found for selected owner';
    } else if (lastAssetRenderContext.emptyReason === 'error') {
      message = 'Failed to load assets';
    }
    body.innerHTML = `<tr><td colspan="${colspan}" class="empty-state">${escapeHtml(message)}</td></tr>`;
    return;
  }

  body.innerHTML = assets.map(asset => {
    const cells = activeAssetColumns.map(column => {
      const def = assetColumnDefinitions[column];
      const value = def ? def.render(asset) : '';
      return `<td data-column="${column}">${value}</td>`;
    }).join('');
    return `<tr data-asset-id="${escapeHtml(asset.id || '')}">${cells}<td class="actions-cell">${renderAssetActionButtons(asset)}</td></tr>`;
  }).join('');
}

function syncColumnModalSelections() {
  const container = el('#column-options');
  if (!container) return;
  const checkboxes = container.querySelectorAll('input[name="columns"]');
  checkboxes.forEach(input => {
    input.checked = activeAssetColumns.includes(input.value);
  });
}

function setActiveColumns(columns) {
  const sanitized = sanitizeColumns(columns);
  if (sanitized.join('|') === activeAssetColumns.join('|')) {
    syncColumnModalSelections();
    return;
  }
  activeAssetColumns = sanitized;
  renderAssetTable(lastRenderedAssets);
  syncColumnModalSelections();
}

function buildColumnOptions() {
  const container = el('#column-options');
  if (!container) return;
  const optionsHtml = assetColumnOrder
    .filter(column => assetColumnDefinitions[column])
    .map(column => {
      const def = assetColumnDefinitions[column];
      return `
        <label>
          <input type="checkbox" name="columns" value="${column}">
          ${escapeHtml(def.label)}
        </label>
      `;
    }).join('');
  container.innerHTML = optionsHtml;
  syncColumnModalSelections();
}

function showColumnError(message) {
  const errorEl = el('#column-error');
  if (!errorEl) return;
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function hideColumnError() {
  const errorEl = el('#column-error');
  if (!errorEl) return;
  errorEl.textContent = '';
  errorEl.classList.add('hidden');
}

function persistColumnPreferences(columns) {
  if (!currentUser) return Promise.resolve();
  const sanitized = sanitizeColumns(columns);
  return api('asset_columns_save', 'POST', { columns: sanitized }).catch(err => {
    console.error('Failed to save column preferences:', err);
  });
}

function loadColumnPreferences() {
  if (!currentUser) {
    setActiveColumns(defaultAssetColumns);
    columnPrefsLoaded = false;
    return Promise.resolve();
  }
  if (columnPrefsLoaded) {
    return Promise.resolve();
  }
  return api('asset_columns_get').then(res => {
    const columns = Array.isArray(res?.columns) ? res.columns : defaultAssetColumns;
    setActiveColumns(columns);
    columnPrefsLoaded = true;
  }).catch(err => {
    console.error('Failed to load column preferences:', err);
    columnPrefsLoaded = true;
    setActiveColumns(defaultAssetColumns);
  });
}

function openColumnModal() {
  const modal = el('#column-modal');
  if (!modal) return;
  buildColumnOptions();
  hideColumnError();
  modal.showModal();
}

// ============= USER MANAGEMENT =============
let usersCache = [];
let currentOwnerFilter = '';
let currentUser = null;
let pollingStatusTimer = null;

const loadUsers = () => {
  return api('users').then(users => {
    if (!Array.isArray(users)) {
      console.warn('Unexpected users payload', users);
      usersCache = [];
    } else {
      usersCache = users;
    }
    populateOwnerDropdowns();
  }).catch(err => {
    console.error('Failed to load users:', err);
  });
};

const populateOwnerDropdowns = () => {
  const ownerSelect = el('#asset-owner');
  const filterSelect = el('#owner-filter');
  
  if (ownerSelect) {
    ownerSelect.innerHTML = '<option value="">No Owner</option>' +
      usersCache.map(u => {
        const displayText = `${u.display_name || u.username} (${u.email || 'no email'})`;
        return `<option value="${u.id}">${displayText}</option>`;
      }).join('');
  }
  
  if (filterSelect) {
    filterSelect.innerHTML = '<option value="">All Assets</option>' +
      usersCache.map(u => {
        const displayText = `${u.display_name || u.username} (${u.email || 'no email'})`;
        return `<option value="${u.id}">${displayText}</option>`;
      }).join('');
  }
};

function getOwnerDisplayName(asset) {
  // Prefer API-provided owner_name/owner_email if available
  if (asset && asset.owner_name) {
    const emailPart = asset.owner_email ? ` (${asset.owner_email})` : '';
    return asset.owner_name + emailPart;
  }
  
  // Fallback to client-side lookup
  if (!asset || !asset.owner_user_id) return '-';
  const user = usersCache.find(u => u.id == asset.owner_user_id);
  if (!user) return `User #${asset.owner_user_id}`;
  const emailPart = user.email ? ` (${user.email})` : '';
  return (user.display_name || user.username) + emailPart;
}

// ============= SYSTEM STATUS =============
const checkSystemStatus = () => {
  api('system_status').then(status => {
    const warning = el('#bootstrap-warning');
    const login = el('#login-panel');
    const main = el('#main');

    if (!status.bootstrapped) {
      warning?.classList.remove('hidden');
      login?.classList.add('hidden');
      main?.classList.add('hidden');
      el('#settings')?.classList.add('hidden');
    } else {
      warning?.classList.add('hidden');
      if (!currentUser) {
        login?.classList.remove('hidden');
        main?.classList.add('hidden');
      }
    }
  }).catch((err) => {
    console.error('System status check failed:', err);
    // Show login anyway if system status fails
    el('#bootstrap-warning')?.classList.add('hidden');
    el('#login-panel')?.classList.remove('hidden');
  });
};

const setActiveUser = (user, { initialLoad = false } = {}) => {
  currentUser = user;
  const loginPanel = el('#login-panel');
  const mainPanel = el('#main');
  const settingsBtn = el('#settings-btn');

  if (user) {
    loginPanel?.classList.add('hidden');
    mainPanel?.classList.remove('hidden');
    if (settingsBtn) {
      if (user.role === 'admin') {
        settingsBtn.classList.remove('hidden');
      } else {
        settingsBtn.classList.add('hidden');
      }
    }
    if (!pollingStatusTimer) {
      pollingStatusTimer = setInterval(updatePollingStatus, 30000);
    }
    if (initialLoad) {
      loadColumnPreferences().finally(() => {
        loadUsers();
        loadAssets();
        updatePollingStatus();
      });
    } else {
      loadColumnPreferences();
    }
  } else {
    mainPanel?.classList.add('hidden');
    loginPanel?.classList.remove('hidden');
    settingsBtn?.classList.add('hidden');
    el('#settings')?.classList.add('hidden');
    currentOwnerFilter = '';
    usersCache = [];
    populateOwnerDropdowns();
    columnPrefsLoaded = false;
    activeAssetColumns = [...defaultAssetColumns];
    lastRenderedAssets = [];
    lastAssetRenderContext = { emptyReason: 'none', total: 0 };
    renderAssetTable([]);
    if (pollingStatusTimer) {
      clearInterval(pollingStatusTimer);
      pollingStatusTimer = null;
    }
  }
};

const restoreSession = () => {
  api('me').then(res => {
    if (res && res.user) {
      setActiveUser(res.user, { initialLoad: true });
    } else {
      setActiveUser(null);
    }
  }).catch(err => {
    console.error('Failed to restore session:', err);
    setActiveUser(null);
  });
};

// ============= AUTHENTICATION =============
const setupAuthHandlers = () => {
  el('#login-btn').onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const username = el('#username').value;
    const password = el('#password').value;

  el('#login-msg').textContent = 'Logging in...';
  el('#login-msg').style.color = '#f59e0b';

    api('login', 'POST', { username, password }).then(r => {
      if (r.ok && r.user) {
        el('#login-msg').textContent = '';
        setActiveUser(r.user, { initialLoad: true });
      } else {
  el('#login-msg').textContent = 'Login failed: ' + (r.error || 'Invalid credentials');
  el('#login-msg').style.color = '#d64545';
      }
    }).catch(err => {
      console.error('Login error:', err);
      let errorMsg = 'Login failed: ';
      if (err.name === 'AbortError') {
        errorMsg += 'Request timeout - server may be slow or unresponsive';
      } else if (err.message.includes('Failed to fetch')) {
        errorMsg += 'Cannot connect to server - is it running?';
      } else {
        errorMsg += err.message || 'Network error';
      }
      el('#login-msg').textContent = errorMsg;
  el('#login-msg').style.color = '#d64545';
    });
  };

  el('#settings-btn').onclick = () => showSettings();
  el('#back-to-main').onclick = () => hideSettings();
};

// ============= SETTINGS MANAGEMENT =============
const showSettings = () => {
  el('#main').classList.add('hidden');
  el('#settings').classList.remove('hidden');
  loadSettingsData();
};

const hideSettings = () => {
  el('#settings').classList.add('hidden');
  el('#main').classList.remove('hidden');
};

const loadSettingsData = () => {
  api('settings_get&category=ldap').then(settings => {
    if (settings) {
      el('#ldap-server').value = settings.host?.value || '';
      el('#ldap-base-dn').value = settings.base_dn?.value || '';
      el('#ldap-bind-dn').value = settings.bind_dn?.value || '';
      el('#ldap-bind-password').value = settings.bind_password?.value || '';
      el('#ldap-user-filter').value = settings.user_filter?.value || '';
      el('#ldap-user-attr').value = settings.user_attr?.value || '';
    }
  });

  api('poller_config').then(config => {
    el('#poller-interval').value = config.interval || 30;
    el('#poller-timeout').value = config.timeout || 10;
    el('#poller-ping-timeout').value = config.ping_timeout || 1;
    el('#poller-api-url').value = config.api_url || '';
    el('#poller-api-key').value = config.api_key || '';
  });

  updatePollingStatusInSettings();
  checkSystemHealth();
  setupSettingsListeners();
};

const setupSettingsListeners = () => {
  el('#ldap-form').onsubmit = (e) => {
    e.preventDefault();
    const settings = {
      host: el('#ldap-server').value,
      base_dn: el('#ldap-base-dn').value,
      bind_dn: el('#ldap-bind-dn').value,
      bind_password: el('#ldap-bind-password').value,
      user_filter: el('#ldap-user-filter').value,
      user_attr: el('#ldap-user-attr').value
    };
    api('settings_update', 'POST', { category: 'ldap', settings }).then(r => {
      showAlert('ldap-status', r.success ? 'LDAP settings saved' : 'Failed to save', r.success ? 'success' : 'error');
    });
  };

  el('#test-ldap').onclick = () => {
    const settings = {
      host: { value: el('#ldap-server').value },
      base_dn: { value: el('#ldap-base-dn').value },
      bind_dn: { value: el('#ldap-bind-dn').value },
      bind_password: { value: el('#ldap-bind-password').value },
      user_filter: { value: el('#ldap-user-filter').value },
      user_attr: { value: el('#ldap-user-attr').value }
    };
    showAlert('ldap-status', 'Testing connection...', 'info');
    api('ldap_test', 'POST', { settings }).then(r => {
      showAlert('ldap-status', r.message, r.success ? 'success' : 'error');
    });
  };

  el('#import-ldap').onclick = () => {
    if (!confirm('Import users from LDAP? This may take a while.')) return;
    showAlert('ldap-status', 'Importing users...', 'info');
    const filter = el('#ldap-user-filter').value.trim() || null;
    api('ldap_import', 'POST', { filter }).then(r => {
      showAlert('ldap-status', r.message, r.success ? 'success' : 'error');
    });
  };

  el('#poller-form').onsubmit = (e) => {
    e.preventDefault();
    const config = {
      interval: el('#poller-interval').value,
      timeout: el('#poller-timeout').value,
      ping_timeout: el('#poller-ping-timeout').value,
      api_url: el('#poller-api-url').value,
      api_key: el('#poller-api-key').value
    };
    api('poller_config_update', 'POST', config).then(r => {
      showAlert('poller-config-status', r.success ? 'Polling settings saved' : 'Failed to save', r.success ? 'success' : 'error');
    });
  };

  el('#start-polling-settings').onclick = () => {
    api('poller_start', 'POST').then(() => {
      updatePollingStatusInSettings();
      updatePollingStatus();
    });
  };

  el('#stop-polling-settings').onclick = () => {
    api('poller_stop', 'POST').then(() => {
      updatePollingStatusInSettings();
      updatePollingStatus();
    });
  };

  const pollerList = el('#poller-instances-list');
  const pollerNameInput = el('#new-poller-name');
  const pollerDnsInput = el('#new-poller-dns');
  const sanitizationEditor = el('#sanitization-rules-editor');
  const sanitizationUpdatedLabel = el('#sanitization-updated-at');
  const sanitizationFormatBtn = el('#format-sanitization-rules');
  const sanitizationResetBtn = el('#reset-sanitization-rules');
  const sanitizationSaveBtn = el('#save-sanitization-rules');
  const SANITIZATION_STATUS_ID = 'poller-sanitization-status';

  const defaultSanitizationRules = {
    version: 1,
    meta: {
      description: 'Default poller sanitization rules'
    },
    rules: {
      ip_addresses: {
        exclude: {
          cidr: ['127.0.0.0/8', '::1/128', 'fe80::/10'],
          exact: [],
          prefix: [],
          suffix: []
        }
      }
    }
  };

  const renderSanitizationUpdatedAt = (value) => {
    if (!sanitizationUpdatedLabel) return;
    if (!value) {
      sanitizationUpdatedLabel.textContent = 'Last updated: not saved yet';
      return;
    }
    try {
      const stamp = new Date(value);
      if (!Number.isNaN(stamp.getTime())) {
        sanitizationUpdatedLabel.textContent = `Last updated: ${stamp.toLocaleString()}`;
        return;
      }
    } catch (err) {
      // ignore
    }
    sanitizationUpdatedLabel.textContent = `Last updated: ${value}`;
  };

  const loadSanitizationRules = (showStatus = true, showSuccess = true) => {
    if (!sanitizationEditor) return Promise.resolve();
    if (showStatus) {
      showAlert(SANITIZATION_STATUS_ID, 'Loading sanitization rules…', 'info');
    }
    return api('poller_sanitization_get').then(res => {
      if (!res || res.success === false) {
        const message = res?.message || 'Failed to load sanitization rules';
        showAlert(SANITIZATION_STATUS_ID, message, 'error');
        return;
      }
      const raw = typeof res.raw === 'string' && res.raw.trim() !== ''
        ? res.raw
        : JSON.stringify(res.rules || defaultSanitizationRules, null, 2);
      sanitizationEditor.value = raw;
      renderSanitizationUpdatedAt(res.updated_at || null);
      if (showSuccess) {
        showAlert(SANITIZATION_STATUS_ID, 'Sanitization rules loaded', 'success');
      } else if (showStatus) {
        // Clear loading state without overriding existing success/error messages
        showAlert(SANITIZATION_STATUS_ID, '', 'info');
      }
    }).catch(err => {
      showAlert(SANITIZATION_STATUS_ID, `Failed to load sanitization rules: ${err.message}`, 'error');
    });
  };

  if (sanitizationFormatBtn && sanitizationEditor) {
    sanitizationFormatBtn.onclick = () => {
      try {
        const parsed = JSON.parse(sanitizationEditor.value || '{}');
        sanitizationEditor.value = JSON.stringify(parsed, null, 2);
        showAlert(SANITIZATION_STATUS_ID, 'Rules formatted for readability', 'info');
      } catch (err) {
        showAlert(SANITIZATION_STATUS_ID, `Invalid JSON: ${err.message}`, 'error');
      }
    };
  }

  if (sanitizationResetBtn && sanitizationEditor) {
    sanitizationResetBtn.onclick = () => {
      if (!confirm('Reset sanitization rules to the default set? Unsaved changes will be lost.')) {
        return;
      }
      sanitizationEditor.value = JSON.stringify(defaultSanitizationRules, null, 2);
      renderSanitizationUpdatedAt(null);
      showAlert(SANITIZATION_STATUS_ID, 'Default rules loaded (remember to save).', 'warning');
    };
  }

  if (sanitizationSaveBtn && sanitizationEditor) {
    sanitizationSaveBtn.onclick = () => {
      const raw = sanitizationEditor.value.trim();
      if (!raw) {
        showAlert(SANITIZATION_STATUS_ID, 'Rules JSON cannot be empty', 'error');
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        showAlert(SANITIZATION_STATUS_ID, `Invalid JSON: ${err.message}`, 'error');
        return;
      }
      const pretty = JSON.stringify(parsed, null, 2);
      sanitizationSaveBtn.disabled = true;
      showAlert(SANITIZATION_STATUS_ID, 'Saving sanitization rules…', 'info');
      api('poller_sanitization_save', 'POST', { raw: pretty }).then(res => {
        if (!res || res.success === false) {
          const message = res?.message || 'Failed to save sanitization rules';
          showAlert(SANITIZATION_STATUS_ID, message, 'error');
          return;
        }
        showAlert(SANITIZATION_STATUS_ID, 'Sanitization rules saved', 'success');
        loadSanitizationRules(false, false);
      }).catch(err => {
        showAlert(SANITIZATION_STATUS_ID, `Failed to save sanitization rules: ${err.message}`, 'error');
      }).finally(() => {
        sanitizationSaveBtn.disabled = false;
      });
    };
  }

  if (sanitizationEditor) {
    loadSanitizationRules();
  }

  const clearPollerStatus = () => {
    const statusEl = el('#poller-instances-status');
    if (statusEl) {
      statusEl.textContent = '';
      statusEl.className = 'alert';
    }
  };

  const setPollerStatus = (message, type = 'info') => {
    if (!el('#poller-instances-status')) return;
    showAlert('poller-instances-status', message, type);
    setTimeout(clearPollerStatus, 6000);
  };

  const renderPollerInstances = (pollers = []) => {
    if (!pollerList) return;

    if (!Array.isArray(pollers) || pollers.length === 0) {
      pollerList.innerHTML = '<div class="muted">No poller profiles configured yet.</div>';
      return;
    }

    pollerList.innerHTML = '';

    pollers.forEach(poller => {
      const row = document.createElement('div');
      row.className = 'poller-instance-row';
      const dnsValue = Array.isArray(poller?.dns_servers) ? poller.dns_servers.join(', ') : '';
      const isDefault = poller?.name?.toLowerCase() === 'default';

      row.innerHTML = `
        <div class="poller-instance-name">
          <strong>${escapeHtml(poller.name || 'Unnamed')}</strong>${isDefault ? ' <span class="badge">default</span>' : ''}
        </div>
        <div class="poller-instance-input">
          <input type="text" value="${escapeHtml(dnsValue)}" data-role="dns-input" placeholder="Comma-separated DNS servers">
        </div>
        <div class="poller-instance-actions">
          <button type="button" class="secondary" data-role="save">Save</button>
          <button type="button" class="contrast" data-role="delete" ${isDefault ? 'disabled' : ''}>Delete</button>
        </div>
      `;

      const dnsInput = row.querySelector('[data-role="dns-input"]');
      const saveBtn = row.querySelector('[data-role="save"]');
      const deleteBtn = row.querySelector('[data-role="delete"]');

      if (saveBtn) {
        saveBtn.onclick = () => {
          setPollerStatus(`Saving poller profile ${poller.name}...`, 'info');
          api('poller_settings_save', 'POST', {
            name: poller.name,
            dns_servers: dnsInput.value
          }).then(res => {
            if (res.success) {
              setPollerStatus(`Poller ${poller.name} saved`, 'success');
              refreshPollerInstances();
            } else {
              setPollerStatus(res.message || `Failed to save poller ${poller.name}`, 'error');
            }
          }).catch(err => {
            setPollerStatus(`Failed to save poller ${poller.name}: ${err.message}`, 'error');
          });
        };
      }

      if (deleteBtn && !deleteBtn.disabled) {
        deleteBtn.onclick = () => {
          if (!confirm(`Delete poller profile "${poller.name}"?`)) {
            return;
          }
          setPollerStatus(`Deleting poller profile ${poller.name}...`, 'info');
          api(`poller_settings_delete&name=${encodeURIComponent(poller.name)}`, 'POST', {}).then(res => {
            if (res.success) {
              setPollerStatus(`Poller ${poller.name} deleted`, 'success');
              refreshPollerInstances();
            } else {
              setPollerStatus(res.message || `Failed to delete poller ${poller.name}`, 'error');
            }
          }).catch(err => {
            setPollerStatus(`Failed to delete poller ${poller.name}: ${err.message}`, 'error');
          });
        };
      }

      pollerList.appendChild(row);
    });
  };

  const refreshPollerInstances = () => {
    if (!pollerList) return Promise.resolve();
    setPollerStatus('Loading poller profiles...', 'info');
    return api('pollers_list').then(res => {
      if (res.success) {
        renderPollerInstances(res.pollers || []);
        if (!res.pollers || res.pollers.length === 0) {
          setPollerStatus('No poller profiles defined. Using system resolver.', 'info');
        } else {
          setPollerStatus('Poller profiles loaded', 'success');
        }
      } else {
        setPollerStatus(res.message || 'Failed to load poller profiles', 'error');
      }
    }).catch(err => {
      setPollerStatus(`Failed to load poller profiles: ${err.message}`, 'error');
    }).finally(() => {
      setTimeout(clearPollerStatus, 6000);
    });
  };

  const addPollerBtn = el('#add-poller-instance');
  if (addPollerBtn) {
    addPollerBtn.onclick = () => {
      const name = pollerNameInput ? pollerNameInput.value.trim() : '';
      const dns = pollerDnsInput ? pollerDnsInput.value.trim() : '';
      if (!name) {
        setPollerStatus('Poller name is required', 'error');
        return;
      }
      setPollerStatus(`Saving poller profile ${name}...`, 'info');
      api('poller_settings_save', 'POST', { name, dns_servers: dns }).then(res => {
        if (res.success) {
          setPollerStatus(`Poller ${name} saved`, 'success');
          if (pollerNameInput) pollerNameInput.value = '';
          if (pollerDnsInput) pollerDnsInput.value = '';
          refreshPollerInstances();
        } else {
          setPollerStatus(res.message || `Failed to save poller ${name}`, 'error');
        }
      }).catch(err => {
        setPollerStatus(`Failed to save poller ${name}: ${err.message}`, 'error');
      });
    };
  }

  if (pollerList) {
    refreshPollerInstances();
  }

  // Polling Log Viewer - Simple load on demand
  let lastLogId = 0;
  let autoRefresh = false;
  let refreshInterval = null;

  const loadLogs = () => {
    api(`poller_logs&since=${lastLogId}`).then(logs => {
      if (!logs || logs.length === 0) {
        if (lastLogId === 0) {
          el('#poller-logs').innerHTML = '<div style="color: #888;">No logs available yet</div>';
        }
        return;
      }
      
      const logsContainer = el('#poller-logs');
      if (lastLogId === 0) {
        logsContainer.innerHTML = ''; // Clear "no logs" message
      }
      
      logs.forEach(log => {
        const logLine = document.createElement('div');
        
        // Color code by level
        let color = '#3563e9'; // info defaults to blue
        if (log.level === 'error') color = '#d64545';
        if (log.level === 'warning') color = '#f59e0b';
        if (log.level === 'success') color = '#2ba471';
        
        logLine.style.color = color;
        logLine.textContent = `[${log.timestamp}] ${log.level.toUpperCase()}: ${log.message}`;
        
        logsContainer.appendChild(logLine);
        lastLogId = Math.max(lastLogId, log.id);
      });
      
      // Auto-scroll to bottom
      logsContainer.scrollTop = logsContainer.scrollHeight;
      
      // Keep only last 200 lines
      while (logsContainer.children.length > 200) {
        logsContainer.removeChild(logsContainer.firstChild);
      }
    }).catch(err => {
      console.error('Error fetching logs:', err);
    });
  };

  el('#start-log-stream').onclick = () => {
    if (autoRefresh) return;
    
    autoRefresh = true;
    loadLogs(); // Load immediately
    refreshInterval = setInterval(loadLogs, 3000); // Refresh every 3 seconds
    
    el('#start-log-stream').disabled = true;
    el('#stop-log-stream').disabled = false;
  };

  el('#stop-log-stream').onclick = () => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
      autoRefresh = false;
    }
    
    el('#start-log-stream').disabled = false;
    el('#stop-log-stream').disabled = true;
  };

  el('#clear-logs').onclick = () => {
    el('#poller-logs').innerHTML = '';
    lastLogId = 0;
  };

  el('#check-health-btn').onclick = checkSystemHealth;

  elAll('.settings-tab').forEach(tab => {
    tab.onclick = (e) => {
      e.preventDefault();
      const tabName = tab.dataset.tab;
      elAll('.settings-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      elAll('.settings-panel').forEach(p => p.style.display = 'none');
      el('#' + tabName + '-settings').style.display = 'block';
      
      // Load custom fields when that tab is opened
      if (tabName === 'custom-fields') {
        loadCustomFields();
      }
    };
  });

  // Custom Fields Management
  const customFieldModal = getCustomFieldModal();
  const customFieldForm = getCustomFieldForm();

  if (el('#add-custom-field-btn')) {
    el('#add-custom-field-btn').onclick = () => {
      const modalTitle = customFieldModal?.querySelector('#field-modal-title');
      const idInput = customFieldForm?.querySelector('#field-id');
      if (modalTitle) {
        modalTitle.textContent = 'Add Custom Field';
      }
      if (idInput) {
        idInput.value = '';
      }
      customFieldForm?.reset();
      customFieldModal?.showModal();
    };
  }

  if (customFieldForm) {
    customFieldForm.onsubmit = (e) => {
      e.preventDefault();
      saveCustomField();
    };
  }

  // Show/hide select options based on field type
  const fieldTypeInput = customFieldForm?.querySelector('#field-type');
  if (fieldTypeInput) {
    fieldTypeInput.onchange = (e) => {
      const selectOptionsContainer = getCustomFieldElement('#select-options-container');
      if (selectOptionsContainer) {
        selectOptionsContainer.style.display = e.target.value === 'select' ? 'block' : 'none';
      }
    };
  }
};

// ============= CUSTOM FIELDS =============
const getCustomFieldModal = () => el('#custom-field-modal');
const getCustomFieldForm = () => {
  const modal = getCustomFieldModal();
  return modal ? modal.querySelector('#custom-field-form') : null;
};
const getCustomFieldElement = (selector) => {
  const modal = getCustomFieldModal();
  return modal ? modal.querySelector(selector) : null;
};

const loadCustomFields = () => {
  api('custom_fields').then(fields => {
    const container = el('#custom-fields-list');
    if (!container) return;
    
    if (!fields || fields.length === 0) {
      container.innerHTML = '<p style="color: var(--muted-color);">No custom fields defined yet. Click "Add Custom Field" to create one.</p>';
      return;
    }
    
    container.innerHTML = fields.map(field => {
      const appliesTo = field.applies_to_types ? field.applies_to_types.join(', ') : 'All asset types';
  const required = field.is_required ? '<span style="color: var(--accent-red);">*</span>' : '';
      return `
        <article style="padding: 15px; border: 1px solid var(--muted-border-color); border-radius: 4px;">
          <div style="display: flex; justify-content: space-between; align-items: start;">
            <div style="flex: 1;">
              <h4 style="margin: 0 0 5px 0;">${field.label} ${required}</h4>
              <div style="font-size: 0.9em; color: var(--muted-color);">
                <div><strong>Name:</strong> ${field.name}</div>
                <div><strong>Type:</strong> ${field.field_type}</div>
                <div><strong>Applies to:</strong> ${appliesTo}</div>
                ${field.help_text ? `<div><strong>Help:</strong> ${field.help_text}</div>` : ''}
                ${field.default_value ? `<div><strong>Default:</strong> ${field.default_value}</div>` : ''}
                <div><strong>Order:</strong> ${field.display_order}</div>
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="secondary" style="padding: 6px 12px;" onclick="editCustomField(${field.id})">Edit</button>
              <button class="contrast" style="padding: 6px 12px;" onclick="deleteCustomField(${field.id}, '${field.label}')">Delete</button>
            </div>
          </div>
        </article>
      `;
    }).join('');
  }).catch(err => {
    console.error('Failed to load custom fields:', err);
    const container = el('#custom-fields-list');
    if (container) {
      container.innerHTML = '<p style="color: var(--accent-red);">Failed to load custom fields</p>';
    }
  });
};

const editCustomField = (id) => {
  const modal = getCustomFieldModal();
  const form = getCustomFieldForm();
  if (!modal || !form) return;

  api(`custom_field_get&id=${id}`).then(field => {
    const modalTitle = modal.querySelector('#field-modal-title');
    const idInput = form.querySelector('#field-id');
    const nameInput = form.querySelector('#field-name');
    const labelInput = form.querySelector('#field-label');
    const typeInput = form.querySelector('#field-type');
    const defaultInput = form.querySelector('#field-default-value');
    const helpInput = form.querySelector('#field-help-text');
    const requiredInput = form.querySelector('#field-required');
    const orderInput = form.querySelector('#field-display-order');
    const appliesToInput = form.querySelector('#field-applies-to');
    const selectOptionsInput = form.querySelector('#field-select-options');
    const selectOptionsContainer = modal.querySelector('#select-options-container');

    if (modalTitle) modalTitle.textContent = 'Edit Custom Field';
    if (idInput) idInput.value = field.id;
    if (nameInput) nameInput.value = field.name;
    if (labelInput) labelInput.value = field.label;
    if (typeInput) typeInput.value = field.field_type;
    if (defaultInput) defaultInput.value = field.default_value || '';
    if (helpInput) helpInput.value = field.help_text || '';
    if (requiredInput) requiredInput.checked = !!field.is_required;
    if (orderInput) orderInput.value = field.display_order;
    if (appliesToInput) {
      appliesToInput.value = field.applies_to_types ? field.applies_to_types.join(', ') : '';
    }

    if (selectOptionsContainer) {
      if (field.field_type === 'select' && field.select_options) {
        if (selectOptionsInput) {
          selectOptionsInput.value = field.select_options.join('\n');
        }
        selectOptionsContainer.style.display = 'block';
      } else {
        if (selectOptionsInput) {
          selectOptionsInput.value = '';
        }
        selectOptionsContainer.style.display = 'none';
      }
    }

    modal.showModal();
  }).catch(err => {
    console.error('Failed to load field:', err);
    alert('Failed to load field');
  });
};

const deleteCustomField = (id, label) => {
  if (!confirm(`Delete custom field "${label}"? This will remove all values for this field from all assets.`)) return;
  
  api(`custom_field_delete&id=${id}`, 'DELETE').then(() => {
    loadCustomFields();
  }).catch(err => {
    console.error('Failed to delete field:', err);
    alert('Failed to delete field');
  });
};

const saveCustomField = () => {
  const form = getCustomFieldForm();
  if (!form) return;

  const idInput = form.querySelector('#field-id');
  const nameInput = form.querySelector('#field-name');
  const labelInput = form.querySelector('#field-label');
  const typeInput = form.querySelector('#field-type');
  const requiredInput = form.querySelector('#field-required');
  const defaultInput = form.querySelector('#field-default-value');
  const helpInput = form.querySelector('#field-help-text');
  const orderInput = form.querySelector('#field-display-order');
  const appliesToInput = form.querySelector('#field-applies-to');
  const selectOptionsInput = form.querySelector('#field-select-options');

  const id = idInput ? idInput.value : '';
  const data = {
    name: nameInput ? nameInput.value : '',
    label: labelInput ? labelInput.value : '',
    field_type: typeInput ? typeInput.value : 'text',
    is_required: requiredInput ? requiredInput.checked : false,
    default_value: defaultInput && defaultInput.value !== '' ? defaultInput.value : null,
    help_text: helpInput && helpInput.value !== '' ? helpInput.value : null,
    display_order: orderInput ? (parseInt(orderInput.value, 10) || 0) : 0
  };
  
  // Handle applies_to_types
  const appliesTo = appliesToInput ? appliesToInput.value.trim() : '';
  data.applies_to_types = appliesTo ? appliesTo.split(',').map(t => t.trim()).filter(t => t) : null;
  
  // Handle select options
  if (data.field_type === 'select') {
    const options = selectOptionsInput ? selectOptionsInput.value.trim() : '';
    data.select_options = options ? options.split('\n').map(o => o.trim()).filter(o => o) : [];
  } else {
    data.select_options = null;
  }
  
  const action = id ? 'custom_field_update' : 'custom_field_create';
  if (id) data.id = id;
  
  api(action, 'POST', data).then(() => {
    getCustomFieldModal()?.close();
    loadCustomFields();
  }).catch(err => {
    console.error('Failed to save field:', err);
    alert('Failed to save field: ' + err.message);
  });
};

const showAlert = (elementId, message, type) => {
  const alert = el('#' + elementId);
  if (alert) {
    alert.textContent = message;
    alert.className = 'alert show ' + type;
    setTimeout(() => alert.classList.remove('show'), 5000);
  }
};

// ============= POLLING STATUS =============
const updatePollingStatus = () => {
  if (!currentUser) return;
  api('poller_status').then(status => {
    const statusEl = el('#polling-status');
    const text = status.status === 'running' 
      ? `Polling: Running (${status.targets_count} targets)`
      : `Polling: Stopped (${status.targets_count} targets)`;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = status.status === 'running' ? '#2ba471' : '#d64545';
    }
  }).catch(err => {
    console.error('Failed to update polling status:', err);
    const statusEl = el('#polling-status');
    if (statusEl) {
      statusEl.textContent = 'Polling: Status unavailable';
      statusEl.style.color = '#888';
    }
  });
};

const updatePollingStatusInSettings = () => {
  if (!currentUser) return;
  api('poller_status').then(status => {
    const statusEl = el('#polling-status-settings');
    const startBtn = el('#start-polling-settings');
    const stopBtn = el('#stop-polling-settings');
    const text = status.status === 'running' 
      ? `Running (${status.targets_count} targets)`
      : `Stopped (${status.targets_count} targets)`;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = status.status === 'running' ? '#2ba471' : '#d64545';
    }
    if (startBtn) startBtn.disabled = status.status === 'running';
    if (stopBtn) stopBtn.disabled = status.status !== 'running';
  });
};

// ============= SYSTEM HEALTH =============
const checkSystemHealth = () => {
  api('system_health').then(health => {
    const container = el('#system-health-display');
    if (container) {
      container.innerHTML = `
        <div class="health-item"><strong>Database:</strong> ${health.database ? '✅ Connected' : '❌ Error'}</div>
        <div class="health-item"><strong>PHP Version:</strong> ${health.php_version || 'Unknown'}</div>
        <div class="health-item"><strong>Disk Space:</strong> ${health.disk_free || 'Unknown'}</div>
        <div class="health-item"><strong>Memory Usage:</strong> ${health.memory_usage || 'Unknown'}</div>
      `;
    }
  });
};

// ============= ASSET MANAGEMENT =============
const loadAssets = () => {
  api('assets').then(assets => {
    const total = Array.isArray(assets) ? assets.length : 0;
    let filteredAssets = Array.isArray(assets) ? assets : [];

    if (currentOwnerFilter) {
      filteredAssets = filteredAssets.filter(a => a.owner_user_id == currentOwnerFilter);
    }

    let emptyReason = 'none';
    if (!filteredAssets.length) {
      emptyReason = total > 0 ? 'filter' : 'none';
    }

    lastRenderedAssets = filteredAssets;
    lastAssetRenderContext = { emptyReason, total };
    renderAssetTable(filteredAssets);
  }).catch(err => {
    console.error('Failed to load assets:', err);
    lastRenderedAssets = [];
    lastAssetRenderContext = { emptyReason: 'error', total: 0 };
    renderAssetTable([]);
  });
};

// ============= CUSTOM FIELDS IN ASSETS =============
const renderCustomFieldsInModal = (assetType, customFieldValues = []) => {
  const container = el('#custom-fields-container');
  if (!container) return;

  const valuesById = new Map();
  if (Array.isArray(customFieldValues)) {
    customFieldValues.forEach(field => {
      if (!field) return;
      const key = String(field.id ?? field.field_id ?? '');
      if (key) {
        valuesById.set(key, field);
      }
    });
  } else if (customFieldValues && typeof customFieldValues === 'object') {
    Object.values(customFieldValues).forEach(field => {
      if (!field) return;
      const key = String(field.id ?? field.field_id ?? '');
      if (key) {
        valuesById.set(key, field);
      }
    });
  }
  
  // Get fields applicable to this asset type
  api(`custom_fields_for_type&type=${assetType || 'unknown'}`).then(fields => {
    if (!fields || fields.length === 0) {
      container.innerHTML = '';
      return;
    }
    
    container.innerHTML = '<hr><h4 style="margin-top: 15px;">Custom Fields</h4>' + fields.map(field => {
      const existing = valuesById.get(String(field.id));
      const value = existing && existing.value !== undefined ? existing.value : (field.default_value || '');
      const required = field.is_required ? 'required' : '';
  const star = field.is_required ? '<span style="color: var(--accent-red);">*</span>' : '';
      
      let inputHtml = '';
      
      switch (field.field_type) {
        case 'text':
        case 'email':
        case 'url':
          inputHtml = `<input type="${field.field_type}" id="cf-${field.id}" value="${value || ''}" ${required} placeholder="${field.default_value || ''}">`;
          break;
        case 'number':
          inputHtml = `<input type="number" id="cf-${field.id}" value="${value || ''}" ${required}>`;
          break;
        case 'date':
          inputHtml = `<input type="date" id="cf-${field.id}" value="${value || ''}" ${required}>`;
          break;
        case 'textarea':
          inputHtml = `<textarea id="cf-${field.id}" rows="3" ${required}>${value || ''}</textarea>`;
          break;
        case 'checkbox':
          const checked = value === 'true' || value === '1' || value === 'on' ? 'checked' : '';
          inputHtml = `<input type="checkbox" id="cf-${field.id}" ${checked}>`;
          break;
        case 'select':
          const options = field.select_options || [];
          inputHtml = `<select id="cf-${field.id}" ${required}>
            <option value="">Select...</option>
            ${options.map(opt => `<option value="${opt}" ${value === opt ? 'selected' : ''}>${opt}</option>`).join('')}
          </select>`;
          break;
      }
      
      return `
        <label data-field-id="${field.id}">
          ${field.label} ${star}
          ${inputHtml}
          ${field.help_text ? `<small>${field.help_text}</small>` : ''}
        </label>
      `;
    }).join('');
  }).catch(err => {
    console.error('Failed to load custom fields:', err);
    container.innerHTML = '';
  });
};

const getCustomFieldValues = () => {
  const container = el('#custom-fields-container');
  if (!container) return {};
  
  const values = {};
  const labels = container.querySelectorAll('label[data-field-id]');
  
  labels.forEach(label => {
    const fieldId = label.dataset.fieldId;
    const input = label.querySelector('input, select, textarea');
    if (!input) return;
    
    if (input.type === 'checkbox') {
      values[fieldId] = input.checked ? 'true' : 'false';
    } else {
      values[fieldId] = input.value;
    }
  });
  
  return values;
};

const saveCustomFieldValues = async (assetId) => {
  const values = getCustomFieldValues();
  
  for (const [fieldId, value] of Object.entries(values)) {
    try {
      await api('custom_field_set_value', 'POST', {
        asset_id: assetId,
        field_id: parseInt(fieldId),
        value: value
      });
    } catch (err) {
      console.error(`Failed to save custom field ${fieldId}:`, err);
    }
  }
};

const viewAsset = (id) => {
  console.log('viewAsset called with id:', id);
  api(`asset_get&id=${id}`).then(a => {
    console.log('Asset data:', a);
    const drawer = el('#drawer');
    const content = el('#asset-detail');
    const hasAttributes = a.attributes && Object.keys(a.attributes).length > 0;
    const ownerName = getOwnerDisplayName(a) || '-';
    const ipList = Array.isArray(a.ips) ? a.ips.map(x => escapeHtml(x.ip)).filter(Boolean).join(', ') : '';
    const pollAddress = a.poll_address ? escapeHtml(a.poll_address) : '-';
    const status = a.online_status || 'unknown';
    const statusColor = getStatusColor(status);
  const statusLabel = `<span class="status-indicator" style="--status-color: ${statusColor};">${escapeHtml(status)}</span>`;
    const changeHistoryHtml = renderChangeHistory(a.changes || []);

    // Build custom fields display
    let customFieldsHtml = '';
    const customFieldsArray = Array.isArray(a.custom_fields)
      ? a.custom_fields
      : (a.custom_fields && typeof a.custom_fields === 'object' ? Object.values(a.custom_fields) : []);
    if (customFieldsArray.length > 0) {
      const fieldsWithValues = customFieldsArray.filter(f => f && f.value !== undefined && f.value !== null && f.value !== '');
      if (fieldsWithValues.length > 0) {
        customFieldsHtml = '<hr><h4>Custom Fields</h4>';
        fieldsWithValues.forEach(field => {
          if (!field) return;
          let displayValue = field.value;
          if (field.field_type === 'checkbox') {
            displayValue = (field.value === 'true' || field.value === '1' || field.value === true) ? '✓ Yes' : '✗ No';
          }
          let renderedValue;
          if (displayValue === null || displayValue === undefined) {
            renderedValue = '<span class="change-null">null</span>';
          } else if (typeof displayValue === 'object') {
            renderedValue = `<pre class="change-json">${escapeHtml(JSON.stringify(displayValue, null, 2))}</pre>`;
          } else {
            renderedValue = escapeHtml(String(displayValue));
          }
          customFieldsHtml += `<div class="kv"><strong>${escapeHtml(field.label || field.name || 'Field')}:</strong> ${renderedValue}</div>`;
        });
      }
    }

    const attributesHtml = hasAttributes
      ? `<hr><div class="kv"><strong>Attributes:</strong></div><pre>${escapeHtml(JSON.stringify(a.attributes, null, 2))}</pre>`
      : '';

    content.innerHTML = `
      <h3>${escapeHtml(a.name)}</h3>
      <div class="kv"><strong>Type:</strong> ${escapeHtml(a.type || '-')}</div>
      <div class="kv"><strong>Owner:</strong> ${escapeHtml(ownerName)}</div>
      <div class="kv"><strong>MAC:</strong> ${escapeHtml(a.mac || '-')}</div>
      <div class="kv"><strong>Polling Address:</strong> ${pollAddress}</div>
      <div class="kv"><strong>IPs:</strong> ${ipList || '-'}</div>
      <div class="kv"><strong>Status:</strong> ${statusLabel}</div>
      <div class="kv"><strong>Last Seen:</strong> ${escapeHtml(formatDateTime(a.last_seen))}</div>
      <div class="kv"><strong>Created:</strong> ${escapeHtml(formatDateTime(a.created_at))}</div>
      <div class="kv"><strong>Updated:</strong> ${escapeHtml(formatDateTime(a.updated_at))}</div>
      ${customFieldsHtml}
      ${attributesHtml}
      ${changeHistoryHtml}
    `;
    drawer.classList.remove('hidden');
  }).catch(err => {
    console.error('Error loading asset:', err);
    alert('Failed to load asset: ' + err.message);
  });
};

const editAsset = (id) => {
  console.log('editAsset called with id:', id);
  
  // Ensure users are loaded before editing
  const loadAssetData = () => {
    api(`asset_get&id=${id}`).then(a => {
      console.log('Asset data for edit:', a);
      
      // Check if we got valid data
      if (!a || !a.id) {
        alert('Failed to load asset: Invalid response from server');
        console.error('Invalid asset data:', a);
        return;
      }
      
      el('#asset-id').value = a.id;
      el('#asset-name').value = a.name || '';
  populateAssetTypeSelect(a.type || '');
      el('#asset-type').value = a.type || '';
      el('#asset-mac').value = a.mac || '';
      el('#asset-ips').value = (a.ips || []).map(x => x.ip).join(', ');
  el('#asset-owner').value = a.owner_user_id !== undefined && a.owner_user_id !== null ? String(a.owner_user_id) : '';
      
      // Handle attributes - only show if exists and has content
      const attrs = a.attributes && Object.keys(a.attributes).length > 0 ? a.attributes : {};
      el('#asset-attributes').value = Object.keys(attrs).length > 0 ? JSON.stringify(attrs, null, 2) : '';
      
      // Polling fields
      el('#asset-poll-enabled').checked = a.poll_enabled || false;
  el('#asset-poll-address').value = a.poll_address || '';
      el('#asset-poll-type').value = a.poll_type || 'ping';
      el('#asset-poll-username').value = a.poll_username || '';
      el('#asset-poll-password').value = a.poll_password || '';
      el('#asset-poll-port').value = a.poll_port || '';
    el('#asset-poll-enable-password').value = a.poll_enable_password || '';
    updateEnablePasswordVisibility();
      
      // Load custom fields for this asset type
      renderCustomFieldsInModal(a.type, a.custom_fields || []);
      
      el('#modal-title').textContent = 'Edit Asset';
      el('#asset-modal').showModal();
    }).catch(err => {
      console.error('Error loading asset for edit:', err);
      alert('Failed to load asset: ' + err.message);
    });
  };
  
  // If users not loaded yet, load them first
  if (usersCache.length === 0) {
    loadUsers().then(() => loadAssetData());
  } else {
    loadAssetData();
  }
};

const deleteAsset = (id) => {
  console.log('deleteAsset called with id:', id);
  api(`asset_get&id=${id}`).then(a => {
    console.log('Asset data for delete:', a);
    el('#delete-asset-name').textContent = a.name;
    el('#delete-modal').dataset.assetId = id;
    el('#delete-modal').showModal();
  }).catch(err => {
    console.error('Error loading asset for delete:', err);
    alert('Failed to load asset: ' + err.message);
  });
};

// Make functions globally accessible for onclick handlers
window.viewAsset = viewAsset;
window.editAsset = editAsset;
window.deleteAsset = deleteAsset;

// ============= EVENT HANDLER INITIALIZATION =============
const setupAllHandlers = () => {
  populateAssetTypeSelect();
  // Asset management handlers
  el('#refresh').onclick = loadAssets;

  // Column preferences modal
  const columnBtn = el('#column-config');
  if (columnBtn) {
    columnBtn.onclick = () => openColumnModal();
  }

  const columnForm = el('#column-form');
  if (columnForm) {
    columnForm.onsubmit = (e) => {
      e.preventDefault();
      const selected = Array.from(columnForm.querySelectorAll('input[name="columns"]:checked')).map(input => input.value);
      if (!selected.length) {
        showColumnError('Select at least one column to display.');
        return;
      }
      hideColumnError();
      setActiveColumns(selected);
      persistColumnPreferences(selected);
      el('#column-modal')?.close();
    };
  }

  const resetColumnsBtn = el('#reset-columns');
  if (resetColumnsBtn) {
    resetColumnsBtn.onclick = () => {
      hideColumnError();
      setActiveColumns(defaultAssetColumns);
      persistColumnPreferences(defaultAssetColumns);
      el('#column-modal')?.close();
    };
  }

  const columnModal = el('#column-modal');
  if (columnModal) {
    columnModal.addEventListener('close', () => hideColumnError());
  }

  el('#new-asset').onclick = () => {
    el('#asset-id').value = '';
    el('#asset-name').value = '';
    populateAssetTypeSelect();
    el('#asset-type').value = '';
    el('#asset-mac').value = '';
    el('#asset-ips').value = '';
    el('#asset-owner').value = '';
    el('#asset-poll-address').value = '';
    el('#asset-attributes').value = '';
    el('#asset-poll-enabled').checked = false;
    el('#asset-poll-type').value = 'ping';
    el('#asset-poll-username').value = '';
    el('#asset-poll-password').value = '';
    el('#asset-poll-port').value = '';
    el('#asset-poll-enable-password').value = '';
    updateEnablePasswordVisibility();
    el('#modal-title').textContent = 'Add Asset';
    // Load custom fields for new asset
    renderCustomFieldsInModal('', []);
    el('#asset-modal').showModal();
  };

  // Listen to asset type changes to update custom fields dynamically
  if (el('#asset-type')) {
    el('#asset-type').onchange = (e) => {
      const assetId = el('#asset-id').value;
      if (!assetId) {
        // Only reload fields for new assets
        renderCustomFieldsInModal(e.target.value, []);
      }
    };
  }

  const pollTypeSelect = el('#asset-poll-type');
  if (pollTypeSelect) {
    pollTypeSelect.addEventListener('change', updateEnablePasswordVisibility);
  }
  updateEnablePasswordVisibility();

  const assetForm = el('#asset-form');
  if (assetForm) {
    assetForm.onsubmit = async (e) => {
      e.preventDefault();
      const id = el('#asset-id').value;

      // Validate JSON attributes
      const attrsInput = el('#asset-attributes').value.trim();
      let attributes = {};
      if (attrsInput) {
        try {
          attributes = JSON.parse(attrsInput);
          if (typeof attributes !== 'object' || Array.isArray(attributes)) {
            alert('Attributes must be a valid JSON object (not an array)');
            return;
          }
        } catch (err) {
          alert('Invalid JSON in attributes field:\n' + err.message);
          return;
        }
      }

      const ownerValue = el('#asset-owner').value;
      const enablePassword = el('#asset-poll-enable-password').value;
      const data = {
        name: el('#asset-name').value,
        type: el('#asset-type').value,
        mac: el('#asset-mac').value || null,
        ips: el('#asset-ips').value.split(',').map(ip => ip.trim()).filter(ip => ip),
        owner_user_id: ownerValue ? parseInt(ownerValue, 10) : null,
        attributes: attributes,
        poll_address: (el('#asset-poll-address').value || '').trim() || null,
        poll_enabled: el('#asset-poll-enabled').checked,
        poll_type: el('#asset-poll-type').value,
        poll_username: el('#asset-poll-username').value || null,
        poll_password: el('#asset-poll-password').value || null,
        poll_port: el('#asset-poll-port').value ? parseInt(el('#asset-poll-port').value) : null,
        poll_enable_password: enablePassword !== '' ? enablePassword : null
      };

      if (id) {
        // Update existing asset
        console.log('Updating asset with ID:', id);
        console.log('Update data:', { id, ...data });
        api('asset_update', 'POST', { id, ...data }).then(async r => {
          console.log('Update response:', r);
          if (r.success || r.ok) {
            await saveCustomFieldValues(id);
            el('#asset-modal').close();
            loadAssets();
          } else {
            alert('Error: ' + (r.message || r.error));
          }
        }).catch(err => {
          console.error('Update error:', err);
          alert('Failed to update asset: ' + err.message);
        });
      } else {
        // Create new asset
        console.log('Creating new asset');
        console.log('Create data:', data);
        api('asset_create', 'POST', data).then(async r => {
          console.log('Create response:', r);
          if (r.success || r.ok) {
            const newAssetId = r.id;
            if (newAssetId) {
              await saveCustomFieldValues(newAssetId);
            }
            el('#asset-modal').close();
            loadAssets();
          } else {
            alert('Error: ' + (r.message || r.error));
          }
        }).catch(err => {
          console.error('Create error:', err);
          alert('Failed to create asset: ' + err.message);
        });
      }
    };
  }

  const confirmDeleteBtn = el('#confirm-delete');
  if (confirmDeleteBtn) {
    confirmDeleteBtn.onclick = () => {
      const id = el('#delete-modal').dataset.assetId;
      api(`asset_delete&id=${id}`, 'POST').then(r => {
        if (r.success || r.ok) {
          el('#delete-modal').close();
          loadAssets();
        } else {
          alert('Error: ' + (r.message || r.error));
        }
      }).catch(err => {
        alert('Failed to delete asset: ' + err.message);
      });
    };
  }

  el('#search').addEventListener('keyup', () => {
    const q = el('#search').value.toLowerCase();
    elAll('.asset-card').forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? '' : 'none';
    });
  });

  // Modal close buttons
  elAll('.modal-close, .modal-cancel').forEach(btn => {
    btn.onclick = () => {
      if (btn.closest('dialog')) {
        btn.closest('dialog').close();
      }
    };
  });

  el('#drawer .close').onclick = () => {
    el('#drawer').classList.add('hidden');
  };

};

document.addEventListener('app:unauthorized', () => {
  if (currentUser) {
    setActiveUser(null);
    const loginMsg = el('#login-msg');
    if (loginMsg) {
      loginMsg.textContent = 'Session expired. Please log in again.';
      loginMsg.style.color = '#d64545';
    }
  }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupAuthHandlers();
  setupAllHandlers();
  setupSettingsListeners();
  checkSystemStatus();
  restoreSession();
  
  // Setup owner filter handler
  const ownerFilter = el('#owner-filter');
  if (ownerFilter) {
    ownerFilter.onchange = (e) => {
      currentOwnerFilter = e.target.value;
      loadAssets();
    };
  }
});
