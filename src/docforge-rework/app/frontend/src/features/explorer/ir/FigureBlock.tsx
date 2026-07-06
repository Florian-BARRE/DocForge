// ====== Code Summary ======
// A FIGURE block's crop image plus every enrichment recorded for it (classification, OCR, VLM…).

import { blobUrl, type IREnrichment, type IRFigure } from "../../../api/explorer";
import { theme } from "../../../theme";
import { EnrichmentItem } from "./EnrichmentItem";

interface FigureBlockProps {
  figure: IRFigure | undefined;
  enrichments: IREnrichment[];
}

export function FigureBlock({ figure, enrichments }: FigureBlockProps) {
  return (
    <div style={{ display: "flex", gap: theme.space.m, flexWrap: "wrap" }}>
      {figure?.crop_blob_hash ? (
        <img
          src={blobUrl(figure.crop_blob_hash)}
          loading="lazy"
          alt="Figure crop"
          style={{ maxWidth: 220, maxHeight: 220, borderRadius: theme.radius.s, border: `1px solid ${theme.color.line}` }}
        />
      ) : (
        <div
          style={{
            width: 120, height: 90, display: "flex", alignItems: "center", justifyContent: "center",
            background: theme.color.card, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
            color: theme.color.dim, fontSize: theme.font.size.xs,
          }}
        >
          no crop
        </div>
      )}
      {enrichments.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 200 }}>
          {enrichments.map((e) => <EnrichmentItem key={e.id} enrichment={e} />)}
        </div>
      )}
    </div>
  );
}
