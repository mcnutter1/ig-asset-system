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

// ============= USER MANAGEMENT =============
let usersCache = [];
let currentOwnerFilter = '';

const loadUsers = () => {
  return api('users').then(users => {
    usersCache = users || [];
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

const getOwnerDisplayName = (asset) => {
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
};

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
      
      // Load custom fields when that tab is opened
      if (tabName === 'custom-fields') {
        loadCustomFields();
      }
    };
  });

  // Custom Fields Management
  if (el('#add-custom-field-btn')) {
    el('#add-custom-field-btn').onclick = () => {
      el('#field-modal-title').textContent = 'Add Custom Field';
      el('#field-id').value = '';
      el('#custom-field-form').reset();
      el('#custom-field-modal').showModal();
    };
  }

  if (el('#custom-field-form')) {
    el('#custom-field-form').onsubmit = (e) => {
      e.preventDefault();
      saveCustomField();
    };
  }

  // Show/hide select options based on field type
  if (el('#field-type')) {
    el('#field-type').onchange = (e) => {
      const selectOptionsContainer = el('#select-options-container');
      if (selectOptionsContainer) {
        selectOptionsContainer.style.display = e.target.value === 'select' ? 'block' : 'none';
      }
    };
  }
};

// ============= CUSTOM FIELDS =============
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
      const required = field.is_required ? '<span style="color: #ff6b6b;">*</span>' : '';
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
      container.innerHTML = '<p style="color: #ff6b6b;">Failed to load custom fields</p>';
    }
  });
};

const editCustomField = (id) => {
  api(`custom_field_get&id=${id}`).then(field => {
    el('#field-modal-title').textContent = 'Edit Custom Field';
    el('#field-id').value = field.id;
    el('#field-name').value = field.name;
    el('#field-label').value = field.label;
    el('#field-type').value = field.field_type;
    el('#field-default-value').value = field.default_value || '';
    el('#field-help-text').value = field.help_text || '';
    el('#field-required').checked = field.is_required;
    el('#field-display-order').value = field.display_order;
    
    // Handle applies_to_types
    el('#field-applies-to').value = field.applies_to_types ? field.applies_to_types.join(', ') : '';
    
    // Handle select options
    if (field.field_type === 'select' && field.select_options) {
      el('#field-select-options').value = field.select_options.join('\n');
      el('#select-options-container').style.display = 'block';
    } else {
      el('#select-options-container').style.display = 'none';
    }
    
    el('#custom-field-modal').showModal();
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
  const id = el('#field-id').value;
  const data = {
    name: el('#field-name').value,
    label: el('#field-label').value,
    field_type: el('#field-type').value,
    is_required: el('#field-required').checked,
    default_value: el('#field-default-value').value || null,
    help_text: el('#field-help-text').value || null,
    display_order: parseInt(el('#field-display-order').value) || 0
  };
  
  // Handle applies_to_types
  const appliesTo = el('#field-applies-to').value.trim();
  data.applies_to_types = appliesTo ? appliesTo.split(',').map(t => t.trim()).filter(t => t) : null;
  
  // Handle select options
  if (data.field_type === 'select') {
    const options = el('#field-select-options').value.trim();
    data.select_options = options ? options.split('\n').map(o => o.trim()).filter(o => o) : [];
  } else {
    data.select_options = null;
  }
  
  const action = id ? 'custom_field_update' : 'custom_field_create';
  if (id) data.id = id;
  
  api(action, 'POST', data).then(() => {
    el('#custom-field-modal').close();
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
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #888;">No assets found</td></tr>';
      return;
    }
    
    // Filter assets by owner if filter is set
    let filteredAssets = assets;
    if (currentOwnerFilter) {
      filteredAssets = assets.filter(a => a.owner_user_id == currentOwnerFilter);
    }
    
    if (filteredAssets.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #888;">No assets found for selected owner</td></tr>';
      return;
    }
    
    tbody.innerHTML = filteredAssets.map(a => {
      const ips = (a.ips || []).map(x => x.ip).join(', ') || '-';
      const statusColor = a.online_status === 'online' ? '#6dd17f' : '#ff6b6b';
      const lastSeen = a.updated_at ? new Date(a.updated_at).toLocaleString() : '-';
      const ownerName = getOwnerDisplayName(a);
      
      return `
        <tr>
          <td><strong>${a.name}</strong></td>
          <td>${a.type}</td>
          <td style="font-family: monospace; font-size: 0.9em;">${ips}</td>
          <td style="font-family: monospace; font-size: 0.9em;">${a.mac || '-'}</td>
          <td>${ownerName}</td>
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

// ============= CUSTOM FIELDS IN ASSETS =============
const renderCustomFieldsInModal = (assetType, customFieldValues = []) => {
  const container = el('#custom-fields-container');
  if (!container) return;
  
  // Get fields applicable to this asset type
  api(`custom_fields_for_type&type=${assetType || 'unknown'}`).then(fields => {
    if (!fields || fields.length === 0) {
      container.innerHTML = '';
      return;
    }
    
    container.innerHTML = '<hr><h4 style="margin-top: 15px;">Custom Fields</h4>' + fields.map(field => {
      // Find existing value for this field
      const fieldValue = customFieldValues.find(f => f.id === field.id);
      const value = fieldValue ? fieldValue.value : (field.default_value || '');
      const required = field.is_required ? 'required' : '';
      const star = field.is_required ? '<span style="color: #ff6b6b;">*</span>' : '';
      
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
    const ownerName = getOwnerDisplayName(a);
    
    // Build custom fields display
    let customFieldsHtml = '';
    if (a.custom_fields && a.custom_fields.length > 0) {
      const fieldsWithValues = a.custom_fields.filter(f => f.value);
      if (fieldsWithValues.length > 0) {
        customFieldsHtml = '<hr><h4>Custom Fields</h4>';
        fieldsWithValues.forEach(field => {
          let displayValue = field.value;
          if (field.field_type === 'checkbox') {
            displayValue = (field.value === 'true' || field.value === '1') ? '✓ Yes' : '✗ No';
          }
          customFieldsHtml += `<div class="kv"><strong>${field.label}:</strong> ${displayValue}</div>`;
        });
      }
    }
    
    content.innerHTML = `
      <h3>${a.name}</h3>
      <div class="kv"><strong>Type:</strong> ${a.type}</div>
      <div class="kv"><strong>Owner:</strong> ${ownerName}</div>
      <div class="kv"><strong>MAC:</strong> ${a.mac || '-'}</div>
      <div class="kv"><strong>IPs:</strong> ${(a.ips || []).map(x => x.ip).join(', ') || '-'}</div>
      <div class="kv"><strong>Status:</strong> ${a.online_status}</div>
      <div class="kv"><strong>Created:</strong> ${a.created_at}</div>
      <div class="kv"><strong>Updated:</strong> ${a.updated_at}</div>
      ${customFieldsHtml}
      ${hasAttributes ? `<hr><div class="kv"><strong>Attributes:</strong></div><pre>${JSON.stringify(a.attributes, null, 2)}</pre>` : ''}
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
      el('#asset-type').value = a.type || '';
      el('#asset-mac').value = a.mac || '';
      el('#asset-ips').value = (a.ips || []).map(x => x.ip).join(', ');
      el('#asset-owner').value = a.owner_user_id || '';
      
      // Handle attributes - only show if exists and has content
      const attrs = a.attributes && Object.keys(a.attributes).length > 0 ? a.attributes : {};
      el('#asset-attributes').value = Object.keys(attrs).length > 0 ? JSON.stringify(attrs, null, 2) : '';
      
      // Polling fields
      el('#asset-poll-enabled').checked = a.poll_enabled || false;
      el('#asset-poll-type').value = a.poll_type || 'ping';
      el('#asset-poll-username').value = a.poll_username || '';
      el('#asset-poll-password').value = a.poll_password || '';
      el('#asset-poll-port').value = a.poll_port || '';
      
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

  el('#asset-form').onsubmit = async (e) => {
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
      api('asset_update', 'POST', {id, ...data}).then(async r => {
        console.log('Update response:', r);
        if (r.success || r.ok) {
          // Save custom field values
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
          // Save custom field values for new asset
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
  loadUsers(); // Load users for owner dropdowns
  
  // Setup owner filter handler
  const ownerFilter = el('#owner-filter');
  if (ownerFilter) {
    ownerFilter.onchange = (e) => {
      currentOwnerFilter = e.target.value;
      loadAssets();
    };
  }
});
