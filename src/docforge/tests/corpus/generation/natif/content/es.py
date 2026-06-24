# ====== Code Summary ======
# Spanish content packs (contract + report). Real Spanish prose so language detection resolves "es".

# ====== Local Project Imports ======
from .models import ContentPack

CONTRACT_ES = ContentPack(
    language="es",
    title="Contrato marco de prestación de servicios gestionados",
    subtitle="Referencia CG-2026-ES-014 — ejemplar original firmado por duplicado",
    searchable_phrase="resolución por incumplimiento grave y reversibilidad de los datos.",
    abstract=(
        "El presente contrato marco establece las condiciones generales y particulares aplicables a "
        "los servicios gestionados prestados por el Proveedor al Cliente, así como los compromisos "
        "de nivel de servicio, las obligaciones de confidencialidad y el régimen de responsabilidad "
        "de las partes. Prevalece sobre cualquier documento anterior de alcance equivalente."
    ),
    section_titles=[
        "Objeto y alcance",
        "Definiciones e interpretación",
        "Obligaciones del Proveedor",
        "Obligaciones del Cliente",
        "Condiciones económicas y facturación",
        "Niveles de servicio y penalizaciones",
        "Propiedad intelectual",
        "Confidencialidad y datos personales",
        "Responsabilidad y seguros",
        "Duración, resolución y reversibilidad",
        "Fuerza mayor",
        "Ley aplicable y resolución de controversias",
    ],
    paragraphs=[
        "Las partes reconocen que la ejecución de los servicios se inscribe en una relación de "
        "cooperación leal, obligándose cada una a comunicar oportunamente cualquier información que "
        "pueda afectar a la correcta realización de los compromisos asumidos en virtud del presente contrato.",
        "El Proveedor pondrá los medios humanos y técnicos necesarios para la prestación de los "
        "servicios conforme a las reglas del arte, las normas vigentes y los requisitos de seguridad "
        "detallados en el anexo técnico, el cual forma parte integrante del presente contrato.",
        "El Cliente se compromete a facilitar, en plazos razonables, todos los accesos, "
        "autorizaciones y elementos documentales indispensables, entendiéndose que todo retraso "
        "imputable al Cliente suspende de pleno derecho los plazos correlativos exigibles al Proveedor.",
        "La facturación se realiza mensualmente a mes vencido sobre la base de los servicios "
        "efectivamente prestados; cualquier reclamación sobre una factura deberá notificarse por "
        "escrito en un plazo de treinta días, transcurrido el cual la factura se entenderá aceptada.",
        "Los compromisos de nivel de servicio se miden con periodicidad mensual; en caso de "
        "incumplimiento constatado, se aplican penalizaciones a tanto alzado sin perjuicio del "
        "derecho del Cliente a reclamar la reparación íntegra del perjuicio directo debidamente acreditado.",
        "Cada parte conserva la titularidad de los elementos anteriores al contrato; los desarrollos "
        "específicos realizados por cuenta del Cliente se le ceden a partir del pago íntegro del "
        "precio correspondiente, sin perjuicio de los componentes de terceros sujetos a sus licencias.",
        "Las partes se comprometen a preservar la estricta confidencialidad de la información "
        "intercambiada y a utilizarla únicamente con fines de ejecución del contrato, subsistiendo "
        "esta obligación durante tres años después de su terminación, cualquiera que sea su causa.",
        "El tratamiento de datos de carácter personal se efectúa respetando el reglamento aplicable; "
        "el Proveedor actúa como encargado del tratamiento y aplica medidas técnicas y organizativas "
        "apropiadas para garantizar un nivel de seguridad adecuado al riesgo del tratamiento.",
        "La responsabilidad de cada parte se limita, por año contractual, al importe total sin "
        "impuestos efectivamente abonado durante los doce últimos meses, salvo en caso de culpa "
        "grave, daño corporal o incumplimiento de la obligación de confidencialidad antes señalada.",
    ],
    clauses=[
        "El presente artículo tiene por objeto precisar los derechos y obligaciones recíprocos de "
        "las partes; se interpreta a la luz del preámbulo y de los anexos, que forman un todo "
        "indivisible y expresan la integridad del acuerdo alcanzado entre las partes contratantes.",
        "En caso de incumplimiento grave por una de las partes de sus obligaciones esenciales, no "
        "subsanado en un plazo de quince días tras un requerimiento que haya resultado infructuoso, "
        "la otra parte podrá resolver el contrato de pleno derecho, sin perjuicio de cualesquiera daños.",
        "A la expiración o resolución del contrato, el Proveedor garantiza la reversibilidad de los "
        "datos en un formato abierto y documentado, y presta una asistencia razonable para la "
        "reanudación de los servicios por el Cliente o por cualquier tercero que este haya designado.",
        "Ninguna de las partes será responsable de un incumplimiento derivado de un caso de fuerza "
        "mayor en el sentido de la jurisprudencia aplicable; la parte impedida informará a la otra "
        "sin demora y las obligaciones afectadas quedarán suspendidas mientras dure el acontecimiento.",
    ],
    list_items=[
        "la disponibilidad del servicio medida con periodicidad mensual",
        "el plazo de toma en consideración de los incidentes críticos",
        "el plazo de restablecimiento tras una interrupción mayor",
        "la frecuencia y el formato de los comités de seguimiento",
        "las modalidades de escalado en caso de desacuerdo persistente",
    ],
    table_caption="Tabla 1 — Compromisos de nivel de servicio y penalizaciones asociadas",
    table_headers=["Indicador", "Objetivo", "Umbral crítico", "Penalización", "Periodicidad"],
    table_rows=[
        ["Disponibilidad", "99,9 %", "99,0 %", "5 % de la cuota", "Mensual"],
        ["Atención P1", "15 min", "30 min", "2 % de la cuota", "Por incidente"],
        ["Restablecimiento P1", "4 h", "8 h", "5 % de la cuota", "Por incidente"],
        ["Informes", "D+5", "D+10", "1 % de la cuota", "Mensual"],
    ],
    notes=[
        "Los importes se entienden sin impuestos, salvo mención expresa en contrario.",
        "Los plazos se computan en días hábiles según el calendario de la sede del Proveedor.",
        "Ninguna tolerancia puntual constituirá renuncia a invocar una estipulación del contrato.",
    ],
    column_blurb=(
        "La gobernanza del contrato se basa en un comité de seguimiento trimestral y un comité "
        "operativo mensual; estos órganos examinan los indicadores, deciden sobre las evoluciones de "
        "alcance y dejan constancia de sus decisiones en actas contradictorias. Las partes convienen "
        "en que la calidad de la relación prevalece sobre la aplicación mecánica de las "
        "penalizaciones, que siguen siendo un instrumento de último recurso ante una deriva persistente."
    ),
)

REPORT_ES = ContentPack(
    language="es",
    title="Informe anual de actividad y desempeño digital",
    subtitle="Ejercicio 2026 — versión consolidada para el comité de dirección",
    searchable_phrase="una trayectoria de crecimiento sostenido pese a la presión sobre los márgenes.",
    abstract=(
        "Este informe presenta un análisis consolidado de la actividad del ejercicio transcurrido, "
        "pone en perspectiva los resultados financieros y operativos frente a los objetivos fijados "
        "y formula recomendaciones destinadas a orientar las decisiones estratégicas futuras."
    ),
    section_titles=[
        "Resumen ejecutivo",
        "Contexto de mercado y entorno competitivo",
        "Desempeño comercial por región",
        "Análisis financiero detallado",
        "Transformación digital y sistema de información",
        "Gestión de riesgos operativos",
        "Recursos humanos y organización",
        "Compromisos ambientales y sociales",
        "Perspectivas y plan de acción",
        "Conclusión y recomendaciones",
    ],
    paragraphs=[
        "Durante el ejercicio, la empresa confirmó una trayectoria de crecimiento sostenido pese a "
        "un entorno macroeconómico incierto, marcado por la volatilidad de los costes de los "
        "insumos y una mayor presión sobre los márgenes, absorbida en parte por las ganancias de productividad.",
        "La dinámica comercial fue especialmente vigorosa en los mercados europeos, donde el "
        "despliegue de una oferta empaquetada permitió acelerar el ciclo de venta y mejorar de forma "
        "significativa la tasa de conversión de los clientes potenciales cualificados en clientes recurrentes.",
        "En el plano financiero, el margen bruto progresa en valor absoluto mientras que la tasa de "
        "margen se contrae ligeramente por efecto de una política de precios deliberadamente "
        "agresiva en los segmentos de captación considerados estratégicos para conquistar cuota de mercado.",
        "La transformación digital se tradujo en la modernización de la base técnica, la "
        "racionalización del catálogo de aplicaciones y la industrialización de las cadenas de "
        "tratamiento de datos, gobernadas ahora por indicadores de calidad y frescura medidos de forma continua.",
        "El mapa de riesgos operativos fue actualizado; los principales focos de exposición se "
        "refieren a la dependencia de un número reducido de proveedores críticos, la ciberseguridad "
        "y el cumplimiento normativo, para los que se han puesto en marcha planes de remediación.",
        "La organización prosiguió su desarrollo de capacidades con un esfuerzo sostenido de "
        "formación, un refuerzo de las funciones transversales y una atención particular a la "
        "retención de los perfiles escasos cuya contribución es determinante para el éxito de los proyectos.",
        "Los compromisos ambientales avanzan conforme a la hoja de ruta; la reducción de la huella "
        "de carbono de las operaciones y la prolongación de la vida útil de los equipos constituyen "
        "las dos palancas más estructurantes a corto y medio plazo para el conjunto del grupo.",
        "Las perspectivas para el próximo ejercicio se basan en la consolidación de las posiciones "
        "adquiridas, el lanzamiento controlado de nuevas ofertas y una disciplina de ejecución "
        "reforzada, condición necesaria para el restablecimiento progresivo de la tasa de margen.",
    ],
    list_items=[
        "consolidar las posiciones comerciales en los mercados principales",
        "restablecer progresivamente la tasa de margen bruto",
        "reducir la dependencia de los proveedores críticos",
        "acelerar la industrialización del tratamiento de datos",
        "reforzar la retención de las competencias escasas",
    ],
    table_caption="Tabla 1 — Indicadores clave de desempeño por región (en miles de euros)",
    table_headers=["Región", "Ingresos", "Margen bruto", "Crecimiento", "Plantilla"],
    table_rows=[
        ["Europa", "12 480", "4 742", "+12,4 %", "184"],
        ["Américas", "8 930", "3 215", "+8,1 %", "97"],
        ["Asia-Pacífico", "5 210", "1 980", "+15,7 %", "63"],
        ["Resto del mundo", "2 140", "742", "+4,3 %", "21"],
    ],
    notes=[
        "Los importes se expresan en miles de euros y se redondean a la unidad más próxima.",
        "Las tasas de crecimiento se calculan a perímetro y tipos de cambio constantes.",
        "La plantilla se expresa en equivalentes a tiempo completo a 31 de diciembre del ejercicio.",
    ],
    column_blurb=(
        "El contexto de mercado sigue siendo favorable en los segmentos de alto valor añadido, pero "
        "la competencia se intensifica por efecto de la llegada de actores especializados y la "
        "progresiva banalización de las ofertas de gama de entrada. En este marco, la diferenciación "
        "se basa menos en el precio que en la calidad de servicio percibida, la riqueza funcional y "
        "la capacidad de acompañar a los clientes a lo largo del tiempo mediante un soporte reactivo."
    ),
)
