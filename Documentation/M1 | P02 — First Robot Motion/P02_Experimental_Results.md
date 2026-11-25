# P02 — Résultats expérimentaux

## Démonstration omnidirectionnelle

Résultats communiqués pour le 25 novembre 2026. Le robot était sur banc, les quatre roues Mecanum suspendues. Les valeurs ci-dessous sont les consignes du script, en unités SI. Selon la convention utilisée, Vx positif pointe vers l’avant, Vy positif vers la gauche et Wz positif correspond à une rotation antihoraire (CCW). [Script inspecté](../examples/demo_m1_omnidirectional.py)

| ID | Mouvement | Vx (m/s) | Vy (m/s) | Wz (rad/s) | Durée commandée (s) | Verdict physique |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| M01 | Forward | 0,05 | 0 | 0 | 1 | PASS |
| M02 | Backward | −0,05 | 0 | 0 | 1 | PASS |
| M03 | Strafe Left | 0 | 0,05 | 0 | 1 | PASS |
| M04 | Strafe Right | 0 | −0,05 | 0 | 1 | PASS |
| M05 | Rotate CCW | 0 | 0 | 0,20 | 1 | PASS |
| M06 | Rotate CW | 0 | 0 | −0,20 | 1 | PASS |
| M07 | Diagonal Forward Left | 0,03 | 0,03 | 0 | 1 | PASS |
| M08 | Diagonal Forward Right | 0,03 | −0,03 | 0 | 1 | PASS |

| Indicateur communiqué | Résultat |
| --- | --- |
| Validation logicielle | 8/8 |
| Validation physique par l’opérateur | 8/8 |
| Tension avant et après la séquence | 11,40 V avant et 11,40 V après |
| Velocity feedback après chaque mouvement | Vx, Vy et Wz nuls |
| État final du supervisor | `DISARMED` |
| Source finale | `NONE` |
| Sortie finale `/cmd_vel` | Nulle |

Les contrôles logiciels portent sur l’autorisation du mouvement et le retour à zéro de la sortie. Le verdict physique `PASS` correspond à une observation qualitative du mouvement attendu et de l’arrêt des quatre roues. Le feedback nul après arrêt décrit les échantillons rapportés à cet instant. La durée d’une seconde correspond à la consigne logicielle. Les vitesses individuelles, la réponse transitoire et la précision de suivi pendant le mouvement restent à mesurer. Les deux lectures de tension ne permettent pas d’évaluer l’autonomie ou la chute de tension sous charge.

## Test de connexion DDS

| Indicateur communiqué | Valeur |
| --- | --- |
| Délai de connexion précédent | 2 s |
| Nouveau délai de connexion par défaut | 10 s |
| Temps de connexion réussi mesuré | 9,286 s |

La modification s’applique à `connect()`, y compris lorsque `arm()` l’appelle. Les délais de sécurité du mouvement et les réglages du watchdog restent inchangés. Une connexion réussie est rapportée dans cette fenêtre. La cause de la découverte lente reste indéterminée. Le temps mesuré couvre la connexion réussie rapportée, dont les conditions incluent la disponibilité des services et la réception de l’état sûr. La contribution de chaque étape est inconnue. [Contrôleur](../controllers/m1_motion_controller.py)

## Données à archiver

Le compte rendu s’appuie sur les résultats expérimentaux fournis. Aucun nouvel essai n’a été lancé pour la rédaction. Le transcript console, les messages ROS horodatés, la méthode de chronométrage DDS, les répétitions et la révision logicielle précise de chaque essai restent à joindre pour permettre une analyse reproductible.
