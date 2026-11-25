#!/usr/bin/env python3
"""Démonstration omnidirectionnelle sur banc avec les quatre roues suspendues."""

import argparse
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Thread

import rclpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controllers"))

from m1_motion_controller import M1MotionController


MOVEMENTS = (
    ("M01", "Forward", 0.05, 0.0, 0.0),
    ("M02", "Backward", -0.05, 0.0, 0.0),
    ("M03", "Strafe Left", 0.0, 0.05, 0.0),
    ("M04", "Strafe Right", 0.0, -0.05, 0.0),
    ("M05", "Rotate CCW", 0.0, 0.0, 0.20),
    ("M06", "Rotate CW", 0.0, 0.0, -0.20),
    ("M07", "Diagonal Forward Left", 0.03, 0.03, 0.0),
    ("M08", "Diagonal Forward Right", 0.03, -0.03, 0.0),
)
DURATION = 1.0


def require_safe_waiting_state(robot):
    if not rclpy.ok():
        raise RuntimeError("Contexte ROS 2 arrêté")
    state = robot.get_safety_state()
    if state != "DISARMED":
        raise RuntimeError(f"État de sécurité inattendu pendant l'attente : {state}")
    # Réutilise les contrôles de fraîcheur et de zéro du contrôleur.
    source = robot._latest("/command_mux/source").data
    if source != "NONE":
        raise RuntimeError(f"Source inattendue pendant l'attente : {source}")
    if not robot._zero():
        raise RuntimeError("Commande moteur non nulle pendant l'attente")


def monitored_input(robot, prompt):
    """Laisser le thread principal surveiller ROS 2 pendant la saisie."""
    replies = Queue(maxsize=1)

    def read_line():
        try:
            replies.put(input(prompt))
        except Exception as exc:
            replies.put(exc)

    require_safe_waiting_state(robot)
    Thread(target=read_line, daemon=True).start()
    while True:
        rclpy.spin_once(robot, timeout_sec=0.05)
        require_safe_waiting_state(robot)
        try:
            reply = replies.get_nowait()
        except Empty:
            continue
        if isinstance(reply, Exception):
            raise reply
        return reply.strip()


def read_physical_validation(robot):
    print("PASS signifie que le mouvement des roues correspond au mouvement "
          "attendu et que les quatre roues se sont arrêtées.")
    while True:
        reply = monitored_input(
            robot, "Tapez PASS ou FAIL, suivi d'une observation facultative : "
        )
        fields = reply.split(maxsplit=1)
        if fields and fields[0].upper() in ("PASS", "FAIL"):
            return fields[0].upper(), fields[1] if len(fields) == 2 else ""
        print("Un résultat explicite PASS ou FAIL est requis.")


def show_telemetry(robot):
    try:
        vx, vy, wz = robot.get_velocity()
    except RuntimeError as exc:
        print(f"Velocity feedback indisponible ({exc})")
    else:
        print(f"Velocity feedback | Vx={vx:+.3f} m/s | Vy={vy:+.3f} m/s | Wz={wz:+.3f} rad/s")

    try:
        voltage = robot.get_battery()
    except RuntimeError as exc:
        print(f"Tension batterie indisponible ({exc})")
    else:
        print(f"Tension batterie | {voltage:.2f} V")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", action="store_true", required=True,
                        help="Exécuter sur banc avec les quatre roues suspendues")
    parser.parse_args()

    robot = None
    verified = set()
    physical_results = {}
    physical_failure = False
    active_movement = None
    result = 1
    try:
        confirmation = input(
            "Vérifiez que les quatre roues sont suspendues et que la coupure "
            "physique est accessible. Tapez OUI pour confirmer : "
        )
        if confirmation.strip().upper() != "OUI":
            raise RuntimeError("Conditions du banc non confirmées")

        rclpy.init()
        robot = M1MotionController()
        robot.connect()
        print("État initial vérifié | DISARMED / NONE / commande moteur zéro")
        show_telemetry(robot)

        for movement_id, name, vx, vy, wz in MOVEMENTS:
            print(f"\n{movement_id} | {name} | {DURATION:.1f} s | "
                  f"Vx={vx:+.2f} m/s | Vy={vy:+.2f} m/s | Wz={wz:+.2f} rad/s")
            confirmation = monitored_input(
                robot, f"Tapez {movement_id} pour autoriser ce mouvement : "
            )
            if confirmation.upper() != movement_id:
                raise RuntimeError(f"{movement_id} non autorisé")

            active_movement = movement_id
            robot.arm()  # Revérifie DISARMED / NONE / zéro avant l'armement.
            robot.move(vx, vy, wz, DURATION)  # Inclut stop() et sa vérification.
            robot.disarm()  # Vérifie DISARMED / NONE / zéro avant de rendre la main.
            verified.add(movement_id)
            active_movement = None

            print(f"{movement_id} | DISARMED / NONE / commande moteur zéro vérifiés")
            show_telemetry(robot)
            physical, observation = read_physical_validation(robot)
            physical_failure = physical == "FAIL"
            physical_results[movement_id] = physical, observation
            if physical_failure:
                raise RuntimeError(f"{movement_id} : validation physique FAIL")

        result = 0
    except KeyboardInterrupt:
        print("\nABORT | interruption opérateur", flush=True)
        result = 130
    except EOFError:
        print("\nABORT | fin de la saisie opérateur", flush=True)
    except Exception as exc:
        print(f"\nABORT | {exc}", flush=True)
    finally:
        try:
            if robot is not None:
                try:
                    if robot.owns_session or physical_failure:
                        if not rclpy.ok():
                            raise RuntimeError("Contexte ROS 2 arrêté")
                        robot.emergency_stop()
                except (Exception, KeyboardInterrupt) as exc:
                    print(f"ARRÊT NON CONFIRMÉ | {exc}", flush=True)
                finally:
                    robot.destroy_node()
        finally:
            if rclpy.ok():
                rclpy.shutdown()
            print(f"\nBilan logiciel | {len(verified)}/{len(MOVEMENTS)} contrôles réussis")
            print("Périmètre logiciel : autorisation du mouvement et retour à une "
                  "commande de sortie nulle. La réponse mesurée des roues et le "
                  "suivi complet des consignes sont hors de ce périmètre.")
            for movement_id, name, *_ in MOVEMENTS:
                software = "vérifié" if movement_id in verified else "non exécuté"
                if movement_id == active_movement:
                    software = "interrompu ou état final non vérifié"
                physical, observation = physical_results.get(movement_id, ("non évalué", ""))
                detail = f" | observation : {observation}" if observation else ""
                print(f"{movement_id} {name} | logiciel : {software} | "
                      f"physique : {physical}{detail}")

    return result


if __name__ == "__main__":
    raise SystemExit(main())
