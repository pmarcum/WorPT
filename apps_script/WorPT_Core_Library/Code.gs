/**
 * WorPT Core library
 * ==================
 * Everything the WorPT dashboard does in Apps Script: the access gate, and passing each request on to the
 * WorPT server with the server's key, the signed-in person's Google email and their access level.
 * The key never leaves Apps Script: nothing returned to the browser contains it.
 *
 * Used by the WorPT_Dashboard_WebApp project (identifier WorPTCore). Each web app passes its configuration
 * (from its own Script Properties) as the first argument; see that project's Code.gs.
 *
 * Access (agreed 5-6 November 2026, as in BibMan):
 *   ADMIN_EMAILS  admins: see every proposal; never need the access code
 *   CORE_MEMBERS  core members: may create proposals; never need the access code
 *   everyone else signs in with Google and types WORPT_ACCESS_CODE once (remembered until it changes)
 * Emails are compared ignoring capitals; separate them with commas.
 */
const WORPT_CORE_LIBRARY_VERSION = 1;
const WORPT_REPO_RAW = 'https://raw.githubusercontent.com/pmarcum/WorPT/';

function getCoreVersion() { return WORPT_CORE_LIBRARY_VERSION; }

// ── who is who ─────────────────────────────────────────────────────────────────
function _email_() { return (Session.getActiveUser().getEmail() || '').trim(); }
function _inList_(list, email) {
  const me = (email || '').trim().toLowerCase();
  return !!me && String(list || '').toLowerCase().split(/[\s,;]+/).filter(Boolean).includes(me);
}
function _isAdmin_(config, email) { return _inList_(config.adminEmails, email); }
function _isCore_(config, email) { return _inList_(config.coreMembers, email) || _isAdmin_(config, email); }
function _accessLevel_(config, email) { return _isAdmin_(config, email) ? 'admin' : _isCore_(config, email) ? 'core' : 'code'; }

// ── the access code (remembered per person and per dashboard, as a hash of the code) ───────────────────────────
function _accessCode_(config) { return String(config.accessCode || '').trim(); }
function _sha256_(text) {
  return Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, text, Utilities.Charset.UTF_8));
}
function _accessKey_(config) { return 'worpt_access_' + _sha256_(config.dashUrl || 'dashboard').replace(/[^A-Za-z0-9]/g, '').slice(0, 16); }
function _accessMark_(config) { return _sha256_('worpt-access\n' + (config.dashUrl || '') + '\n' + _accessCode_(config)); }
function _hasAccess_(config) {
  if (!_accessCode_(config)) return false;
  let saved = '';
  try { saved = PropertiesService.getUserProperties().getProperty(_accessKey_(config)) || ''; } catch (e) { saved = ''; }
  return saved === _accessMark_(config);
}
function _rememberAccessCode_(config, typed) {
  const code = _accessCode_(config);
  if (!code || String(typed == null ? '' : typed).trim() !== code) return false;
  PropertiesService.getUserProperties().setProperty(_accessKey_(config), _accessMark_(config));
  return true;
}
/** Checked on every call, not only when the page opens: the functions behind the page can be called directly. */
function _requireAccess_(config) {
  const email = _email_();
  if (!email) throw new Error('WorPT: please sign in to your Google account, then open WorPT again.');
  if (_isCore_(config, email)) return email;
  if (!_accessCode_(config)) throw new Error('WorPT: no access code has been set up yet (Script Property WORPT_ACCESS_CODE).');
  if (!_hasAccess_(config)) throw new Error('WorPT: the access code has changed, or has not been entered. Reload WorPT to enter it.');
  return email;
}

// ── opening the page ───────────────────────────────────────────────────────────
/** '' when this person may open the dashboard, otherwise the HTML of the page to show instead. */
function dashboardGate(config, params) {
  params = params || {};
  const email = _email_();
  if (!email) return _gatePage_(config, params, 'Please sign in to your Google account, then open this link again.', false);
  if (!config.credential || !config.serverUrl) {
    return _gatePage_(config, params, 'WorPT is not set up yet. (For the administrator: set the Script Properties ' +
                      'WORPT_CREDENTIAL and WORPT_URL in the WorPT Dashboard project.)', false);
  }
  if (_isCore_(config, email)) return '';
  if (!_accessCode_(config)) {
    return _gatePage_(config, params, 'WorPT has no access code set up yet. (For the administrator: set the Script ' +
                      'Property WORPT_ACCESS_CODE in the WorPT Dashboard project.)', false);
  }
  if (params.access != null && String(params.access).trim() !== '') {
    if (_rememberAccessCode_(config, params.access)) return '';
    return _gatePage_(config, params, 'The access code in this link is not (or no longer) the right one. Please type the current code:', true);
  }
  if (_hasAccess_(config)) return '';
  return _gatePage_(config, params, 'Please type the WorPT access code you were given:', true);
}

function _esc_(t) { return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

function _gatePage_(config, params, message, withBox) {
  const branch = dashboardBranchName(params.branch || '');
  const target = (config.dashUrl || '') + (branch !== 'main' ? '?branch=' + encodeURIComponent(branch) : '');
  const box = !withBox ? '' :
    '<div style="margin-top:16px"><input id="c" type="password" autocomplete="off" autofocus aria-label="Access code" ' +
    'style="font-family:monospace;font-size:14px;padding:8px 10px;width:240px;border-radius:4px;border:1px solid #353540;' +
    'background:#0f0f11;color:#e8e8f0" onkeydown="if(event.key===\'Enter\')go()"> ' +
    '<button onclick="go()" style="font-family:monospace;font-size:13px;padding:8px 14px;border-radius:4px;border:0;' +
    'background:#7eb8f7;color:#0f0f11;font-weight:600;cursor:pointer">Open WorPT</button></div>' +
    '<p id="m" style="color:#a0a0ae;min-height:1.4em;margin-top:12px"></p>' +
    '<script>const T=' + JSON.stringify(target) + ';' +
    'function m(h){document.getElementById("m").innerHTML=h}' +
    'function go(){const v=document.getElementById("c").value;if(!v.trim())return;m("Checking…");' +
    'google.script.run.withSuccessHandler(function(r){if(r&&r.ok){' +
    'm(\'Code accepted. <a href="\'+T+\'" target="_top" style="color:#7eb8f7">Open WorPT</a>\');' +
    'try{window.open(T,"_top")}catch(e){}}' +
    'else{m("That code didn\'t work. Please check it with whoever gave you the WorPT link.")}})' +
    '.withFailureHandler(function(e){m(String(e&&e.message||e))}).gas("enterAccessCode",v)}</script>';
  return '<html><body style="font-family:monospace;background:#17171a;color:#e8e8f0;margin:0;padding:40px">' +
    '<h2 style="color:#7eb8f7;margin:0 0 12px">WorPT</h2><p style="line-height:1.6;max-width:560px">' + _esc_(message) + '</p>' +
    box + '</body></html>';
}

/** A ?branch=NAME link loads a test page from that branch; anything else means the normal page from main. */
function dashboardBranchName(branch) {
  return (typeof branch === 'string' && /^[A-Za-z0-9._-]{1,100}$/.test(branch)) ? branch : 'main';
}

/** The page lives on GitHub, so every group gets page improvements without redeploying anything. */
function fetchDashboardHtml(branch) {
  const b = dashboardBranchName(branch);
  try {
    const resp = UrlFetchApp.fetch(WORPT_REPO_RAW + encodeURIComponent(b) + '/Index.html?t=' + Date.now(), { muteHttpExceptions: true });
    if (resp.getResponseCode() === 200) return resp.getContentText();
  } catch (err) {
    Logger.log('WorPTCore.fetchDashboardHtml: ' + err.message);
  }
  const which = b === 'main' ? '' : ' test page from branch "' + _esc_(b) + '"';   // a missing test page never falls back to main
  return '<html><body style="font-family:monospace;padding:2em;background:#17171a;color:#e8e8f0">' +
    '<h3 style="color:#f77e7e">The WorPT dashboard' + which + ' is not available just now</h3>' +
    '<p>Could not fetch the page' + which + ' from GitHub. ' +
    (b === 'main' ? 'Please try again in a moment.' : 'Check that the branch exists and contains Index.html.') + '</p></body></html>';
}

// ── talking to the server ──────────────────────────────────────────────────────
/** One request to the WorPT server. Always returns the server's {status: ...} answer, or a plain error like it. */
function _api_(config, method, path, body) {
  const email = _email_();
  const options = {
    method: method, muteHttpExceptions: true, followRedirects: false,
    headers: { 'X-WorPT-Credential': config.credential, 'X-WorPT-User': email, 'X-WorPT-Access': _accessLevel_(config, email) },
  };
  if (body !== undefined && method !== 'get') { options.contentType = 'application/json'; options.payload = JSON.stringify(body); }
  let resp;
  try {
    resp = UrlFetchApp.fetch(String(config.serverUrl).replace(/\/+$/, '') + path, options);
  } catch (err) {
    return { status: 'error', code: 'unreachable', message: 'WorPT could not reach its server just now (' + err.message + '). Nothing was changed; please try again in a moment.' };
  }
  const code = resp.getResponseCode(), text = resp.getContentText();
  try {
    const out = JSON.parse(text);
    if (out && out.status) return out;
  } catch (e) { /* not JSON: nginx or gunicorn answered instead of WorPT */ }
  return { status: 'error', code: 'server', message: 'WorPT\'s server did not answer properly (HTTP ' + code + '). If this keeps happening, check the server: sudo systemctl status worpt.' };
}

const _id_ = v => encodeURIComponent(String(v));
const _q_ = obj => Object.keys(obj).filter(k => obj[k] !== undefined && obj[k] !== null)
  .map(k => encodeURIComponent(k) + '=' + encodeURIComponent(String(obj[k]))).join('&');

/** Every request the page can make. Anything not listed here is refused. */
const ROUTES = {
  me:               ()            => ['get', '/api/me'],
  listProposals:    ()            => ['get', '/api/proposals'],
  createProposal:   (b)           => ['post', '/api/proposals', b],
  getProposal:      (pid)         => ['get', '/api/proposals/' + _id_(pid)],
  changed:          (pid)         => ['get', '/api/proposals/' + _id_(pid) + '/changed'],
  updateProposal:   (pid, b)      => ['patch', '/api/proposals/' + _id_(pid), b],
  deleteProposal:   (pid, title)  => ['delete', '/api/proposals/' + _id_(pid) + '?' + _q_({ confirm_title: title })],
  history:          (pid)         => ['get', '/api/proposals/' + _id_(pid) + '/history?limit=300'],
  people:           (q)           => ['get', '/api/people?' + _q_({ q: q || '' })],
  createPerson:     (b)           => ['post', '/api/people', b],
  updatePerson:     (id, b)       => ['patch', '/api/people/' + _id_(id), b],
  addMember:        (pid, b)      => ['post', '/api/proposals/' + _id_(pid) + '/members', b],
  updateMember:     (id, b)       => ['patch', '/api/members/' + _id_(id), b],
  removeMember:     (id, confirm) => ['delete', '/api/members/' + _id_(id) + '?' + _q_({ confirm: confirm ? 1 : 0 })],
  addItem:          (pid, b)      => ['post', '/api/proposals/' + _id_(pid) + '/items', b],
  updateItem:       (id, b)       => ['patch', '/api/items/' + _id_(id), b],
  deleteItem:       (id, confirm) => ['delete', '/api/items/' + _id_(id) + '?' + _q_({ confirm: confirm ? 1 : 0 })],
  addAssignment:    (id, b)       => ['post', '/api/items/' + _id_(id) + '/assignments', b],
  updateAssignment: (id, b)       => ['patch', '/api/assignments/' + _id_(id), b],
  deleteAssignment: (id)          => ['delete', '/api/assignments/' + _id_(id)],
  addNonlabor:      (pid, b)      => ['post', '/api/proposals/' + _id_(pid) + '/nonlabor', b],
  updateNonlabor:   (id, b)       => ['patch', '/api/nonlabor/' + _id_(id), b],
  deleteNonlabor:   (id)          => ['delete', '/api/nonlabor/' + _id_(id)],
  tableNames:       (pid)         => ['get', '/api/proposals/' + _id_(pid) + '/tables'],
  table:            (pid, name)   => ['get', '/api/proposals/' + _id_(pid) + '/tables/' + _id_(name)],
};

function _call_(config, fn, args) {
  if (!Object.prototype.hasOwnProperty.call(ROUTES, fn)) return { status: 'error', code: 'unknown', message: 'WorPT does not know the request "' + fn + '".' };
  const r = ROUTES[fn].apply(null, args || []);
  return _api_(config, r[0], r[1], r[2]);
}

/**
 * dispatch: the one function the page calls (through the web app's gas()).
 *   gas('getProposal', pid)                      → the server's answer
 *   gas('change', pid, 'updateItem', id, fields) → {result, proposal}: the change, then the proposal as it now
 *     stands (only when the change succeeded), in one trip, so the ripple panel updates as soon as possible.
 */
function dispatch(config, fn, ...args) {
  if (fn === 'enterAccessCode') {                         // the one call allowed before the access code is entered
    if (!_email_()) throw new Error('WorPT: you are not signed in to a Google account.');
    return { ok: _rememberAccessCode_(config, args[0]) };
  }
  _requireAccess_(config);
  if (fn === 'getClientConfig') return getClientConfig(config);
  if (fn === 'change') {
    const pid = args[0], result = _call_(config, args[1], args.slice(2));
    const proposal = result.status === 'ok' && pid ? _call_(config, 'getProposal', [pid]) : null;
    return { result: result, proposal: proposal };
  }
  return _call_(config, fn, args);
}

// ── versions ───────────────────────────────────────────────────────────────────
function getClientConfig(config) {
  const email = _email_();
  let latest = {};
  try {
    const r = UrlFetchApp.fetch(WORPT_REPO_RAW + 'main/version.json?t=' + Date.now(), { muteHttpExceptions: true });
    if (r.getResponseCode() === 200) latest = JSON.parse(r.getContentText());
  } catch (e) { latest = {}; }
  const core = WORPT_CORE_LIBRARY_VERSION, app = config.webAppVersion || 1;
  return {
    email: email, access: _accessLevel_(config, email),
    coreLibraryVersion: core, webAppVersion: app,
    latestCoreLibrary: latest.worpt_core_library_version || core,
    latestWebApp: latest.worpt_dashboard_webapp_version || app,
    coreLibraryNotes: latest.worpt_core_library_notes || '',
    webAppNotes: latest.worpt_dashboard_webapp_notes || '',
  };
}
