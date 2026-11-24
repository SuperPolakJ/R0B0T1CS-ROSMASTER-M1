#!/usr/bin/env python3
"""R0B0T1CS LAB / P01-R05: passive odometry and sensor fusion inventory.

Reads selected Yahboom ROS 2 sources within an existing Docker container.
Does NOT launch nodes, open hardware interfaces, change settings, or move motors.
"""
import datetime
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = '/root/yahboomcar_ros2_ws/yahboomcar_ws/src'
TARGETS = {
    'M1_bringup_launch.py': f'{ROOT}/yahboomcar_bringup/launch/yahboomcar_bringup_M1_launch.py',
    'imu_filter_param.yaml': f'{ROOT}/yahboomcar_bringup/param/imu_filter_param.yaml',
    'base_node_M1.cpp': f'{ROOT}/yahboomcar_base_node/src/base_node_M1.cpp',
    'Mcnamu_driver_M1.py': f'{ROOT}/yahboomcar_bringup/yahboomcar_bringup/Mcnamu_driver_M1.py',
}
KEYWORDS = re.compile(r'odom|imu|madgwick|ekf|kalman|robot_localization|tf|frame_id|base_link|base_footprint|world|map|velocity|quaternion|angular|linear|covariance|frequency|publish|subscribe', re.I)

def cmd(args, timeout=18):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, '', str(ex)

def main():
    print('[1/3] Identification d’un container Yahboom actif...')
    rc, out, err = cmd(['docker', 'ps', '--format', '{{.Names}}\t{{.Image}}'])
    if rc:
        raise SystemExit('Docker non accessible : ' + err)
    containers = [line.split('\t', 1) for line in out.splitlines() if '\t' in line and 'ros-humble-m1' in line.lower()]
    if not containers:
        raise SystemExit('Aucun container Yahboom actif. Aucun container ne sera démarré automatiquement.')
    name, img = containers[0]
    print('Container : ' + name)
    print('[2/3] Lecture passive des fichiers de localisation...')
    findings = []
    extracted = {}
    for label, path in TARGETS.items():
        rc, data, err = cmd(['docker', 'exec', name, 'cat', path])
        if rc:
            findings.append({'file': label, 'status': 'not_found', 'error': err})
            print('  ? ' + label + ' : indisponible')
            continue
        extracted[label] = data
        matches = [{'line': n, 'text': s.strip()[:260]} for n, s in enumerate(data.splitlines(), 1) if KEYWORDS.search(s)]
        findings.append({'file': label, 'status': 'found', 'line_count': len(data.splitlines()), 'matches': matches[:120]})
        print('  ✓ ' + label)
    # Search only filenames, not contents, for additional localization configuration.
    rc, out, err = cmd(['docker', 'exec', name, 'find', ROOT, '-maxdepth', '8', '-type', 'f', '-iname', '*ekf*'])
    ekf_files = out.splitlines()[:50] if rc == 0 else []
    # Inspect a small number of discovered EKF files statically.
    for i, path in enumerate(ekf_files[:4]):
        rc, data, err = cmd(['docker', 'exec', name, 'cat', path])
        if rc == 0 and len(data) < 60000:
            extracted[f'additional_ekf_{i+1}.txt'] = f'# Source path: {path}\n' + data
    print('[3/3] Création d’une archive ZIP...')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = Path.home() / f'R05_odometry_fusion_overview_{stamp}.zip'
    report = {'research': 'R05', 'mode': 'static_read_only', 'container': name, 'image': img,
              'files': findings, 'ekf_candidates': ekf_files,
              'limit': 'Static source inspection only; runtime topics, sensor values and actual fusion behavior not verified.'}
    summary = ['# R05 — Odometry & Sensor Fusion (inventaire statique)', '',
               f'- Container : `{name}`', '- Aucun Node lancé, aucun accès aux capteurs ni aux moteurs.',
               '- Résultats basés sur les fichiers présents, non sur des mesures en fonctionnement.', '',
               '## Fichiers', '']
    summary += [f"- `{x['file']}` : {x['status']}" for x in findings]
    summary += ['', '## Fichiers EKF potentiels', '']
    summary += [f'- `{x}`' for x in ekf_files] or ['- Aucun trouvé sous le workspace inspecté.']
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('R05_overview.json', json.dumps(report, indent=2, ensure_ascii=False))
        archive.writestr('R05_summary.md', '\n'.join(summary) + '\n')
        for label, data in extracted.items():
            archive.writestr('sources/' + label, data)
    print('✅ Archive créée : ' + str(path))
    print('À vérifier avant partage : archive contenant du code source Yahboom.')
    print('Aucune commande de mouvement, aucun Node lancé, aucune configuration modifiée.')

if __name__ == '__main__':
    main()
