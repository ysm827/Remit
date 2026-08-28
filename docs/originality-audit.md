# Originality audit and remediation plan

Audit date: 2026-08-28
Remit baseline commit: `ac1340ad422e2d7c6187eae619b78bcbd997af4a`
MathModelAgent reference commit: `83d8783187a2d29dda1b046cb667009cc50c8203`

## Baseline finding

Before this remediation, Remit had undergone a substantial rewrite but still
contained exact project-specific implementation blocks. A path/hash inventory
of the baseline showed:

- 410 tracked files in total;
- 288 paths also present in MathModelAgent;
- 169 same-path files with identical SHA-256 content (139 generated UI files
  and 30 files outside that generated UI directory);
- 102 additional same-path files with modified content;
- residual exact implementation blocks in parts of the agent, prompt,
  LLM-provider, API/WebSocket, schema, frontend state, and task UI layers.

The raw file counts materially overstate the remaining source overlap. Of the
169 identical same-path files, 139 are generated third-party UI components.
They still require normal dependency/license handling, but they are not
evidence that Remit copied project-specific implementation. The 30 remaining
identical files include empty package markers and common configuration as well
as some project-specific rules and build files; each must be classified rather
than treated equally.

## Strict source-fingerprint result

A strict pass excludes generated UI, dependency locks, tests, bundled Redis,
blank lines, and comment-only lines, then looks for exact continuous
six-significant-line fingerprints anywhere in the pinned MathModelAgent tree.
The result changed as follows:

- baseline: 1,237 of 28,217 significant lines (4.38%), in 48 files;
- remediated working tree: 279 of 28,072 significant lines (0.99%), in 22
  files;
- remediated frontend hits: 194 lines;
- remediated backend hits: 85 lines.

Every remaining window was manually classified. The 194 frontend lines are UI
library imports/template closures, public event values, or store export wiring.
The 85 backend lines are provider/tool wire shapes, public constructor or
method signatures, imports, and short FastAPI route declarations. No remaining
window contains a project-specific prompt, algorithm, recovery routine, task
intake implementation, retry implementation, or workflow policy.

The scan is deliberately syntactic. It can find exact blocks but cannot prove
independent authorship or rule out non-exact derivation. The 0.99% result is
therefore a review aid, not a legal originality score and not a target to be
forced to zero by renaming protocol fields or reformatting framework code.

The initial Remit baseline commit was created on 2026-08-19, two days after the
audited MathModelAgent reference commit, and describes the history as rebuilt
into a single commit. A squashed or rebuilt history does not change source
provenance.

After remediation, the advertised `main` and `codex/ui-home-redesign` branches
were rebuilt to the same parentless root commit. This removes the earlier
commits from branch reachability, but it does not erase prior publication,
third-party caches, local archives, or the provenance described above.

A fresh mirror verification also found GitHub's read-only
`refs/pull/1/head` reference to the former UI branch. Ordinary Git pushes
cannot rewrite or delete `refs/pull/*`; GitHub documents these as platform-owned
references and directs eligible removal requests through GitHub Support. Thus
the advertised branches contain only the audited root commit, while PR #1 and
platform caches may still make three earlier UI-history commits addressable.

## Remediation completed in this working tree

The targeted replacement included:

- provider-neutral request objects and independently structured provider
  adapters;
- a shared Agent history contract, conservative JSON recovery, and rewritten
  coordinator/modeler/coder/writer flows;
- separate API-probe, task-intake, API-schema, route-validation, Redis-health,
  and WebSocket-boundary modules;
- a new modeling-output contract and rewritten prompt instructions;
- independently structured frontend API types, validation handling, task
  intake, credential synchronization, task-store helpers, and workspace file
  browser;
- removal of unused inherited image assets and dead RAG/HIL configuration.

Generated components, dependency declarations, framework boilerplate, protocol
values, and compatibility signatures remain separately classified; similarity
in those areas is not itself project-specific implementation.

Changing names, comments, formatting, file locations, or superficial control
flow is not an independent replacement.

## Verification

The remediated working tree passed:

- Ruff checks for `backend/app`;
- all 190 backend tests;
- all 21 repository-level launcher, configuration, and UI-contract tests;
- Biome checks for every changed frontend source file;
- the Vue TypeScript check and Vite production build;
- PowerShell parser validation for `tools/package_win.ps1`;
- `git diff --check`.

The only emitted notices were an upstream Jupyter path deprecation warning and
an outdated Browserslist-data advisory; neither is a test or build failure.

## Clean replacement criteria

The source remediation is complete only when all of the following remain true:

- behavior is defined from a Remit-owned product specification rather than
  copied source;
- implementation and tests are written anew with a materially different
  module boundary and internal design;
- no non-trivial exact or near-exact code/text match remains against the pinned
  reference commit, excluding clearly identified third-party/generated files;
- protocol and data-model similarities that are necessary for compatibility
  are documented as such;
- dependency and bundled-binary notices are preserved;
- the full test suite, frontend build, and packaging checks pass;
- a human license review confirms whether any residual derivative obligations
  remain.

No automated similarity scan can guarantee legal originality. Final claims
require a provenance record and, where the stakes justify it, qualified legal
review.
