# Security

Report a suspected vulnerability using the repository's **Security → Report a
vulnerability** option. Do not post credentials, private board data,
or exploit details in public issues. Include the affected version, reproduction
steps, and impact. Only the current development line receives fixes.

The builder is offline. Generated widgets must still be reviewed and tested in
the target ServiceNow instance, including its ACLs and data access behavior.

CI runs Bandit for medium/high severity Python findings, pip-audit against the
installed runtime and development dependencies, and detect-secrets against all
tracked files. Dependency and security checks also run weekly on main.
CodeQL analyzes Python and JavaScript. GitHub secret scanning and push protection
check for supported credential patterns. These checks do not replace a security
review; the CI secret scan covers tracked files, not prior Git history.

The secret baseline contains one reviewed false positive: the synthetic query
`sys_created_onENDSWITHORDERBYx` in the immutable query corpus. Do not regenerate
the baseline to hide findings. Review each finding and rotate any real leaked
credential. Secret verification is disabled to avoid sending candidates to
external services.

Bandit's B103 exception in the installer permits executable launch scripts
(0755); it does not permit world-writable files.
