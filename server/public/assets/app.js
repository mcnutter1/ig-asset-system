const api = (a, method='GET', body=null, headers={}) => {
  const url = 'api.php?action=' + encodeURIComponent(a);
  return fetch(url, {
    method,
    headers: Object.assign({'Content-Type': 'application/json'}, headers),
    body: body ? JSON.stringify(body) : null,
    credentials: 'include'
  }).then(r => r.json());
};

const el = sel => document.querySelector(sel);
const list = el('#asset-list');
const drawer = el('#drawer');
const detail = el('#asset-detail');

// Check system status on page load
const checkSystemStatus = () => {
  console.log('Checking system status...');
  api('system_status').then((status) => {
    console.log('Bootstrap status:', status); // Debug log
    
    const bootstrapWarning = el('#bootstrap-warning');
    const loginPanel = el('#login-panel');
    
    console.log('Bootstrap warning element:', bootstrapWarning);
    console.log('Login panel element:', loginPanel);
    
    if (!status.bootstrapped) {
      console.log('System NOT bootstrapped - showing warning');
      // System not bootstrapped - show warning
      if (bootstrapWarning) bootstrapWarning.classList.remove('hidden');
      if (loginPanel) loginPanel.classList.add('hidden');
      el('#main')?.classList.add('hidden');
      el('#settings')?.classList.add('hidden');
    } else {
      console.log('System IS bootstrapped - hiding warning, showing login');
      // System is bootstrapped - hide warning and show login
      if (bootstrapWarning) {
        bootstrapWarning.classList.add('hidden');
        console.log('Bootstrap warning hidden');
      }
      if (loginPanel) {
        loginPanel.classList.remove('hidden');
        console.log('Login panel shown');
      }
    }
  }).catch((error) => {
    console.error('API error:', error); // Debug log
    // If API fails completely, show bootstrap warning
    el('#bootstrap-warning')?.classList.remove('hidden');
    el('#login-panel')?.classList.add('hidden');
    el('#main')?.classList.add('hidden');
    el('#settings')?.classList.add('hidden');
  });
};

// Initialize system status check
checkSystemStatus();

const renderAssetCard = (a) => {
  const ips = (a.ips||[]).map(x=>x.ip).join(', ');
  return `<div class="asset">
    <h3>${a.name} <span class="badge">${a.type}</span></h3>
    <div class="kv">ID: ${a.id}</div>
    <div class="kv">MAC: ${a.mac||'-'}</div>
    <div class="kv">IPs: ${ips||'-'}</div>
    <div class="kv">Online: <span class="badge">${a.online_status}</span></div>
    <div class="kv">Last Seen: ${a.last_seen||'-'}</div>
    <div class="flex" style="margin-top:8px">
      <button data-id="${a.id}" class="view">View</button>
    </div>
  </div>`;
};

const renderAssets = (items=[]) => {
  list.innerHTML = items.map(renderAssetCard).join('');
  list.querySelectorAll('.view').forEach(b => b.addEventListener('click', () => openDetail(b.dataset.id)));
};

const openDetail = (id) => api('asset_get&id='+id).then(a => {
  drawer.classList.remove('hidden');
  detail.innerHTML = `
    <h2>${a.name}</h2>
    <div class="flex">
      <span class="badge">${a.type}</span>
      <span class="badge">Owner: ${a.owner_user_id || '-'}</span>
      <span class="badge">Online: ${a.online_status}</span>
    </div>
    <h3>Identifiers</h3>
    <div class="kv">ID: ${a.id}</div>
    <div class="kv">MAC: ${a.mac || '-'}</div>
    <div class="kv">IPs: ${(a.ips||[]).map(x=>x.ip).join(', ') || '-'}</div>
    <h3>Attributes (JSON)</h3>
    <pre>${JSON.stringify(a.attributes || {}, null, 2)}</pre>
    <h3>Timeline</h3>
    <pre>${(a.changes||[]).map(c => `[${c.changed_at}] ${c.actor} (${c.source}) changed ${c.field}`).join('\n') || 'No changes'}</pre>
    <h3>Actions</h3>
    <button id="edit-btn">Edit</button>
    <button id="delete-btn" style="background:#3a1020;border-color:#5a1a33">Delete</button>
  `;
  el('#edit-btn').onclick = () => editAsset(a);
  el('#delete-btn').onclick = () => {
    if (confirm('Delete this asset?')) api('asset_delete&id='+a.id, 'DELETE').then(()=>{ drawer.classList.add('hidden'); load(); });
  };
});

const editAsset = (a) => {
  const name = prompt('Name', a.name);
  if (name===null) return;
  const mac = prompt('MAC', a.mac||'');
  const ips = prompt('IP list (comma-separated)', (a.ips||[]).map(x=>x.ip).join(', '));
  const attrs = prompt('Attributes JSON', JSON.stringify(a.attributes||{}, null, 2));
  const payload = { id:a.id, name, mac, ips: ips? ips.split(',').map(x=>x.trim()).filter(Boolean):[], attributes: JSON.parse(attrs||'{}') };
  api('asset_update','POST',payload).then(()=>openDetail(a.id));
};

const load = () => {
  const q = el('#search').value.trim();
  api('assets'+(q? '&q='+encodeURIComponent(q):'')).then(renderAssets);
};

// Login wiring
el('#login-btn').onclick = () => {
  const username = el('#username').value.trim();
  const password = el('#password').value.trim();
  api('login','POST',{username,password}).then((r)=>{
    el('#login-panel').classList.add('hidden');
    el('#main').classList.remove('hidden');
    el('#user-info').textContent = r.user.display_name || r.user.username;
    
    // Show admin controls for admin users
    if (r.user.role === 'admin') {
      el('#admin-controls').classList.remove('hidden');
    }
    
    load();
  }).catch(()=> el('#login-msg').textContent = 'Login failed');
};

el('#refresh').onclick = load;
el('#new-asset').onclick = () => {
  const name = prompt('Asset name'); if (!name) return;
  api('asset_create','POST',{name}).then(()=>load());
};
el('#search').addEventListener('keydown', (e)=>{ if (e.key==='Enter') load(); });
el('.close').onclick = ()=> drawer.classList.add('hidden');

// Settings functionality
el('#settings-btn').onclick = () => {
  el('#main').classList.add('hidden');
  el('#settings').classList.remove('hidden');
  loadLdapSettings();
};

el('#back-to-main').onclick = () => {
  el('#settings').classList.add('hidden');
  el('#main').classList.remove('hidden');
};

const loadLdapSettings = () => {
  api('settings_get&category=ldap').then((settings) => {
    el('#ldap-enabled').checked = settings.enabled?.value === 'true';
    el('#ldap-host').value = settings.host?.value || '';
    el('#ldap-port').value = settings.port?.value || '389';
    el('#ldap-bind-dn').value = settings.bind_dn?.value || '';
    el('#ldap-bind-password').value = settings.bind_password?.value || '';
    el('#ldap-base-dn').value = settings.base_dn?.value || '';
    el('#ldap-user-attr').value = settings.user_attr?.value || 'sAMAccountName';
  });
};

el('#ldap-form').onsubmit = (e) => {
  e.preventDefault();
  const settings = {
    enabled: el('#ldap-enabled').checked ? 'true' : 'false',
    host: el('#ldap-host').value,
    port: el('#ldap-port').value,
    bind_dn: el('#ldap-bind-dn').value,
    bind_password: el('#ldap-bind-password').value,
    base_dn: el('#ldap-base-dn').value,
    user_attr: el('#ldap-user-attr').value
  };
  
  api('settings_update', 'POST', { category: 'ldap', settings }).then((r) => {
    if (r.success) {
      showLdapStatus('Settings saved successfully', 'success');
    } else {
      showLdapStatus('Failed to save settings', 'error');
    }
  });
};

el('#test-ldap').onclick = () => {
  const settings = {
    host: { value: el('#ldap-host').value },
    port: { value: el('#ldap-port').value },
    bind_dn: { value: el('#ldap-bind-dn').value },
    bind_password: { value: el('#ldap-bind-password').value },
    base_dn: { value: el('#ldap-base-dn').value },
    user_attr: { value: el('#ldap-user-attr').value }
  };
  
  api('ldap_test', 'POST', { settings }).then((result) => {
    showLdapStatus(result.message, result.success ? 'success' : 'error');
  });
};

el('#import-ldap').onclick = () => {
  if (!confirm('Import users from LDAP? This may take a while.')) return;
  
  api('ldap_import', 'POST', {}).then((result) => {
    showLdapStatus(result.message, result.success ? 'success' : 'error');
  });
};

const showLdapStatus = (message, type) => {
  const status = el('#ldap-status');
  status.textContent = message;
  status.className = type;
  setTimeout(() => {
    status.textContent = '';
    status.className = '';
  }, 5000);
};

// Modal management
const showModal = (title, content) => {
  el('#modal-title').textContent = title;
  el('#modal-content').innerHTML = content;
  el('#modal').classList.remove('hidden');
};

const hideModal = () => {
  el('#modal').classList.add('hidden');
};

// Modern settings management
const showSettings = () => {
  el('#main').classList.add('hidden');
  el('#settings').classList.remove('hidden');
  loadModernSettingsContent();
};

const hideSettings = () => {
  el('#settings').classList.add('hidden');
  el('#main').classList.remove('hidden');
};

const loadModernSettingsContent = () => {
  const content = `
    <div class="settings-nav">
      <button class="settings-tab active" data-tab="ldap">LDAP Settings</button>
      <button class="settings-tab" data-tab="poller">Polling Configuration</button>
      <button class="settings-tab" data-tab="system">System Settings</button>
    </div>
    <div class="settings-content">
      <div id="ldap-settings" class="settings-panel active">
        <h3>LDAP Configuration</h3>
        <form id="modern-ldap-form">
          <div class="form-group">
            <label>LDAP Server:</label>
            <input type="text" id="modern-ldap-server" placeholder="ldap://domain.com:389">
          </div>
          <div class="form-group">
            <label>Base DN:</label>
            <input type="text" id="modern-ldap-base-dn" placeholder="dc=domain,dc=com">
          </div>
          <div class="form-group">
            <label>Bind DN:</label>
            <input type="text" id="modern-ldap-bind-dn" placeholder="cn=admin,dc=domain,dc=com">
          </div>
          <div class="form-group">
            <label>Bind Password:</label>
            <input type="password" id="modern-ldap-bind-password">
          </div>
          <div class="form-group">
            <label>User Filter:</label>
            <input type="text" id="modern-ldap-user-filter" placeholder="(objectClass=person)">
          </div>
          <div class="form-group">
            <label>Username Attribute:</label>
            <input type="text" id="modern-ldap-user-attr" placeholder="sAMAccountName">
          </div>
          <div class="form-actions">
            <button type="button" onclick="testModernLdapConnection()">Test Connection</button>
            <button type="button" onclick="importModernLdapUsers()">Import Users</button>
            <button type="submit">Save LDAP Settings</button>
          </div>
          <div id="modern-ldap-status" class="status-message"></div>
        </form>
      </div>
      
      <div id="poller-settings" class="settings-panel">
        <h3>Polling Configuration</h3>
        <form id="poller-form">
          <div class="form-group">
            <label>Polling Interval (seconds):</label>
            <input type="number" id="poller-interval" min="5" max="3600" value="30">
            <small>How often to poll targets (5-3600 seconds)</small>
          </div>
          <div class="form-group">
            <label>Connection Timeout (seconds):</label>
            <input type="number" id="poller-timeout" min="1" max="60" value="10">
            <small>SSH/HTTP connection timeout (1-60 seconds)</small>
          </div>
          <div class="form-group">
            <label>Ping Timeout (seconds):</label>
            <input type="number" id="poller-ping-timeout" min="1" max="10" value="1">
            <small>Network ping timeout (1-10 seconds)</small>
          </div>
          <div class="form-group">
            <label>API URL:</label>
            <input type="url" id="poller-api-url" placeholder="http://localhost:8080/api.php">
            <small>API endpoint for poller to send updates</small>
          </div>
          <div class="form-group">
            <label>API Key:</label>
            <input type="text" id="poller-api-key" placeholder="Enter API authentication key">
            <small>Authentication key for API access</small>
          </div>
          <div class="form-actions">
            <button type="submit">Save Polling Settings</button>
          </div>
          <div id="poller-config-status" class="status-message"></div>
        </form>
        
        <div class="polling-control">
          <h4>Polling Control</h4>
          <div class="control-buttons">
            <button id="start-polling-settings" onclick="startPollingFromSettings()">Start Polling</button>
            <button id="stop-polling-settings" onclick="stopPollingFromSettings()">Stop Polling</button>
            <span id="polling-status-settings">Status: Unknown</span>
          </div>
        </div>
      </div>
      
      <div id="system-settings" class="settings-panel">
        <h3>System Settings</h3>
        <div class="system-info">
          <h4>System Status</h4>
          <div id="system-health-display"></div>
        </div>
        <div class="system-actions">
          <button onclick="checkSystemHealth()">Check System Health</button>
          <button onclick="downloadSystemLogs()">Download Logs</button>
        </div>
      </div>
    </div>
  `;
  
  el('#settings-container').innerHTML = content;
  
  // Load current settings
  loadModernLdapSettings();
  loadPollerConfigSettings();
  updatePollingStatusInSettings();
  
  // Setup tab switching
  document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.onclick = () => switchSettingsTab(tab.dataset.tab);
  });
};

const switchSettingsTab = (tabName) => {
  document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });
  
  document.querySelectorAll('.settings-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === tabName + '-settings');
  });
};

// Modern LDAP functions
const loadModernLdapSettings = () => {
  api('settings_get&category=ldap').then(settings => {
    if (settings) {
      el('#modern-ldap-server').value = settings.host?.value || '';
      el('#modern-ldap-base-dn').value = settings.base_dn?.value || '';
      el('#modern-ldap-bind-dn').value = settings.bind_dn?.value || '';
      el('#modern-ldap-bind-password').value = settings.bind_password?.value || '';
      el('#modern-ldap-user-filter').value = settings.user_filter?.value || '';
      el('#modern-ldap-user-attr').value = settings.user_attr?.value || '';
    }
  });
  
  const form = el('#modern-ldap-form');
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      saveModernLdapSettings();
    };
  }
};

const saveModernLdapSettings = () => {
  const settings = {
    host: el('#modern-ldap-server').value,
    base_dn: el('#modern-ldap-base-dn').value,
    bind_dn: el('#modern-ldap-bind-dn').value,
    bind_password: el('#modern-ldap-bind-password').value,
    user_filter: el('#modern-ldap-user-filter').value,
    user_attr: el('#modern-ldap-user-attr').value
  };
  
  api('settings_update', 'POST', { category: 'ldap', settings }).then(response => {
    showStatusMessage('modern-ldap-status', response.success ? 'LDAP settings saved successfully' : 'Failed to save LDAP settings', response.success ? 'success' : 'error');
  });
};

const testModernLdapConnection = () => {
  const settings = {
    host: { value: el('#modern-ldap-server').value },
    base_dn: { value: el('#modern-ldap-base-dn').value },
    bind_dn: { value: el('#modern-ldap-bind-dn').value },
    bind_password: { value: el('#modern-ldap-bind-password').value },
    user_filter: { value: el('#modern-ldap-user-filter').value },
    user_attr: { value: el('#modern-ldap-user-attr').value }
  };
  
  showStatusMessage('modern-ldap-status', 'Testing LDAP connection...', 'info');
  api('ldap_test', 'POST', { settings }).then(result => {
    showStatusMessage('modern-ldap-status', result.message, result.success ? 'success' : 'error');
  });
};

const importModernLdapUsers = () => {
  if (!confirm('Import users from LDAP? This may take a while.')) return;
  
  showStatusMessage('modern-ldap-status', 'Importing LDAP users...', 'info');
  api('ldap_import', 'POST', {}).then(result => {
    showStatusMessage('modern-ldap-status', result.message, result.success ? 'success' : 'error');
  });
};

// Poller configuration functions
const loadPollerConfigSettings = () => {
  api('poller_config').then(config => {
    el('#poller-interval').value = config.interval || 30;
    el('#poller-timeout').value = config.timeout || 10;
    el('#poller-ping-timeout').value = config.ping_timeout || 1;
    el('#poller-api-url').value = config.api_url || '';
    el('#poller-api-key').value = config.api_key || '';
  });
  
  const form = el('#poller-form');
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      savePollerConfigSettings();
    };
  }
};

const savePollerConfigSettings = () => {
  const config = {
    interval: el('#poller-interval').value,
    timeout: el('#poller-timeout').value,
    ping_timeout: el('#poller-ping-timeout').value,
    api_url: el('#poller-api-url').value,
    api_key: el('#poller-api-key').value
  };
  
  api('poller_config_update', 'POST', config).then(response => {
    showStatusMessage('poller-config-status', response.success ? 'Polling settings saved successfully' : 'Failed to save polling settings', response.success ? 'success' : 'error');
  });
};

const startPollingFromSettings = () => {
  api('poller_start', 'POST').then(response => {
    if (response.success) {
      updatePollingStatusInSettings();
    } else {
      showStatusMessage('poller-config-status', 'Failed to start poller: ' + response.message, 'error');
    }
  });
};

const stopPollingFromSettings = () => {
  api('poller_stop', 'POST').then(response => {
    if (response.success) {
      updatePollingStatusInSettings();
    } else {
      showStatusMessage('poller-config-status', 'Failed to stop poller: ' + response.message, 'error');
    }
  });
};

const updatePollingStatusInSettings = () => {
  api('poller_status').then(status => {
    const statusElSettings = el('#polling-status-settings');
    const startBtnSettings = el('#start-polling-settings');
    const stopBtnSettings = el('#stop-polling-settings');
    
    const statusText = status.status === 'running' 
      ? `Status: Running (${status.targets_count} targets)`
      : `Status: Stopped (${status.targets_count} targets)`;
    const statusColor = status.status === 'running' ? '#6dd17f' : '#ff6b6b';
    
    if (statusElSettings) {
      statusElSettings.textContent = statusText;
      statusElSettings.style.color = statusColor;
    }
    
    const isRunning = status.status === 'running';
    if (startBtnSettings) startBtnSettings.disabled = isRunning;
    if (stopBtnSettings) stopBtnSettings.disabled = !isRunning;
    
    if (status.last_run && statusElSettings) {
      statusElSettings.title = `Last run: ${status.last_run}`;
    }
  }).catch(() => {
    const statusElSettings = el('#polling-status-settings');
    if (statusElSettings) {
      statusElSettings.textContent = 'Status: Error';
      statusElSettings.style.color = '#ff6b6b';
    }
  });
};

// System health functions
const checkSystemHealth = () => {
  api('system_health').then(health => {
    const healthEl = el('#system-health-display');
    if (healthEl) {
      healthEl.innerHTML = `
        <div class="health-item">Database: ${health.database ? '✅ Connected' : '❌ Error'}</div>
        <div class="health-item">PHP Version: ${health.php_version || 'Unknown'}</div>
        <div class="health-item">Disk Space: ${health.disk_free || 'Unknown'}</div>
        <div class="health-item">Memory Usage: ${health.memory_usage || 'Unknown'}</div>
      `;
    }
  });
};

const downloadSystemLogs = () => {
  alert('Log download functionality would be implemented here');
};

// Utility function for status messages
const showStatusMessage = (elementId, message, type) => {
  const statusEl = el('#' + elementId);
  if (statusEl) {
    statusEl.textContent = message;
    statusEl.className = 'status-message ' + type;
    setTimeout(() => {
      statusEl.textContent = '';
      statusEl.className = 'status-message';
    }, 5000);
  }
};
