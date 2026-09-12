// --- WidgetForge shell helpers (ES5 / Rhino safe) ---

var WF_COLORS = ['#3fb9b0', '#d9b26a', '#7f9cf5', '#e2757b', '#63c98a',
                 '#b98fd0', '#e0954a', '#5aa9d6', '#c9718f', '#8fb04a'];

function wfColor(i) {
  return WF_COLORS[i % WF_COLORS.length];
}

function wfNum(v) {
  var n = parseFloat(v);
  if (isNaN(n)) { return 0; }
  return n;
}

// Round to at most 1 decimal, drop a trailing .0
function wfRound(n) {
  var r = Math.round(n * 10) / 10;
  if (r === Math.floor(r)) { return '' + Math.floor(r); }
  return '' + r;
}

// 12345 -> "12,345"
function wfComma(n) {
  var s = wfRound(n);
  var neg = false;
  if (s.charAt(0) === '-') { neg = true; s = s.substring(1); }
  var parts = s.split('.');
  var whole = parts[0];
  var out = '';
  var c = 0;
  for (var i = whole.length - 1; i >= 0; i--) {
    out = whole.charAt(i) + out;
    c++;
    if (c % 3 === 0 && i > 0) { out = ',' + out; }
  }
  if (parts.length > 1) { out = out + '.' + parts[1]; }
  return (neg ? '-' : '') + out;
}

function wfPercent(part, total) {
  if (!total) { return 0; }
  return Math.round((part / total) * 1000) / 10;
}

function wfCount(table, filter) {
  var ga = new GlideAggregate(table);
  if (filter) { ga.addEncodedQuery(filter); }
  ga.addAggregate('COUNT');
  ga.query();
  if (ga.next()) { return wfNum(ga.getAggregate('COUNT')); }
  return 0;
}

function wfAgg(table, filter, agg, field) {
  var ga = new GlideAggregate(table);
  if (filter) { ga.addEncodedQuery(filter); }
  if (agg === 'sum') { ga.addAggregate('SUM', field); }
  else if (agg === 'avg') { ga.addAggregate('AVG', field); }
  else if (agg === 'max') { ga.addAggregate('MAX', field); }
  else if (agg === 'min') { ga.addAggregate('MIN', field); }
  else { ga.addAggregate('COUNT'); }
  ga.query();
  if (ga.next()) {
    if (agg === 'sum') { return wfNum(ga.getAggregate('SUM', field)); }
    if (agg === 'avg') { return wfNum(ga.getAggregate('AVG', field)); }
    if (agg === 'max') { return wfNum(ga.getAggregate('MAX', field)); }
    if (agg === 'min') { return wfNum(ga.getAggregate('MIN', field)); }
    return wfNum(ga.getAggregate('COUNT'));
  }
  return 0;
}

// Group-by counts. Returns [{label, value, color, pct}] sorted desc.
function wfGroup(table, filter, field, limit) {
  var rows = [];
  var ga = new GlideAggregate(table);
  if (filter) { ga.addEncodedQuery(filter); }
  ga.groupBy(field);
  ga.addAggregate('COUNT');
  ga.orderByAggregate('COUNT');
  ga.query();
  while (ga.next()) {
    var label = ga.getDisplayValue(field);
    if (label === null || label === '' || label === 'undefined') { label = '(empty)'; }
    rows.push({ label: '' + label, value: wfNum(ga.getAggregate('COUNT')) });
  }
  rows.sort(function (a, b) { return b.value - a.value; });
  var max = limit ? parseInt(limit, 10) : 0;
  if (max > 0 && rows.length > max) {
    var tail = 0;
    for (var t = max; t < rows.length; t++) { tail += rows[t].value; }
    rows = rows.slice(0, max);
    if (tail > 0) { rows.push({ label: 'Other', value: tail }); }
  }
  var total = 0;
  for (var i = 0; i < rows.length; i++) { total += rows[i].value; }
  for (var j = 0; j < rows.length; j++) {
    rows[j].color = wfColor(j);
    rows[j].pct = wfPercent(rows[j].value, total);
  }
  return rows;
}

// Daily counts for the last n days. Returns {points:[{label,key,value}], total, max}
function wfTrend(table, filter, dateField, days) {
  var n = parseInt(days, 10);
  if (!n || n < 2) { n = 30; }
  if (n > 365) { n = 365; }

  var start = new GlideDateTime();
  start.addDaysLocalTime(-(n - 1));
  var q = dateField + '>=' + start.getDate().getValue();
  if (filter) { q = filter + '^' + q; }

  var counts = {};
  var ga = new GlideAggregate(table);
  ga.addEncodedQuery(q);
  ga.addTrendAggregate(dateField, 'date');
  ga.addAggregate('COUNT');
  ga.query();
  while (ga.next()) {
    var key = ga.getValue('timeref');
    if (!key) { key = ga.getValue(dateField); }
    if (!key) { continue; }
    key = ('' + key).substring(0, 10);
    counts[key] = wfNum(ga.getAggregate('COUNT')) + (counts[key] ? counts[key] : 0);
  }

  var points = [];
  var total = 0;
  var max = 0;
  var cur = new GlideDateTime();
  cur.addDaysLocalTime(-(n - 1));
  for (var i = 0; i < n; i++) {
    var k = cur.getDate().getValue();
    var v = counts[k] ? counts[k] : 0;
    points.push({ key: k, label: k.substring(5), value: v });
    total += v;
    if (v > max) { max = v; }
    cur.addDaysLocalTime(1);
  }
  return { points: points, total: total, max: max };
}

// SVG donut arc path. Angles in degrees, 0 = 12 o'clock, clockwise.
function wfArc(cx, cy, rOuter, rInner, a0, a1) {
  if (a1 - a0 >= 359.999) { a1 = a0 + 359.999; }
  var o0 = wfPoint(cx, cy, rOuter, a0);
  var o1 = wfPoint(cx, cy, rOuter, a1);
  var i1 = wfPoint(cx, cy, rInner, a1);
  var i0 = wfPoint(cx, cy, rInner, a0);
  var big = (a1 - a0) > 180 ? 1 : 0;
  return 'M ' + o0.x + ' ' + o0.y +
         ' A ' + rOuter + ' ' + rOuter + ' 0 ' + big + ' 1 ' + o1.x + ' ' + o1.y +
         ' L ' + i1.x + ' ' + i1.y +
         ' A ' + rInner + ' ' + rInner + ' 0 ' + big + ' 0 ' + i0.x + ' ' + i0.y + ' Z';
}

function wfPoint(cx, cy, r, deg) {
  var rad = (deg - 90) * Math.PI / 180;
  return {
    x: Math.round((cx + r * Math.cos(rad)) * 100) / 100,
    y: Math.round((cy + r * Math.sin(rad)) * 100) / 100
  };
}

function wfTrim(s, n) {
  s = '' + (s === null || s === undefined ? '' : s);
  if (s.length <= n) { return s; }
  return s.substring(0, n - 1) + '\u2026';
}

// Keys of a {label: count} map, biggest first, capped.
function wfTopKeys(map, limit) {
  var keys = [];
  for (var k in map) {
    if (map.hasOwnProperty(k)) { keys.push(k); }
  }
  keys.sort(function (a, b) { return map[b] - map[a]; });
  if (limit > 0 && keys.length > limit) { keys = keys.slice(0, limit); }
  return keys;
}
