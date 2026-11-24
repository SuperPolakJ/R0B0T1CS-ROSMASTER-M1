#!/usr/bin/env python3
"""R0B0T1CS LAB P01 — passive ROSMASTER M1 discovery (stdlib only).
Runs on the Raspberry Pi host, reads selected system metadata and selected
Yahboom source files inside an already-running Docker container.
Never starts containers, services, ROS nodes or communicates with serial ports.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

VERSION = "1.0.0"
WORKSPACE = "/root/yahboomcar_ros2_ws/yahboomcar_ws/src"
MAX_OUTPUT = 24000
TIMEOUT = 12
SENSITIVE = re.compile(r"(?i)(password|passwd|secret|token|private.key|api.key|authorization|credential|wifi.psk|ssid|wpa_|BEGIN [A-Z ]*PRIVATE KEY)")

def run(argv, timeout=TIMEOUT):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
        return {"returncode": p.returncode, "stdout": p.stdout[:MAX_OUTPUT], "stderr": p.stderr[:1500]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

def safe_lines(lines, cap=300):
    output = []
    for line in lines:
        if SENSITIVE.search(line):
            continue
        output.append(line[:340])
        if len(output) >= cap:
            break
    return output

def container_scan_code():
    # Execute only a Python read-only static scanner, not Yahboom source files.
    scanner = r'''
import json, os, re
base = "/root/yahboomcar_ros2_ws/yahboomcar_ws/src"
keywords = re.compile(r"(?i)(/dev/tty|/dev/serial|serial\.Serial|ros2\.node|create_publisher|create_subscription|create_service|create_client|create_timer|declare_parameter|Node\(|executable=|package=|IncludeLaunchDescription|cmd_vel|/odom|/imu|/scan|baudrate|baud_rate|Serial\(|get_logger\(\))")
secret = re.compile(r"(?i)(password|passwd|secret|token|api.key|authorization|credential|wifi.psk|ssid|wpa_|BEGIN [A-Z ]*PRIVATE KEY)")
files=[]; matches=[]; packages=[]
if os.path.isdir(base):
 for dirname in sorted(os.listdir(base)):
  path=os.path.join(base, dirname)
  if os.path.isdir(path) and os.path.exists(os.path.join(path,'package.xml')): packages.append(dirname)
 for root, dirs, names in os.walk(base):
  rel=os.path.relpath(root,base)
  depth=rel.count(os.sep)+ (rel!='.')
  dirs[:]=sorted([x for x in dirs if not x.startswith('.') and x not in ('build','install','log','__pycache__','node_modules')]) if depth < 5 else []
  for name in sorted(names):
   if not name.endswith(('.py','.cpp','.hpp','.h','.cc','.c','.xml')): continue
   path=os.path.join(root,name)
   try:
    if os.path.getsize(path)>150000: continue
   except OSError: continue
   short=os.path.relpath(path,base)
   if name.endswith(('.launch.py','_launch.py')): files.append(short)
   if len(matches)>=360: continue
   try:
    with open(path,encoding='utf-8',errors='replace') as f:
     for i,line in enumerate(f,1):
      if len(matches)>=360: break
      if keywords.search(line) and not secret.search(line):
       matches.append({'file':short,'line':i,'text':line.strip()[:220]})
   except (OSError,UnicodeError): pass
print(json.dumps({'packages':packages,'launch_files':files[:120],'static_references':matches},ensure_ascii=False))
'''
    return run(["docker", "exec", "great_dubinsky", "python3", "-c", scanner], timeout=35)

def main():
    if sys.platform != 'linux':
        print('Ce script doit être lancé sur le Raspberry Pi (Linux).',file=sys.stderr)
        sys.exit(2)
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    home = Path.home()
    output = home / f"rosmaster_p01_discovery_{stamp}.zip"
    report = {
        'tool': 'R0B0T1CS LAB P01 passive discovery',
        'version': VERSION,
        'time_local': dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        'safety': 'Read-only. No serial ports opened. No ROS node launched. No service/container changes.',
        'host': {}, 'docker': {}
    }
    print('[1/4] Informations système et périphériques...')
    host_commands = {
        'os_release': ['cat','/etc/os-release'],
        'kernel': ['uname','-a'],
        'model': ['cat','/proc/device-tree/model'],
        'interfaces': ['ip','-brief','link'],
        'usb_tree': ['lsusb','-t'],
        'usb_devices': ['lsusb'],
        'serial_links': ['ls','-l','/dev/serial/by-id','/dev/serial/by-path'],
        'ttyusb0_udev': ['udevadm','info','--query=property','--name=/dev/ttyUSB0'],
        'ttyusb1_udev': ['udevadm','info','--query=property','--name=/dev/ttyUSB1'],
        'docker_version': ['docker','--version'],
    }
    for label, command in host_commands.items():
        result=run(command)
        if label.endswith('_udev') and 'stdout' in result:
            keep=('ID_VENDOR=', 'ID_MODEL=', 'ID_SERIAL=', 'ID_VENDOR_ID=', 'ID_MODEL_ID=', 'ID_PATH=', 'DEVNAME=')
            result['stdout']='\n'.join(x for x in result['stdout'].splitlines() if x.startswith(keep))
        report['host'][label]=result
    print('[2/4] Docker (inventaire sans lancement)...')
    report['docker']['containers']=run(['docker','ps','-a','--format','{{.Names}} | {{.Image}} | {{.Status}}'])
    report['docker']['active_container']=run(['docker','inspect','--format','{{.Name}} | {{.State.Status}} | network={{.HostConfig.NetworkMode}}','great_dubinsky'])
    print('[3/4] ROS 2 et packages Yahboom...')
    report['docker']['ros_distro']=run(['docker','exec','great_dubinsky','bash','-lc','source /opt/ros/humble/setup.bash && printf "ROS_DISTRO=%s\\n" "$ROS_DISTRO"'])
    report['docker']['ros_packages']=run(['docker','exec','great_dubinsky','bash','-lc','source /opt/ros/humble/setup.bash && ros2 pkg list | grep -E "^(yahboom|robot_localization|imu_filter|joy$|robot_state_publisher)"'])
    report['docker']['code_inventory']=container_scan_code()
    print('[4/4] Création de l’archive...')
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('discovery_report.json',json.dumps(report,ensure_ascii=False,indent=2))
        lines=['# R0B0T1CS LAB — P01 Passive Discovery', '',f'Date : {report["time_local"]}', '',
               '## Safety','Read-only; no ROS launch, no serial transmission, no motor commands.','',
               '## Command results (selected)', '']
        for section in ('host','docker'):
            for key, value in report[section].items():
                lines.append(f'### {section}/{key}')
                if key == 'code_inventory' and value.get('stdout'):
                    try:
                        obj=json.loads(value['stdout'])
                        lines.append('Packages: '+', '.join(obj.get('packages',[])))
                        lines.append('Launch files: '+', '.join(obj.get('launch_files',[])))
                        lines.append(f"Static code matches: {len(obj.get('static_references', []))}")
                    except (ValueError,TypeError): lines.append('Code inventory unreadable; see JSON report.')
                else:
                    lines.extend(safe_lines(value.get('stdout','').splitlines(),cap=50))
                if value.get('error'): lines.append('Error: '+value['error'])
                elif value.get('returncode',0)!=0: lines.append('Return code: '+str(value['returncode']))
                lines.append('')
        z.writestr('summary.md','\n'.join(lines))
        z.writestr('README.txt', 'Diagnostic passif P01. Transmettre uniquement après vérification du contenu.\nLes données comprennent des noms de périphériques et des extraits de code source.\nAucune information de connexion Wi-Fi, clé privée ou variable d’environnement n’est collectée intentionnellement.\n')
    print(f'\n✅ Archive créée : {output}')
    print('Inspecte le contenu avant de partager le fichier. Aucune configuration n’a été modifiée.')

if __name__=='__main__': main()
