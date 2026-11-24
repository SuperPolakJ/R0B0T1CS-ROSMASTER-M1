#!/usr/bin/env python3
"""R0B0T1CS LAB R01 - passive M1 driver source inspection.

Only executes docker ps, test -f, and cat inside existing containers.
Does not start containers, nodes, serial ports, or motor commands.
"""
import datetime
import io
import json
import pathlib
import subprocess
import zipfile

SOURCES = {
    'Mcnamu_driver_M1.py': '/root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_bringup/yahboomcar_bringup/Mcnamu_driver_M1.py',
    'base_node_M1.cpp': '/root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_base_node/src/base_node_M1.cpp',
}

def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)

def main():
    ps = run('docker', 'ps', '--format', '{{.Names}}')
    if ps.returncode:
        raise SystemExit('Docker inaccessible : ' + ps.stderr.strip())
    candidate = None
    for name in ps.stdout.splitlines():
        p = run('docker', 'exec', name, 'test', '-f', SOURCES['Mcnamu_driver_M1.py'])
        if p.returncode == 0:
            candidate = name
            break
    if not candidate:
        raise SystemExit('Aucun container actif avec le driver M1. Aucune action effectuée.')
    output = pathlib.Path.home() / ('R01_M1_driver_sources_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.zip')
    meta = {'container': candidate, 'files': [], 'mode': 'read-only'}
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for basename, source in SOURCES.items():
            result = run('docker', 'exec', candidate, 'cat', source)
            if result.returncode != 0:
                print('ERREUR :', basename, result.stderr.strip())
                continue
            archive.writestr(basename, result.stdout)
            meta['files'].append({'file': basename, 'source': source, 'bytes': len(result.stdout.encode())})
        archive.writestr('manifest.json', json.dumps(meta, indent=2))
    print('Container inspecté :', candidate)
    print('Fichiers collectés :', ', '.join(f['file'] for f in meta['files']))
    print('Archive créée :', output)
    print('Inspecter le contenu de l’archive avant de la partager.')

if __name__ == '__main__':
    main()
