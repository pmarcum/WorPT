/**
 * WorPT Dashboard web app (thin shell)
 * ====================================
 * Holds this group's settings and the few lines Google requires in a web app itself. Everything else is in the
 * WorPT Core library (identifier WorPTCore), and the page (Index.html) is fetched live from GitHub, so
 * improvements reach every user without changing this file.
 *
 * Script Properties (Project Settings → Script Properties):
 *   WORPT_CREDENTIAL               the WorPT server's key (from the VM's credential.conf); never shown to browsers
 *   WORPT_URL                      https://YOUR-SUBDOMAIN.duckdns.org/worpt   (no trailing slash)
 *   WORPT_ACCESS_CODE              the access code people type once; change it to shut out anyone you don't give the new one to
 *   ADMIN_EMAILS                   admins (see every proposal): Google emails separated by commas
 *   CORE_MEMBERS                   core members (may create proposals, never need the code): Google emails separated by commas
 *   WORPT_DASHBOARD_WEBAPP_VERSION the number of this file's version (worpt_dashboard_webapp_version in version.json)
 *
 * Deploy → New deployment → Web app: Execute as "User accessing the web app"; Who has access "Anyone with a Google account".
 * Later changes: Deploy → Manage deployments → Edit → New version (the link stays the same).
 */
function _cfg() {
  const p = PropertiesService.getScriptProperties();
  return {
    credential:    p.getProperty('WORPT_CREDENTIAL')  || '',
    serverUrl:     p.getProperty('WORPT_URL')         || '',
    accessCode:    p.getProperty('WORPT_ACCESS_CODE') || '',
    adminEmails:   p.getProperty('ADMIN_EMAILS')      || '',
    coreMembers:   p.getProperty('CORE_MEMBERS')      || '',
    dashUrl:       ScriptApp.getService().getUrl(),
    webAppVersion: parseInt(p.getProperty('WORPT_DASHBOARD_WEBAPP_VERSION'), 10) || 1,
  };
}

// The browser-tab icon (kept on GitHub, so a new picture needs no new version of this file).
const ICON = 'https://raw.githubusercontent.com/pmarcum/WorPT/main/images/worpt-favicon.png';

function doGet(e) {
  const params = (e && e.parameter) || {}, config = _cfg();
  const gate = WorPTCore.dashboardGate(config, params);
  if (gate) return HtmlService.createHtmlOutput(gate).setTitle('WorPT — access code').setFaviconUrl(ICON);
  const branch = WorPTCore.dashboardBranchName(params.branch || '');
  return HtmlService.createHtmlOutput(WorPTCore.fetchDashboardHtml(branch))
    .setTitle(branch === 'main' ? 'WorPT' : 'WorPT (test page: ' + branch + ')')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1').setFaviconUrl(ICON);
}

// The page calls google.script.run.gas('functionName', ...args); the library checks access on every call.
function gas(fn, ...args) { return WorPTCore.dispatch(_cfg(), fn, ...args); }

// Run once from the editor to grant the permissions (fetching the page and calling the server).
function authorize() { Logger.log('WorPT authorized for ' + Session.getActiveUser().getEmail()); UrlFetchApp.fetch('https://raw.githubusercontent.com/pmarcum/WorPT/main/version.json'); }
