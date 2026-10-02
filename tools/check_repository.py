"""Read-only preflight over tracked and non-ignored candidate files."""
from pathlib import Path
from collections import Counter
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {'.py', '.ps1', '.js', '.cjs', '.json', '.yaml', '.yml', '.md', '.txt', '.html', '.csv'}
SECRETS = {
    'GitHub token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'AWS access key': rb'\bAKIA[0-9A-Z]{16}\b',
    'API credential': rb'\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{40,}\b',
}


def candidates():
    raw = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT
    )
    return sorted(set(x.decode('utf-8') for x in raw.split(b'\0') if x))


def main():
    files = candidates()
    failures = []
    total = 0
    groups = Counter()
    for name in files:
        path = ROOT / name
        if not path.exists():
            failures.append({'path': name, 'issue': 'missing tracked file'})
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            failures.append({'path': name, 'issue': 'symlink/outside project'})
            continue
        size = path.stat().st_size
        total += size
        groups[name.split('/')[0] if '/' in name else '(root)'] += 1
        if size > 40 * 1024 * 1024:
            failures.append({'path': name, 'issue': 'exceeds repository 40 MiB per-file limit'})
        if path.suffix.lower() in {'.gguf', '.exe', '.dll', '.msi', '.pem', '.pfx', '.p12', '.key', '.part', '.pyc'}:
            failures.append({'path': name, 'issue': 'binary cache or credential file'})
        if path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
            failures.append({'path': name, 'issue': 'environment secrets file'})
        if path.suffix.lower() in TEXT_EXTENSIONS:
            content = path.read_bytes()
            for label, pattern in SECRETS.items():
                if re.search(pattern, content):
                    failures.append({'path': name, 'issue': label})  # Never print matched secret.
    # Check the new navigation pages; legacy relative links are preserved verbatim.
    for name in ['README.md', 'CONTRIBUTING.md', 'docs/REVIEW_INDEX.md', 'docs/DEMO.md', 'docs/DATA_AND_LICENSES.md']:
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            target = target.split('#')[0]
            dest = (path.parent / target).resolve()
            if not dest.exists():
                failures.append({'path': name, 'issue': 'broken local link', 'target': target})
            elif dest.is_file() and dest.relative_to(ROOT).as_posix() not in files:
                failures.append({'path': name, 'issue': 'link target excluded from repository', 'target': target})
    result = {'status': 'passed' if not failures else 'failed', 'files': len(files),
              'total_bytes': total, 'groups': dict(sorted(groups.items())), 'failures': failures,
              'scope': 'Pattern and size preflight, not a comprehensive security audit.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
