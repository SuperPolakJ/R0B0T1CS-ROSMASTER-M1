#!/usr/bin/env python3
"""R0B0T1CS LAB — P01 / R06: passive Linux / Docker startup inventory.

Read-only host queries. Never launches containers, nodes, or motors.
Does not collect environment variables, secrets, logs, network addresses,
service definitions, or file contents.
"""
import datetime
import json
import pathlib
import subprocess
import zipfile


def command(argv, timeout=12):
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
        return {"ok": result.returncode == 0, "output": result.stdout[:24000],
                "error": result.stderr[:500] if result.returncode else ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "output": "", "error": type(exc).__name__}


def main():
    print('[1/4] Identification Linux et horloge (lecture seule)...')
    system = {
        'os_release': command(['cat', '/etc/os-release']),
        'kernel': command(['uname', '-srmo']),
        'clock': command(['timedatectl', 'status']),
        'docker_version': command(['docker', '--version']),
    }
    print('[2/4] Containers Docker et configurations de démarrage...')
    ps = command(['docker', 'ps', '-a', '--format', '{{json .}}'])
    containers = []
    if ps['ok']:
        for line in ps['output'].splitlines():
            try:
                entry = json.loads(line)
                name = entry.get('Names', '')
                item = {'name': name, 'image': entry.get('Image', ''), 'state': entry.get('State', ''),
                        'status': entry.get('Status', '')}
                if name:
                    # Restrict inspect output to non-secret, structural fields.
                    fmt = '{{json .HostConfig.NetworkMode}}|{{json .HostConfig.RestartPolicy.Name}}|{{json .Mounts}}'
                    info = command(['docker', 'inspect', '--format', fmt, name])
                    if info['ok']:
                        parts = info['output'].strip().split('|', 2)
                        if len(parts) == 3:
                            try:
                                item['network_mode'] = json.loads(parts[0])
                                item['restart_policy'] = json.loads(parts[1])
                                mounts = json.loads(parts[2])
                                item['mounts'] = [{'type': m.get('Type'), 'destination': m.get('Destination')}
                                                  for m in mounts if isinstance(m, dict)]
                            except (ValueError, TypeError):
                                item['metadata_note'] = 'inspect format was not parseable'
                containers.append(item)
            except ValueError:
                pass
    print('[3/4] Services et tâches de démarrage (noms uniquement)...')
    services = {
        'enabled_services': command(['systemctl', 'list-unit-files', '--type=service', '--state=enabled', '--no-pager', '--no-legend']),
        'running_services': command(['systemctl', 'list-units', '--type=service', '--state=running', '--no-pager', '--no-legend']),
        'system_crontab_paths': [],
        'user_autostart_names': [],
    }
    for folder in ('/etc/cron.d', '/etc/systemd/system', '/home/pi/.config/autostart'):
        try:
            p = pathlib.Path(folder)
            files = sorted(x.name for x in p.iterdir() if x.is_file() or x.is_symlink())
            services['user_autostart_names' if 'autostart' in folder else 'system_crontab_paths'].append({'directory': folder, 'names': files[:100]})
        except (OSError, PermissionError):
            continue
    print('[4/4] Génération du rapport et de l’archive...')
    report = {
        'project': 'R0B0T1CS LAB / P01 / R06', 'method': 'passive_inventory',
        'scope': 'Linux + Docker containers + service names; no service contents or secrets',
        'system': system, 'containers': containers, 'docker_ps_error': ps['error'], 'services': services,
        'limitations': ['Service names do not prove a specific ROS node is launched.',
                        'Mount destinations are reported; host source paths excluded.',
                        'No scripts or containers are executed.',
                        'No credentials, environment variables, raw container inspect, or service content collected.'],
    }
    summary = ['# R06 — Linux, Docker et démarrage', '',
               '**Inventaire passif : aucune modification, aucun Node ni moteur activé.**', '',
               f'- Containers listés : {len(containers)}',
               f'- Containers en cours d’exécution : {sum(c["state"] == "running" for c in containers)}',
               '- Métadonnées : images, état, mode réseau, politique de redémarrage, destinations des volumes.',
               '- Services : noms des unités activées et exécutées.',
               '- Limites : inventaire déclaratif, pas une preuve de fonctionnement ROS 2.', '']
    for c in containers:
        summary.append(f'- `{c["name"]}` : `{c["image"]}` — {c["status"]} — réseau={c.get("network_mode", "inconnu")}, restart={c.get("restart_policy", "inconnu")}')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = pathlib.Path.home() / f'R06_linux_docker_startup_{stamp}.zip'
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('R06_report.json', json.dumps(report, ensure_ascii=False, indent=2))
        z.writestr('R06_summary.md', '\n'.join(summary) + '\n')
        z.writestr('README.txt', 'Inspecter les données avant partage. Des noms locaux de services et containers peuvent être présents.\n')
    print(f'✅ Archive créée : {dest}')
    print('Inspecte l’archive avant partage. Aucune configuration modifiée.')


if __name__ == '__main__':
    main()
