function runGauge(s) {
  var v = wfCount(s.table, s.filter);
  var target = wfNum(s.target);
  if (target <= 0) { target = 1; }
  var pct = wfPercent(v, target);
  var capped = pct > 100 ? 100 : pct;
  var sweep = (capped / 100) * 180;
  return {
    value: wfComma(v),
    pct: pct,
    target: wfComma(target),
    track: wfArc(100, 100, 88, 66, -90, 90),
    fill: wfArc(100, 100, 88, 66, -90, -90 + sweep),
    caption: s.caption || ''
  };
}
