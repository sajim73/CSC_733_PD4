"""Verify generated RQ1/RQ2/RQ3 CSV bytes against the ORIGINAL PD2 reference.

Outputs from other numerical library versions may differ, so a mismatch means
investigate; it does not on its own establish scientific non-reproducibility.
Usage: python tools/verify_reference.py [results-directory]
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'reference' / 'sha256_csv.json'


def main():
    output = Path(sys.argv[1]).resolve() if len(sys.argv) >= 2 else ROOT / 'results'
    expected = json.loads(MANIFEST.read_text())['files']
    mismatches = 0
    for name, digest in expected.items():
        path = output / name
        if not path.is_file():
            print(f'MISSING {name}: {path}')
            mismatches += 1
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        status = 'PASS' if actual == digest else 'MISMATCH'
        print(f'{status}: {name} ({actual[:14]})')
        if actual != digest:
            mismatches += 1
    print(f'REFERENCE CHECK: {len(expected) - mismatches}/{len(expected)} exact CSV matches')
    return int(mismatches > 0)


if __name__ == '__main__':
    sys.exit(main())
