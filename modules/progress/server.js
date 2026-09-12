function runProgress(s) {
  var total = wfCount(s.table, s.filter);
  var doneQ = s.doneFilter || '';
  if (s.filter && doneQ) { doneQ = s.filter + '^' + doneQ; }
  else if (s.filter) { doneQ = s.filter; }
  var done = wfCount(s.table, doneQ);
  if (done > total) { done = total; }
  return {
    pct: wfPercent(done, total),
    label: wfComma(done) + ' of ' + wfComma(total),
    caption: s.caption || ''
  };
}
