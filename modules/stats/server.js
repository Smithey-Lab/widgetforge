function runStats(s) {
  var out = [];
  var rows = s.stats || [];
  for (var i = 0; i < rows.length; i++) {
    var q = rows[i].value || '';
    out.push({
      label: rows[i].label,
      value: wfComma(wfCount(s.table, q)),
      color: wfColor(i)
    });
  }
  return { items: out };
}
