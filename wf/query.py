"""The encoded-query condition builder.

Ported from the parser that shipped in builder.js, behaviour for behaviour.
The two traps that were fixed there are easy to reintroduce anywhere this is
rewritten, so they are called out again:

  1. Searching for the operator breaks on values that contain one.
     `state=IN_PROGRESS` would parse as field `state=` with operator `IN`.
     OP_RE therefore anchors on a field-name pattern first, then the operator.

  2. `^OR` can prefix a genuine field name. A field literally called
     `ORDER_number` is not an OR join. The OR branch only fires when what
     follows also parses as a condition.

And the governing rule: a builder that quietly rewrites a working filter is
worse than a text box. `cond_safe` parses, rebuilds, and compares byte for
byte. Anything that does not come back identical stays raw and untouched.
"""

import re

# (encoded operator, label shown in the UI)
COND_OPS = [
    ('=', 'is'), ('!=', 'is not'),
    ('>', 'greater than'), ('<', 'less than'),
    ('>=', 'at least'), ('<=', 'at most'),
    ('LIKE', 'contains'), ('NOTLIKE', 'does not contain'),
    ('STARTSWITH', 'starts with'), ('ENDSWITH', 'ends with'),
    ('IN', 'is one of'), ('NOT IN', 'is not one of'),
    ('ISEMPTY', 'is empty'), ('ISNOTEMPTY', 'is not empty'),
    ('ON', 'on'), ('NOTON', 'not on'), ('BETWEEN', 'between'),
    ('RELATIVEGE', 'relative, at least'), ('RELATIVELE', 'relative, at most'),
]

OP_VALUES = [op for op, _ in COND_OPS]

# Operators that take no value. The value box is hidden for these, and the
# value is dropped when one is chosen, so it cannot leak back into the query.
NO_VALUE = ('ISEMPTY', 'ISNOTEMPTY')

# Operators whose value is a date or date range, which get the hint list.
DATE_OPS = ('ON', 'NOTON', 'BETWEEN')

DATE_HINTS = [
    'Today@javascript:gs.beginningOfToday()@javascript:gs.endOfToday()',
    'Yesterday@javascript:gs.beginningOfYesterday()@javascript:gs.endOfYesterday()',
    'This week@javascript:gs.beginningOfThisWeek()@javascript:gs.endOfThisWeek()',
    'This month@javascript:gs.beginningOfThisMonth()@javascript:gs.endOfThisMonth()',
    'Last month@javascript:gs.beginningOfLastMonth()@javascript:gs.endOfLastMonth()',
]

# Field name first, then the operator. Longest-first alternation matters:
# ISNOTEMPTY must be tried before ISEMPTY, NOTLIKE before LIKE, NOTON before
# ON, and >= before >, or the shorter one wins and eats the rest as a value.
OP_RE = re.compile(
    r'^([a-z0-9_.]+)'
    r'(ISNOTEMPTY|ISEMPTY|STARTSWITH|ENDSWITH|NOTLIKE|LIKE|'
    r'RELATIVEGE|RELATIVELE|NOTON|ON|BETWEEN|NOT IN|IN|>=|<=|!=|=|>|<)'
    r'([\s\S]*)$'
)

# Query syntax the visual editor cannot rebuild exactly, so it never tries.
RAW_MARKER_RE = re.compile(r'\^(EQ|NQ|ORDERBY)')


class Row(object):
    """One condition line: join, field, operator, value."""

    __slots__ = ('join', 'field', 'op', 'value')

    def __init__(self, join='AND', field='', op='=', value=''):
        self.join = 'OR' if join == 'OR' else 'AND'
        self.field = field
        self.op = op
        self.value = value

    def __eq__(self, other):
        return (isinstance(other, Row)
                and (self.join, self.field, self.op, self.value)
                == (other.join, other.field, other.op, other.value))

    def __repr__(self):
        return 'Row(%r, %r, %r, %r)' % (self.join, self.field, self.op, self.value)


def parse_query(q):
    """(rows, raw). raw=True means the visual editor must not touch this."""
    if not q:
        return [], False
    if RAW_MARKER_RE.search(q):
        return [], True

    rows = []
    parts = q.split('^')
    for i, part in enumerate(parts):
        join = 'AND'
        # Trap 2: only treat a leading OR as a join if the remainder is itself
        # a condition. Otherwise a field named ORphan becomes an OR clause.
        if i > 0 and part.startswith('OR') and OP_RE.match(part[2:]):
            join = 'OR'
            part = part[2:]
        m = OP_RE.match(part)
        if not m:
            return [], True
        op = m.group(2)
        rows.append(Row(join, m.group(1), op, '' if op in NO_VALUE else m.group(3)))
    return rows, False


def build_query(rows):
    """Serialise rows back to an encoded query. Incomplete rows are skipped."""
    out = []
    for r in rows:
        if not r.field or not r.op:
            continue
        frag = r.field + r.op + ('' if r.op in NO_VALUE else (r.value or ''))
        out.append(frag if not out else (('^OR' if r.join == 'OR' else '^') + frag))
    return ''.join(out)


def cond_safe(q):
    """Rows if the visual editor can rebuild `q` exactly, else None.

    None is not an error. It means "leave the text box alone", which is the
    whole point of the guard.
    """
    rows, raw = parse_query(q)
    if raw:
        return None
    if build_query(rows) != (q or ''):
        return None
    return rows
