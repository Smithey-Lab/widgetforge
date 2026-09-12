function runTable(s) {
  var cols = s.columns || [];
  var fields = [];
  var heads = [];
  var i;
  for (i = 0; i < cols.length; i++) {
    fields.push(cols[i].value);
    heads.push(cols[i].label);
  }
  var rows = [];
  var limit = parseInt(s.limit, 10);
  if (!limit || limit < 1) { limit = 25; }
  if (limit > 500) { limit = 500; }

  var gr = new GlideRecord(s.table);
  if (s.filter) { gr.addEncodedQuery(s.filter); }
  if (s.orderBy) {
    if (s.desc === false) { gr.orderBy(s.orderBy); } else { gr.orderByDesc(s.orderBy); }
  }
  gr.setLimit(limit);
  gr.query();
  while (gr.next()) {
    var cells = [];
    for (i = 0; i < fields.length; i++) {
      cells.push(wfTrim(gr.getDisplayValue(fields[i]), 90));
    }
    rows.push({ sys_id: '' + gr.getUniqueValue(), cells: cells });
  }
  return {
    heads: heads, rows: rows, empty: rows.length === 0,
    linkTo: s.linkTo || '', tableName: s.table,
    note: rows.length >= limit ? 'first ' + limit : ''
  };
}
