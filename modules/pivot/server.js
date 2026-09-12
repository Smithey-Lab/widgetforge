function runPivot(s) {
  var rowLimit = parseInt(s.rowLimit, 10) || 10;
  var colLimit = parseInt(s.colLimit, 10) || 6;
  if (rowLimit > 40) { rowLimit = 40; }
  if (colLimit > 12) { colLimit = 12; }

  var cells = {};
  var rowTotals = {};
  var colTotals = {};
  var grand = 0;

  var ga = new GlideAggregate(s.table);
  if (s.filter) { ga.addEncodedQuery(s.filter); }
  ga.groupBy(s.rowField);
  ga.groupBy(s.colField);
  ga.addAggregate('COUNT');
  ga.query();
  while (ga.next()) {
    var rk = ga.getDisplayValue(s.rowField);
    var ck = ga.getDisplayValue(s.colField);
    if (rk === null || rk === '') { rk = '(empty)'; }
    if (ck === null || ck === '') { ck = '(empty)'; }
    rk = '' + rk;
    ck = '' + ck;
    var n = wfNum(ga.getAggregate('COUNT'));
    cells[rk + '\u0000' + ck] = (cells[rk + '\u0000' + ck] || 0) + n;
    rowTotals[rk] = (rowTotals[rk] || 0) + n;
    colTotals[ck] = (colTotals[ck] || 0) + n;
    grand += n;
  }

  var rowKeys = wfTopKeys(rowTotals, rowLimit);
  var colKeys = wfTopKeys(colTotals, colLimit);

  var peak = 0;
  var i, j;
  for (i = 0; i < rowKeys.length; i++) {
    for (j = 0; j < colKeys.length; j++) {
      var v = cells[rowKeys[i] + '\u0000' + colKeys[j]] || 0;
      if (v > peak) { peak = v; }
    }
  }

  var out = [];
  for (i = 0; i < rowKeys.length; i++) {
    var line = { label: rowKeys[i], total: wfComma(rowTotals[rowKeys[i]] || 0), cells: [] };
    for (j = 0; j < colKeys.length; j++) {
      var raw = cells[rowKeys[i] + '\u0000' + colKeys[j]] || 0;
      line.cells.push({
        text: raw ? wfComma(raw) : '',
        shade: (s.heat !== false && peak > 0) ? Math.round((raw / peak) * 100) / 100 : 0
      });
    }
    out.push(line);
  }

  var foot = [];
  for (j = 0; j < colKeys.length; j++) { foot.push(wfComma(colTotals[colKeys[j]] || 0)); }

  return {
    cols: colKeys, rows: out, foot: foot, grand: wfComma(grand),
    totals: s.totals !== false, empty: out.length === 0
  };
}
