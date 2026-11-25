#!/bin/bash
# Stage the change for the next normal boot; never stop or start Docker here.
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
START=/home/pi/Rosmaster/rosmaster/start_ros2_humble.sh
BACKUP=${START}.pre_m1_explorer
DEST=/home/pi/share/m1_explorer_motion
OLD='/bin/bash /root/run_handle.sh'
NEW='/bin/bash /root/share/m1_explorer_motion/start_m1_explorer.sh'
if [[ $EUID != 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
if [[ ${1:-} == --rollback ]]; then
  [[ -f "$BACKUP" ]] || { echo 'Original backup not found.' >&2; exit 1; }
  cp -a -- "$BACKUP" "${START}.restore.tmp"
  mv -f -- "${START}.restore.tmp" "$START"
  echo 'Original startup restored for next boot. Active container unchanged.'
  exit 0
fi
[[ $# == 0 ]] || { echo 'Usage: install_m1_motion.sh [--rollback]' >&2; exit 1; }
[[ -f "$START" && -f /home/pi/share/motion_safety_supervisor.py ]] || {
  echo 'Missing startup script or tested supervisor.' >&2; exit 1; }
for f in command_mux.py m1_explorer.launch.py start_m1_explorer.sh; do
  [[ -f "$BASE/$f" ]] || { echo "Missing $f" >&2; exit 1; }
done
python3 - "$BASE" /home/pi/share/motion_safety_supervisor.py <<'PY'
import pathlib, sys
base = pathlib.Path(sys.argv[1])
for path in [base/'command_mux.py', base/'m1_explorer.launch.py', pathlib.Path(sys.argv[2])]:
    compile(path.read_bytes(), str(path), 'exec')
PY
bash -n "$BASE/start_m1_explorer.sh"
# Refuse to overwrite an unexpected startup configuration or an existing backup.
if [[ -e "$BACKUP" ]]; then
  echo "Backup already exists: $BACKUP. Restore first or inspect manually." >&2; exit 1
fi
python3 - "$START" "$OLD" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); text = p.read_text()
if text.count(sys.argv[2]) != 1:
    raise SystemExit('Unexpected startup script; no changes applied.')
PY
install -d -o pi -g "$(id -gn pi)" -m 0755 "$DEST"
for f in command_mux.py m1_explorer.launch.py start_m1_explorer.sh; do
  install -o pi -g "$(id -gn pi)" -m 0644 "$BASE/$f" "$DEST/$f"
done
cp -a -- "$START" "$BACKUP"
cp -a -- "$START" "${START}.m1.tmp"
python3 - "${START}.m1.tmp" "$OLD" "$NEW" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); text = p.read_text()
p.write_text(text.replace(sys.argv[2], sys.argv[3], 1))
PY
bash -n "${START}.m1.tmp"
mv -f -- "${START}.m1.tmp" "$START"
echo 'Installed for next normal boot. No running processes changed.'
echo "Original saved at $BACKUP"
