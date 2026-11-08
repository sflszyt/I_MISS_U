"""Offline, redacted audit of the entire candidate tree or Git index.

Exit 1 means findings; exit 2 means an incomplete audit. No matched values or
file contents are printed. This is a heuristic, not proof of anonymity.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path


PATTERNS = {
    'fixed_sha256_requires_review': re.compile(r'(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])'),
    'provider_key': re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'windows_user_path': re.compile(r'(?i)[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)[^\\/\s\"\']+'),
    'wechat_id': re.compile(r'\bwxid_[A-Za-z0-9]+'),
    'credential_literal': re.compile(r'''(?i)["']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|password|token|key|secret)["']?\s*[:=]\s*["']([A-Za-z0-9_+/=-]{20,})["']'''),
}
EMAIL = re.compile(r'[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})')
SAFE_EMAIL_DOMAINS = {'example.com', 'example.org', 'example.net', 'example.invalid', 'test.invalid'}
# Exact application storage-field name, not an authentication value.
NON_CREDENTIAL_VALUES = {'companion_archive_disabled'}


def scan_text(path, text, private_patterns=()):
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for category, pattern in PATTERNS.items():
            matches = list(pattern.finditer(line))
            if category == 'credential_literal':
                matches = [match for match in matches if match.group(1) not in NON_CREDENTIAL_VALUES]
            if matches:
                findings.append({'path': path, 'line': number, 'category': category})
        if any(match.group(1).lower() not in SAFE_EMAIL_DOMAINS for match in EMAIL.finditer(line)):
            findings.append({'path': path, 'line': number, 'category': 'email'})
        if any(pattern.search(line) for pattern in private_patterns):
            findings.append({'path': path, 'line': number, 'category': 'local_private_identifier'})
    return findings


def git(root, *args, input=None):
    result = subprocess.run(['git', '-C', str(root), *args], input=input, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Git command failed; output withheld')
    return result


def ignored_paths(root, paths):
    if not paths:
        return set()
    result = git(root, 'check-ignore', '--no-index', '-z', '--stdin',
                 input=('\0'.join(paths) + '\0').encode('utf-8'))
    return set(result.stdout.decode('utf-8').rstrip('\0').split('\0')) - {''}


def audit(root, staged=False):
    policy = root / '.privacy-policy.json'
    private_patterns = []
    if policy.exists():
        try:
            values = json.loads(policy.read_text(encoding='utf-8'))
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError('invalid policy')
            private_patterns = [re.compile(value, re.I) for value in values]
        except (ValueError, OSError, re.error):
            raise RuntimeError('Invalid private scan policy') from None
    tracked = set(git(root, 'ls-files', '-z').stdout.decode('utf-8').split('\0')) - {''}
    paths = tracked if staged else tracked | (set(git(root, 'ls-files', '--others', '--exclude-standard', '-z').stdout.decode('utf-8').split('\0')) - {''})
    ignored = ignored_paths(root, sorted(paths))
    findings = []
    errors = []
    scanned = 0
    for path in sorted(paths):
        if path in ignored:
            if path in tracked:
                findings.append({'path': path, 'line': 0, 'category': 'tracked_ignored_file'})
            continue  # Never open private files, even if still tracked.
        file = root / path
        try:
            if staged:
                entry = git(root, 'ls-files', '-s', '--', path).stdout
                if not entry.startswith(b'100644 ') and not entry.startswith(b'100755 '):
                    raise ValueError('unsupported_git_mode')
                data = git(root, 'show', ':' + path).stdout
            else:
                if file.is_symlink() or file.resolve().is_relative_to(root.resolve()) is False:
                    raise ValueError('unsafe_path')
                if not file.exists():
                    continue  # Deleted worktree file; index mode checks its old contents.
                data = file.read_bytes()
            if b'\0' in data:
                raise ValueError('binary_requires_review')
            text = data.decode('utf-8-sig')
            findings.extend(scan_text(path, text, private_patterns))
            scanned += 1
        except (OSError, UnicodeError, ValueError):
            errors.append({'path': path, 'category': 'unreadable_or_nontext_requires_review'})
    return {'mode': 'index' if staged else 'candidate', 'scanned': scanned,
            'findings': findings, 'errors': errors,
            'excluded_paths': sorted(ignored),
            'candidate_paths': sorted(paths - ignored)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Scan the entire index, not only changed files')
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[1]
        report = audit(root, args.staged)
    except (RuntimeError, OSError, UnicodeError):
        print(json.dumps({'error': 'Audit incomplete; Git or filesystem error'}))
        return 2
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 2 if report['errors'] else (1 if report['findings'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
