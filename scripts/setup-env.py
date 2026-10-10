#!/usr/bin/env python3
"""Fill missing demo secrets without overwriting existing configuration."""
import argparse
import base64
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'.env')
    args = parser.parse_args()
    path = args.output
    text = path.read_text() if path.exists() else (Path(__file__).resolve().parents[1]/'.env.example').read_text()
    factories = {'DSUI_MASTER_KEY':lambda:base64.b64encode(secrets.token_bytes(32)).decode(),
                 'DEMO_ADMIN_SECRET':lambda:secrets.token_hex(24),
                 'AIRFLOW_FERNET_KEY':lambda:base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                 'AIRFLOW_API_PASSWORD':lambda:secrets.token_urlsafe(24)}
    lines = text.splitlines()
    for key, factory in factories.items():
        indices = [i for i,line in enumerate(lines) if line.startswith(key+'=')]
        if not indices:
            lines.append(key+'='+factory())
        elif not lines[indices[-1]].split('=',1)[1].strip():
            lines[indices[-1]] = key+'='+factory()
    path.write_text('\n'.join(lines)+'\n')
    path.chmod(0o600)
    print(f'Demo environment ready at {path}; existing values preserved.')


if __name__ == '__main__':
    main()
