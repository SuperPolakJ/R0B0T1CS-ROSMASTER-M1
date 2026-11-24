#!/usr/bin/env python3
"""R0B0T1CS LAB / P01 — diagnostic statique complémentaire v1.1.

Exécuter sur l'hôte Raspberry Pi, avec Docker installé.
Pas d'ouverture des ports série, pas de commandes ROS, pas de démarrage de nodes,
pas de modification de la configuration. Écrit UNIQUEMENT une archive ZIP dans ~.
Lire l'archive avant de la partager : les extraits de code et les identifiants de
périphériques peuvent contenir des informations propres au robot.
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys
import zipfile

VERSION = "1.1.0"
WORKSPACE = "/root/yahboomcar_ros2_ws/yahboomcar_ws/src"

# Script Python exécuté dans le container via `docker exec ... python3 -c ...`.
# Lecture statique uniquement. Les sources Yahboom ne sont jamais exécutées.
SCANNER = r"""
import json, os, re
base = "/root/yahboomcar_ros2_ws/yahboomcar_ws/src"
selected = [
 "yahboomcar_base_node", "yahboomcar_bringup", "yahboomcar_ctrl",
 "yahboomcar_laser", "yahboomcar_astra", "yahboomcar_depth",
 "yahboomcar_description", "yahboomcar_nav", "yahboomcar_vision",
 "yahboomcar_msgs", "yahboomcar_interfaces", "yahboomcar_voice_ctrl",
 "robot_pose_publisher_ros2", "laserscan_to_point_publisher",
 "yahboomcar_multi", "largemodel", "multi_brains"
]
kw = re.compile(r'''(?ix)
   /dev/(?:tty|serial|video)|ttyUSB|ttyAMA|serial\.Serial|baud(?:rate|_rate)?
 | create_(?:publisher|subscription|service|client|timer)\s*\(
 | Action(?:Server|Client)\s*\(|Node\s*\(|executable\s*=|package\s*=
 | IncludeLaunchDescription|/cmd_vel|/odom|/imu|/scan|frame_id|Twist\b
 | Rosmaster|CP210|CH340|robot_localization|ekf|uart|i2c|spi
''')
private = re.compile(r'(?i)(password|passwd|secret|token|credential|authorization|api[_-]?key|private[_-]?key|wifi|wpa_|ssid|BEGIN [A-Z ]*PRIVATE KEY)')
result = {"workspace": base, "packages": {}}
for pkg in selected:
    folder=os.path.join(base,pkg)
    if not os.path.isdir(folder):
        result['packages'][pkg]={"present":False}; continue
    entry={"present":True,"manifests":[],"launch_files":[],"matches":[],"files_scanned":0,"truncated":False}
    for root,dirs,names in os.walk(folder):
        depth=os.path.relpath(root,folder).count(os.sep)
        dirs[:]=sorted(x for x in dirs if not x.startswith('.') and x not in ('build','install','log','__pycache__','node_modules','venv','env') and depth<5)
        for name in sorted(names):
            if not name.endswith(('.py','.cpp','.cc','.h','.hpp','.xml','.yaml','.yml','.sh')): continue
            fn=os.path.join(root,name)
            try:
                if os.path.islink(fn) or os.path.getsize(fn)>180000: continue
            except OSError: continue
            rel=os.path.relpath(fn,base)
            entry['files_scanned']+=1
            if name.endswith(('.launch.py','_launch.py','.launch.xml','.launch.yaml')): entry['launch_files'].append(rel)
            if name == 'package.xml':
                try:
                    import xml.etree.ElementTree as ET
                    node=ET.parse(fn).getroot()
                    entry['manifests'].append({'path':rel, 'name':node.findtext('name'), 'version':node.findtext('version'),
                        'dependencies':sorted({(n.text or '').strip() for n in node if n.tag in ('depend','exec_depend','build_depend','buildtool_depend') and n.text})})
                except Exception: pass
            if name == 'setup.py':
                try:
                    with open(fn,encoding='utf8',errors='replace') as f:
                        for no,line in enumerate(f,1):
                            if ('console_scripts' in line or re.search(r'\b\w+\s*=\s*\w+[.\w]*:main',line)) and not private.search(line):
                                entry['matches'].append({'file':rel,'line':no,'type':'entrypoint','snippet':line.strip()[:220]})
                except OSError: pass
            if len(entry['matches']) >= 150:
                entry['truncated']=True; continue
            try:
                with open(fn,encoding='utf-8',errors='replace') as f: lines=f.readlines()
            except OSError: continue
            for i,line in enumerate(lines):
                if len(entry['matches']) >= 150:
                    entry['truncated']=True; break
                if not kw.search(line) or private.search(line): continue
                # Inclure 4 lignes suivantes pour révéler les arguments de Node(),
                # create_subscription(), etc. Écarter les lignes sensibles.
                snippet=' '.join(z.strip() for z in lines[i:min(i+5,len(lines))] if not private.search(z))[:420]
                entry['matches'].append({'file':rel,'line':i+1,'type':'source','snippet':snippet})
    result['packages'][pkg]=entry
print(json.dumps(result, ensure_ascii=False))
"""


def run(args, timeout=120):
    try:
        p = subprocess.run(args, text=True, capture_output=True, errors='replace', timeout=timeout, check=False)
        return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr[:800]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    if sys.platform != 'linux':
        sys.exit('Ce script doit être exécuté sur le Raspberry Pi (Linux).')
    containers=run(['docker','ps','--format','{{.ID}}\t{{.Image}}\t{{.Names}}'])
    if containers.get('returncode') != 0:
        sys.exit('Impossible de lire les containers Docker actifs. Aucune modification effectuée.')
    candidates=[line.split('\t') for line in containers['stdout'].splitlines() if 'ros-humble-m1' in line]
    if not candidates:
        sys.exit('Aucun container Yahboom ros-humble-m1 actif. Aucun démarrage automatique effectué.')
    cid,image,cname=candidates[0]
    print(f'[1/3] Container sélectionné : {cname} ({image})')
    print('[2/3] Inspection passive des fichiers sources ciblés...')
    response=run(['docker','exec',cid,'python3','-c',SCANNER],timeout=120)
    if response.get('returncode') != 0:
        sys.exit('Inspection interrompue : '+response.get('stderr',response.get('error','erreur inconnue')))
    try:
        details=json.loads(response['stdout'])
    except ValueError:
        sys.exit('Réponse JSON inattendue, aucune archive créée. Aucune configuration modifiée.')
    host={
        'date_local':run(['date','--iso-8601=seconds']),
        'timezone_sync':run(['timedatectl','show','-p','Timezone','-p','NTPSynchronized','-p','NTP'],timeout=10),
        'video_devices':run(['bash','-lc','ls -l /dev/video* 2>/dev/null || true']),
    }
    package_count=sum(1 for p in details['packages'].values() if p['present'])
    match_count=sum(len(p.get('matches',[])) for p in details['packages'].values())
    data={
        'tool':'R0B0T1CS LAB P01 targeted passive static discovery',
        'version':VERSION,'generated_local':datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'safety':'Static read-only inspection. No serial, motors, ROS launch, or Docker lifecycle actions.',
        'container':{'name':cname,'image':image},'host':host,'code':details,
    }
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    archive=pathlib.Path.home()/('rosmaster_p01_targeted_discovery_'+stamp+'.zip')
    print('[3/3] Création de l’archive...')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('targeted_report.json',json.dumps(data,ensure_ascii=False,indent=2))
        summary=[
          '# R0B0T1CS LAB — P01 Targeted Discovery v1.1',
          '',f'Container : {cname}',f'Packages inspectés : {package_count}',
          f'Extraits statiques : {match_count}',
          '', '## Dossiers inspectés et nombre de correspondances',
        ]
        for pkg,val in details['packages'].items():
            summary.append(f'- {pkg}: '+('absent' if not val['present'] else f"{len(val['matches'])} extraits; limite atteinte={val['truncated']}"))
        summary += ['', '**Vérifier cette archive avant tout partage.**',
                   'Aucun mot de passe ni clé privée ne sont collectés intentionnellement.']
        z.writestr('summary.md','\n'.join(summary)+'\n')
    print(f'✅ Archive créée : {archive}')
    print(f'Packages ciblés : {package_count} ; extraits : {match_count}')
    print('Aucun port série ouvert, aucun Node démarré, aucune commande moteur envoyée.')

if __name__=='__main__':
    main()
