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
