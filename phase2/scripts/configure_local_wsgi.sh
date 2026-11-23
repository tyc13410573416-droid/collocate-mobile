#!/usr/bin/env bash
set -euo pipefail
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
/opt/medtrace/python/bin/python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple gunicorn==23.0.0
mkdir -p /etc/systemd/system/medtrace-api.service.d
cat >/etc/systemd/system/medtrace-api.service.d/wsgi.conf <<'UNIT'
[Service]
ExecStart=
ExecStart=/opt/medtrace/python/bin/gunicorn --bind 0.0.0.0:5052 --workers 1 --threads 4 --timeout 360 --graceful-timeout 15 phase1.app:app
UNIT
systemctl daemon-reload
systemctl restart medtrace-api
for attempt in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:5052/api/image-status >/dev/null; then
        printf 'Local production WSGI is ready.\n'
        exit 0
    fi
    sleep 1
done
exit 1
