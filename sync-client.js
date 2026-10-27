(function () {
  var KEY = 'collocate.supabase.settings.v2';
  var DEFAULTS = {
    url: 'https://wokmsbmlsrhjmyswotcp.supabase.co',
    key: 'sb_publishable_IdRngUxcbhBBCLc45971PQ_mvHxTA2t',
    syncId: 'tyc_sync_01',
    auto: false
  };
  var revision = null;
  var busy = false;
  function $(id) { return document.getElementById(id); }
  function read() {
    try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY) || '{}')); }
    catch (_) { return Object.assign({}, DEFAULTS); }
  }
  function save(value) { localStorage.setItem(KEY, JSON.stringify(value)); }
  function fields() {
    return {
      url: (($('sync-url') && $('sync-url').value) || '').trim().replace(/\/$/, ''),
      key: (($('sync-token') && $('sync-token').value) || '').trim(),
      syncId: (($('sync-id') && $('sync-id').value) || '').trim(),
      auto: !!($('sync-auto') && $('sync-auto').checked)
    };
  }
  function status(message) { var node = $('sync-status'); if (node) node.textContent = message; }
  function configured(s) { return !!(s.url && s.key && s.syncId); }
  function endpoint(s) { return s.url + '/rest/v1/collocate_states?sync_id=eq.' + encodeURIComponent(s.syncId); }
  function request(s, options) {
    options = options || {};
    var headers = {
      apikey: s.key,
      Authorization: 'Bearer ' + s.key,
      'X-Collocate-Sync-ID': s.syncId,
      Prefer: 'return=representation'
    };
    if (options.method && options.method !== 'GET') headers['Content-Type'] = 'application/json';
    headers = Object.assign(headers, options.headers || {});
    var requestOptions = Object.assign({}, options, {headers: headers});
    return fetch(endpoint(s), requestOptions).then(function (response) {
      return response.text().then(function (raw) {
        var data = null; try { data = raw ? JSON.parse(raw) : null; } catch (_) {}
        if (!response.ok) throw new Error((data && (data.message || data.hint || data.error)) || ('HTTP ' + response.status));
        return data;
      });
    });
  }
  function fill() {
    var value = read();
    if ($('sync-url')) $('sync-url').value = value.url || '';
    if ($('sync-token')) $('sync-token').value = value.key || '';
    if ($('sync-id')) $('sync-id').value = value.syncId || '';
    if ($('sync-auto')) $('sync-auto').checked = !!value.auto;
  }
  function pull() {
    if (busy) { status('Sync is already running. Please wait.'); return; }
    var s = fields();
    if (!configured(s)) { status('Please fill the Supabase settings first.'); return; }
    busy = true; save(s); status('Reading from Supabase...');
    request(s, {method: 'GET'}).then(function (rows) {
      var row = Array.isArray(rows) ? rows[0] : null;
      if (!row || !row.state) { revision = 0; status('Cloud is empty. Upload data from the device that has your records.'); return; }
      if (!window.CollocateSyncBridge) throw new Error('App bridge is unavailable. Refresh the page.');
      return window.CollocateSyncBridge.importState(row.state).then(function () {
        revision = Number(row.revision || 0);
        status('Downloaded cloud data, revision ' + revision + '.');
      });
    }).catch(function (error) { status('Download failed: ' + error.message); })
      .then(function () { busy = false; }, function () { busy = false; });
  }
  function push(silent) {
    if (busy) { if (!silent) status('Sync is already running. Please wait.'); return; }
    var s = fields();
    if (!configured(s)) { if (!silent) status('Please fill the Supabase settings first.'); return; }
    busy = true; save(s); if (!silent) status('Uploading to Supabase...');
    window.CollocateSyncBridge.exportState().then(function (state) {
      return request(s, {method: 'GET'}).then(function (rows) {
        var row = Array.isArray(rows) ? rows[0] : null;
        var remoteRevision = Number(row && row.revision || 0);
        if (row && revision !== null && remoteRevision !== revision) throw new Error('Cloud has a newer revision ' + remoteRevision + '. Download it first.');
        var next = remoteRevision + 1;
        var body = JSON.stringify({sync_id: s.syncId, revision: next, state: state, updated_at: new Date().toISOString()});
        return request(s, {method: row ? 'PATCH' : 'POST', body: body, headers: row ? {'If-Match': '*'} : {}}).then(function () {
          revision = next; status('Uploaded to cloud, revision ' + revision + '.');
        });
      });
    }).catch(function (error) { if (!silent || /newer revision/i.test(error.message)) status('Upload failed: ' + error.message); })
      .then(function () { busy = false; }, function () { busy = false; });
  }
  function start() {
    fill();
    document.querySelectorAll('[data-sync-open]').forEach(function (button) { button.addEventListener('click', function () { fill(); var dialog = $('sync-dialog'); if (dialog && dialog.showModal) dialog.showModal(); }); });
    document.querySelectorAll('[data-sync-close]').forEach(function (button) { button.addEventListener('click', function () { var dialog = $('sync-dialog'); if (dialog) dialog.close(); }); });
    if ($('sync-pull')) $('sync-pull').addEventListener('click', pull);
    if ($('sync-push')) $('sync-push').addEventListener('click', function () { push(false); });
    if ($('sync-form')) $('sync-form').addEventListener('submit', function (event) { event.preventDefault(); });
    status('Ready. Choose upload or download.');
    window.addEventListener('collocate-state-saved', function () { var s = read(); if (s.auto && configured(s)) push(true); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
