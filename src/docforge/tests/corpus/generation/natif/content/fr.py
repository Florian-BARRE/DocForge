# ====== Code Summary ======
# French content packs (contract + report) for the corpus builders. Real French prose so language
# detection resolves "fr"; deep enough pools that builders compose multi-page documents.

# ====== Local Project Imports ======
from .models import ContentPack

CONTRACT_FR = ContentPack(
    language="fr",
    title="Contrat-cadre de prestations de services managés",
    subtitle="Référence CG-2026-FR-014 — exemplaire original signé en deux exemplaires",
    searchable_phrase="résiliation pour manquement grave et réversibilité des données.",
    abstract=(
        "Le présent contrat-cadre définit les conditions générales et particulières applicables aux "
        "prestations de services managés fournies par le Prestataire au Client, ainsi que les "
        "engagements de niveau de service, les obligations de confidentialité et le régime de "
        "responsabilité des parties. Il prévaut sur tout document antérieur de portée équivalente."
    ),
    section_titles=[
        "Objet et périmètre",
        "Définitions et interprétation",
        "Obligations du Prestataire",
        "Obligations du Client",
        "Conditions financières et facturation",
        "Niveaux de service et pénalités",
        "Propriété intellectuelle",
        "Confidentialité et données personnelles",
        "Responsabilité et assurances",
        "Durée, résiliation et réversibilité",
        "Force majeure",
        "Droit applicable et règlement des différends",
    ],
    paragraphs=[
        "Les parties reconnaissent que l'exécution des prestations s'inscrit dans une relation de "
        "coopération loyale, chacune s'obligeant à communiquer en temps utile toute information de "
        "nature à affecter la bonne réalisation des engagements souscrits au titre des présentes.",
        "Le Prestataire met en œuvre les moyens humains et techniques nécessaires à la fourniture "
        "des prestations conformément aux règles de l'art, aux normes en vigueur et aux exigences "
        "de sécurité détaillées dans l'annexe technique, laquelle fait partie intégrante du contrat.",
        "Le Client s'engage à fournir, dans des délais raisonnables, l'ensemble des accès, "
        "habilitations et éléments documentaires indispensables, étant entendu que tout retard "
        "imputable au Client suspend de plein droit les délais corrélatifs opposables au Prestataire.",
        "La facturation intervient mensuellement à terme échu sur la base des prestations "
        "effectivement réalisées ; toute contestation d'une facture doit être notifiée par écrit "
        "dans un délai de trente jours, à défaut de quoi la facture est réputée définitivement acceptée.",
        "Les engagements de niveau de service sont mesurés sur une base mensuelle ; en cas de "
        "manquement constaté, des pénalités forfaitaires s'appliquent sans préjudice du droit du "
        "Client de réclamer la réparation intégrale du préjudice direct dûment justifié.",
        "Chaque partie demeure propriétaire des éléments antérieurs au contrat ; les développements "
        "spécifiques réalisés pour le compte du Client lui sont cédés à compter du paiement intégral "
        "du prix correspondant, sous réserve des composants tiers soumis à leurs licences propres.",
        "Les parties s'engagent à préserver la stricte confidentialité des informations échangées et "
        "à n'en faire usage qu'aux seules fins d'exécution du contrat, cette obligation survivant "
        "trois années après son terme quelle qu'en soit la cause.",
        "Le traitement des données à caractère personnel s'effectue dans le respect du règlement "
        "applicable ; le Prestataire agit en qualité de sous-traitant et met en place des mesures "
        "techniques et organisationnelles appropriées pour garantir un niveau de sécurité adapté.",
        "La responsabilité de chaque partie est plafonnée, par année contractuelle, au montant total "
        "hors taxes effectivement réglé au titre des douze derniers mois, hors cas de faute lourde, "
        "de dommage corporel ou de manquement à l'obligation de confidentialité.",
    ],
    clauses=[
        "Le présent article a pour objet de préciser les droits et obligations réciproques des "
        "parties ; il s'interprète à la lumière du préambule et des annexes, lesquels forment un "
        "tout indivisible et expriment l'intégralité de l'accord intervenu entre les parties.",
        "En cas de manquement grave de l'une des parties à ses obligations essentielles, non réparé "
        "dans un délai de quinze jours suivant une mise en demeure restée infructueuse, l'autre "
        "partie pourra résilier le contrat de plein droit, sans préjudice de tous dommages et intérêts.",
        "À l'expiration ou à la résiliation du contrat, le Prestataire assure la réversibilité des "
        "données dans un format ouvert et documenté, et apporte une assistance raisonnable à la "
        "reprise des prestations par le Client ou tout tiers qu'il aura désigné.",
        "Aucune des parties ne pourra être tenue responsable d'un manquement résultant d'un cas de "
        "force majeure au sens de la jurisprudence ; la partie empêchée en informe l'autre sans délai "
        "et les obligations affectées sont suspendues pour la durée de l'événement.",
    ],
    list_items=[
        "la disponibilité du service mesurée sur une base mensuelle calendaire",
        "le délai de prise en compte des incidents critiques",
        "le délai de rétablissement après interruption majeure",
        "la fréquence et le format des comités de pilotage",
        "les modalités d'escalade en cas de désaccord persistant",
    ],
    table_caption="Tableau 1 — Engagements de niveau de service et pénalités associées",
    table_headers=["Indicateur", "Cible", "Seuil critique", "Pénalité", "Périodicité"],
    table_rows=[
        ["Disponibilité", "99,9 %", "99,0 %", "5 % du forfait", "Mensuelle"],
        ["Prise en compte P1", "15 min", "30 min", "2 % du forfait", "Par incident"],
        ["Rétablissement P1", "4 h", "8 h", "5 % du forfait", "Par incident"],
        ["Reporting", "J+5", "J+10", "1 % du forfait", "Mensuelle"],
    ],
    notes=[
        "Les montants exprimés s'entendent hors taxes, sauf mention contraire expresse.",
        "Les délais sont décomptés en jours ouvrés selon le calendrier du siège du Prestataire.",
        "Toute tolérance ponctuelle ne saurait valoir renonciation à se prévaloir d'une stipulation.",
    ],
    column_blurb=(
        "La gouvernance du contrat repose sur un comité de pilotage trimestriel et un comité "
        "opérationnel mensuel ; ces instances examinent les indicateurs, arbitrent les évolutions de "
        "périmètre et consignent leurs décisions dans des comptes rendus contradictoires. Les parties "
        "conviennent que la qualité de la relation prime sur l'application mécanique des pénalités, "
        "lesquelles demeurent un instrument de dernier recours mobilisé en cas de dérive persistante "
        "et dûment caractérisée au regard des seuils contractuels."
    ),
)

REPORT_FR = ContentPack(
    language="fr",
    title="Rapport annuel d'activité et de performance numérique",
    subtitle="Exercice 2026 — version consolidée destinée au comité de direction",
    searchable_phrase="trajectoire de croissance soutenue malgré la pression sur les marges.",
    abstract=(
        "Ce rapport présente une analyse consolidée de l'activité de l'exercice écoulé, met en "
        "perspective les résultats financiers et opérationnels au regard des objectifs fixés, et "
        "formule des recommandations destinées à éclairer les arbitrages stratégiques à venir."
    ),
    section_titles=[
        "Synthèse exécutive",
        "Contexte de marché et environnement concurrentiel",
        "Performance commerciale par région",
        "Analyse financière détaillée",
        "Transformation numérique et système d'information",
        "Gestion des risques opérationnels",
        "Ressources humaines et organisation",
        "Engagements environnementaux et sociétaux",
        "Perspectives et plan d'action",
        "Conclusion et recommandations",
    ],
    paragraphs=[
        "Au cours de l'exercice, l'entreprise a confirmé une trajectoire de croissance soutenue "
        "malgré un environnement macroéconomique incertain marqué par la volatilité des coûts des "
        "intrants et une pression accrue sur les marges, absorbée en partie par les gains de productivité.",
        "La dynamique commerciale a été particulièrement vigoureuse sur les marchés européens, où "
        "le déploiement d'une offre packagée a permis d'accélérer le cycle de vente et d'améliorer "
        "significativement le taux de transformation des prospects qualifiés en clients récurrents.",
        "Sur le plan financier, la marge brute progresse en valeur absolue tandis que le taux de "
        "marge se contracte légèrement sous l'effet d'une politique tarifaire volontairement "
        "agressive sur les segments d'acquisition jugés stratégiques pour la conquête de parts de marché.",
        "La transformation numérique s'est traduite par la modernisation du socle technique, la "
        "rationalisation du portefeuille applicatif et l'industrialisation des chaînes de traitement "
        "de la donnée, désormais pilotées par des indicateurs de qualité et de fraîcheur mesurés en continu.",
        "La cartographie des risques opérationnels a été actualisée ; les principaux foyers d'exposition "
        "concernent la dépendance à un nombre restreint de fournisseurs critiques, la cybersécurité "
        "et la conformité réglementaire, pour lesquels des plans de remédiation ont été engagés.",
        "L'organisation a poursuivi sa montée en compétences avec un effort soutenu de formation, un "
        "renforcement des fonctions transverses et une attention particulière portée à la rétention "
        "des profils rares dont la contribution est déterminante pour la réussite des projets.",
        "Les engagements environnementaux progressent conformément à la feuille de route ; la "
        "réduction de l'empreinte carbone des opérations et l'allongement de la durée de vie des "
        "équipements constituent les deux leviers les plus structurants à court et moyen terme.",
        "Les perspectives pour l'exercice à venir reposent sur la consolidation des positions "
        "acquises, le lancement maîtrisé de nouvelles offres et une discipline d'exécution renforcée, "
        "condition nécessaire au rétablissement progressif du taux de marge à son niveau cible.",
    ],
    list_items=[
        "consolider les positions commerciales sur les marchés cœur",
        "rétablir progressivement le taux de marge brute",
        "réduire la dépendance aux fournisseurs critiques",
        "accélérer l'industrialisation des traitements de données",
        "renforcer la rétention des compétences rares",
    ],
    table_caption="Tableau 1 — Indicateurs clés de performance par région (en milliers d'euros)",
    table_headers=["Région", "Chiffre d'affaires", "Marge brute", "Croissance", "Effectif"],
    table_rows=[
        ["Europe", "12 480", "4 742", "+12,4 %", "184"],
        ["Amériques", "8 930", "3 215", "+8,1 %", "97"],
        ["Asie-Pacifique", "5 210", "1 980", "+15,7 %", "63"],
        ["Reste du monde", "2 140", "742", "+4,3 %", "21"],
    ],
    notes=[
        "Les montants sont exprimés en milliers d'euros et arrondis à l'unité la plus proche.",
        "Les taux de croissance sont calculés à périmètre et taux de change constants.",
        "Les effectifs sont exprimés en équivalents temps plein au 31 décembre de l'exercice.",
    ],
    column_blurb=(
        "Le contexte de marché demeure porteur sur les segments à forte valeur ajoutée, mais la "
        "concurrence s'intensifie sous l'effet de l'arrivée d'acteurs spécialisés et de la "
        "banalisation progressive des offres d'entrée de gamme. Dans ce cadre, la différenciation "
        "repose moins sur le prix que sur la qualité de service perçue, la richesse fonctionnelle et "
        "la capacité à accompagner les clients dans la durée par un dispositif de support réactif."
    ),
)
