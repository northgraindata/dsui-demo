"""Check a live webserver and scheduler instead of only the installed version."""
import json
import urllib.request

with urllib.request.urlopen('http://localhost:8080/health', timeout=5) as response:
    report = json.load(response)
for component in ('metadatabase', 'scheduler'):
    if report[component]['status'] != 'healthy':
        raise SystemExit(f'{component} is unhealthy')
