# BatiSuivi Analytics

Prototype pédagogique de suivi de chantier sous Flask, avec menu latéral rétractable, tableaux de bord, graphiques Plotly, pages séparées et export CSV.

## Démarrer sous Windows
1. Installer Python 3.10+ et cocher « Add Python to PATH ».
2. Ouvrir un terminal dans ce dossier.
3. Exécuter `python -m pip install -r requirements.txt`.
4. Exécuter `python app.py`.
5. Ouvrir http://127.0.0.1:5000.

Aucune connexion ni aucun compte ne sont nécessaires. La base SQLite et les données de démonstration sont créées au premier lancement. Les données sont synthétiques. Bootstrap et Plotly sont chargés depuis un CDN, donc une connexion Internet est utile pour les graphiques et le style. Sauvegarder `batisuivi.db` régulièrement.


## Collecte de données
Une page dédiée « Collecte de données » est accessible dans le menu latéral. Elle regroupe la création de chantier, l'avancement des travaux, les mouvements de matériaux, les dépenses et les incidents, avec un historique récent.


1. Ouvre un terminal dans le dossier du projet et installe les dépendances avec `python -m pip install -r requirements.txt`.
2. Lance l'application avec `python app.py` (utilise `python` plutôt que `py` si le lanceur `py` de Windows affiche une erreur).
3. Ouvre `http://127.0.0.1:5000`. Lors de la première utilisation, clique sur « Première utilisation ? Créer le compte administrateur » ou ouvre directement `http://127.0.0.1:5000/initialiser-admin`.
4. Crée ton identifiant, ton nom et un mot de passe d'au moins 10 caractères dans le formulaire du navigateur. Les caractères du mot de passe seront masqués dans le champ : tu n'as pas besoin de le saisir dans le terminal.
5. Après création, connecte-toi et ouvre « Gestion des comptes » pour créer les comptes des autres utilisateurs.

La page de première initialisation n'est accessible que tant qu'aucun compte utilisateur n'existe. Les mots de passe sont hachés avec Werkzeug. Les pages métier et les routes d'enregistrement/export nécessitent une session ouverte. La base `batisuivi.db` contient aussi la table `users`. Sauvegarde la base avant toute modification. Cette configuration est prévue pour un usage local de démonstration ; avant un déploiement réseau/Internet, configure une clé secrète persistante via la variable d'environnement `BATISUIVI_SECRET_KEY` et désactive le mode debug.

## Profils et autorisations (version 8)

L'application utilise trois rôles :
- **Administrateur** : accès complet, collecte et création des comptes.
- **Agent de collecte** : accès aux écrans de consultation et à la rubrique « Collecte de données » ; peut enregistrer les chantiers, avancements, matériaux, dépenses et incidents.
- **Maître d'ouvrage** : consultation uniquement. La rubrique de collecte est masquée et les routes d'écriture refusent également les requêtes directes.

Crée le premier administrateur depuis le navigateur via `/initialiser-admin`. Ensuite connecte-toi, ouvre « Gestion des comptes » et attribue le rôle approprié à chaque personne.

### Important si tu mets à jour une base existante

La version 7 utilisait une contrainte SQLite qui n'acceptait que `admin` et `user`. Pour éviter une erreur lors de la création de comptes avec les nouveaux rôles, fais une copie de sauvegarde de `batisuivi.db` avant de mettre à jour. Cette version crée la nouvelle structure dans une base vierge ; pour conserver une base v7, il faut migrer la table `users` (ou repartir d'une base sauvegardée et migrée). Ne supprime pas l'ancienne base sans sauvegarde.

## Modules complémentaires (version 9)
- **Analyse statistique** : moyenne, médiane, écart-type, minimum/maximum, analyse des écarts prévu/réalisé, productivité par relevé, résultats par activité et répartition des coûts.
- **Rapports** : téléchargement d'un rapport texte `.txt`, d'un rapport PDF mis en page et export CSV.
- **Planning** : ajout des tâches avec dates, responsable, statut et observations.
- **Photos du chantier** : archivage par chantier/date/légende. Formats acceptés : JPG, JPEG, PNG et WEBP, limite 8 Mo par photo.
- **Équipe et personnel** : liste des agents, fonctions, téléphone et salaire mensuel. Le bouton « Ajouter aux dépenses » inscrit le salaire dans les dépenses de main-d'œuvre pour le mois sélectionné; le même membre ne peut pas être payé deux fois pour le même mois.

### Installation / mise à jour
1. Décompresser le projet dans un dossier de travail.
2. Dans le terminal ouvert dans ce dossier, exécuter `py -m pip install -r requirements.txt`.
3. Puis exécuter `py app.py`.
4. Les pages Planning, Photos et Équipe sont consultables par les profils autorisés; les actions de saisie sont réservées à l'administrateur et à l'agent de collecte. Le maître d'ouvrage reste en consultation.

**Important :** avant de remplacer une version précédente, fais une copie de `batisuivi.db`. Les nouvelles tables (planning, personnel, paie, photos) sont créées automatiquement au lancement. Le calcul des salaires est une aide au suivi : vérifie les montants, primes, retenues et obligations légales avant d'utiliser ces données dans une paie réelle. Les données de démonstration ne constituent pas une mesure réelle du chantier.

## Ajustements profil et planning
- Le profil permet de modifier le nom affiché, de téléverser une photo (JPG, PNG ou WEBP) et de se déconnecter.
- Le planning initial est créé à partir des activités déjà enregistrées dans le suivi, puis propose des étapes prévisionnelles pour la suite du chantier. Les dates futures sont indicatives et doivent être confirmées par l’équipe.
- Les administrateurs et collecteurs peuvent valider les tâches réalisées. Le maître d’ouvrage ne voit que les tâches validées.
- Une migration douce ajoute les champs de photo de profil et de validation aux bases existantes au lancement, sans supprimer les données présentes.


### Graphiques d'analyse dynamiques
La page Analyses recalcule les graphiques à chaque chargement depuis les données SQLite : prévu/réalisé par date, écarts quotidiens, comparaison par activité et répartition des dépenses. Les filtres de dates mettent à jour les graphiques d'avancement côté navigateur. Après une nouvelle saisie, ouvrir/recharger Analyses pour récupérer les dernières valeurs enregistrées.

## Démonstration multi-chantiers et analyses dynamiques
La base est préremplie avec trois chantiers synthétiques : un bâtiment R+2 à Yaoundé, une route à Douala et un bâtiment scolaire à Bafoussam. Chaque chantier possède des relevés d'avancement, des dépenses, des matériaux, des incidents et des tâches de planning. Les chantiers d'exemple sont ajoutés automatiquement s'ils ne sont pas déjà présents dans la base.

Dans **Analyses**, les boutons permettent d'afficher l'étude détaillée de chaque chantier ou l'analyse globale. Les graphiques sont recalculés depuis SQLite à chaque chargement de la page ; après une saisie ou une modification, actualiser la page pour voir les courbes et les conclusions automatiques mises à jour. En analyse globale, la comparaison du taux de réalisation se fait par activité/unité afin de ne pas additionner directement des unités différentes. Les conclusions sont des indicateurs d'aide à la décision, à vérifier avec les observations du chantier.


## Synchronisation des données et séparation des chantiers

- L'application démarre avec trois chantiers de démonstration distincts (bâtiment R+2, route, bâtiment scolaire). Les relevés, dépenses, devis, planning, équipe et photos sont associés à un identifiant de chantier.
- Le chantier sélectionné est conservé dans les liens du menu latéral pour éviter de consulter ou saisir les données dans un autre chantier par inadvertance.
- Le taux d'avancement du tableau de bord est calculé à partir des relevés enregistrés, par activité et par unité, afin de ne pas additionner directement des quantités en m², m³, kg, etc. Les taux individuels sont plafonnés à 100 % pour cet indicateur synthétique.
- Le graphique journalier compte les relevés de suivi par date; le graphique des activités montre le pourcentage réalisé par activité; les dépenses sont agrégées depuis les dépenses effectivement saisies.
- La rubrique Dévis permet d'enregistrer des lignes d'estimation propres à un chantier. Les devis restent distincts des dépenses réelles afin d'éviter le double comptage.
- Le planning crée les principales phases, de la préparation à la réception, par chantier. Une tâche marquée « Réalisé » apparaît dans la section dédiée; les données de suivi exactes peuvent aussi faire passer une tâche correspondante à « En cours » ou « Réalisé ».
- Les photos sont téléversées dans la galerie et filtrées par chantier.
- Les graphiques et analyses se recalculent à partir de la base lors du chargement/rafraîchissement de la page.

## Correctifs de cohérence (23 octobre 2026)
- Le graphique « Relevés de suivi par jour » utilise désormais les quantités réellement réalisées, regroupées par date, activité et unité (et non le nombre de lignes saisies).
- Les données du graphique et les indicateurs sont recalculés à partir des enregistrements de la base au chargement du tableau de bord.
- Le planning rapproche les intitulés détaillés des phases avec les activités de suivi usuelles (fouilles, béton de propreté, ferraillage, coffrage, etc.) afin de synchroniser les statuts quand les quantités montrent qu'une tâche est partiellement ou totalement exécutée.
- Les unités ne sont pas additionnées entre elles dans le calcul de l'avancement global : un taux est calculé par activité/unité.

### Liaison des dépenses aux phases du planning

Dans « Collecte de données », chaque nouvelle dépense peut maintenant être associée à une phase précise du planning. Le tableau de bord actualise les totaux de dépenses, la part du budget consommée, la répartition par catégorie et le graphique « Dépenses par phase du planning » à partir des dépenses réellement enregistrées. Les dépenses des anciennes versions sont conservées ; comme elles n'avaient pas de phase associée, elles apparaissent sous « Non affectées » plutôt que d'être attribuées arbitrairement. L'association d'une dépense à une phase sert à analyser les coûts : elle ne crée pas automatiquement une dépense lorsqu'une quantité de travail est saisie.
