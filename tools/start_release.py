"""Local or container single-service entry point. Never logs request query strings."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.environment import load_environment
import uvicorn
def configuration(environ=None):
    env=os.environ if environ is None else environ
    host=env.get('BIND_HOST','127.0.0.1')
    import ipaddress
    if host!='localhost':ipaddress.ip_address(host)
    port=int(env.get('PORT','8000'))
    if not 1<=port<=65535:raise ValueError('PORT outside permitted range')
    browser='127.0.0.1' if host in ('localhost','0.0.0.0','::') else host
    if ':' in browser:browser='['+browser+']'
    return host,port,f'http://{browser}:{port}'

if __name__=='__main__':
    # Local private configuration only; never copy it into a browser bundle.
    private=Path(__file__).resolve().parents[1]/'backend/.env.local'
    load_environment(os.getenv('MFT_ENV_FILE') or (private if private.is_file() else None))
    host,port,url=configuration()
    print(f'Open MakeFromThis: {url}',flush=True)
    uvicorn.run('app.main:app',host=host,port=port,workers=1,proxy_headers=False,
                access_log=False,limit_concurrency=32,timeout_keep_alive=5,timeout_graceful_shutdown=45)
