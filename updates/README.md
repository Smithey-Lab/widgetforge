# Update scripts

Drop a file in this folder named `NNN_short_name.py`. `update.py` sorts by
version, applies anything newer than `VERSION`, runs the test suite, and
restores a backup if either step fails.

```python
VERSION = '3.1.0'
SUMMARY = 'One line describing the change.'


def apply(ctx):
    ctx.edit('app.py', 'exact old text', 'new text')
    ctx.write('modules/heatmap/module.json', '{ ... }')
    ctx.add_module('heatmap', {
        'module.json': '{ ... }',
        'server.js': 'function runHeatmap(s) { ... }',
        'template.html': '<div ng-if="card.kind === \'heatmap\'">...</div>',
        'style.css': '.wf-heat { ... }',
    })
    ctx.delete('modules/old_card')
    ctx.note('Added the heatmap card.')
```

## What ctx gives you

| Call | What it does |
|---|---|
| `ctx.edit(path, old, new)` | Replaces `old` with `new`. **Raises unless `old` appears exactly once.** |
| `ctx.edit(path, old, new, count=3)` | Same, but expects exactly three matches. |
| `ctx.write(path, text)` | Creates or overwrites a whole file. |
| `ctx.delete(path)` | Removes a file or folder. Raises if it is not there. |
| `ctx.add_module(id, files)` | Writes a whole `modules/<id>/` folder. |
| `ctx.note(msg)` | Prints a line at the end of a successful run. |

## The rule about anchors

`ctx.edit` refuses to run when its anchor is missing or ambiguous. This is
deliberate. An update that silently matches nothing leaves you believing a
change landed when it did not, and the failure only surfaces later as
mysteriously wrong output. If an anchor is ambiguous, widen it with
surrounding lines until it is unique rather than passing a higher `count`.

## Shipping an update

Zip the scripts under an `updates/` folder and apply the zip directly:

```
py update.py wf-update-3.1.0.zip
```

`update.py` pulls the scripts out, applies them, tests, and reports.

## If something goes wrong

`py update.py --rollback` restores `.backup/`, which holds the tree exactly
as it was before the last run. `py update.py --check` does a full dry run
and changes nothing.
