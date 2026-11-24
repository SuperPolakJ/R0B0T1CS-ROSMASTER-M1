#!/usr/bin/env python3
"""R0B0T1CS LAB P01 / R02 — passive ROS 2 source overview.
Runs on Raspberry Pi host. Reads selected source files inside an existing
running Yahboom Docker container. Does not launch ROS nodes or open devices.
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys
import zipfile

BASE = '/root/yahboomcar_ros2_ws/yahboomcar_ws/src'
PACKAGES = ['yahboomcar_bringup', 'yahboomcar_base_node', 'yahboomcar_ctrl',
            'yahboomcar_laser', 'yahboomcar_nav', 'yahboomcar_description',
            'yahboomcar_astra', 'yahboomcar_depth']
INSPECTOR = r'''
import ast, json, pathlib, re
base = pathlib.Path("/root/yahboomcar_ros2_ws/yahboomcar_ws/src")
packages = ['yahboomcar_bringup','yahboomcar_base_node','yahboomcar_ctrl','yahboomcar_laser','yahboomcar_nav','yahboomcar_description','yahboomcar_astra','yahboomcar_depth']
pat = re.compile(r'(?<![\w])(/[A-Za-z][A-Za-z0-9_/-]{1,90})')
result = {'packages':{}, 'main_launch':None}
for pkg in packages:
    folder = base / pkg
    info={'exists':folder.is_dir(),'launch_files':[],'topic_name_candidates':[]}
    if folder.is_dir():
        files = sorted(p for p in folder.rglob('*') if p.is_file() and len(p.relative_to(folder).parts)<=5)
        launch = [p for p in files if p.name.endswith(('_launch.py','.launch.py','.launch.xml','.launch.yaml'))]
        info['launch_files']=[str(p.relative_to(folder)) for p in launch[:45]]
        # Only extract topic-like literals from selected Python/C++ source, not arbitrary configs/secrets.
        names=set()
        count=0
        for path in files:
            if path.suffix not in ('.py','.cpp','.hpp','.h','.cc') or path.stat().st_size > 250000:
                continue
            if any(x in path.parts for x in ('build','install','log','.git')):
                continue
            count += 1
            if count > 100: break
            try: contents = path.read_text(encoding='utf-8', errors='replace')
            except OSError: continue
            for m in pat.finditer(contents):
                item=m.group(1)
                # Skip paths and filesystem-related strings; these are candidates, not verified topics.
                if item.startswith(('/dev/','/root/','/home/','/opt/','/usr/','/tmp/','/etc/','/var/','/camera_info/')):continue
                if not any(c.isalpha() for c in item):continue
                if len(item) < 3:continue
                names.add(item)
        info['topic_name_candidates']=sorted(names)[:100]
    result['packages'][pkg]=info
main=base/'yahboomcar_bringup/launch/yahboomcar_bringup_M1_launch.py'
if main.is_file():
    code=main.read_text(encoding='utf-8',errors='replace')
    tree=ast.parse(code)
    node_declarations=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Node':
            kw={k.arg: (k.value.value if isinstance(k.value,ast.Constant) and isinstance(k.value.value,(str,int,float,bool)) else '<dynamic>') for k in n.keywords if k.arg in ('package','executable','name')}
            node_declarations.append(kw)
    result['main_launch']={'path':str(main.relative_to(base)),'declared_nodes':node_declarations,'includes_ekf':('ekf_M1_launch.py' in code),'robot_model_urdf':('yahboomcar_M1.urdf.xacro' in code),'notes':'Static declarations; not proof any node is running.'}
print(json.dumps(result,ensure_ascii=False))
'''

def run(args, *, inp=None):
    return subprocess.run(args, input=inp, text=True, capture_output=True, timeout=75, check=False)

def main():
    res=run(['docker','ps','--format','{{.Names}}|{{.Image}}'])
    if res.returncode:
        sys.exit('Erreur : impossible de lire les containers Docker : '+res.stderr.strip())
    rows=[line.split('|',1) for line in res.stdout.splitlines() if '|' in line]
    matching=[r for r in rows if 'ros-humble-m1' in r[1]]
    if not matching:
        sys.exit('Aucun container Yahboom ROS Humble actif. Aucun container ne sera démarré.')
    chosen=None
    for name, img in matching:
        chk=run(['docker','exec',name,'test','-d',BASE])
        if chk.returncode==0:
            chosen=(name,img)
            break
    if not chosen:
        sys.exit('Aucun container actif ne contient le workspace Yahboom attendu.')
    print('Container sélectionné :',chosen[0])
    print('Lecture statique des fichiers ROS 2 (aucun Node lancé)...')
    proc=run(['docker','exec','-i',chosen[0],'python3','-'], inp=INSPECTOR)
    if proc.returncode:
        sys.exit('Analyse impossible : '+proc.stderr.strip()[:600])
    data=json.loads(proc.stdout)
    data['diagnostic']={'name':'R02 ROS2 overview','mode':'static_read_only','container':chosen[0], 'image':chosen[1], 'collected_at_host':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    outfile=pathlib.Path.home()/f'R02_ros2_overview_{stamp}.zip'
    lines=['# R02 — Inventaire ROS 2 (analyse statique)', '',
           '> Les éléments listés proviennent des fichiers source : ils ne prouvent pas que les Nodes sont actifs.', '',
           '## Launch M1 principal']
    main_launch=data['main_launch']
    if main_launch:
        for item in main_launch['declared_nodes']:
            lines.append(f"- `{item.get('package','?')}` → `{item.get('executable','?')}`")
    else:
        lines.append('- Fichier principal introuvable.')
    lines+=['','## Packages ciblés / Topics candidats (à valider)']
    for pkg, info in data['packages'].items():
        lines.append(f"### {pkg}")
        lines.append(f"- Dossier présent : {'oui' if info['exists'] else 'non'}")
        lines.append(f"- Fichiers Launch repérés : {len(info['launch_files'])}")
        lines.append('- Chaînes ressemblant à des Topics : '+(', '.join('`'+x+'`' for x in info['topic_name_candidates'][:25]) or 'aucune'))
    lines += ['', '## Sécurité', '- Aucune commande envoyée aux moteurs.', '- Aucun Node ROS 2 démarré.', '- Aucun port série ouvert.', '- Aucun fichier source complet exporté.', '']
    with zipfile.ZipFile(outfile,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('R02_overview.json',json.dumps(data,ensure_ascii=False,indent=2))
        z.writestr('R02_summary.md','\n'.join(lines))
    print(f'Archive créée : {outfile}')
    print('Lecture seule : aucun Node lancé, aucun port série ouvert.')
    print('Vérifie le contenu du ZIP avant de le partager.')

if __name__=='__main__': main()
