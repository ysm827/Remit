# Security policy

## Supported version

Remit is currently pre-1.0. Security fixes are made on the latest `main`
revision; older snapshots are not supported.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use the
repository's **Security → Report a vulnerability** form on GitHub. Include a
minimal reproduction, affected revision, impact, and any suggested mitigation.
If private vulnerability reporting is unavailable, contact the repository
owner privately before publishing details.

You should receive an acknowledgement within seven days. No response-time or
embargo guarantee is offered, but good-faith reports will be investigated and
credited when requested.

## Deployment boundary

Remit is designed for a trusted local workstation. It accepts files, invokes
LLM providers, and can execute model-generated Python or MATLAB code. Do not
expose it directly to the public internet or use it as a multi-tenant service.
Before any network deployment, add authentication, authorization, task
isolation, resource limits, sandboxed execution, TLS, and an explicit data
retention policy.

Never attach API keys, private datasets, task workspaces, or generated reports
to a public security issue.
