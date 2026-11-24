#!/usr/bin/env python3
"""R0B0T1CS LAB / P01-R03 — passive sensor and peripheral inventory.

Python 3 standard library only. Does not open serial/video/I2C devices, launch ROS
nodes, change configuration, or send commands to robot hardware.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

BASE = Path('/home/pi')
OUTPUT = BASE if BASE.is_dir() else Path.home()
NOW = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
ZIP = OUTPUT / ('R03_sensor_inventory_' + NOW + '.zip')


def run(argv, timeout=18):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return {'status': p.returncode, 'stdout': p.stdout[:24000].strip(),
                'stderr': p.stderr[:500].strip()}
    except (OSError, subprocess.TimeoutExpired) as ex:
        return {'status': 'error', 'stdout': '', 'stderr': str(ex)}


def symlinks(path):
    p = Path(path)
    if not p.is_dir():
        return []
    return [{'name': i.name, 'target': str(i.resolve())} for i in sorted(p.iterdir())
            if i.is_symlink()][:80]


def safe_udev(dev):
    out = run(['udevadm', 'info', '--query=property', '--name=' + dev])
    keys = {'ID_VENDOR', 'ID_VENDOR_ID', 'ID_MODEL', 'ID_MODEL_ID',
            'ID_USB_DRIVER', 'ID_V4L_PRODUCT', 'ID_BUS', 'ID_PATH'}
    selected = {}
    for line in out['stdout'].splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k in keys:
                selected[k] = v
    return selected


print('[1/4] Inventaire Linux / USB / interfaces (lecture seule)')
report = {'project': 'R0B0T1CS LAB P01 / R03 Sensor Inventory',
          'timestamp_from_robot_clock': dt.datetime.now().isoformat(),
          'disclaimer': 'Inventaire statique, présence physique et fonctionnement non prouvés.',
          'host': {}, 'devices': {}, 'docker': {}, 'yahboom_sources': {}}
for label, args in {
    'os_release': ['cat', '/etc/os-release'],
    'uname': ['uname', '-a'],
    'usb_devices': ['lsusb'],
    'usb_tree': ['lsusb', '-t'],
    'video4linux': ['sh', '-c', 'ls -l /sys/class/video4linux 2>/dev/null || true'],
}.items():
    report['host'][label] = run(args)
report['devices']['serial_by_id'] = symlinks('/dev/serial/by-id')
report['devices']['serial_by_path'] = symlinks('/dev/serial/by-path')
report['devices']['video_by_id'] = symlinks('/dev/v4l/by-id')
report['devices']['video_by_path'] = symlinks('/dev/v4l/by-path')
interesting = []
for globpat in ('ttyUSB*', 'ttyACM*', 'ttyAMA*', 'video*', 'i2c-*', 'gpiochip*'):
    interesting.extend(Path('/dev').glob(globpat))
for p in sorted(set(interesting), key=str):
    if len(report['devices'].get('device_nodes', [])) >= 80:
        break
    report['devices'].setdefault('device_nodes', []).append(
        {'path': str(p), 'udev': safe_udev(str(p)) if p.name.startswith(('ttyUSB', 'ttyACM', 'video')) else {}})

print('[2/4] Identification d’un container Yahboom existant')
containers = run(['docker', 'ps', '--format', '{{.ID}}\t{{.Names}}\t{{.Image}}'])
report['docker']['running_containers'] = containers
chosen = None
if containers['status'] == 0:
    rows = [line.split('\t') for line in containers['stdout'].splitlines() if '\t' in line]
    preferred = [r for r in rows if len(r) >= 3 and ('yahboom' in r[2].lower() or 'ros-humble-m1' in r[2].lower())]
    if len(preferred) == 1:
        chosen = preferred[0]
    elif not preferred:
        report['docker']['note'] = 'Aucun container Yahboom actif identifié de manière univoque.'
    else:
        report['docker']['note'] = 'Plusieurs containers Yahboom actifs ; aucun choix automatique.'

print('[3/4] Recherche passive des packages capteurs Yahboom')
if chosen:
    report['docker']['selected_container'] = {'id': chosen[0], 'name': chosen[1], 'image': chosen[2]}
    # The code inside container reads only metadata and filenames, never executes package code.
    inspector = r'''
import json
from pathlib import Path
root=Path('/root/yahboomcar_ros2_ws/yahboomcar_ws/src')
terms=('laser','lidar','astra','camera','depth','imu','vision','voice','base','description','bringup','control','ctrl','sensor')
result={'workspace_exists':root.is_dir(),'packages':[]}
if root.is_dir():
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir() or not any(t in pkg.name.lower() for t in terms):
            continue
        manifests=list(pkg.glob('package.xml'))
        launches=[str(p.relative_to(pkg)) for p in pkg.rglob('*launch.py') if len(p.relative_to(pkg).parts)<6]
        confs=[str(p.relative_to(pkg)) for p in pkg.rglob('*.yaml') if len(p.relative_to(pkg).parts)<6]
        result['packages'].append({'name':pkg.name,'has_package_xml':bool(manifests),
            'launch_files':launches[:35],'yaml_files':confs[:35]})
print(json.dumps(result,ensure_ascii=False))
'''
    raw = run(['docker', 'exec', chosen[0], 'python3', '-c', inspector], timeout=45)
    if raw['status'] == 0:
        try:
            report['yahboom_sources'] = json.loads(raw['stdout'])
        except json.JSONDecodeError:
            report['yahboom_sources'] = {'note': 'Impossible de décoder le résultat.', 'error': raw['stderr']}
    else:
        report['yahboom_sources'] = {'error': raw['stderr'], 'status': raw['status']}
else:
    report['yahboom_sources'] = {'note': 'Inspection des packages ignorée : container non sélectionné.'}

print('[4/4] Création d’un résumé et d’une archive ZIP')
lines = ['# R03 — Inventaire passif des capteurs et périphériques', '',
         'Horodatage fourni par le Raspberry Pi : ' + report['timestamp_from_robot_clock'], '',
         '> La détection d’un périphérique ne prouve pas que son capteur fonctionne.',
         '> Aucun périphérique série, caméra ou moteur n’a été ouvert.', '',
         '## USB détectés', '```', report['host']['usb_devices']['stdout'] or '(commande indisponible)', '```', '',
         '## Interfaces et identifiants persistants']
for kind in ('serial_by_id', 'serial_by_path', 'video_by_id', 'device_nodes'):
    lines.append('### ' + kind)
    entries = report['devices'].get(kind, [])
    lines.extend('- ' + (e.get('path') or e.get('name', '')) +
                 (' → ' + e['target'] if e.get('target') else '') +
                 (' (' + e['udev'].get('ID_MODEL','') + ')' if e.get('udev') else '')
                 for e in entries)
    if not entries:
        lines.append('- Aucun résultat')
lines += ['', '## Packages Yahboom liés aux capteurs']
for pkg in report['yahboom_sources'].get('packages', []):
    lines.append('- **' + pkg['name'] + '** : ' + str(len(pkg['launch_files'])) +
                 ' fichiers launch ; ' + str(len(pkg['yaml_files'])) + ' fichiers YAML')
if not report['yahboom_sources'].get('packages'):
    lines.append('- Aucun package inventorié : vérifier le JSON pour la raison.')
lines += ['', '## Limites', '- Inventaire sans mesure de données capteurs en temps réel.',
          '- Connexions physiques STM32, IMU, encodeurs, OLED : à confirmer.',
          '- Ne pas déduire une fréquence, une précision ou une disponibilité matérielle d’un nom de package.',
          '- Vérifier le contenu avant partage : les identifiants et chemins matériels peuvent être visibles.', '']
with zipfile.ZipFile(ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('R03_inventory.json', json.dumps(report, indent=2, ensure_ascii=False))
    z.writestr('R03_summary.md', '\n'.join(lines))
    z.writestr('README.txt', 'R03 — inventaire passif (lecture seule).\nVérifier avant partage.\n')
print('✅ Archive créée :', ZIP)
print('Interfaces inventoriées :', len(report['devices'].get('device_nodes', [])))
print('Packages Yahboom inventoriés :', len(report['yahboom_sources'].get('packages', [])))
print('Aucune commande moteur ni ouverture de capteur.')
