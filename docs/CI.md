# CI and repository protection

The repository's [workflow](../.github/workflows/verify.yml) runs on push, pull request, merge queue and manual dispatch. It runs offline/core checks and actual Chromium checks independently, then exposes one aggregate status: **`agui-required`**. A skipped, cancelled or failed dependency cannot make the aggregate pass.

Actions are pinned to commit SHAs resolved from their official releases. Jobs have bounded timeouts, `contents: read`, no model credentials, and checkout credential persistence disabled. Logs, screenshots and traces are retained for 14 days. This workflow never calls a live model or deploys an application.

## Local equivalents

```sh
python -m pip install -r requirements-ci.txt
npm ci --ignore-scripts
npx --no-install playwright install chromium
python scripts/check_all.py
python scripts/check_all.py --browser
```

Expected negative failures are explicitly checked: service-desk idempotency/receipt defects, cross-domain overlap, and an interrupted UI exposing review. A command merely returning nonzero is insufficient. Reports are written to `.agui/evidence/ci/`. The expected reference release and offline-model evaluation remain blocked, even when the toolkit CI is green.

## Make the status mandatory

A workflow file alone cannot enforce merging policy. An administrator must configure the target branch after the first successful run:

1. Require `agui-required`, with **GitHub Actions as the expected source**, and require the branch to be up to date.
2. Apply the rule to administrators; disallow force pushes and branch deletion.
3. Protect modifications to workflow, checker, policy and test adapters through reviewed PRs and an appropriate CODEOWNERS/reviewer policy. Choose reviewers who can actually review changes; do not configure an impossible self-review requirement for a solo maintainer.
4. If environment secrets are later used, run live evaluations only on reviewed code in a separately protected environment. Do not execute untrusted PR code with privileged credentials.

The read-only audit below verifies the named classic branch-protection controls, not all organization rulesets or workflow integrity:

```sh
# GITHUB_TOKEN is supplied by your authorized environment, never committed.
python scripts/check_repository_protection.py --repo owner/repository --branch main
```

It requires Administration **read** access. Missing credentials, 403 or 404 produce `unverified` and exit 2. A missing control produces `blocked` and exit 1. Git SSH push permission does not provide this API permission. If the organization uses rulesets instead, inspect those effective rules separately; an absent classic rule is not evidence of an unprotected repository.

## Integrate with an application

This repository's CI verifies the **toolkit**. Adapt [the application CI template](../templates/ci.yml) to the target's paths, dependencies and real test adapters. Its required check must evaluate the target application's contract and current evidence. Do not use this toolkit's green check as the target application's release approval.

Sources: [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use), [required status checks](https://docs.github.com/en/pull-requests/reference/status-checks).
