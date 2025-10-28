// API Helper
const api = (action, method = 'GET', body = null) => {
  const url = '/api.php?action=' + encodeURIComponent(action);
  return fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null,
    credentials: 'include'
  }).then(r => r.json());
};

const el = sel => document.querySelector(sel);
const elAll = sel => document.querySelectorAll(sel);

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
      login?.classList.remove('hidden');
    }
  }).catch(() => {
    el('#bootstrap-warning')?.classList.remove('hidden');
  });
};

// ============= AUTHENTICATION =============
const setupAuthHandlers = () => {
  el('#login-btn').onclick = () => {
    const username = el('#username').value;
    const password = el('#password').value;

    api('login', 'POST', { username, password }).then(r => {
      if (r.success) {
        el('#login-panel').classList.add('hidden');
        el('#main').classList.remove('hidden');
        el('#settings-btn').classList.remove('hidden');
        loadAssets();
        updatePollingStatus();
      } else {
        el('#login-msg').textContent = 'Login failed: ' + r.message;
        el('#login-msg').style.color = '#ff6b6b';
      }
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
    api('ldap_import', 'POST', {}).then(r => {
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
    api('poller_start', 'POST').then(() => updatePollingStatusInSettings());
  };

  el('#stop-polling-settings').onclick = () => {
    api('poller_stop', 'POST').then(() => updatePollingStatusInSettings());
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
    };
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
  api('poller_status').then(status => {
    const statusEl = el('#polling-status');
    const startBtn = el('#start-polling');
    const stopBtn = el('#stop-polling');
    const text = status.status === 'running' 
      ? `Polling: Running (${status.targets_count} targets)`
      : `Polling: Stopped (${status.targets_count} targets)`;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = status.status === 'running' ? '#6dd17f' : '#ff6b6b';
    }
    if (startBtn) startBtn.disabled = status.status === 'running';
    if (stopBtn) stopBtn.disabled = status.status !== 'running';
  });
};

const updatePollingStatusInSettings = () => {
  api('poller_status').then(status => {
    const statusEl = el('#polling-status-settings');
    const startBtn = el('#start-polling-settings');
    const stopBtn = el('#stop-polling-settings');
    const text = status.status === 'running' 
      ? `Running (${status.targets_count} targets)`
      : `Stopped (${status.targets_count} targets)`;
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.style.color = status.status === 'running' ? '#6dd17f' : '#ff6b6b';
    }
    if (startBtn) startBtn.disabled = status.status === 'running';
    if (stopBtn) stopBtn.disabled = status.status !== 'running';
  });
};

el('#start-polling').onclick = () => {
  api('poller_start', 'POST').then(() => updatePollingStatus());
};

el('#stop-polling').onclick = () => {
  api('poller_stop', 'POST').then(() => updatePollingStatus());
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
    const grid = el('#asset-list');
    grid.innerHTML = assets.map(a => `
      <div class="asset-card">
        <h4>${a.name} <span class="badge">${a.type}</span></h4>
        <div class="kv"><strong>ID:</strong> <span>${a.id}</span></div>
        <div class="kv"><strong>MAC:</strong> <span>${a.mac || '-'}</span></div>
        <div class="kv"><strong>IPs:</strong> <span>${(a.ips || []).map(x => x.ip).join(', ') || '-'}</span></div>
        <div class="kv"><strong>Status:</strong> <span class="badge">${a.online_status}</span></div>
        <div style="display: flex; gap: 10px; margin-top: 12px;">
          <button onclick="viewAsset(${a.id})" class="secondary" style="width: auto; padding: 6px 12px;">View</button>
          <button onclick="editAsset(${a.id})" class="secondary" style="width: auto; padding: 6px 12px;">Edit</button>
          <button onclick="deleteAsset(${a.id})" class="contrast" style="width: auto; padding: 6px 12px;">Delete</button>
        </div>
      </div>
    `).join('');
  });
};

const viewAsset = (id) => {
  api(`assets/${id}`).then(a => {
    const drawer = el('#drawer');
    const content = el('#asset-detail');
    content.innerHTML = `
      <h3>${a.name}</h3>
      <div class="kv"><strong>Type:</strong> ${a.type}</div>
      <div class="kv"><strong>MAC:</strong> ${a.mac || '-'}</div>
      <div class="kv"><strong>IPs:</strong> ${(a.ips || []).map(x => x.ip).join(', ') || '-'}</div>
      <div class="kv"><strong>Status:</strong> ${a.online_status}</div>
      <div class="kv"><strong>Created:</strong> ${a.created_at}</div>
      <div class="kv"><strong>Updated:</strong> ${a.updated_at}</div>
      <pre>${JSON.stringify(a.attributes, null, 2)}</pre>
    `;
    drawer.classList.remove('hidden');
  });
};

const editAsset = (id) => {
  api(`assets/${id}`).then(a => {
    el('#asset-id').value = a.id;
    el('#asset-name').value = a.name;
    el('#asset-type').value = a.type;
    el('#asset-mac').value = a.mac || '';
    el('#asset-ips').value = (a.ips || []).map(x => x.ip).join(', ');
    el('#asset-owner').value = a.owner_id || '';
    el('#asset-attributes').value = JSON.stringify(a.attributes, null, 2);
    el('#modal-title').textContent = 'Edit Asset';
    el('#asset-modal').showModal();
  });
};

const deleteAsset = (id) => {
  api(`assets/${id}`).then(a => {
    el('#delete-asset-name').textContent = a.name;
    el('#delete-modal').dataset.assetId = id;
    el('#delete-modal').showModal();
  });
};

// ============= EVENT HANDLER INITIALIZATION =============
const setupAllHandlers = () => {
  // Asset management handlers
  el('#refresh').onclick = loadAssets;

  el('#new-asset').onclick = () => {
    el('#asset-id').value = '';
    el('#asset-name').value = '';
    el('#asset-type').value = '';
    el('#asset-mac').value = '';
    el('#asset-ips').value = '';
    el('#asset-owner').value = '';
    el('#asset-attributes').value = '';
    el('#modal-title').textContent = 'Add Asset';
    el('#asset-modal').showModal();
  };

  el('#asset-form').onsubmit = (e) => {
    e.preventDefault();
    const id = el('#asset-id').value;
    const data = {
      name: el('#asset-name').value,
      type: el('#asset-type').value,
      mac: el('#asset-mac').value || null,
      ips: el('#asset-ips').value.split(',').map(ip => ({ ip: ip.trim() })),
      owner_id: el('#asset-owner').value || null,
      attributes: el('#asset-attributes').value ? JSON.parse(el('#asset-attributes').value) : {}
    };
    const method = id ? 'PUT' : 'POST';
    const action = id ? `assets/${id}` : 'assets';
    api(action, method, data).then(r => {
      if (r.success) {
        el('#asset-modal').close();
        loadAssets();
      } else {
        alert('Error: ' + r.message);
      }
    });
  };

  el('#confirm-delete').onclick = () => {
    const id = el('#delete-modal').dataset.assetId;
    api(`assets/${id}`, 'DELETE').then(r => {
      if (r.success) {
        el('#delete-modal').close();
        loadAssets();
      } else {
        alert('Error: ' + r.message);
      }
    });
  };

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

  // Polling handlers
  el('#start-polling').onclick = () => {
    api('poller_start', 'POST').then(() => updatePollingStatus());
  };

  el('#stop-polling').onclick = () => {
    api('poller_stop', 'POST').then(() => updatePollingStatus());
  };
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupAuthHandlers();
  setupAllHandlers();
  setupSettingsListeners();
  checkSystemStatus();
  updatePollingStatus();
  setInterval(updatePollingStatus, 30000);
});
