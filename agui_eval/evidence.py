import hashlib
import json
import os
from pathlib import Path


def artifact(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    return {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def emit(result):
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    destination = os.environ.get('AGUI_EVIDENCE_OUTPUT')
    if destination:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_text(encoded)
    print(encoded, end='')
    return 0 if result['cases'] and all(c['status'] == 'passed' for c in result['cases']) else 1
