// ====== Code Summary ======
// A FIGURE block's crop image plus every enrichment recorded for it (classification, OCR, VLM…).

import { type IREnrichment, type IRFigure } from "../../../api/explorer";
import { BlobImage } from "../../../components/BlobImage";
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
        <BlobImage
          hash={figure.crop_blob_hash}
          alt="Figure crop"
          style={{ maxWidth: 220, maxHeight: 220, borderRadius: theme.radius.m, border: `1px solid ${theme.color.line}` }}
        />
      ) : (
        <div
          style={{
            width: 120, height: 90, display: "flex", alignItems: "center", justifyContent: "center",
            background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
            color: theme.color.dim, fontSize: theme.font.size.xs,
          }}
        >
          no crop
        </div>
      )}
      {enrichments.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1, minWidth: 200 }}>
          {enrichments.map((e) => <EnrichmentItem key={e.id} enrichment={e} />)}
        </div>
      )}
    </div>
  );
}
