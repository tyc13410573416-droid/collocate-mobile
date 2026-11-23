"""Allow the verified team URL on the private image backend, without secrets."""
import json
from pathlib import Path
import re

root=Path('/mnt/e/MedTraceNexent')
state=json.loads((root/'status/sharing.json').read_text(encoding='utf-8-sig'))
url=state['url']
if not isinstance(url,str) or not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',url):
    raise ValueError('Unexpected public sharing hostname')
env=Path('/opt/medtrace/private/medtrace.env')
values=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line)
allowed=[value.strip() for value in values.get('IMAGE_ALLOWED_ORIGINS','').split(',') if value.strip()]
allowed=[value for value in allowed if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',value)]
values['IMAGE_ALLOWED_ORIGINS']=','.join(dict.fromkeys(allowed+[url]))
env.write_text(''.join(key+'='+value+'\n' for key,value in values.items()));env.chmod(0o600)
print('Team HTTPS origin configured')
