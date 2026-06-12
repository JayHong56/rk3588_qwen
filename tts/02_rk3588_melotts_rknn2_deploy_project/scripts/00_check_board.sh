#!/usr/bin/env bash
set -euo pipefail
uname -a
cat /etc/os-release || true
lscpu | sed -n '1,25p' || true
ls -l /dev/rknpu* /dev/dri/render* 2>/dev/null || true
python3 - <<'PYEOF' || true
try:
    from rknnlite.api import RKNNLite
    print("rknnlite import OK")
except Exception as e:
    print("rknnlite import FAIL", repr(e))
PYEOF
aplay -l || true
id || true
