function runHbar(s) {
  var rows = wfGroup(s.table, s.filter, s.groupBy, s.limit);
  var max = 0;
  var i;
  for (i = 0; i < rows.length; i++) { if (rows[i].value > max) { max = rows[i].value; } }
  var out = [];
  for (i = 0; i < rows.length; i++) {
    out.push({
      label: rows[i].label,
      value: wfComma(rows[i].value),
      pct: rows[i].pct,
      w: max > 0 ? Math.round((rows[i].value / max) * 1000) / 10 : 0,
      color: rows[i].color
    });
  }
  return { rows: out, showPct: s.showPct === true, empty: out.length === 0 };
}
