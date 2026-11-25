# M1 EXPLORER — Guide utilisateur

## Préparer le banc

1. Obtenir l’autorisation explicite de réaliser l’essai matériel. Suspendre les quatre roues, stabiliser le robot et garder la coupure physique accessible. Le déplacement au sol reste hors autorisation.
2. Utiliser la pile de démarrage installée. Identifier le conteneur par son image et son contexte avec `docker ps`, puis ouvrir un shell dans le conteneur choisi avec `docker exec -it <ID> bash`. Remplacer `<ID>` par l’identifiant relevé. Si plusieurs conteneurs correspondent ou si la pile est indisponible, vérifier le déploiement avant l’essai.
3. Dans ce shell, préparer l’environnement et consulter le graphe. Les commandes suivantes sont des diagnostics en lecture seule une fois l’environnement chargé.

```bash
source /opt/ros/humble/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
export ROS_DOMAIN_ID=61
cd /root/share/M1_EXPLORER
ros2 node list
ros2 service list -t
ros2 topic info /cmd_vel
ros2 topic echo /motion_safety/status --once
ros2 topic echo /command_mux/source --once
ros2 topic echo /cmd_vel --once
```

Vérifier `DISARMED`, `NONE` et un `Twist` nul. Laisser le temps à DDS de découvrir les endpoints et fermer les outils concurrents de commande. Effectuer ces vérifications dans l’environnement ciblé. Le graphe et les contrôles du script restent nécessaires à chaque session.

## Démonstration omnidirectionnelle autorisée sur banc

Depuis le workspace du conteneur, lancer la démonstration uniquement pendant un essai autorisé.

```bash
python3 examples/demo_m1_omnidirectional.py --bench
```

1. Saisir `OUI` après avoir vérifié les quatre roues suspendues et la coupure physique accessible.
2. Lire l’identifiant et la consigne affichés. Saisir l’identifiant demandé pour autoriser le mouvement correspondant. Le contrôleur arme, commande pendant une seconde, arrête et désarme.
3. Observer le comportement des roues et vérifier l’arrêt de chacune. Saisir `PASS` seulement si leur mouvement correspond à celui attendu et si les quatre se sont arrêtées. Sinon, saisir `FAIL`. Une observation peut suivre le verdict sur la même ligne, par exemple `PASS arrêt constaté sur les quatre roues`.
4. Consulter le bilan logiciel et les verdicts physiques séparés. La tension et le velocity feedback sont affichés lorsqu’ils sont disponibles, à la connexion et après désarmement. Conserver le bilan avec les conditions d’essai. [Séquence et consignes](P02_Experimental_Results.md)

Pendant les saisies entre mouvements, le script surveille la fraîcheur de l’état, de la source et de la sortie nulle. Une anomalie interrompt l’essai. `Ctrl+C` interrompt également la séquence. Un `FAIL` entraîne une tentative d’arrêt d’urgence logiciel si le contexte ROS est disponible, même après désarmement. En cas de mouvement inattendu ou d’arrêt incertain, utiliser la coupure physique accessible. Après un défaut, interrompre l’essai et diagnostiquer avant toute nouvelle autorisation. La procédure de démonstration n’effectue aucun reset ou réarmement automatique.

Si `connect()` échoue, relever les services indisponibles, topics sans données fraîches, valeurs inattendues et éventuels écarts de topologie indiqués par le contrôleur. Vérifier que le shell vise le bon conteneur et domaine. Une absence persistante de télémétrie ou un état impossible à confirmer demande un diagnostic avant de poursuivre. [Architecture](M1_EXPLORER_Software_Architecture.md)

## Observer la batterie et l’OLED

Sur l’hôte, consulter les unités et le JSON sans redémarrer de service.

```bash
systemctl is-active m1-battery-monitor.service yahboom_oled.service
cat /home/pi/share/M1_EXPLORER/data/battery_status.json
```

L’écran alterne entre les informations système et la batterie. Une tension ou une estimation indisponible apparaît comme `N/A`. Le pourcentage est une estimation indicative. Vérifier la fraîcheur du JSON et la présence de `/voltage` en cas d’indisponibilité prolongée. [Limites connues](P02_Known_Limitations.md)

Les procédures ci-dessus décrivent l’exploitation de la configuration inspectée. Les installateurs historiques nécessitent une revue des chemins avant toute utilisation. Le test historique `tests/test_motion_safety.py` publie directement sur `/cmd_vel_input` et doit rester hors de la chaîne permanente.
