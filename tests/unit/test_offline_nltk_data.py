"""B5 uses pinned real English data, never a download or synthetic tokenizer."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.check_test_nltk_data import DATA_ROOT, ENGLISH_FILES, verify


def test_bundled_data_is_exact_existing_approved_resource():
    root = verify()
    recipe = (Path(__file__).resolve().parents[2] / 'sandbox/guest/prepare.sh').read_text()
    for name, (size, digest) in ENGLISH_FILES.items():
        raw = (root / 'tokenizers/punkt_tab/english' / name).read_bytes()
        assert len(raw) == size and hashlib.sha256(raw).hexdigest() == digest
        assert digest in recipe


@pytest.mark.parametrize('variant', ['missing', 'corrupt', 'extra', 'symlink', 'linked-directory'])
def test_resource_mutations_fail_before_consumer_import(tmp_path, variant):
    root = tmp_path / 'data'
    shutil.copytree(DATA_ROOT, root)
    directory = root / 'tokenizers/punkt_tab/english'
    path = directory / 'abbrev_types.txt'
    if variant == 'missing': path.unlink()
    elif variant == 'corrupt': path.write_bytes(b'X' + path.read_bytes()[1:])
    elif variant == 'extra': (directory / 'unexpected.pickle').write_bytes(b'not allowed')
    elif variant == 'symlink':
        path.unlink()
        path.symlink_to(DATA_ROOT / 'tokenizers/punkt_tab/english/abbrev_types.txt')
    else:
        moved = directory.with_name('saved')
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match='Pinned English tokenizer'):
        verify(root)


def test_cold_tokenizer_import_with_empty_home_and_no_network(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'SYSTEMROOT', 'LANG', 'LC_ALL'}}
    env.update(HOME=str(tmp_path), NLTK_DATA=str(tmp_path / 'missing'), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, 'scripts/check_test_nltk_data.py', '--smoke'],
                            cwd=repo, env=env, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert 'offline smoke passed' in result.stdout
    assert not (tmp_path / 'nltk_data').exists()


def test_ci_enforces_full_pyflakes_and_verifies_data_before_import():
    import yaml
    repo = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((repo / '.github/workflows/validate.yml').read_text())
    job = workflow['jobs']['validate']
    assert job['env']['NLTK_DATA'] == '${{ github.workspace }}/tests/fixtures/nltk_data'
    steps = job['steps']
    smoke = next(i for i, step in enumerate(steps) if step.get('name') == 'Verify bundled offline tokenizer')
    imports = next(i for i, step in enumerate(steps) if step.get('name') == 'Backend import smoke')
    assert smoke < imports
    assert steps[smoke]['run'] == 'python scripts/check_test_nltk_data.py --smoke'
    command = next(step['run'] for step in steps if step.get('name') == 'Pyflakes checks (ruff F)')
    assert command == 'ruff check --isolated --select F jarvis mcp_servers scripts services sandbox tests'
