# WidgetForge technical handoff

WidgetForge 3.5.0 is an offline Python/Qt desktop builder for ServiceNow Service
Portal widgets. It compiles a board into HTML, CSS, server JavaScript, and client
JavaScript. See ARCHITECTURE.md for data structures and CONTRIBUTING.md for
implementation recipes.

Available card types are Bar chart, Donut chart, Gauge, Ranked bars, Section
heading, Trend line, Record list, Metric, Matrix, Progress bar, Stat row, Record
table, and Note. Each type is defined by its folder under `modules/`.

## 1. Validation limits

The local assertion suite covers compilation, query parsing, persistence,
layout, and Qt behavior. Generated widgets have not been validated against a
live ServiceNow instance. Test deployment in a scratch widget with appropriate
ACLs before using generated output in production. The example filters assume
standard fields and must be checked against the target instance.

## 2. Design decisions

- Keep the model, compiler, queries, and board storage independent of Qt.
- Preserve compiler output compatibility unless a change explicitly requires
  different output and includes regression coverage.
- Keep the application offline. Do not add credentials or instance connections
  without an explicit design change.
- Generated scripts target ES5 and generated CSS stays flat.
- Boards use a 24-column, 16-row grid; overflow is a build error.
- Add card types through module folders and their data-driven schemas.
- Preserve the captured query corpus; it records legacy parser behavior.
- Sanitize boards loaded from disk and write saved data atomically.
- Keep user boards and application state out of version control. Tests must use
  temporary state folders rather than a user's normal application data.
- Complex custom interfaces are outside the generic card-builder scope.

## 3. Development

Use the project virtual environment and `QT_QPA_PLATFORM=offscreen` for the full
suite. Runtime and development dependencies are pinned in requirements files.
Use feature branches and pull requests for changes, promote tested development
to main, and keep the long-lived branches synchronized with merge commits.

CI checks lint, the Qt suite on Windows and Linux, medium/high Python security
findings, dependency vulnerabilities, and tracked-file secrets. SECURITY.md
documents scan coverage and narrow reviewed exceptions.

The public repository starts from a reviewed source snapshot with fresh Git
history. Both main and dev require pull requests and passing checks. Native
secret scanning, push protection, and private vulnerability reporting complement
the CI checks. CodeQL analyzes Python and JavaScript on pushes, PRs, and weekly.
