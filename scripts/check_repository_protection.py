#!/usr/bin/env python3
"""Read-only verification of classic GitHub branch protection; never changes policy.

Rulesets and organization policy need separate review. A 403/404 is unverified,
not proof that protection is absent. Git SSH access does not grant this API access.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request


def assess(protection, required_check):
    status = protection.get('required_status_checks') or {}
    # Pin the expected status to GitHub Actions, rather than accepting any writer.
    checks = status.get('checks') or []
    matching = any(c.get('context') == required_check and c.get('app_id') == 15368 for c in checks)
    checks_result = {
        'required_check_from_github_actions': matching,
        'strict_up_to_date': status.get('strict') is True,
        'admin_enforcement': (protection.get('enforce_admins') or {}).get('enabled') is True,
        'force_push_blocked': (protection.get('allow_force_pushes') or {}).get('enabled') is False,
        'deletion_blocked': (protection.get('allow_deletions') or {}).get('enabled') is False,
    }
    return {'status':'passed' if all(checks_result.values()) else 'blocked',
            'scope':'classic branch-protection controls only; not workflow integrity or organization rulesets',
            'checks':checks_result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--branch', default='main')
    parser.add_argument('--check', default='agui-required')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo) or not re.fullmatch(r'[A-Za-z0-9_.-]+', args.branch):
        parser.error('repo must be owner/name and branch must be a simple branch name')
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print(json.dumps({'status':'unverified','reason':'GITHUB_TOKEN with repository Administration read permission required.'}))
        return 2
    request = urllib.request.Request(f'https://api.github.com/repos/{args.repo}/branches/{args.branch}/protection',
        headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token,'User-Agent':'agui-harness-protection-audit'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response: protection=json.load(response)
    except (urllib.error.URLError, ValueError) as error:
        print(json.dumps({'status':'unverified','reason':f'Protection API unavailable: {getattr(error,"code",type(error).__name__)}'}))
        return 2
    result=assess(protection,args.check); print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__ == '__main__': raise SystemExit(main())
