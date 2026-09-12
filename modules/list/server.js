function runList(s) {
  var cols = s.fields || [];
  var rows = [];
  var limit = parseInt(s.limit, 10);
  if (!limit || limit < 1) { limit = 10; }
  if (limit > 200) { limit = 200; }
  if (!cols.length) { return { rows: [], empty: true, showLabels: false }; }

  var gr = new GlideRecord(s.table);
  if (s.filter) { gr.addEncodedQuery(s.filter); }
  if (s.orderBy) {
    if (s.desc === false) { gr.orderBy(s.orderBy); } else { gr.orderByDesc(s.orderBy); }
  }
  gr.setLimit(limit);
  gr.query();
  while (gr.next()) {
    var rest = [];
    for (var i = 1; i < cols.length; i++) {
      var v = gr.getDisplayValue(cols[i].value);
      if (v === null || v === undefined || v === '') { continue; }
      rest.push({ label: cols[i].label, value: wfTrim(v, 34) });
    }
    rows.push({
      sys_id: '' + gr.getUniqueValue(),
      main: wfTrim(gr.getDisplayValue(cols[0].value), 74),
      rest: rest
    });
  }
  return { rows: rows, empty: rows.length === 0, showLabels: s.showLabels !== false };
}
