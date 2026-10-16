#!/usr/bin/env bash
set -Eeuo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
trap 'logger -t marinkino-duckdns "DuckDNS update failed; check domain and token"' ERR
project=''
if [[ ${1:-} == --project ]]; then project=$2; else project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd); fi
helper_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Read token without sourcing .env or putting it in process arguments/logs.
python3 - "$project" "$helper_dir" <<'PY'
import sys
import urllib.parse
import urllib.request
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from security_config import deployment_config
values = deployment_config(Path(sys.argv[1]))
domain, token = values.get('DUCKDNS_DOMAIN', ''), values.get('DUCKDNS_TOKEN', '')
if domain and token:
    if not domain.endswith('.duckdns.org'):
        raise SystemExit('DUCKDNS_DOMAIN must end in .duckdns.org')
    query = urllib.parse.urlencode({'domains': domain.removesuffix('.duckdns.org'), 'token': token, 'ip': ''})
    request = urllib.request.Request('https://www.duckdns.org/update?' + query)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.read(64).strip() != b'OK':
                raise SystemExit('DuckDNS update refused')
    except Exception:
        raise SystemExit('DuckDNS request failed') from None
PY
