"""Build a generic, empty-state cross-model comparison HTML.

Output: backend/data/thinking_styles/trace_dump/comparison.html

The HTML starts empty. The user loads jsonl files via a button (or drops them
on the left pane); each file adds a new model column. Rows are the union of
(task_id, style, topology) seen across loaded files; cells missing in a file
are rendered as null (—). Clicking a PASS/FAIL cell renders that trial's
trace inside the right pane. The right pane also has an "Open external .md"
button (and drop area) for viewing arbitrary markdown files.

No data is embedded at build time; the file is self-contained and works from
file://.
"""
import argparse
from pathlib import Path


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>cross-model comparison</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  html, body { height: 100%; margin: 0; padding: 0; }
  body { font-family: -apple-system, system-ui, sans-serif; background: #fafafa; color: #1a1a1a; display: grid; grid-template-columns: 1fr 1fr; height: 100vh; overflow: hidden; }
  .pane { overflow: auto; height: 100vh; position: relative; }
  .pane.left { border-right: 1px solid #ccc; }
  header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 10px 16px; z-index: 10; }
  header h1 { font-size: 14px; margin: 0 0 6px 0; color: #444; font-weight: 600; }
  header .controls { display: flex; gap: 10px; align-items: center; font-size: 12px; flex-wrap: wrap; }
  header label { display: flex; gap: 4px; align-items: center; }
  header select { font-size: 12px; padding: 2px 4px; }
  header button { font-size: 12px; padding: 4px 10px; cursor: pointer; border: 1px solid #888; background: #fff; border-radius: 4px; }
  header button:hover { background: #eef; }
  header .legend { margin-left: auto; font-size: 11px; color: #555; }
  header .legend .swatch { display: inline-block; width: 11px; height: 11px; vertical-align: middle; margin-right: 4px; border-radius: 2px; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  thead th { position: sticky; top: 70px; background: #f0f0f0; border-bottom: 2px solid #999; padding: 6px 8px; text-align: left; z-index: 5; }
  thead th.model-head { text-align: center; }
  thead .summary { font-size: 10px; font-weight: normal; color: #555; margin-top: 2px; }
  td { padding: 3px 6px; border-bottom: 1px solid #eee; white-space: nowrap; }
  td.task, td.style, td.topo, td.level, td.days { font-family: ui-monospace, monospace; font-size: 11px; color: #444; }
  td.level.easy { color: #16a34a; }
  td.level.medium { color: #d97706; }
  td.level.hard { color: #dc2626; }
  td.days { text-align: right; }
  td.al { text-align: center; color: #d97706; font-weight: bold; }
  tr.task-alt { background: #fbfbfb; }
  tr.aligned { background: #fffaf0; }
  tr.aligned.task-alt { background: #fef3e2; }
  tr.task-start td { border-top: 2px solid #bbb; }
  td.pass { background: #d1fadf; text-align: center; cursor: pointer; }
  td.fail { background: #ffd5d5; text-align: center; cursor: pointer; }
  td.missing { background: #f5f5f5; text-align: center; color: #aaa; }
  td.pass:hover, td.fail:hover { filter: brightness(0.95); }
  td.pass .lab, td.fail .lab { font-weight: 600; padding: 2px 6px; }
  td.selected { outline: 3px solid #2563eb; outline-offset: -3px; }
  tr.hidden { display: none; }
  .empty-msg { padding: 40px 24px; color: #888; font-size: 13px; text-align: center; }
  /* right pane viewer */
  .pane.right { background: #fff; display: flex; flex-direction: column; }
  .viewer-header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 10px 16px; z-index: 10; font-size: 13px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .viewer-header button { font-size: 12px; padding: 4px 10px; cursor: pointer; border: 1px solid #888; background: #fff; border-radius: 4px; }
  .viewer-header button:hover { background: #eef; }
  .viewer-header .fname { font-family: ui-monospace, monospace; font-size: 12px; color: #555; }
  #content { padding: 20px 24px; overflow: auto; flex: 1; }
  .pane.dragover { background: #eef6ff; outline: 2px dashed #4a90e2; outline-offset: -16px; }
  #content h1 { font-size: 18px; }
  #content h2 { font-size: 16px; margin-top: 18px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
  #content h3 { font-size: 14px; margin-top: 14px; color: #1a4c8b; }
  #content code, #content pre { font-family: ui-monospace, monospace; font-size: 12px; }
  #content pre { background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
  #content blockquote { border-left: 3px solid #ccc; margin: 0; padding: 4px 12px; color: #555; }
  #content ul { padding-left: 20px; }
</style>
</head>
<body>
<div class="pane left">
  <header>
    <h1 id="title">cross-model comparison — <span id="title-status">no files loaded</span></h1>
    <div class="controls">
      <button id="load-jsonl">Load jsonl files…</button>
      <button id="clear-all">Clear</button>
      <label>task <select id="f-task"><option value="">(all)</option></select></label>
      <label>style <select id="f-style"><option value="">(all)</option></select></label>
      <label>topology <select id="f-topo"><option value="">(all)</option></select></label>
      <label><input type="checkbox" id="f-aligned" /> aligned only</label>
      <label><input type="checkbox" id="f-fail" /> any-fail only</label>
      <span class="legend">
        <span class="swatch" style="background:#d1fadf"></span>PASS
        <span class="swatch" style="background:#ffd5d5"></span>FAIL
        <span class="swatch" style="background:#f5f5f5"></span>null
        <span class="swatch" style="background:#fffaf0"></span>aligned
      </span>
    </div>
  </header>
  <div id="table-container">
    <div class="empty-msg">Click "Load jsonl files…" above (or drop .jsonl files onto this pane) to start comparing.</div>
  </div>
</div>
<div class="pane right">
  <div class="viewer-header">
    <span>📄 Viewer</span>
    <button id="open-md">Open external .md</button>
    <span class="fname" id="fname"></span>
  </div>
  <div id="content"><div class="empty-msg">Click a PASS/FAIL cell on the left to render that trial here.<br/>Or use "Open external .md" / drop a .md file on this pane.</div></div>
</div>

<input type="file" id="jsonl-input" accept=".jsonl,application/json" multiple style="display:none" />
<input type="file" id="md-input" accept=".md,text/markdown,text/plain" style="display:none" />

<script>
// ---------- state ----------
const state = {
  models: [],                  // [{key, label, fileName, trials: Map<rowKey, trialRow>, pass, fail}]
  rowKeys: [],                 // ordered list of "task||style||topo" keys
  rowMeta: new Map(),          // rowKey -> {task, style, topo}
  styles: [],                  // discovered styles in arrival order
  topos: [],
  tasks: [],                   // sorted by numeric suffix
  selected: null,              // {modelKey, rowKey}
};

function safe(s) { return String(s).replace(/[^A-Za-z0-9._-]+/g, "_"); }
function taskNum(t) { const m = /(\d+)/.exec(t); return m ? parseInt(m[1], 10) : 0; }
function rowKey(t, s, tp) { return t + "||" + s + "||" + tp; }
function uniqueModelKey(label, fileName) {
  // ensure unique even if same model loaded twice
  let base = label || fileName || ("model" + (state.models.length + 1));
  let k = base, i = 2;
  while (state.models.some(m => m.key === k)) { k = base + " #" + i; i++; }
  return k;
}

// ---------- jsonl ingest ----------
function addJsonlFile(text, fileName) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    let r; try { r = JSON.parse(line); } catch (e) { continue; }
    rows.push(r);
  }
  if (!rows.length) { alert("No rows parsed from " + fileName); return; }
  const label = rows[0].model || fileName.replace(/\.jsonl$/i, "");
  const key = uniqueModelKey(label, fileName);
  const trials = new Map();
  let pass = 0, fail = 0;
  for (const r of rows) {
    const k = rowKey(r.task_id, r.style_id, r.topology);
    trials.set(k, r);
    if (r.metrics && r.metrics.final_pass) pass++; else fail++;
    if (!state.rowMeta.has(k)) {
      state.rowMeta.set(k, { task: r.task_id, style: r.style_id, topo: r.topology, level: r.level, days: r.days });
      state.rowKeys.push(k);
    }
    if (!state.styles.includes(r.style_id)) state.styles.push(r.style_id);
    if (!state.topos.includes(r.topology)) state.topos.push(r.topology);
    if (!state.tasks.includes(r.task_id)) state.tasks.push(r.task_id);
  }
  state.models.push({ key, label, fileName, trials, pass, fail });
  state.tasks.sort((a, b) => taskNum(a) - taskNum(b) || a.localeCompare(b));
  // re-sort rowKeys by (task num, style order, topo order)
  state.rowKeys.sort((a, b) => {
    const ma = state.rowMeta.get(a), mb = state.rowMeta.get(b);
    const da = taskNum(ma.task) - taskNum(mb.task); if (da) return da;
    const sa = state.styles.indexOf(ma.style) - state.styles.indexOf(mb.style); if (sa) return sa;
    return state.topos.indexOf(ma.topo) - state.topos.indexOf(mb.topo);
  });
  rebuildFilterOptions();
  renderTable();
  updateTitle();
}

function clearAll() {
  state.models = []; state.rowKeys = []; state.rowMeta.clear();
  state.styles = []; state.topos = []; state.tasks = []; state.selected = null;
  rebuildFilterOptions();
  document.getElementById('table-container').innerHTML =
    '<div class="empty-msg">Click "Load jsonl files…" above (or drop .jsonl files onto this pane) to start comparing.</div>';
  document.getElementById('content').innerHTML =
    '<div class="empty-msg">Click a PASS/FAIL cell on the left to render that trial here.<br/>Or use "Open external .md" / drop a .md file on this pane.</div>';
  document.getElementById('fname').textContent = '';
  updateTitle();
}

function updateTitle() {
  const ts = document.getElementById('title-status');
  if (!state.models.length) { ts.textContent = 'no files loaded'; return; }
  ts.textContent = state.models.length + ' file(s), ' + state.rowKeys.length + ' rows';
}

function rebuildFilterOptions() {
  const sel = (id, vals) => {
    const el = document.getElementById(id);
    const cur = el.value;
    el.innerHTML = '<option value="">(all)</option>' + vals.map(v => '<option value="'+v+'">'+v+'</option>').join('');
    if (vals.includes(cur)) el.value = cur;
  };
  sel('f-task', state.tasks);
  sel('f-style', state.styles);
  sel('f-topo', state.topos);
}

// ---------- table render ----------
function renderTable() {
  if (!state.models.length || !state.rowKeys.length) {
    document.getElementById('table-container').innerHTML = '<div class="empty-msg">No data.</div>';
    return;
  }
  const head = ['<th>task</th>', '<th>level</th>', '<th>days</th>', '<th>style</th>', '<th>topology</th>', '<th>al</th>'];
  for (const m of state.models) {
    const tot = m.pass + m.fail;
    const rate = tot ? (m.pass / tot * 100).toFixed(1) : '0.0';
    head.push('<th class="model-head">' + escapeHtml(m.label) +
      '<div class="summary">' + m.pass + '/' + tot + ' (' + rate + '%)</div></th>');
  }
  const body = [];
  let prevTask = null;
  state.rowKeys.forEach((k, idx) => {
    const meta = state.rowMeta.get(k);
    const aligned = (meta.style === meta.topo);
    const taskIdx = state.tasks.indexOf(meta.task);
    const alt = (taskIdx % 2 === 1) ? 'task-alt' : 'task-even';
    const start = (meta.task !== prevTask) ? ' task-start' : '';
    prevTask = meta.task;
    const cls = 'row task-' + safe(meta.task) + ' style-' + meta.style + ' topo-' + meta.topo +
                ' ' + alt + (aligned ? ' aligned' : '') + start;
    const lvl = meta.level || '';
    const tds = [
      '<td class="task">' + escapeHtml(meta.task) + '</td>',
      '<td class="level ' + escapeAttr(lvl) + '">' + escapeHtml(lvl) + '</td>',
      '<td class="days">' + (meta.days !== undefined && meta.days !== null ? escapeHtml(meta.days) : '') + '</td>',
      '<td class="style">' + escapeHtml(meta.style) + '</td>',
      '<td class="topo">' + escapeHtml(meta.topo) + '</td>',
      '<td class="al">' + (aligned ? '●' : '') + '</td>',
    ];
    for (const m of state.models) {
      const r = m.trials.get(k);
      if (!r) {
        tds.push('<td class="missing">—</td>');
      } else {
        const p = !!(r.metrics && r.metrics.final_pass);
        const label = p ? 'PASS' : 'FAIL';
        const title = 'delivery=' + (r.metrics && r.metrics.delivery) +
          ' | commonsense=' + (r.metrics && r.metrics.commonsense_pass_macro) +
          ' | hard=' + (r.metrics && r.metrics.hard_pass_macro) +
          ' | duration=' + (r.duration_seconds || 0).toFixed(1) + 's' +
          ' | msgs=' + (r.message_count || 0);
        tds.push('<td class="' + (p ? 'pass' : 'fail') + '" data-mk="' + escapeAttr(m.key) +
                 '" data-rk="' + escapeAttr(k) + '" title="' + escapeAttr(title) + '"><span class="lab">' + label + '</span></td>');
      }
    }
    body.push('<tr class="' + cls + '">' + tds.join('') + '</tr>');
  });
  const tableHtml = '<table><thead><tr>' + head.join('') + '</tr></thead><tbody>' + body.join('\n') + '</tbody></table>';
  document.getElementById('table-container').innerHTML = tableHtml;
  applyFilters();
}

// ---------- filters ----------
function applyFilters() {
  const t = document.getElementById('f-task').value;
  const s = document.getElementById('f-style').value;
  const tp = document.getElementById('f-topo').value;
  const onlyAl = document.getElementById('f-aligned').checked;
  const onlyFail = document.getElementById('f-fail').checked;
  document.querySelectorAll('tbody tr').forEach(tr => {
    let show = true;
    if (t && !tr.classList.contains('task-' + safe(t))) show = false;
    if (s && !tr.classList.contains('style-' + s)) show = false;
    if (tp && !tr.classList.contains('topo-' + tp)) show = false;
    if (onlyAl && !tr.classList.contains('aligned')) show = false;
    if (onlyFail) {
      const hasFail = tr.querySelector('td.fail') !== null;
      if (!hasFail) show = false;
    }
    tr.classList.toggle('hidden', !show);
  });
}
['f-task','f-style','f-topo','f-aligned','f-fail'].forEach(id => {
  document.getElementById(id).addEventListener('change', applyFilters);
});

// ---------- cell click -> render trial in right pane ----------
document.addEventListener('click', e => {
  const td = e.target.closest('td.pass, td.fail');
  if (!td) return;
  const mk = td.getAttribute('data-mk'), rk = td.getAttribute('data-rk');
  if (!mk || !rk) return;
  const model = state.models.find(m => m.key === mk);
  if (!model) return;
  const row = model.trials.get(rk);
  if (!row) return;
  if (state.selected) {
    const prev = document.querySelector('td.selected');
    if (prev) prev.classList.remove('selected');
  }
  td.classList.add('selected');
  state.selected = { modelKey: mk, rowKey: rk };
  renderTrial(row, model);
});

// ---------- render trial as markdown -> HTML ----------
function renderTrial(row, model) {
  const md = trialToMarkdown(row);
  document.getElementById('content').innerHTML = marked.parse(md);
  const meta = state.rowMeta.get(rowKey(row.task_id, row.style_id, row.topology));
  document.getElementById('fname').textContent =
    model.label + ' / ' + row.task_id + ' / ' + row.style_id + ' → ' + row.topology;
}

function trialToMarkdown(row) {
  const m = row.metrics || {};
  const pass = !!m.final_pass;
  const lines = [];
  lines.push('# ' + row.task_id + ' | style=' + row.style_id + ' -> topology=' + row.topology);
  lines.push('');
  lines.push('- model: `' + row.model + '`');
  lines.push('- final: **' + (pass ? 'PASS' : 'FAIL') + '**  (delivery=' + m.delivery +
    ', commonsense_macro=' + m.commonsense_pass_macro + ', hard_macro=' + m.hard_pass_macro + ')');
  lines.push('- duration: ' + (row.duration_seconds || 0).toFixed(1) + 's  |  message_count: ' + row.message_count);
  lines.push('- temperature: ' + row.temperature + '  |  reasoning_effort: ' + row.reasoning_effort);
  lines.push('- level: ' + row.level + '  |  days: ' + row.days);
  lines.push('');
  lines.push('## Query');
  lines.push('');
  lines.push('> ' + (row.query || '').replace(/\n/g, '\n> '));
  lines.push('');
  const msgs = row.messages || [];
  lines.push('## Trace (' + msgs.length + ' messages)');
  lines.push('');
  if (!msgs.length) lines.push('_(no messages — single-shot or empty trace)_');
  msgs.forEach((mm, i) => {
    const frm = mm.from_agent || mm.role || mm.name || '?';
    const to = mm.to_agent || '';
    const meta = mm.metadata || {};
    let metaTail = '';
    const keep = {};
    ['turn','phase','round','stage','kind','type'].forEach(k => { if (meta[k] !== undefined) keep[k] = meta[k]; });
    if (Object.keys(keep).length) metaTail = ' · ' + Object.entries(keep).map(([k,v]) => k+'='+v).join(' ');
    lines.push('### [' + i + '] ' + frm + ' -> ' + to + metaTail);
    lines.push('');
    lines.push(contentToString(mm.content));
    lines.push('');
  });
  // check breakdown
  lines.push('## Check breakdown');
  lines.push('');
  ['Commonsense', 'Hard'].forEach(kind => {
    const src = (kind === 'Commonsense') ? m.commonsense_per_item : m.hard_per_item;
    lines.push('**' + kind + ':**');
    if (!src || !Object.keys(src).length) { lines.push('- (no items)'); lines.push(''); return; }
    const fail = [], pass = [], na = [];
    for (const [name, entry] of Object.entries(src)) {
      if (Array.isArray(entry) && entry.length >= 1) {
        const flag = entry[0], reason = entry[1];
        if (flag === false) fail.push([name, reason]);
        else if (flag === null) na.push([name, reason]);
        else pass.push([name, reason]);
      }
    }
    fail.forEach(([n, r]) => lines.push('- ❌ `' + n + '` — ' + (r || '')));
    pass.forEach(([n])    => lines.push('- ✅ `' + n + '`'));
    na.forEach(([n])      => lines.push('- ➖ `' + n + '` (N/A)'));
    lines.push('');
  });
  if (row.final_output !== undefined && row.final_output !== null) {
    lines.push('## Final output');
    lines.push('');
    if (typeof row.final_output === 'string') {
      lines.push('```'); lines.push(row.final_output); lines.push('```');
    } else {
      lines.push('```json'); lines.push(JSON.stringify(row.final_output, null, 2)); lines.push('```');
    }
    lines.push('');
  }
  if (row.parsed_plan !== undefined && row.parsed_plan !== null) {
    lines.push('## Parsed plan');
    lines.push('');
    lines.push('```json'); lines.push(JSON.stringify(row.parsed_plan, null, 2)); lines.push('```');
  }
  return lines.join('\n');
}

function contentToString(c) {
  if (typeof c === 'string') return c;
  if (Array.isArray(c)) return c.map(x => typeof x === 'string' ? x : (x.text || x.content || JSON.stringify(x))).join('\n');
  if (c === null || c === undefined) return '';
  return JSON.stringify(c);
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function escapeAttr(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ---------- buttons + file inputs ----------
const jsonlInput = document.getElementById('jsonl-input');
document.getElementById('load-jsonl').addEventListener('click', () => jsonlInput.click());
jsonlInput.addEventListener('change', () => { handleJsonlFiles(jsonlInput.files); jsonlInput.value = ''; });

const mdInput = document.getElementById('md-input');
document.getElementById('open-md').addEventListener('click', () => mdInput.click());
mdInput.addEventListener('change', () => {
  const f = mdInput.files && mdInput.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('content').innerHTML = marked.parse(reader.result);
    document.getElementById('fname').textContent = f.name + ' (external)';
  };
  reader.readAsText(f);
  mdInput.value = '';
});

document.getElementById('clear-all').addEventListener('click', () => { if (confirm('Clear all loaded files?')) clearAll(); });

function handleJsonlFiles(fileList) {
  for (const f of fileList) {
    const reader = new FileReader();
    reader.onload = () => addJsonlFile(reader.result, f.name);
    reader.readAsText(f);
  }
}

// ---------- drag/drop ----------
function isJsonlName(n) { return /\.jsonl$/i.test(n); }
function isMdName(n) { return /\.md$/i.test(n) || /\.markdown$/i.test(n); }

const leftPane = document.querySelector('.pane.left');
const rightPane = document.querySelector('.pane.right');
['dragenter','dragover'].forEach(ev => {
  leftPane.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); leftPane.classList.add('dragover'); });
  rightPane.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); rightPane.classList.add('dragover'); });
});
['dragleave','drop'].forEach(ev => {
  leftPane.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); leftPane.classList.remove('dragover'); });
  rightPane.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); rightPane.classList.remove('dragover'); });
});
leftPane.addEventListener('drop', e => {
  const files = Array.from(e.dataTransfer.files || []).filter(f => isJsonlName(f.name));
  if (files.length) handleJsonlFiles(files);
});
rightPane.addEventListener('drop', e => {
  const f = Array.from(e.dataTransfer.files || []).find(f => isMdName(f.name));
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('content').innerHTML = marked.parse(reader.result);
    document.getElementById('fname').textContent = f.name + ' (external)';
  };
  reader.readAsText(f);
});
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default="backend/data/thinking_styles/trace_dump/comparison.html",
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HTML, encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
