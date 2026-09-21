#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -z "${CARVEFOUNDRY_REPO:-}" && -d /mnt/moar/Downloads/git/CarveFoundry ]]; then
    export CARVEFOUNDRY_REPO=/mnt/moar/Downloads/git/CarveFoundry
fi
python3 server.py "${@}"
