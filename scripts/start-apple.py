"""Start the demo with Apple Containers and container-compose on macOS.

Render interpolation before container-compose 1.2 processes connection URLs.
Share files through host directories because writable block volumes cannot be
attached to several Apple VMs. Resolve service addresses without changing DNS.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ORDER = ('postgres','minio','data-generator','airflow','dsui')
SAFE_ENV = {key:os.environ[key] for key in ('PATH','HOME','TMPDIR','LANG') if key in os.environ}


def run(command, **options):
    return subprocess.run(command, env=SAFE_ENV, check=True, **options)


def address(service):
    result=run(['container','inspect','dsui-demo-'+service],capture_output=True,text=True)
    return json.loads(result.stdout)[0]['status']['networks'][0]['ipv4Address'].split('/')[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--state-dir',type=Path,default=ROOT/'.state')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--dsui-image')
    parser.add_argument('--airflow-image')
    args=parser.parse_args()
    state=args.state_dir.resolve(); state.mkdir(parents=True,exist_ok=True);state.chmod(0o700)
    for name in ('exports','logs','data'):
        path=state/name;path.mkdir(exist_ok=True);path.chmod(0o777)
    values=dict(line.split('=',1) for line in args.env_file.read_text().splitlines() if line and not line.startswith('#'))
    def substitute(match):
        name,operator,default=match.groups()
        if values.get(name):return values[name]
        if operator == ':?':raise ValueError(f'Missing required setting: {name}')
        return default or ''
    def expand(value):
        if isinstance(value,str):return re.sub(r'\$\{(\w+)(?:(:-|:\?)([^}]*))?\}',substitute,value)
        if isinstance(value,list):return [expand(item) for item in value]
        if isinstance(value,dict):return {key:expand(item) for key,item in value.items()}
        return value
    config=expand(yaml.safe_load((ROOT/'compose.yaml').read_text()))
    for service in config['services'].values():
        service.pop('depends_on',None)
        if 'build' in service:service['build']['context']=str(ROOT/service['build']['context'])
        mounts=[]
        for mount in service.get('volumes',[]):
            if mount.startswith('./'):mount=str(ROOT/mount)
            for volume,directory in (('demo-exports','exports'),('airflow-logs','logs'),('dsui-data','data')):
                if mount.startswith(volume+':'):mount=str(state/directory)+mount[len(volume):]
            mounts.append(mount)
        service['volumes']=mounts
    if args.dsui_image:config['services']['dsui']['image']=args.dsui_image
    if args.airflow_image:config['services']['airflow']['image']=args.airflow_image
    if args.build:
        for name in ('minio','data-generator','airflow','dsui'):
            service=config['services'][name];build=service['build']
            run(['container','build','-t',service['image'],'-f',str(ROOT/build.get('dockerfile','data-generator/Dockerfile')),build['context']])
    for name in reversed(ORDER):
        subprocess.run(['container','stop','dsui-demo-'+name],env=SAFE_ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    addresses={}
    for name in ORDER:
        current=copy.deepcopy(config)
        service=current['services'][name]
        for key,value in service.get('environment',{}).items():
            if isinstance(value,str):
                for host,ip in addresses.items():value=value.replace('@'+host+':','@'+ip+':').replace('http://'+host+':','http://'+ip+':')
                service['environment'][key]=value
        if name == 'dsui':
            dsui=(ROOT/'dsui.yaml').read_text()
            for host,ip in addresses.items():dsui=dsui.replace('host: '+host,'host: '+ip).replace('http://'+host+':','http://'+ip+':')
            path=state/'dsui.yaml';path.write_text(dsui)
            service['volumes'][0]=str(path)+':/etc/dsui/dsui.yaml:ro'
        path=state/'compose.yaml';path.write_text(yaml.safe_dump(current,sort_keys=False));path.chmod(0o600)
        print('Starting '+name,flush=True)
        run(['container-compose','up','--file',str(path),'--env-file',str(args.env_file.resolve()),'-d',name],stdout=subprocess.DEVNULL)
        test=service['healthcheck']['test'];check=['sh','-c',test[1]] if test[0]=='CMD-SHELL' else test[1:]
        deadline=time.monotonic()+900
        while subprocess.run(['container','exec','dsui-demo-'+name,*check],env=SAFE_ENV,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            if time.monotonic()>deadline:raise TimeoutError(name+' did not become healthy; inspect container logs')
            time.sleep(2)
        addresses[name]=address(name)
        print(name+' healthy',flush=True)
    print('Demo: http://localhost:'+values.get('DSUI_PORT','4192')+'/demo/',flush=True)


if __name__ == '__main__':
    main()
