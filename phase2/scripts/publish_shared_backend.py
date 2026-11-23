"""Publish only a public service address on a separate runtime branch."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote

REPO = 'repos/tyc13410573416-droid/collocate-mobile'
BRANCH = 'codex/ocr-runtime'


def api(path, body=None, method=None):
    executable = shutil.which('gh') or 'E:/gh.exe'
    args = [executable, 'api', REPO + '/' + path]
    if body is not None:
        args += ['-X', method or 'POST', '--input', '-']
    process = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             encoding='utf-8', timeout=30)
    if process.returncode:
        if 'HTTP 404' in process.stderr:
            raise FileNotFoundError('runtime branch not created')
        raise RuntimeError('GitHub runtime address update failed; check network and gh login')
    return json.loads(process.stdout)


def publish(url, active=True):
    if active and not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com', url):
        raise ValueError('Unexpected sharing address; nothing published')
    record = {'version': 1, 'active': active, 'image_api_base': url if active else '',
              'updated_at': datetime.now(timezone.utc).isoformat()}
    current = None
    try:
        current = api('contents/backend.json?ref=' + quote(BRANCH, safe=''))
        old = json.loads(base64.b64decode(current['content']))
        if old.get('active') == active and old.get('image_api_base') == record['image_api_base']:
            print('Fixed team entry already points to this OCR service')
            return
    except FileNotFoundError:
        pass
    encoded = base64.b64encode((json.dumps(record, indent=2) + '\n').encode()).decode()
    if current:
        api('contents/backend.json', {'message': 'Update team OCR service address',
            'content': encoded, 'branch': BRANCH, 'sha': current['sha']}, 'PUT')
    else:
        blob = api('git/blobs', {'encoding': 'base64', 'content': encoded})
        tree = api('git/trees', {'tree': [{'path': 'backend.json', 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}]})
        commit = api('git/commits', {'message': 'Initialize public OCR connection registry', 'tree': tree['sha'], 'parents': []})
        api('git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': commit['sha']})
    print('Fixed team entry updated; no credentials published')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='E:/MedTraceNexent/status/sharing.json')
    parser.add_argument('--offline', action='store_true')
    options = parser.parse_args()
    state = json.loads(Path(options.state).read_text(encoding='utf-8-sig'))
    publish(state.get('url', ''), not options.offline)
