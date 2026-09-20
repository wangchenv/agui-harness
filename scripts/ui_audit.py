#!/usr/bin/env python3
"""Check declared web tokens and inventory, not rendered UI or full accessibility."""
import argparse
import json
import os
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def structure(value, name):
    schema = json.loads((ROOT/'schemas'/name).read_text())
    return [e.message for e in Draft202012Validator(schema).iter_errors(value)]


def luminance(hex_color):
    rgb = [int(hex_color[i:i+2], 16)/255 for i in (1,3,5)]
    linear = [x/12.92 if x <= 0.04045 else ((x+0.055)/1.055)**2.4 for x in rgb]
    return sum(x*w for x,w in zip(linear, (0.2126,0.7152,0.0722)))


def contrast(a, b):
    lo, hi = sorted([luminance(a), luminance(b)])
    return (hi+0.05)/(lo+0.05)


def audit_tokens(tokens):
    errors = structure(tokens, 'ui-tokens.schema.json')
    if errors:
        return errors
    pairs = tokens['contrast_pairs']
    declared = {(p['foreground'],p['background'],p['usage']) for p in pairs}
    required = {('text','surface','text'),('text_muted','surface','text'),
                ('primary_text','primary','text'),('focus','canvas','non_text')}
    if not required <= declared:
        errors.append('Missing required text/muted/primary/focus contrast pair; usage cannot downgrade normal text.')
    for pair in pairs:
        a,b = pair['foreground'],pair['background']
        if a not in tokens['color'] or b not in tokens['color']:
            errors.append(f'Unknown color token: {a}/{b}')
            continue
        ratio = contrast(tokens['color'][a],tokens['color'][b])
        limit = 4.5 if pair['usage']=='text' else 3.0
        if ratio < limit:
            errors.append(f'{a}/{b}: contrast {ratio:.4f} below {limit} for {pair["usage"]}; no rounded-up passes.')
    for name in ['spacing_px']:
        if tokens[name] != sorted(tokens[name]):
            errors.append(f'{name} must be in ascending order.')
    if tokens['typography']['scale_px'] != sorted(tokens['typography']['scale_px']):
        errors.append('Typography scale must ascend.')
    bp=tokens['breakpoints_px']
    if not bp['mobile'] < bp['tablet'] < bp['desktop']:
        errors.append('Breakpoints must ascend: mobile < tablet < desktop.')
    return errors


def audit_inventory(inventory):
    errors=structure(inventory,'ui-inventory.schema.json')
    if errors:
        return errors
    components={c['id']:c for c in inventory['components']}
    if len(components)!=len(inventory['components']):
        errors.append('Duplicate component IDs.')
    if len({s['id'] for s in inventory['screens']})!=len(inventory['screens']):
        errors.append('Duplicate screen IDs.')
    for screen in inventory['screens']:
        if not set(screen['components']) <= set(components):
            errors.append(f'{screen["id"]}: unknown component reference.')
    for c in components.values():
        if len({a['id'] for a in c['actions']})!=len(c['actions']):
            errors.append(f'{c["id"]}: duplicate action IDs.')
        for a in c['actions']:
            if not set(a['allowed_states']) <= set(c['states']):
                errors.append(f'{c["id"]}/{a["id"]}: unknown allowed state.')
            if a['effect']=='write':
                if set(a['allowed_states']) & {'partial','unknown','interrupted','stale','submitting','committed'}:
                    errors.append(f'{c["id"]}/{a["id"]}: write allowed during unsafe/incomplete/terminal state.')
                if a['result_source']!='receipt':
                    errors.append(f'{c["id"]}/{a["id"]}: write success must be based on receipt.')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokens',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    args=parser.parse_args()
    cases=[]
    for id,path,validator in [('design_tokens',args.tokens,audit_tokens),('component_inventory',args.inventory,audit_inventory)]:
        try:
            errors=validator(json.loads(path.read_text()))
        except (ValueError,OSError) as exc:
            errors=[str(exc)]
        cases.append({'id':id,'status':'failed' if errors else 'passed','detail':'; '.join(errors) if errors else 'Declared design checks passed; rendered/browser behavior unverified.'})
    result={'schema_version':1,'cases':cases}
    encoded=json.dumps(result,ensure_ascii=False,indent=2)
    output=os.environ.get('AGUI_EVIDENCE_OUTPUT')
    if output:
        Path(output).write_text(encoded+'\n')
    print(encoded)
    return 1 if any(c['status']!='passed' for c in cases) else 0


if __name__=='__main__':
    raise SystemExit(main())
