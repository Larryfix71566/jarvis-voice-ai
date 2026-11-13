"""Verify the pinned English test resource without downloading anything."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/nltk_data'
# Existing approved official member pins from sandbox/guest/prepare.sh.
ENGLISH_FILES = {
    'abbrev_types.txt': (619, '92a3e070f43d9b4c5534758ca40ad7343b04e7e29bfe0c2eb658a39445a4f779'),
    'collocations.tab': (594, '8e2da1225e4dd2cc9dba261ee231ccb134859e21b46006e7f472c5ee269af0cf'),
    'ortho_context.tab': (236303, '4bbcca25ed3d3f06c02402abf8419b9f033b8adc06e7b482eca4e45f81a5dc4c'),
    'sent_starters.txt': (241, 'f3f8535483e1dba487241b764945168123bca3209a9645e59acd1225dc76edac'),
}


def verify(root: Path = DATA_ROOT) -> Path:
    """Fail before consumer imports if any required bytes are absent or changed."""
    directory = root / 'tokenizers/punkt_tab/english'
    if any(path.is_symlink() for path in (root, root / 'tokenizers', directory.parent, directory)) or not directory.is_dir():
        raise ValueError('Pinned English tokenizer directory is missing or linked')
    if {path.name for path in directory.iterdir()} != set(ENGLISH_FILES):
        raise ValueError('Pinned English tokenizer member set differs')
    for name, (size, digest) in ENGLISH_FILES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise ValueError(f'Pinned English tokenizer size/type differs: {name}')
        with path.open('rb') as stream:
            data = stream.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Pinned English tokenizer hash differs: {name}')
    return root.resolve()


def smoke(root: Path = DATA_ROOT) -> None:
    """Cold import/tokenization with no user-resource fallback or network."""
    from unittest.mock import patch

    root = verify(root)
    os.environ['NLTK_DATA'] = str(root)

    def forbidden(*args, **kwargs):
        raise AssertionError('Offline tokenizer smoke attempted network/download')

    with (patch('socket.socket.connect', forbidden),
          patch('socket.socket.connect_ex', forbidden),
          patch('socket.socket.sendto', forbidden),
          patch('socket.getaddrinfo', forbidden)):
        import nltk
        nltk.data.path[:] = [str(root)]
        with patch.object(nltk, 'download', forbidden):
            from pipecat.utils import string
            assert string.nltk is nltk
            resource = Path(str(nltk.data.find('tokenizers/punkt_tab/english/'))).resolve()
            assert resource == root / 'tokenizers/punkt_tab/english'
            assert nltk.sent_tokenize('Dr. Smith arrived. This is offline.') == [
                'Dr. Smith arrived.', 'This is offline.']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    verify()
    if args.smoke:
        smoke()
    print('Pinned English tokenizer verified' + ('; offline smoke passed' if args.smoke else ''))


if __name__ == '__main__':
    main()
