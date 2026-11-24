#!/usr/bin/env python3
"""R0B0T1CS LAB — P01 / R04: inventaire statique de la motorisation.

Lecture seule : n'active aucun node, ne communique avec aucun port série
et n'envoie aucune commande aux moteurs. Ne nécessite pas sudo.
"""
import datetime as dt
import json
import re
import subprocess
import zipfile
from pathlib import Path

WORKSPACE = "/root/yahboomcar_ros2_ws/yahboomcar_ws/src"
FILES = {
    "Mcnamu_driver_M1.py": f"{WORKSPACE}/yahboomcar_bringup/yahboomcar_bringup/Mcnamu_driver_M1.py",
    "base_node_M1.cpp": f"{WORKSPACE}/yahboomcar_base_node/src/base_node_M1.cpp",
    "yahboomcar_bringup_M1_launch.py": f"{WORKSPACE}/yahboomcar_bringup/launch/yahboomcar_bringup_M1_launch.py",
}
OUT_DIR = Path.home()
PATTERN = re.compile(
    r"cmd_vel|vel_raw|odom_raw|joint_states|set_car_motion|"
    r"get_motion_data|get_motor|encoder|motor|wheel|mecan|"
    r"create_subscription|create_publisher|create_timer|"
    r"linear\.[xy]|angular\.z|base_node_M1|Mcnamu_driver_M1",
    re.IGNORECASE,
)

def run(args, timeout=15):
    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
        return completed.returncode, completed.stdout, completed.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)

def main():
    print("[1/3] Recherche d'un container Yahboom en cours d'exécution...")
    rc, out, err = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"])
    if rc:
        raise SystemExit(f"Impossible d'interroger Docker : {err}")
    candidates = [
        (name, img) for line in out.splitlines()
        if "\t" in line
        for name, img in [line.split("\t", 1)]
        if "ros-humble-m1" in img.lower()
    ]
    if not candidates:
        raise SystemExit("Aucun container Yahboom actif trouvé. Rien n'a été démarré.")
    name, image = candidates[0]
    print(f"Container : {name} ({image})")
    print("[2/3] Lecture passive des 3 fichiers ciblés...")
    sources = {}
    results = []
    for label, path in FILES.items():
        rc, content, err = run(["docker", "exec", name, "cat", path])
        if rc:
            results.append({"file": label, "path": path, "status": "unavailable", "error": err})
            print(f"  ! {label} : indisponible")
            continue
        sources[label] = content
        matches = [
            {"line": i, "text": line.strip()[:240]}
            for i, line in enumerate(content.splitlines(), 1)
            if PATTERN.search(line)
        ][:100]
        results.append({
            "file": label, "path": path, "status": "ok",
            "lines": len(content.splitlines()), "interesting_lines": matches
        })
        print(f"  ✓ {label} : {len(content.splitlines())} lignes")
    if not sources:
        raise SystemExit("Aucun fichier récupéré, aucune archive créée.")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = OUT_DIR / f"R04_motor_overview_{stamp}.zip"
    report = {
        "project": "P01 / R04 - Motor System Overview",
        "inspection": "static_read_only",
        "container": name, "docker_image": image,
        "sources": results,
        "caveat": "Déclarations du code uniquement ; aucun essai moteur ni validation runtime."
    }
    lines = [
        "# R04 — Inventaire moteur (statique)",
        "", f"- Container examiné : `{name}`",
        "- Méthode : lecture seule des fichiers ROS 2 Yahboom.",
        "- Aucun Node lancé, aucune commande moteur envoyée.",
        "- Les correspondances montrent le code déclaré, pas les mesures en fonctionnement.",
        "", "## Fichiers inspectés", ""
    ]
    for item in results:
        lines.append(f"- `{item['file']}` : {item['status']}")
    lines += ["", "## Indices utiles", ""]
    for item in results:
        if item["status"] != "ok":
            continue
        lines.append(f"### {item['file']}")
        for match in item["interesting_lines"][:20]:
            lines.append(f"- L{match['line']}: `{match['text'].replace('`', '')}`")
        lines.append("")
    print("[3/3] Création de l'archive...")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("R04_overview.json", json.dumps(report, ensure_ascii=False, indent=2))
        z.writestr("R04_summary.md", "\n".join(lines))
        for label, content in sources.items():
            z.writestr(f"sources/{label}", content)
    print(f"✅ Archive créée : {archive}")
    print("Vérifier l'archive avant partage : elle contient des extraits du code Yahboom.")
    print("Aucun moteur activé, aucun Node lancé, aucun port série ouvert.")

if __name__ == "__main__":
    main()
