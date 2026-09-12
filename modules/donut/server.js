function runDonut(s) {
  var rows = wfGroup(s.table, s.filter, s.groupBy, s.limit);
  var total = 0;
  var i;
  for (i = 0; i < rows.length; i++) { total += rows[i].value; }
  var segs = [];
  var angle = 0;
  for (i = 0; i < rows.length; i++) {
    var sweep = total > 0 ? (rows[i].value / total) * 360 : 0;
    if (sweep > 0) {
      segs.push({
        d: wfArc(100, 100, 88, 58, angle, angle + sweep),
        color: rows[i].color,
        label: rows[i].label,
        value: wfComma(rows[i].value),
        pct: rows[i].pct
      });
    }
    angle += sweep;
  }
  return {
    segs: segs,
    total: wfComma(total),
    legend: s.legend !== false,
    centerLabel: s.centerLabel || '',
    empty: segs.length === 0
  };
}
