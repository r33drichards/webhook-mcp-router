"""Check external embedded SQL resources have explicit PR trigger coverage.
The workflow deliberately uses a single-line flow list; reject other layouts
rather than pretending to implement a general YAML parser without dependencies.
"""
import ast
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'tools/Router.Migrator/Router.Migrator.csproj'
WORKFLOW = ROOT / '.github/workflows/router-dbup-rehearsal.yml'

def external_sql_paths():
    paths = []
    for item in ET.parse(PROJECT).getroot().iter('EmbeddedResource'):
        include = item.attrib['Include']
        if include.startswith('../') and include.endswith('.sql'):
            paths.append((PROJECT.parent / include).resolve().relative_to(ROOT).as_posix())
    assert len(paths) == 2, 'Review changed embedded SQL input set'
    return paths

def validate(text):
    match = re.search(r'^  pull_request:\n    paths: (\[[^\n]+\])$', text, re.M)
    assert match, 'Unsupported or missing PR path-filter layout'
    paths = ast.literal_eval(match[1])
    assert isinstance(paths, list) and all(isinstance(p, str) for p in paths)
    for source in external_sql_paths():
        assert source in paths, 'Embedded SQL source missing explicit PR trigger'
    assert '.github/workflows/router-dbup-rehearsal.yml' in paths
    assert 'ci/*sql-migration*' in paths, 'Contract test must trigger rehearsal too'

text = WORKFLOW.read_text()
validate(text)
count = 1
for path in external_sql_paths() + ['.github/workflows/router-dbup-rehearsal.yml', 'ci/*sql-migration*']:
    broken = text.replace(repr(path), "'unrelated-file'")
    try:
        validate(broken)
    except AssertionError:
        count += 1
    else:
        raise AssertionError('Missing path incorrectly accepted')
print(f'PASS {count} embedded-schema workflow path cases')
