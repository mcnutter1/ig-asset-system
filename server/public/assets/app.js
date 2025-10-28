// API Helper
const api = (action, method = 'GET', body = null, timeout = 30000) => {
  const url = '/api.php?action=' + encodeURIComponent(action);
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
  }).catch((err) => {
    console.error('System status check failed:', err);
    // Show login anyway if system status fails
    el('#bootstrap-warning')?.classList.add('hidden');
    el('#login-panel')?.classList.remove('hidden');
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
    el('#login-msg').style.color = '#ffaa00';

    api('login', 'POST', { username, password }).then(r => {
      if (r.ok && r.user) {
        el('#login-panel').classList.add('hidden');
        el('#main').classList.remove('hidden');
        el('#settings-btn').classList.remove('hidden');
        loadAssets();
        updatePollingStatus();
      } else {
        el('#login-msg').textContent = 'Login failed: ' + (r.error || 'Invalid credentials');
        el('#login-msg').style.color = '#ff6b6b';
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
      el('#login-msg').style.color = '#ff6b6b';
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
        let color = '#0f0'; // green for info
        if (log.level === 'error') color = '#ff6b6b';
        if (log.level === 'warning') color = '#ffaa00';
        if (log.level === 'success') color = '#6dd17f';
        
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
    const tbody = el('#asset-list');
    if (!assets || assets.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #888;">No assets found</td></tr>';
      return;
    }
    
    tbody.innerHTML = assets.map(a => {
      const ips = (a.ips || []).map(x => x.ip).join(', ') || '-';
      const statusColor = a.online_status === 'online' ? '#6dd17f' : '#ff6b6b';
      const lastSeen = a.updated_at ? new Date(a.updated_at).toLocaleString() : '-';
      
      return `
        <tr>
          <td><strong>${a.name}</strong></td>
          <td>${a.type}</td>
          <td style="font-family: monospace; font-size: 0.9em;">${ips}</td>
          <td style="font-family: monospace; font-size: 0.9em;">${a.mac || '-'}</td>
          <td><span style="color: ${statusColor};">● ${a.online_status}</span></td>
          <td style="font-size: 0.85em; color: #888;">${lastSeen}</td>
          <td style="white-space: nowrap;">
            <button onclick="viewAsset('${a.id}')" class="secondary" style="padding: 4px 12px; margin-right: 5px;">View</button>
            <button onclick="editAsset('${a.id}')" class="secondary" style="padding: 4px 12px; margin-right: 5px;">Edit</button>
            <button onclick="deleteAsset('${a.id}')" class="contrast" style="padding: 4px 12px;">Delete</button>
          </td>
        </tr>
      `;
    }).join('');
  });
};

const viewAsset = (id) => {
  console.log('viewAsset called with id:', id);
  api(`asset_get&id=${id}`).then(a => {
    console.log('Asset data:', a);
    const drawer = el('#drawer');
    const content = el('#asset-detail');
    const hasAttributes = a.attributes && Object.keys(a.attributes).length > 0;
    content.innerHTML = `
      <h3>${a.name}</h3>
      <div class="kv"><strong>Type:</strong> ${a.type}</div>
      <div class="kv"><strong>MAC:</strong> ${a.mac || '-'}</div>
      <div class="kv"><strong>IPs:</strong> ${(a.ips || []).map(x => x.ip).join(', ') || '-'}</div>
      <div class="kv"><strong>Status:</strong> ${a.online_status}</div>
      <div class="kv"><strong>Created:</strong> ${a.created_at}</div>
      <div class="kv"><strong>Updated:</strong> ${a.updated_at}</div>
      ${hasAttributes ? `<div class="kv"><strong>Attributes:</strong></div><pre>${JSON.stringify(a.attributes, null, 2)}</pre>` : ''}
    `;
    drawer.classList.remove('hidden');
  }).catch(err => {
    console.error('Error loading asset:', err);
    alert('Failed to load asset: ' + err.message);
  });
};

const editAsset = (id) => {
  console.log('editAsset called with id:', id);
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
    el('#asset-type').value = a.type || '';
    el('#asset-mac').value = a.mac || '';
    el('#asset-ips').value = (a.ips || []).map(x => x.ip).join(', ');
    el('#asset-owner').value = a.owner_id || a.owner_user_id || '';
    
    // Handle attributes - only show if exists and has content
    const attrs = a.attributes && Object.keys(a.attributes).length > 0 ? a.attributes : {};
    el('#asset-attributes').value = Object.keys(attrs).length > 0 ? JSON.stringify(attrs, null, 2) : '';
    
    // Polling fields
    el('#asset-poll-enabled').checked = a.poll_enabled || false;
    el('#asset-poll-type').value = a.poll_type || 'ping';
    el('#asset-poll-username').value = a.poll_username || '';
    el('#asset-poll-password').value = a.poll_password || '';
    el('#asset-poll-port').value = a.poll_port || '';
    
    el('#modal-title').textContent = 'Edit Asset';
    el('#asset-modal').showModal();
  }).catch(err => {
    console.error('Error loading asset for edit:', err);
    alert('Failed to load asset: ' + err.message);
  });
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
    el('#asset-poll-enabled').checked = false;
    el('#asset-poll-type').value = 'ping';
    el('#asset-poll-username').value = '';
    el('#asset-poll-password').value = '';
    el('#asset-poll-port').value = '';
    el('#modal-title').textContent = 'Add Asset';
    el('#asset-modal').showModal();
  };

  el('#asset-form').onsubmit = (e) => {
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
    
    const data = {
      name: el('#asset-name').value,
      type: el('#asset-type').value,
      mac: el('#asset-mac').value || null,
      ips: el('#asset-ips').value.split(',').map(ip => ip.trim()).filter(ip => ip),
      owner_user_id: el('#asset-owner').value || null,
      attributes: attributes,
      poll_enabled: el('#asset-poll-enabled').checked,
      poll_type: el('#asset-poll-type').value,
      poll_username: el('#asset-poll-username').value || null,
      poll_password: el('#asset-poll-password').value || null,
      poll_port: el('#asset-poll-port').value ? parseInt(el('#asset-poll-port').value) : null
    };
    
    if (id) {
      // Update existing asset
      console.log('Updating asset with ID:', id);
      console.log('Update data:', {id, ...data});
      api('asset_update', 'POST', {id, ...data}).then(r => {
        console.log('Update response:', r);
        if (r.success || r.ok) {
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
      api('asset_create', 'POST', data).then(r => {
        console.log('Create response:', r);
        if (r.success || r.ok) {
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

  el('#confirm-delete').onclick = () => {
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
