# P02 — First Robot Motion — Rapport technique

## Objectifs

M1 EXPLORER est une plateforme pédagogique de robotique mobile basée sur le Yahboom ROSMASTER M1. Le projet vise une architecture modulaire, maintenable et documentée. P02 met en place une première chaîne de mouvement supervisée, sélectionne explicitement la source de commande et vérifie sur banc le comportement des roues pour des consignes longitudinales, latérales, angulaires et diagonales.

## Périmètre matériel et logiciel

Le Raspberry Pi 5 (8 Go) héberge la supervision et communique via le driver Yahboom avec la carte STM32F103RCT6 qui pilote quatre moteurs DC à encodeurs et quatre roues Mecanum. La plateforme comprend une batterie Li-ion 3S2P, un OLED, un LiDAR T-MINI PLUS, une caméra RGB-D Nuwa-HP60C et une IMU 9 axes. Cet inventaire provient d’[AGENTS.md](../AGENTS.md). Les fonctions LiDAR, caméra et IMU sont hors du périmètre de validation P02 présenté ici.

ROS 2 Humble s’exécute dans Docker sur Raspberry Pi OS (Debian 12). Le contrôleur Python et la manette alimentent le Command Multiplexer, qui transmet la source sélectionnée au Motion Safety Supervisor. Celui-ci valide et limite les commandes avant le driver. La surveillance batterie exporte une télémétrie JSON destinée à l’affichage OLED sur l’hôte. [Architecture logicielle](M1_EXPLORER_Software_Architecture.md)

## Choix de conception

- Le multiplexeur laisse visibles les interruptions de la source. Le supervisor peut ainsi appliquer son watchdog logiciel sans qu’un keepalive synthétique masque l’absence d’entrée.
- La sélection de la source et l’armement sont distincts. Le multiplexeur exige un état frais `DISARMED` pour sélectionner une source de mouvement, puis une entrée neutre après la garde. Le supervisor exige à son tour une consigne nulle récente pour armer.
- Le supervisor limite chaque axe puis applique une limite à la norme planaire `hypot(Vx, Vy)`. Si la norme dépasse la limite, une mise à l’échelle commune de Vx et Vy préserve la direction du vecteur après limitation par axe.
- La démonstration sépare l’autorisation logicielle et le retour à une sortie nulle de l’évaluation physique par l’opérateur. Elle repasse par l’état sûr entre les mouvements. [Contrôleur](../controllers/m1_motion_controller.py) · [Démonstration](../examples/demo_m1_omnidirectional.py)

## Bilan P02

L’essai rapporté du 25 novembre 2026 a obtenu 8/8 contrôles logiciels et 8/8 validations physiques qualitatives sur banc, avec les quatre roues suspendues. Le test DDS associé rapporte une connexion réussie en 9,286 s après passage du délai de connexion de 2 à 10 s. Le caractère reproductible de ce délai et la cause de la découverte lente restent à établir. Les résultats, conditions et limites de preuve sont consignés dans le compte rendu expérimental. [Résultats expérimentaux](P02_Experimental_Results.md)

Les priorités de développement sont la démonstration d’une protection matérielle indépendante, la caractérisation instrumentée des roues, l’isolation DDS et la calibration de l’estimation batterie. Le mouvement au sol reste hors autorisation. [Limites connues](P02_Known_Limitations.md) · [Guide utilisateur](M1_EXPLORER_User_Guide.md)

## Statut des informations

Les comportements logiciels décrits proviennent de la lecture du code. Les chemins hôte proviennent des fichiers de démarrage et de surveillance lus sur l’hôte. Les résultats expérimentaux proviennent du compte rendu fourni par l’opérateur. La disponibilité effective des services au démarrage, les paramètres DDS actifs et les traces brutes de l’essai restent à confirmer ou à archiver selon le cas.
