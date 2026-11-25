# M1 EXPLORER — Architecture logicielle

## Environnements et démarrage

L’environnement de référence est Raspberry Pi OS (Debian 12) sur Raspberry Pi 5, avec Python 3 et ROS 2 Humble dans Docker. Le développement peut s’effectuer depuis VS Code Remote SSH. Le domaine ROS 2 attendu est `ROS_DOMAIN_ID=61`. Le workspace hôte `/home/pi/share/M1_EXPLORER/` apparaît dans le conteneur sous `/root/share/M1_EXPLORER/`. Le nom du conteneur est dynamique. [Consignes du projet](../AGENTS.md)

| Élément inspecté | Configuration relevée |
| --- | --- |
| Autostart graphique hôte | `/home/pi/.config/autostart/start_handle.desktop` référence le script Yahboom via `lxterminal`. |
| Script hôte Yahboom | `/home/pi/Rosmaster/rosmaster/start_ros2_humble.sh` lance l’image M1 `ros-humble-m1:1.1.1` avec réseau hôte et mode privilégié. Il monte le partage, `/dev/input` et `/dev/myserial`, puis appelle le script du projet dans le conteneur. |
| Entrypoint conteneur | `runtime/motion/start_m1_explorer.sh` charge ROS 2 et l’overlay Yahboom, exporte le domaine 61, le type M1 et les valeurs initiales de servo S1/S2 (90/35), puis lance `m1_explorer.launch.py`. |
| Launch de mouvement | Démarre la manette, la traduction de commandes Yahboom, le driver M1, le supervisor et le mux. Le launch configure le respawn du supervisor et du mux avec un délai de 0,2 s. |
| Batterie | L’unité hôte `m1-battery-monitor.service` dépend de `docker.service`. Le script `/usr/local/lib/m1-explorer/battery-service.sh` sélectionne exactement un conteneur actif par image, y lance `runtime/monitoring/battery_monitor.py` avec le domaine 61 et transmet l’identifiant de boot de l’hôte. L’unité prévoit un redémarrage après 5 s. |
| OLED | Le drop-in hôte `yahboom_oled.service.d/90-m1-explorer.conf` pointe vers `/home/pi/software/oled_yahboom/m1_explorer_oled.py`, qui lit le JSON du workspace sur l’hôte. |

Les fichiers confirment le câblage prévu. Leur activation au boot, la disponibilité simultanée des processus et le comportement réel lors d’un redémarrage n’ont pas été vérifiés dans cette revue. Les installateurs historiques référencent d’autres chemins de déploiement. [Entrypoint](../runtime/motion/start_m1_explorer.sh) · [Launch](../runtime/motion/m1_explorer.launch.py) · [Limites](P02_Known_Limitations.md)

## Chaîne de commande et nœuds ROS 2

```text
joy_node → yahboom_joy_M1 → /cmd_vel_joy ─┐
                                         ├→ command_mux → /cmd_vel_input
m1_motion_controller → /cmd_vel_python ──┘
  → motion_safety_supervisor → /cmd_vel → driver Yahboom → STM32 → moteurs
```

Le launch déclare trois exécutables externes `joy/joy_node`, `yahboomcar_ctrl/yahboom_joy_M1` et `yahboomcar_bringup/Mcnamu_driver_M1`. Les noms ROS effectifs de ces nœuds et la liste exhaustive de leurs interfaces nécessitent une inspection du graphe en fonctionnement. Les nœuds Python du projet déclarent leurs noms ci-dessous. [Launch](../runtime/motion/m1_explorer.launch.py)

| Nœud du projet | Rôle |
| --- | --- |
| `command_mux` | Sélectionne et transmet une source de mouvement. |
| `motion_safety_supervisor` | Autorise et limite le mouvement, surveille le flux et publie l’état de sécurité. |
| `m1_motion_controller` | Fournit l’API synchrone utilisée par les démonstrations. Instancié à l’exécution du script opérateur. |
| `battery_monitor` | Lit la tension et exporte un JSON de télémétrie, via un service séparé du launch de mouvement. |

Les six nœuds de l’architecture de démarrage correspondent aux cinq composants du launch de mouvement et au monitor batterie. Une démonstration Python ajoute son propre nœud pendant son exécution.

### Topics

| Topic | Type | Rôle |
| --- | --- | --- |
| `/cmd_vel_joy` | `geometry_msgs/msg/Twist` | Sortie de commande de la manette remappée par le launch vers le mux. |
| `/cmd_vel_python` | `geometry_msgs/msg/Twist` | Entrée d’une application Python vers le mux. |
| `/cmd_vel_input` | `geometry_msgs/msg/Twist` | Sortie du mux vers le supervisor. |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Sortie supervisée vers le driver, observée par le contrôleur. |
| `/motion_safety/status` | `std_msgs/msg/String` | État du supervisor, publié toutes les secondes et aux transitions. |
| `/command_mux/source` | `std_msgs/msg/String` | Source sélectionnée, republiée par un timer de 0,2 s et lors des changements de sélection. |
| `/vel_raw` | `geometry_msgs/msg/Twist` | Velocity feedback consommé par le contrôleur (Vx, Vy et Wz). |
| `/voltage` | `std_msgs/msg/Float32` | Tension en volts consommée par le contrôleur et le monitor batterie. |

Les types de `/vel_raw` et `/voltage` sont confirmés côté abonnés du projet. Le calcul exact du feedback et la provenance matérielle des échantillons relèvent du driver externe. [Contrôleur](../controllers/m1_motion_controller.py) · [Monitor batterie](../runtime/monitoring/battery_monitor.py)

### Services

Tous les services suivants utilisent `std_srvs/srv/Trigger`.

| Service | Effet prévu par le code |
| --- | --- |
| `/command_mux/select_joy`, `/command_mux/select_python` | Sélectionne la source si l’état reçu est récent et vaut `DISARMED`. |
| `/command_mux/select_none` | Inhibe le transfert des entrées. Le désarmement du supervisor reste l’action d’arrêt immédiat côté logiciel. |
| `/motion_safety/arm` | Passe de `DISARMED` à `ARMED` si une entrée nulle récente est disponible. |
| `/motion_safety/disarm` | Efface la consigne et publie zéro. Passe de `ARMED` à `DISARMED` et conserve les états de défaut. |
| `/motion_safety/emergency_stop` | Publie zéro et place le supervisor en `EMERGENCY_STOP`. |
| `/motion_safety/reset` | Efface la commande, publie zéro et ramène le supervisor à `DISARMED`. Intervention explicite hors de la démo. |

### Command Multiplexer

Démarre sur `NONE`. Une source `JOY` ou `PYTHON` exige un état `DISARMED` datant de moins de 2 s. Après sélection, le mux attend une garde de 0,75 s puis un premier `Twist` neutre sur les six composantes. Ensuite, il transmet uniquement les messages reçus de la source choisie tant que l’état du supervisor est frais et vaut `DISARMED` ou `ARMED`. Une perte de fraîcheur ou un état de défaut ramène la sélection à `NONE`. La sélection doit être pilotée par un opérateur à la fois. [Command Multiplexer](../runtime/motion/command_mux.py)

### Motion Safety Supervisor

Démarre `DISARMED`. Les autres états sont `ARMED`, `TIMEOUT`, `EMERGENCY_STOP` et `INVALID_COMMAND`. Le supervisor rejette les valeurs non finies et les composantes hors plan dépassant sa tolérance. Les valeurs par défaut limitent Vx et Vy à ±0,15 m/s, la norme planaire à 0,15 m/s et Wz à ±0,5 rad/s. La boucle à 20 Hz utilise une horloge monotone et surveille un âge de commande de 0,5 s. Elle publie zéro hors de l’état `ARMED`. L’armement exige une entrée nulle âgée de moins que le timeout de commande. L’arrêt à la fermeture repose sur une tentative de publication de zéros si le contexte ROS le permet. [Motion Safety Supervisor](../runtime/motion/motion_safety_supervisor.py)

### Python Motion Controller API

| API | Comportement |
| --- | --- |
| `M1MotionController(connect_timeout=10.0)`, `connect()` | Attend les cinq services utilisés par le contrôleur (arm, disarm, emergency_stop, select_python, select_none), `DISARMED`, `NONE` et une sortie nulle. Vérifie ensuite qu’il existe exactement un publisher sur chacun des trois topics de commande contrôlés (`/cmd_vel`, `/cmd_vel_input`, `/cmd_vel_python`) et un subscriber sur la sortie Python. |
| `arm()` | Rejoue `connect()`, sélectionne `PYTHON`, émet une entrée neutre pendant 1,2 s puis demande l’armement. Attend `ARMED/PYTHON`. |
| `move(vx, vy, wz, duration)` | Nécessite une session armée. Envoie un `Twist` environ toutes les 0,05 s, surveille l’autorisation et les publishers, puis appelle `stop()`. Le banc est limité à 0,05 m/s de norme planaire, 0,20 rad/s en valeur absolue et 2 s par commande. |
| `forward(speed, duration)`, `backward(speed, duration)`, `strafe_left(speed, duration)`, `strafe_right(speed, duration)`, `rotate(speed, duration)` | Raccourcis vers `move()`. Le signe de `speed` fixe le sens de rotation. |
| `stop()`, `disarm()` | `stop()` envoie du neutre pendant 0,2 s et vérifie zéro en sortie. `disarm()` rend la source `NONE` et confirme `DISARMED/NONE/zéro`. |
| `emergency_stop()` | Demande l’arrêt logiciel, sélectionne `NONE` et vérifie `EMERGENCY_STOP/NONE/zéro`. |
| `get_safety_state()`, `get_velocity()`, `get_battery()` | Lisent les derniers échantillons disponibles. Échouent en cas d’absence ou de dépassement du seuil de fraîcheur. |

La connexion conserve la fraîcheur de 2 s pour l’état et la source et de 0,25 s pour la sortie nulle, mesurée à la réception locale. Le feedback vitesse a une limite de 0,5 s et la tension du contrôleur de 2 s. Les autres attentes internes conservent 2 s et les réponses de services 1,5 s. Le délai de connexion ne modifie pas la fenêtre du watchdog. [Python Motion Controller](../controllers/m1_motion_controller.py)

## Batterie et OLED

`battery_monitor` s’abonne à `/voltage` avec le QoS capteur, accepte les mesures finies dans l’intervalle ]0, 13] V, calcule la moyenne des 50 derniers échantillons au maximum et publie un JSON par remplacement atomique environ chaque seconde. Une interruption supérieure à 3 s ou une mesure invalide rend les données indisponibles. Le JSON expose les tensions brute et filtrée, le pourcentage estimé, l’état, le nombre d’échantillons, les timestamps et l’identifiant de boot. Le modèle 3S non calibré utilise une interpolation linéaire par morceaux. Les états sont `CRITICAL` sous 10 %, `WARNING` sous 20 %, `LOW` sous 50 % et `NORMAL` à partir de 50 %. Ces états servent à la télémétrie. [Monitor batterie](../runtime/monitoring/battery_monitor.py)

Le chemin conteneur `/root/share/M1_EXPLORER/data/battery_status.json` correspond à `/home/pi/share/M1_EXPLORER/data/battery_status.json` sur l’hôte. Le script OLED inspecté alterne toutes les 5 s entre la page système (CPU, heure, RAM, disque, IP) et la page batterie (pourcentage approximatif, tension filtrée, état). Il exige un JSON valide, un identifiant de boot correspondant et un âge monotone compris entre 0 et 3 s, puis affiche `N/A` ou `UNKNOWN` en cas de données indisponibles. `Mode: UNKNOWN` est un libellé fixe de la page batterie.

## Arborescence du projet

| Répertoire | Contenu |
| --- | --- |
| `runtime/motion/` | Mux, supervisor, launch et point d’entrée Docker. |
| `runtime/monitoring/` | Monitor batterie. |
| `controllers/` | Bibliothèque de commande Python. |
| `examples/` | Démonstrations de mouvement initiale et omnidirectionnelle. |
| `tests/` | Test end-to-end supervisé et test historique à injection directe dans le supervisor. |
| `config/` | Répertoire réservé à la configuration, sans fichier relevé. |
| `data/` | Télémétrie produite à l’exécution. |
| `documentation/` | Documentation technique et d’exploitation. |
| `installers/`, `backups/` | Installateurs historiques et sauvegardes locales. |
