"""Fail CI when the release tag, running version and frontend cache keys diverge."""
import ast
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components' / 'rotacloud_attendance'


def check(tag=None):
    version = json.loads((COMPONENT / 'manifest.json').read_text())['version']
    values = ast.parse((COMPONENT / 'const.py').read_text())
    running = next(ast.literal_eval(node.value) for node in values.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets))
    if running != version:
        raise ValueError('Manifest and running integration versions differ')
    if tag and tag.removeprefix('v') != version:
        raise ValueError('Release tag does not match the integration version')
    for name in ('staff-live.js', 'staff-terminal.js'):
        source = (COMPONENT / 'frontend' / name).read_text()
        keys = re.findall(r"staff-shared\.js\?v=([^'\"]+)", source)
        if keys != [version]:
            raise ValueError(name + ' has a mismatched shared-module version')
    for name in ('staff-live.js', 'staff-shared.js'):
        if (ROOT / 'frontend' / name).read_bytes() != (COMPONENT / 'frontend' / name).read_bytes():
            raise ValueError(name + ' frontend copies differ')
    return version


if __name__ == '__main__':
    print('Release version verified: ' + check(os.environ.get('RELEASE_TAG')))
