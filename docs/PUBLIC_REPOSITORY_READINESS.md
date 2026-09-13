# Public Repository Readiness

Status: **Remediation in progress / publication not yet approved**

This document records repository-specific boundaries for a possible future change from private to public. It does not authorize a visibility change, select an application license, approve a binary release, or rewrite repository history.

The audit/control-plane issue is #23. Public-readiness changes must remain isolated from unrelated feature work such as PR #22.

## Audit evidence

The reachable-ref audit was performed from a disposable mirror with GitHub pull-request refs fetched in addition to ordinary branch refs.

At the audited snapshot:

- `main` was `b05a88761c82f7f1d92644d9adf709cfbac60f4f`;
- 14 branch heads, 0 tags, and 15 fetched pull-request refs were inventoried;
- 118 unique commits were reachable from the fetched refs;
- the audited risky-path extension set produced 0 historical candidates;
- Gitleaks 8.30.1 reported 0 findings from its reachable patch-history scan;
- its 115 scanned-commit count was reconciled against 118 reachable commits by identifying three commits with no scannable ordinary patch hunk: one delete-only commit, one file addition for which Git produced no ordinary text patch, and one merge commit.

A separate blob-complete audit then enumerated every unique reachable blob at exact PR #24 head `d0170e7807194ac3d4326d1ee2248fc593608395` while `main` remained at the audited snapshot. It covered 261 unique reachable blobs totaling 2,382,969 bytes. All 261 blobs could be decoded as text by the audit helper, no opaque binary blob remained, and a printable-string corpus was generated for 260 blobs. Gitleaks directory scans over the raw blob corpus, decoded corpus, and printable-string corpus each produced the empty JSON array `[]`, i.e. 0 findings. An initial helper summary incorrectly counted each empty array as one finding under Windows PowerShell 5.1; the already-produced reports were re-counted with null/array-aware logic and the counting defect was documented in Issue #23.

Current audit status is therefore:

- `PASS_GITLEAKS_REACHABLE_PATCH_HISTORY`;
- `PASS_HISTORICAL_RISKY_PATH_EXTENSION_INVENTORY`;
- `PASS_BLOB_COMPLETE_SECRET_SCAN`.

A fresh inventory is still required immediately before publication because repository state may change after the audit.

## Evidence hygiene for a public repository

Raw local verification and build logs are not suitable default publication artifacts. They can contain machine names, user-profile paths, workspace paths, or unnecessary private-sample metadata even when they contain no credential.

Repository policy for new evidence:

- keep raw local `logs/verification/*.log` files outside source control;
- publish only the minimum sanitized result needed to reproduce a decision;
- record exact public repository identifiers such as commit SHAs, PR numbers, workflow run IDs, tool versions, and pass/fail results;
- do not publish real municipal/private PDF files, private filenames, document contents, or unnecessary local filesystem paths;
- use synthetic or otherwise redistributable fixtures for committed regression coverage;
- treat private real-file validation as a separate local gate and summarize it only when the summary is necessary and safe to publish.

Removing a raw log from the current tree does not remove that blob from existing Git history. Historical cleanup, comment editing, branch deletion, and history rewriting are separate human-final decisions.

## Public-fork GitHub Actions boundary

A public fork pull request is untrusted code. The test workflow therefore follows these repository-specific invariants:

- use `pull_request`, not `pull_request_target`, for PR test execution;
- declare `GITHUB_TOKEN` access explicitly as read-only contents access;
- do not reference repository secrets from the untrusted PR workflow;
- pin external Actions to reviewed full commit SHAs;
- set `persist-credentials: false` on checkout;
- bound the test job with a timeout;
- keep regression tests that fail if these invariants are weakened accidentally.

The repository setting controlling which external contributors require workflow approval is not encoded in the workflow. Before/when the repository becomes public, the conservative initial policy is to require approval for all external contributors unless the owner deliberately chooses a less restrictive policy.

## Application license is a separate human gate

Public visibility and an application open-source license are different decisions. At this stage no application license has been selected and no root `LICENSE` file is added by the public-readiness remediation.

Before publication, the owner must deliberately choose one of these directions:

1. select an application license appropriate to the intended reuse/distribution model; or
2. publish the repository without a general application reuse license, understanding that this is public source visibility rather than an ordinary open-source grant.

The choice must be repository-specific. It must not be inherited automatically from another project.

## Source publication is not binary-release approval

The existing Windows portable-build evidence and third-party notices describe a specific internal-evaluation artifact. Making the source repository public would not automatically approve that ZIP, or any later binary, for public redistribution.

Any public binary release requires a fresh artifact-specific inventory and notice review for its exact source commit, Python/runtime closure, native libraries, packager version, and included license/notice files.

## Human-final decisions still open

The audit identified publication metadata that is not a secret but may still be undesirable in a public repository, including historical author identity/email metadata, historical local-path exposure, workstation/environment labels, and private-sample-derived quantitative evidence in existing repository surfaces.

For each category the owner must decide whether to:

- accept the exposure as appropriate for this repository;
- edit/redact mutable GitHub surfaces where justified; or
- use destructive history cleanup only if the exposure is serious enough to justify rewriting shared history.

No remediation PR should silently make those decisions.

## Publication sequence

Before changing visibility:

1. complete and review the isolated public-readiness remediation PR;
2. run exact-head local/CI validation and independent/adversarial review;
3. resolve the application-license human gate;
4. resolve or explicitly accept the remaining historical/publication-surface metadata findings;
5. refresh the complete repository inventory and secret/path checks;
6. obtain the human private-to-public approval;
7. after publication, verify a real public hosted-CI run and configure/read back the intended `main` protection/ruleset and external-fork approval policy;
8. record `PUBLISHED_VERIFIED` only after those post-publication checks succeed.
