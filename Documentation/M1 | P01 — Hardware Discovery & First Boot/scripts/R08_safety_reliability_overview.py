#!/usr/bin/env python3
"""R0B0T1CS LAB - P01/R08: passive safety & reliability inventory.

Reads selected source code and Linux metadata only. Does not launch nodes,
open serial devices, test motors, or change any configuration.
Run as ordinary user pi, without sudo.
"""
import datetime as datetime
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = '/root/yahboomcar_ros2_ws/yahboomcar_ws/src'
TARGETS = {
    'motor_driver': f'{ROOT}/yahboomcar_bringup/yahboomcar_bringup/Mcnamu_driver_M1.py',
    'base_node': f'{ROOT}/yahboomcar_base_node/src/base_node_M1.cpp',
    'joystick': f'{ROOT}/yahboomcar_ctrl/yahboomcar_ctrl/yahboom_joy_M1.py',
    'bringup': f'{ROOT}/yahboomcar_bringup/launch/yahboomcar_bringup_M1_launch.py',
}
KEYWORDS = re.compile(r'\b(stop|emergency|estop|e_stop|watchdog|timeout|deadman|buzzer|battery|voltage|exception|shutdown|signal|set_car_motion|cmd_vel|joy|timer|serial|error|fail|safety|reset|disconnect)\b', re.I)
SECRET = re.compile(r'(password|passwd|private.key|secret|api.key|token|credential|ssid|authorization)', re.I)

def cmd(args, timeout=12):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr[:600]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'exit_code': None, 'stdout': '', 'stderr': str(exc)}

def main():
    print('[1/4] Identification passive du container Yahboom...')
    listed = cmd(['docker','ps','--format','{{.Names}}\t{{.Image}}'])
    if listed['exit_code'] != 0:
        raise SystemExit('Impossible de lire Docker: ' + listed['stderr'])
    containers = [line.split('\t', 1) for line in listed['stdout'].splitlines() if '\t' in line]
    matches = [(name, image) for name, image in containers if 'ros-humble-m1' in image.lower()]
    if not matches:
        raise SystemExit('Aucun container Yahboom en cours; aucun container ne sera demarre.')
    name, image = matches[0]
    print(f'  Container: {name}')

    print('[2/4] Lecture des references de securite dans les sources...')
    source_data = {}
    for label, path in TARGETS.items():
        got = cmd(['docker','exec',name,'cat',path])
        if got['exit_code'] != 0:
            source_data[label] = {'path':path,'status':'not_found','error':got['stderr']}
            continue
        matches_lines=[]
        for line_no, line in enumerate(got['stdout'].splitlines(), 1):
            if KEYWORDS.search(line) and not SECRET.search(line):
                matches_lines.append({'line':line_no, 'snippet':line.strip()[:220]})
        source_data[label] = {
            'path':path,'status':'read', 'total_lines':len(got['stdout'].splitlines()),
            'keyword_matches':matches_lines[:80], 'matches_truncated':len(matches_lines)>80
        }

    print('[3/4] Lecture des etats systeme non sensibles...')
    services={}
    for service in ['docker.service','ssh.service','NetworkManager.service','yahboom_oled.service']:
        p=cmd(['systemctl','is-active',service], timeout=5)
        services[service]=p['stdout'].strip() if p['exit_code']==0 else 'not-active-or-unavailable'
    kernel=cmd(['uname','-r'])['stdout'].strip()
    # No unit files, system logs, personal environment, user identities, or secrets gathered.
    report={
        'project':'R0B0T1CS LAB / P01 / R08',
        'method':'static_read_only',
        'timestamp_from_robot_clock':datetime.datetime.now().astimezone().isoformat(),
        'kernel':kernel,
        'container':{'name':name,'image':image},
        'service_states':services,
        'source_evidence':source_data,
        'limitations':[
            'Keyword matches are clues, not proof of functional safety mechanisms.',
            'No motor commands, watchdog tests or battery protection tests performed.',
            'Firmware STM32 and electrical protections were not inspected.',
            'Robot clock may be incorrect.'
        ]
    }
    summary=['# R08 - Inventaire passif de securite / fiabilite','',
             'Cette analyse ne valide PAS la securite fonctionnelle du robot.','',
             f'- Container: `{name}`',f'- Image: `{image}`',
             f'- Kernel: `{kernel}`','','## Services (etats)','']
    for key,val in services.items(): summary.append(f'- `{key}`: {val}')
    summary.extend(['','## Indices dans les sources',''])
    for key, entry in source_data.items():
        summary.append(f'### {key}')
        summary.append(f"- Etat: {entry['status']}")
        if entry['status']=='read':
            summary.append(f"- Lignes: {entry['total_lines']}; correspondances retenues: {len(entry['keyword_matches'])}")
            for x in entry['keyword_matches'][:25]:
                summary.append(f"  - L{x['line']}: `{x['snippet'].replace('`','')}`")
        summary.append('')
    summary.extend(['## Limites','', '- Aucun test actif effectue.',
                    '- Fonctions de securite a confirmer par inspection et essais dedies, autorises et encadres.',
                    '- Verifier manuellement le contenu de l archive avant partage.'])

    print('[4/4] Creation archive ZIP...')
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out=Path.home()/f'R08_safety_reliability_{stamp}.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('R08_overview.json', json.dumps(report,indent=2,ensure_ascii=False))
        z.writestr('R08_summary.md','\n'.join(summary)+'\n')
    print(f'✅ Archive creee : {out}')
    print('Aucune commande moteur ni modification de configuration. Verifier avant de partager.')

if __name__=='__main__':
    main()
