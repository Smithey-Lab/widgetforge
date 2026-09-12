function runBar(s) {
  var rows = wfGroup(s.table, s.filter, s.groupBy, s.limit);
  var max = 0;
  var i;
  for (i = 0; i < rows.length; i++) { if (rows[i].value > max) { max = rows[i].value; } }
  var bars = [];
  for (i = 0; i < rows.length; i++) {
    bars.push({
      label: wfTrim(rows[i].label, 14),
      full: rows[i].label,
      value: wfComma(rows[i].value),
      h: max > 0 ? Math.round((rows[i].value / max) * 1000) / 10 : 0,
      color: s.single ? '#3fb9b0' : rows[i].color
    });
  }
  return { bars: bars, empty: bars.length === 0 };
}
