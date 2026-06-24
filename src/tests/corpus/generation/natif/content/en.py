# ====== Code Summary ======
# English content packs (contract + report). Real English prose so language detection resolves "en".

# ====== Local Project Imports ======
from .models import ContentPack

CONTRACT_EN = ContentPack(
    language="en",
    title="Master Agreement for Managed Services",
    subtitle="Reference CG-2026-EN-014 — original counterpart executed in two copies",
    searchable_phrase="termination for material breach and reversibility of data.",
    abstract=(
        "This master agreement sets out the general and particular conditions applicable to the "
        "managed services provided by the Provider to the Client, together with the service level "
        "commitments, the confidentiality obligations and the liability regime of the parties. It "
        "prevails over any prior document of equivalent scope."
    ),
    section_titles=[
        "Purpose and scope",
        "Definitions and interpretation",
        "Obligations of the Provider",
        "Obligations of the Client",
        "Financial terms and invoicing",
        "Service levels and penalties",
        "Intellectual property",
        "Confidentiality and personal data",
        "Liability and insurance",
        "Term, termination and reversibility",
        "Force majeure",
        "Governing law and dispute resolution",
    ],
    paragraphs=[
        "The parties acknowledge that performance of the services takes place within a relationship "
        "of good-faith cooperation, each undertaking to communicate in a timely manner any "
        "information likely to affect the proper delivery of the commitments entered into hereunder.",
        "The Provider shall deploy the human and technical resources required to deliver the services "
        "in accordance with industry standards, applicable regulations and the security requirements "
        "detailed in the technical annex, which forms an integral part of this agreement.",
        "The Client undertakes to provide, within reasonable time, all access rights, authorisations "
        "and documentary materials that are indispensable, it being understood that any delay "
        "attributable to the Client automatically suspends the corresponding deadlines binding the Provider.",
        "Invoicing occurs monthly in arrears on the basis of the services actually rendered; any "
        "dispute regarding an invoice must be notified in writing within thirty days, failing which "
        "the invoice shall be deemed definitively accepted by the Client without further recourse.",
        "Service level commitments are measured on a monthly basis; where a breach is recorded, fixed "
        "penalties apply without prejudice to the Client's right to claim full compensation for the "
        "direct loss duly substantiated and demonstrably caused by the breach in question.",
        "Each party retains ownership of the materials pre-existing the agreement; specific "
        "developments produced for the Client are assigned to it upon full payment of the "
        "corresponding price, subject to third-party components governed by their own licences.",
        "The parties undertake to preserve the strict confidentiality of the information exchanged "
        "and to use it solely for the purpose of performing the agreement, this obligation surviving "
        "for three years after its termination for whatever cause.",
        "The processing of personal data is carried out in compliance with the applicable regulation; "
        "the Provider acts as a processor and implements appropriate technical and organisational "
        "measures to guarantee a level of security suited to the risk presented by the processing.",
        "The liability of each party is capped, per contract year, at the total amount excluding "
        "taxes actually paid over the preceding twelve months, save in cases of gross negligence, "
        "bodily injury or breach of the confidentiality obligation set out above.",
    ],
    clauses=[
        "The purpose of this article is to specify the reciprocal rights and obligations of the "
        "parties; it shall be interpreted in the light of the preamble and the annexes, which form "
        "an indivisible whole and express the entirety of the agreement reached between the parties.",
        "In the event of a material breach by either party of its essential obligations, not remedied "
        "within fifteen days following a formal notice that has remained without effect, the other "
        "party may terminate the agreement as of right, without prejudice to any damages.",
        "Upon expiry or termination of the agreement, the Provider shall ensure the reversibility of "
        "the data in an open and documented format, and shall provide reasonable assistance with the "
        "resumption of the services by the Client or any third party it may have designated.",
        "Neither party shall be held liable for a failure resulting from an event of force majeure "
        "within the meaning of applicable case law; the prevented party shall inform the other "
        "without delay and the affected obligations shall be suspended for the duration of the event.",
    ],
    list_items=[
        "service availability measured on a monthly calendar basis",
        "the acknowledgement time for critical incidents",
        "the restoration time after a major interruption",
        "the frequency and format of steering committees",
        "the escalation procedure in case of persistent disagreement",
    ],
    table_caption="Table 1 — Service level commitments and associated penalties",
    table_headers=["Indicator", "Target", "Critical threshold", "Penalty", "Frequency"],
    table_rows=[
        ["Availability", "99.9 %", "99.0 %", "5 % of fee", "Monthly"],
        ["P1 acknowledgement", "15 min", "30 min", "2 % of fee", "Per incident"],
        ["P1 restoration", "4 h", "8 h", "5 % of fee", "Per incident"],
        ["Reporting", "D+5", "D+10", "1 % of fee", "Monthly"],
    ],
    notes=[
        "Amounts are stated exclusive of tax unless expressly indicated otherwise.",
        "Time periods are counted in business days according to the Provider's head-office calendar.",
        "No occasional tolerance shall constitute a waiver of the right to invoke a provision.",
    ],
    column_blurb=(
        "Governance of the agreement rests on a quarterly steering committee and a monthly "
        "operational committee; these bodies review the indicators, arbitrate changes of scope and "
        "record their decisions in contradictory minutes. The parties agree that the quality of the "
        "relationship prevails over the mechanical application of penalties, which remain an "
        "instrument of last resort mobilised only in the event of persistent and duly characterised drift."
    ),
)

REPORT_EN = ContentPack(
    language="en",
    title="Annual Activity and Digital Performance Report",
    subtitle="Financial year 2026 — consolidated version for the management board",
    searchable_phrase="a sustained growth trajectory despite pressure on margins.",
    abstract=(
        "This report presents a consolidated analysis of the past year's activity, places the "
        "financial and operational results in perspective against the stated objectives, and sets "
        "out recommendations intended to inform the strategic trade-offs to come."
    ),
    section_titles=[
        "Executive summary",
        "Market context and competitive environment",
        "Commercial performance by region",
        "Detailed financial analysis",
        "Digital transformation and information system",
        "Operational risk management",
        "Human resources and organisation",
        "Environmental and social commitments",
        "Outlook and action plan",
        "Conclusion and recommendations",
    ],
    paragraphs=[
        "Over the year, the company confirmed a sustained growth trajectory despite an uncertain "
        "macroeconomic environment marked by volatile input costs and increased pressure on margins, "
        "which was partly absorbed by productivity gains across the main operating units.",
        "Commercial momentum was particularly strong in the European markets, where the roll-out of "
        "a packaged offering accelerated the sales cycle and significantly improved the conversion "
        "rate of qualified prospects into recurring customers with multi-year commitments.",
        "From a financial standpoint, gross margin grows in absolute value while the margin rate "
        "contracts slightly under the effect of a deliberately aggressive pricing policy on the "
        "acquisition segments deemed strategic for the conquest of additional market share.",
        "Digital transformation translated into the modernisation of the technical foundation, the "
        "rationalisation of the application portfolio and the industrialisation of the data "
        "processing chains, now governed by quality and freshness indicators measured continuously.",
        "The operational risk map was updated; the main areas of exposure concern the dependence on "
        "a limited number of critical suppliers, cybersecurity and regulatory compliance, for which "
        "remediation plans have been initiated and are tracked at the operational committee.",
        "The organisation continued to build capability with a sustained training effort, a "
        "strengthening of cross-functional functions and particular attention paid to the retention "
        "of scarce profiles whose contribution is decisive for the success of the projects.",
        "Environmental commitments are progressing in line with the roadmap; reducing the carbon "
        "footprint of operations and extending the service life of equipment are the two most "
        "structuring levers in the short and medium term for the group as a whole.",
        "The outlook for the coming year rests on consolidating the positions acquired, the "
        "controlled launch of new offerings and reinforced execution discipline, a necessary "
        "condition for the gradual restoration of the margin rate to its target level.",
    ],
    list_items=[
        "consolidate commercial positions in the core markets",
        "gradually restore the gross margin rate",
        "reduce dependence on critical suppliers",
        "accelerate the industrialisation of data processing",
        "strengthen the retention of scarce skills",
    ],
    table_caption="Table 1 — Key performance indicators by region (in thousands of euros)",
    table_headers=["Region", "Revenue", "Gross margin", "Growth", "Headcount"],
    table_rows=[
        ["Europe", "12,480", "4,742", "+12.4 %", "184"],
        ["Americas", "8,930", "3,215", "+8.1 %", "97"],
        ["Asia-Pacific", "5,210", "1,980", "+15.7 %", "63"],
        ["Rest of world", "2,140", "742", "+4.3 %", "21"],
    ],
    notes=[
        "Amounts are expressed in thousands of euros and rounded to the nearest unit.",
        "Growth rates are calculated at constant scope and exchange rates.",
        "Headcount is expressed in full-time equivalents as at 31 December of the year.",
    ],
    column_blurb=(
        "The market context remains favourable in the high-value-added segments, but competition is "
        "intensifying under the effect of specialised entrants and the gradual commoditisation of "
        "entry-level offerings. In this context, differentiation rests less on price than on "
        "perceived service quality, functional richness and the ability to support customers over "
        "time through a responsive support arrangement and a clear, well-documented service catalogue."
    ),
)
