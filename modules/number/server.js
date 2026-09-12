function runNumber(s) {
  var v = wfAgg(s.table, s.filter, s.agg || 'count', s.aggField || '');
  return {
    value: wfComma(v),
    suffix: s.suffix || '',
    caption: s.caption || ''
  };
}
