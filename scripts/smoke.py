"""Check the running demo API and execute integration assertions in Airflow."""
import argparse
import json
import platform
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(url, path, payload=None, headers=None, expected=200):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url+path, data=data, headers={'Content-Type':'application/json', **(headers or {})})
    try:
        response = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as error:
        assert error.code == expected, f'{path}: HTTP {error.code}'
        return json.load(error)
    with response:
        assert response.status == expected
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:4192')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--allow-health-warning', action='append', default=[], metavar='SERVICE')
    args = parser.parse_args()
    env = dict(line.split('=',1) for line in args.env_file.read_text().splitlines() if line and not line.startswith('#'))
    assert request(args.url,'/api/v1/auth/me')['role'] == 'operator'
    assert request(args.url,'/api/v1/auth/me',headers={'x-demo-admin':env['DEMO_ADMIN_SECRET']})['role'] == 'owner'
    request(args.url,'/api/v1/services',{},expected=403)
    services = request(args.url,'/api/v1/services')
    assert {service['id'] for service in services} == {'analytics','snapshot','landing','orchestration','transformations'}
    for service in services:
        assert service['health'] == 'healthy' or (service['health'] == 'warning' and service['id'] in args.allow_health_warning), service
    for name,sql in (('analytics','select count(*) as n from raw.accounts'),('snapshot','select count(*) as n from marts.fct_revenue_daily')):
        result=request(args.url,f'/api/v1/services/{name}/actions/run-query',{'input':{'sql':sql}})
        assert result['status'] == 'success', result
        result = result['data']
        assert len(result['rows']) == 1 and int(result['rows'][0]['n']) > 0, result
    denied=request(args.url,'/api/v1/services/analytics/actions/run-query',{'input':{'sql':'delete from raw.accounts where false'}})
    assert denied['status'] == 'error', denied
    assert 'read-only' in denied['message'] or 'permission denied' in denied['message'], denied
    print('PASS anonymous/owner roles, management denial, five adapters, SQL reads and write denial',flush=True)
    if platform.system() == 'Darwin':
        base=['container','exec','-i','dsui-demo-airflow']
    else:
        base=['docker','compose','exec','-T','airflow']
    subprocess.run([*base,'python','-'],input=(ROOT/'tests/runtime_pipeline.py').read_text(),text=True,check=True,cwd=ROOT)


if __name__ == '__main__':
    main()
