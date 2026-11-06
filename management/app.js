'use strict';
const $ = (id) => document.getElementById(id);
let apps = [];
let editing = null;
let nextId = 1;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function load() {
  try {
    const response = await fetch('/api/apps');
    if (!response.ok) throw new Error('Could not load the application catalog.');
    const data = await response.json(); apps = data.apps; nextId = data.next_id;
    $('error').hidden = true; render();
  } catch (error) { $('error').textContent = error.message; $('error').hidden = false; }
}
function render() {
  $('total').textContent = apps.length;
  $('active').textContent = apps.filter(a => a.status === 'active').length;
  $('planned').textContent = apps.filter(a => a.status === 'planned').length;
  $('next').textContent = 'A' + String(nextId).padStart(3, '0');
  const query = $('search').value.trim().toLowerCase();
  const filtered = apps.filter(a => (a.name + ' ' + a.id + ' ' + a.slug + ' ' + a.description).toLowerCase().includes(query) && ($('filter').value === 'all' || a.status === $('filter').value));
  $('rows').replaceChildren(); $('empty').hidden = filtered.length !== 0;
  filtered.forEach((app, index) => {
    const row = element('tr'); row.append(element('td', app.id));
    const nameCell = element('td'), content = element('div', undefined, 'app-cell');
    const icon = element('span', ['◷', '◇', '✦', '✳'][index % 4], 'app-icon'); icon.setAttribute('aria-hidden', 'true');
    const detail = element('div'); detail.append(element('div', app.name, 'app-name'), element('div', app.description || app.slug, 'app-desc'));
    content.append(icon, detail); nameCell.append(content); row.append(nameCell);
    const status = element('td'); status.append(element('span', app.status[0].toUpperCase() + app.status.slice(1), 'status ' + app.status)); row.append(status);
    row.append(element('td', app.version ? 'v' + app.version : '—', 'version'));
    const actions = element('td'), buttons = element('div', undefined, 'row-actions');
    if (app.version) { const link = element('a', 'Releases ↗'); link.href = 'https://github.com/zxiaox/fishfish/releases/tag/' + encodeURIComponent(app.slug + '-v' + app.version); link.target = '_blank'; link.rel = 'noopener noreferrer'; buttons.append(link); }
    const edit = element('button', 'Edit'); edit.type = 'button'; edit.addEventListener('click', () => openForm(app)); buttons.append(edit); actions.append(buttons); row.append(actions); $('rows').append(row);
  });
}
function openForm(app = null) {
  editing = app; $('form').reset(); $('form-error').hidden = true;
  $('dialog-title').textContent = app ? 'Edit ' + app.id : 'Add application';
  const form = $('form'); form.elements.slug.readOnly = !!app;
  if (app) for (const key of ['name','slug','description','status']) form.elements[key].value = app[key];
  $('dialog').showModal(); form.elements.name.focus();
}
$('add').addEventListener('click', () => openForm());
$('close').addEventListener('click', () => $('dialog').close());
$('cancel').addEventListener('click', () => $('dialog').close());
$('search').addEventListener('input', render); $('filter').addEventListener('change', render);
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  try {
    const response = await fetch(editing ? '/api/apps/' + editing.id : '/api/apps', {method: editing ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(values)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Could not save application.');
    $('dialog').close(); await load();
  } catch (error) { $('form-error').textContent = error.message; $('form-error').hidden = false; }
});
load();
