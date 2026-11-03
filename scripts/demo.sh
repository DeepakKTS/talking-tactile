#!/bin/sh
# make demo-live / make demo-mock: the three demo servers under caffeinate -i, then the
# iPhone URLs, the .local name first. Ctrl-C stops all three.
#   API     127.0.0.1:8000, live (LIVE=1, costs credits) or mock (MOCK_META=1, no network)
#   web     npm run dev:phone, HTTPS on the LAN at :5173; it proxies /api to the API
#   Gate B  spikes/tracking/serve.py, the touch-test page, HTTPS on the LAN at :8443
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
  live) api_env="env -u MOCK_META LIVE=1" ;;
  mock) api_env="env -u LIVE MOCK_META=1" ;;
  *) echo "usage: scripts/demo.sh live|mock" >&2; exit 2 ;;
esac
for port in 8000 5173 8443; do
  held=$(lsof -nP -iTCP:$port -sTCP:LISTEN -Fpc | sed -n 's/^[pc]//p' | paste -sd ' ' -)
  if [ -n "$held" ]; then
    echo "Port $port is in use (pid and command: $held). Stop it first." >&2
    exit 1
  fi
done
[ -f apps/web/.certs/phone.pem ] || { echo "No phone certificate: cd apps/web && npm run cert:phone" >&2; exit 1; }

trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT
(cd services/api && exec caffeinate -i $api_env uv run uvicorn app.main:app --host 127.0.0.1 --port 8000) &
(cd apps/web && exec caffeinate -i npm run dev:phone) &
caffeinate -i python3 spikes/tracking/serve.py &

for _ in $(seq 1 120); do
  curl -s -o /dev/null http://127.0.0.1:8000/api/health && curl -sk -o /dev/null https://127.0.0.1:5173/ && break
  sleep 0.5
done

heart=913ba16a635188097dbb235741e05e376d23cca17bdb1789aec79a1497a67ada
brain=046e94d4f0b53298900ab96754caeb348dbc624b35841512d4e5b1198a36a699
ip=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo "<LAN address>")
names="$(scutil --get LocalHostName).local $ip"
echo
echo "Demo servers up ($1). On the iPhone, the .local name first, else the address:"
for label in "Device check|5173/explore?check=1" "Heart, version 4|5173/explore?figure=$heart&version=4" \
  "Commons brain, version 4|5173/explore?figure=$brain&version=4" "Gate B touch test|8443/"; do
  echo "  ${label%%|*}:"
  for n in $names; do echo "    https://$n:${label#*|}"; done
done
echo "  Author, on the Mac: https://localhost:5173/author"
echo "Ctrl-C stops all three."
wait
