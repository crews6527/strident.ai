"""Explicit setup for private Tailscale Serve. Does not enable Funnel or public access."""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import urlsplit
from pcs_agent.config import load,save,config_path


def configure_host(config, hostname):
    host=hostname.rstrip('.').lower()
    if not host.endswith('.ts.net') or not all(c.isalnum() or c in '.-' for c in host):
        raise ValueError('Tailscale did not report a valid private .ts.net hostname.')
    return {**config,'preview_hosts':list(dict.fromkeys(config['preview_hosts']+[host])),
            'preview_key':config.get('preview_key') or secrets.token_urlsafe(32)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--disable',action='store_true');args=parser.parse_args()
    command=shutil.which('tailscale')
    if not command:
        candidate=Path(r'C:\Program Files\Tailscale\tailscale.exe')
        if candidate.is_file():command=str(candidate)
    if not command:raise RuntimeError('Tailscale CLI was not found. Install or open Tailscale on this PC first.')
    config=load()
    if args.disable:
        subprocess.run([command,'serve','--https=443','off'],check=True,timeout=30)
        print('Tailscale Serve on HTTPS port 443 is disabled.');return
    print('Close Strident before setup, then reopen it and click Live preview / phone.')
    state=json.loads(subprocess.check_output([command,'status','--json'],timeout=15))
    if state.get('BackendState')!='Running':raise RuntimeError('Sign in to Tailscale on the PC first.')
    host=state.get('Self',{}).get('DNSName','').rstrip('.')
    configured=configure_host(config,host)
    # Avoid replacing an unrelated Serve listener. The user owns any existing configuration.
    existing=json.loads(subprocess.check_output([command,'serve','status','--json'],timeout=15) or b'{}')
    if existing:
        target=f'http://127.0.0.1:{config["preview_port"]}'
        encoded=json.dumps(existing)
        if target not in encoded or 'Funnel' in encoded and 'true' in encoded.lower():
            raise RuntimeError('An existing Tailscale Serve/Funnel configuration needs review. No configuration was replaced. Inspect tailscale serve status.')
    path=config_path()
    if path.exists():shutil.copy2(path,path.with_name('config-before-phone.json'))
    save(configured)
    subprocess.run([command,'serve','--bg','--https=443',f'http://127.0.0.1:{config["preview_port"]}'],check=True,timeout=30)
    print('Private phone address: https://'+host+'/')
    print('Console access key: '+configured['preview_key'])
    print('Keep this key private. Connect the phone to the same Tailscale network, open that address and enter the key. Keep Strident running with its preview open and the PC awake.')
    print('Undo private HTTPS sharing with Enable-Phone.cmd --disable.')

if __name__=='__main__':
    try:main()
    except Exception as exc:print('Phone setup did not finish: '+str(exc));raise SystemExit(1)
