#!/usr/bin/env bash
# namespaces + cgroup v2 + урезанные права + seccomp
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$APP_DIR/.venv/bin/python"

if [[ "${1:-}" == "--inner" ]]; then
  hostname mydocker
  ip link set lo up
  exec setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
    "$PY" "$APP_DIR/seccomp_wrapper.py" "$PY" "$APP_DIR/main.py"
fi

[[ $EUID -eq 0 ]] || exec sudo -E "$0" "$@"

RUN_UID="${SUDO_UID:-1000}"
RUN_GID="${SUDO_GID:-1000}"
CG=/sys/fs/cgroup/mydocker
MEM="${MEM:-100M}"
CPU="${CPU:-50000 100000}"      # 0.5 ядра
PIDS="${PIDS:-50}"

mkdir -p "$CG"
echo "$MEM"  > "$CG/memory.max"
echo 0       > "$CG/memory.swap.max"
echo "$CPU"  > "$CG/cpu.max"
echo "$PIDS" > "$CG/pids.max"

exec sh -c '
  echo $$ > "$0/cgroup.procs"
  exec setpriv --reuid="$1" --regid="$2" --clear-groups \
    unshare --user --map-root-user --pid --fork --mount-proc --mount --net --uts --ipc \
    "$3" --inner
' "$CG" "$RUN_UID" "$RUN_GID" "$APP_DIR/mydocker.sh"