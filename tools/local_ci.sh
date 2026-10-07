#!/usr/bin/env bash
# Runs what .github/workflows/tests.yml runs, on this machine, so a PR can be checked without GitHub Actions minutes.
#   tools/local_ci.sh            offline suite + byte-compile + ruff + zip check + the QGIS 4.2.2 live job (needs Docker)
#   tools/local_ci.sh --offline  everything except the Docker live job
# Not covered: the windows-latest job (path-handling bugs only show there) and gitleaks (secret scan).
# The QGIS image digest below must match the one in the workflow; update both together.
set -u
cd "$(dirname "$0")/.."
QGIS_IMAGE="qgis/qgis@sha256:6ffe6b31646247f2e179cb2cc32bb4df215eedc99f387ad59a6cc88ebfe23e21"
PG_IMAGE="postgis/postgis:16-3.4"
status=0
step() { echo; echo "=== $1"; }

step "offline test suite"
python -m unittest discover -s tests -t . -p "test_*.py" > /tmp/cartogen_offline.log 2>&1 || { echo "FAILED: offline suite"; status=1; }
tail -4 /tmp/cartogen_offline.log

step "byte-compile"
find . -name "*.py" -not -path "./.git/*" -not -path "./build/*" -not -path "./dist/*" -print0 | xargs -0 -n1 python -m py_compile || { echo "FAILED: py_compile"; status=1; }

step "ruff"
ruff check . || status=1

step "release zip"
python plugin_upload.py >/dev/null 2>&1 && test -f cartogen_ai.zip && python -c "
import zipfile, os
z = zipfile.ZipFile('cartogen_ai.zip'); names = z.namelist()
assert any('cartogen-ai/metadata.txt' in n for n in names)
assert any('cartogen-ai/src/cartogen_ai/core/agent/agent_orchestrator.py' in n for n in names)
print('zip ok:', len(names), 'files', round(os.path.getsize('cartogen_ai.zip')/1048576, 2), 'MB')" || { echo "FAILED: zip"; status=1; }

if [ "${1:-}" = "--offline" ]; then echo; echo "(live job skipped: --offline)"; exit $status; fi

step "QGIS 4.2.2 live job (Docker)"
command -v docker >/dev/null || { echo "docker not found"; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker daemon not running (try: sudo dockerd &)"; exit 1; }
NET=cartogen-ci-net; PG=cartogen-ci-pg
docker network create $NET >/dev/null 2>&1
docker rm -f $PG >/dev/null 2>&1
docker run -d --name $PG --network $NET -e POSTGRES_PASSWORD=cartogen_ci $PG_IMAGE >/dev/null
for i in $(seq 1 30); do docker exec $PG pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
docker run --rm --network $NET -v "$PWD":/work -w /work \
  -e QT_QPA_PLATFORM=offscreen -e QGIS_TAG=4.2.2 \
  -e CARTOGEN_TEST_PG_HOST=$PG -e CARTOGEN_TEST_PG_PORT=5432 -e CARTOGEN_TEST_PG_DATABASE=postgres \
  -e CARTOGEN_TEST_PG_USER=postgres -e CARTOGEN_TEST_PG_PASSWORD=cartogen_ci \
  "$QGIS_IMAGE" bash -c '
    grep -v -E "^ultralytics|^#|^$" requirements.txt > /tmp/reqs.txt
    xargs -r python3 -m pip install --break-system-packages < /tmp/reqs.txt >/dev/null 2>&1 || xargs -r python3 -m pip install < /tmp/reqs.txt >/dev/null 2>&1
    python3 -m tests._ci_run_live_tests > /tmp/live.log 2>&1; s=$?
    tail -40 /tmp/live.log
    # known post-test interpreter-shutdown segfault: exit 139 AFTER unittest printed OK is not a failure (see the workflow)
    if [ "$s" -eq 139 ] && grep -q "Segmentation fault" /tmp/live.log && grep -qE "^OK( \(skipped=[0-9]+\))?$" /tmp/live.log; then echo "(known shutdown segfault after OK: treated as pass)"; exit 0; fi
    exit $s' || { echo "FAILED: live QGIS tests"; status=1; }
docker rm -f $PG >/dev/null 2>&1; docker network rm $NET >/dev/null 2>&1
echo; [ $status -eq 0 ] && echo "LOCAL CI: ALL PASSED" || echo "LOCAL CI: FAILURES ABOVE"
exit $status
