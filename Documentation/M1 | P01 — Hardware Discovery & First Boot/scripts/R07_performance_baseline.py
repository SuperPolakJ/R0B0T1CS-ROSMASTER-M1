#!/usr/bin/env python3
"""R0B0T1CS LAB / P01 / R07 — Passive performance baseline.

No stress test, serial access, motor command, system modification or sudo.
Collects a brief point-in-time snapshot and writes a local ZIP report.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import time
import zipfile
from pathlib import Path


def command(args: list[str], timeout: int = 12) -> dict:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {"command": args, "returncode": p.returncode, "stdout": p.stdout[:12000].strip(), "stderr": p.stderr[:1200].strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": args, "error": str(exc)}


def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="replace").strip()
    except (OSError, UnicodeError):
        return None


def cpu_snapshot() -> tuple[int, int] | None:
    line = read_text("/proc/stat")
    if not line:
        return None
    first = line.splitlines()[0].split()
    if first[0] != "cpu":
        return None
    fields = [int(x) for x in first[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields), idle


def memory() -> dict:
    content = read_text("/proc/meminfo") or ""
    result = {}
    for line in content.splitlines():
        if ":" not in line:
            continue
        k, value = line.split(":", 1)
        if k in {"MemTotal", "MemAvailable", "MemFree", "SwapTotal", "SwapFree"}:
            try:
                result[k + "_KiB"] = int(value.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return result


def temperature() -> dict:
    results = {}
    base = Path("/sys/class/thermal")
    for zone in sorted(base.glob("thermal_zone*")):
        label = read_text(str(zone / "type")) or zone.name
        raw = read_text(str(zone / "temp"))
        if raw is None:
            continue
        try:
            results[label + " (" + zone.name + ")"] = round(int(raw) / 1000, 2)
        except ValueError:
            continue
    return results


def disks() -> dict:
    result = {}
    for path in ["/", "/home/pi"]:
        try:
            usage = shutil.disk_usage(path)
            result[path] = {"total_GiB": round(usage.total / 2**30, 2), "used_GiB": round(usage.used / 2**30, 2), "free_GiB": round(usage.free / 2**30, 2), "used_percent": round(100 * usage.used / usage.total, 1)}
        except OSError as exc:
            result[path] = {"error": str(exc)}
    return result


def main():
    print("[1/4] Mesure CPU (1 seconde), mémoire, stockage et température...")
    before = cpu_snapshot()
    time.sleep(1.0)
    after = cpu_snapshot()
    cpu_percent = None
    if before and after and after[0] > before[0]:
        cpu_percent = round(100 * (1 - (after[1] - before[1]) / (after[0] - before[0])), 1)

    try:
        load = list(os.getloadavg())
    except OSError:
        load = None
    data = {
        "project": "R0B0T1CS LAB P01 / R07",
        "measurement_type": "passive single snapshot; CPU sampled over 1 second",
        "timestamp_from_robot_clock": dt.datetime.now().astimezone().isoformat(),
        "clock_note": "The Raspberry Pi clock/timezone was previously observed to be incorrect; timestamp may be inaccurate.",
        "system": {"kernel": platform.release(), "architecture": platform.machine(), "cpu_logical_cores": os.cpu_count(), "uptime_seconds": None},
        "cpu_percent_1s": cpu_percent,
        "load_average_1_5_15min": load,
        "memory": memory(),
        "temperatures_C": temperature(),
        "disks": disks(),
    }
    uptime = read_text("/proc/uptime")
    if uptime:
        try:
            data["system"]["uptime_seconds"] = round(float(uptime.split()[0]))
        except (ValueError, IndexError):
            pass

    print("[2/4] État Docker (une seule lecture, sans démarrer de container)...")
    # docker stats --no-stream is read-only but may take a few seconds.
    data["docker_running"] = command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"], timeout=12)
    data["docker_resources"] = command(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"], timeout=18)

    print("[3/4] Préparation du résumé...")
    lines = [
        "# R07 — Performance & Resources: baseline", "",
        "> Mesure ponctuelle et passive, pas un benchmark. Horloge du robot à vérifier.", "",
        f"- CPU (sur 1 seconde) : **{cpu_percent if cpu_percent is not None else 'non disponible'} %**",
        f"- Cœurs logiques : **{os.cpu_count()}**",
        f"- Températures : **{data['temperatures_C']}**",
        "", "## Mémoire (KiB)", "",
    ]
    for k, v in data["memory"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Stockage", ""]
    for mount, info in data["disks"].items():
        lines.append(f"- `{mount}` : {info}")
    lines += ["", "## Docker (containers actifs)", "", "```text", data["docker_running"].get("stdout", "Non disponible"), "```", "", "## Docker (instantané CPU/RAM)", "", "```text", data["docker_resources"].get("stdout", "Non disponible"), "```", "", "Notes : données système brutes et diagnostic d'erreur éventuel dans R07_baseline.json."]

    print("[4/4] Création de l’archive ZIP...")
    out = Path.home() / ("R07_performance_baseline_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("R07_baseline.json", json.dumps(data, indent=2, ensure_ascii=False))
        z.writestr("R07_summary.md", "\n".join(lines) + "\n")
    print(f"✅ Archive créée : {out}")
    print("Aucun stress test, changement de configuration, Node ROS 2 ou mouvement moteur.")
    print("Vérifie le contenu de l'archive avant de la partager.")


if __name__ == "__main__":
    main()
