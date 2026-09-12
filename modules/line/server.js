function runLine(s) {
  var t = wfTrend(s.table, s.filter, s.dateField, s.days);
  var pts = t.points;
  var n = pts.length;
  var W = 600, H = 180, PAD = 6;
  var max = t.max > 0 ? t.max : 1;
  var line = '';
  var i, x, y;
  for (i = 0; i < n; i++) {
    x = n > 1 ? PAD + (i / (n - 1)) * (W - PAD * 2) : W / 2;
    y = H - PAD - (pts[i].value / max) * (H - PAD * 2);
    line += (i ? ' ' : '') + (Math.round(x * 10) / 10) + ',' + (Math.round(y * 10) / 10);
  }
  var area = '';
  if (n > 1) { area = 'M ' + PAD + ',' + H + ' L ' + line.split(' ').join(' L ') + ' L ' + (W - PAD) + ',' + H + ' Z'; }
  var ticks = [];
  if (n > 0) {
    ticks.push(pts[0].label);
    if (n > 2) { ticks.push(pts[Math.floor(n / 2)].label); }
    if (n > 1) { ticks.push(pts[n - 1].label); }
  }
  return {
    points: line, area: area, fill: s.fill !== false,
    max: wfComma(max), ticks: ticks,
    note: wfComma(t.total) + ' in ' + n + ' days',
    empty: n === 0
  };
}
