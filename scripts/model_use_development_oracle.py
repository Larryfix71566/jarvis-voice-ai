#!/usr/bin/env python3
"""Frozen behavioral oracle; candidate imports are allowed only in the guest."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys

GUEST_ROOTS = {'baseline': '/Users/admin/mortimer/verification',
               'candidate': '/Users/admin/mortimer/source'}
CORPUS_SHA256 = '6e3da0f9c65318a274a33187bcb26935856b2423a947b7d688ada9f957f0e867'
CASE_ID = 'date-diff-mixed-awareness'


def validate_spec(value):
    if (type(value) is not dict or set(value) != {'version', 'cases'}
            or value['version'] != 'date-diff-oracle-v1' or type(value['cases']) is not list
            or not 1 <= len(value['cases']) <= 64):
        raise ValueError('oracle_spec_invalid')
    seen = set()
    for case in value['cases']:
        if type(case) is not dict:
            raise ValueError('oracle_spec_invalid')
        expected = 'expected_error' if 'expected_error' in case else 'expected'
        if (set(case) != {'id', 'timezone', 'a', 'b', expected}
                or type(case['id']) is not str or not case['id'].isascii()
                or not case['id'] or len(case['id']) > 80 or case['id'] in seen
                or type(case['timezone']) is not str or len(case['timezone']) > 80
                or any(item is not None and (type(item) is not str or len(item) > 256)
                       for item in (case['a'], case['b']))):
            raise ValueError('oracle_spec_invalid')
        seen.add(case['id'])
        if expected == 'expected_error':
            if case[expected] is not True:
                raise ValueError('oracle_spec_invalid')
        else:
            result = case[expected]
            if (type(result) is not dict or set(result) != {'days', 'hours'}
                    or type(result['days']) is not int or type(result['hours']) is not float
                    or not math.isfinite(result['hours'])):
                raise ValueError('oracle_spec_invalid')
    return value


def evaluate(function, spec):
    """Return only fixed case IDs/booleans; never returned content or errors."""
    validate_spec(spec)
    outcomes = []
    prior = os.environ.get('JARVIS_TIMEZONE')
    try:
        for case in spec['cases']:
            os.environ['JARVIS_TIMEZONE'] = case['timezone']
            try:
                actual = function(case['a'], case['b'])
                if 'expected_error' in case:
                    passed = type(actual) is dict and set(actual) == {'error'} and type(actual['error']) is str
                else:
                    passed = (type(actual) is dict and set(actual) == {'days', 'hours'}
                              and type(actual['days']) is int and type(actual['hours']) is float
                              and actual == case['expected'])
            except BaseException:
                passed = False
            outcomes.append({'id': case['id'], 'passed': passed})
    finally:
        if prior is None:
            os.environ.pop('JARVIS_TIMEZONE', None)
        else:
            os.environ['JARVIS_TIMEZONE'] = prior
    return {'version': 'date-diff-oracle-result-v1', 'cases': outcomes,
            'passed': all(item['passed'] for item in outcomes)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=tuple(GUEST_ROOTS), required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--spec-sha256', required=True)
    args = parser.parse_args(argv)
    if os.environ.get('MORTIMER_SANDBOX_GUEST') != '1':
        parser.exit(2, 'guest_oracle_required\n')
    root = Path(GUEST_ROOTS[args.phase])
    if root.resolve() != root or args.spec.is_symlink():
        parser.exit(2, 'guest_oracle_source_invalid\n')
    raw = args.spec.read_bytes()
    if len(raw) > 64 * 1024 or hashlib.sha256(raw).hexdigest() != args.spec_sha256:
        parser.exit(2, 'guest_oracle_spec_invalid\n')
    spec = validate_spec(json.loads(raw))
    sys.path.insert(0, str(root))
    function = importlib.import_module('mcp_servers.mcp_time.logic').date_diff
    result = evaluate(function, spec)
    result['phase'] = args.phase
    result['spec_sha256'] = args.spec_sha256
    result['corpus_sha256'] = CORPUS_SHA256
    result['case_id'] = CASE_ID
    result['oracle_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
