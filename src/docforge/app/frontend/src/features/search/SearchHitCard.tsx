// ====== Code Summary ======
// One search hit: its score (as a premium ember badge), the chunk text (reusing the explorer's
// truncatable ChunkText), and a small mono meta line (short document id, chunk index, token count).
// When the hit carries a block location, a "view page" action opens the hit's source page with a
// forge-orange box drawn around it — the render blob is looked up lazily (GET /documents/{id}/pages)
// on click, and degrades gracefully (text-only lightbox) when the page has no render.

import { useState } from "react";
import { getDocumentPages } from "../../api/explorer";
import { HttpError } from "../../api/http";
import type { BlockLocationModel, SearchHitModel } from "../../api/search";
import { PageBoxLightbox } from "../../components/PageBoxLightbox";
import type { OverlayBox } from "../../components/PageBoxOverlay";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { displayPage } from "../explorer/format";
import { ChunkText } from "../explorer/chunks/ChunkText";

interface SearchHitCardProps {
  hit: SearchHitModel;
}

interface HitBoxState {
  renderBlobHash: string | null;
  width: number | null;
  height: number | null;
  boxes: OverlayBox[];
  caption: string;
}

/** The hit's block locations on its primary page — from block_locations, or the single primary bbox. */
function primaryPageBoxes(hit: SearchHitModel): { page: number; boxes: OverlayBox[] } | null {
  const locations: BlockLocationModel[] = hit.block_locations ?? [];
  if (locations.length) {
    const page = hit.page ?? locations[0].page;
    const boxes = locations.filter((loc) => loc.page === page).map((loc) => ({ bbox: loc.bbox }));
    return { page, boxes: boxes.length ? boxes : [{ bbox: locations[0].bbox }] };
  }
  if (hit.page != null && hit.bbox) return { page: hit.page, boxes: [{ bbox: hit.bbox }] };
  return null;
}

export function SearchHitCard({ hit }: SearchHitCardProps) {
  const toast = useToast();
  const [hover, setHover] = useState(false);
  const [locating, setLocating] = useState(false);
  const [box, setBox] = useState<HitBoxState | null>(null);

  const located = primaryPageBoxes(hit);

  const handleViewPage = async () => {
    if (!located) return;
    setLocating(true);
    try {
      const pages = await getDocumentPages(hit.document_id);
      const page = pages.find((p) => p.page_number === located.page) ?? null;
      setBox({
        renderBlobHash: page?.render_blob_hash ?? null,
        width: page?.width ?? null,
        height: page?.height ?? null,
        boxes: located.boxes,
        caption: `Page ${displayPage(located.page)} · ${hit.filename ?? hit.document_id.slice(0, 8)}`,
      });
    } catch (error) {
      toast.error(`Could not load page — ${error instanceof HttpError ? error.message : String(error)}`);
    } finally {
      setLocating(false);
    }
  };

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.surface, border: `1px solid ${hover ? theme.color.accentLine : theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
        boxShadow: hover ? theme.shadow.md : theme.shadow.sm,
        transform: hover ? "translateY(-1px)" : "none",
        transition: "transform .15s ease, box-shadow .15s ease, border-color .15s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong
          style={{
            fontFamily: theme.font.mono, fontSize: theme.font.size.m, fontWeight: 700,
            color: theme.color.accent, background: theme.color.accentSoft,
            borderRadius: theme.radius.pill, padding: "2px 10px",
          }}
        >
          {hit.score.toFixed(4)}
        </strong>
        <span style={{ marginLeft: "auto", fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          doc {hit.document_id.slice(0, 8)} · chunk #{hit.chunk_index} · {hit.token_count} tokens
        </span>
        {located && (
          <button
            onClick={handleViewPage}
            disabled={locating}
            title="Show this hit on its source page"
            style={{
              background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
              color: theme.color.accent, cursor: locating ? "default" : "pointer", fontSize: theme.font.size.xs,
              padding: "3px 8px", whiteSpace: "nowrap",
            }}
          >
            {locating ? "loading…" : "view page"}
          </button>
        )}
      </div>
      <ChunkText text={hit.text} />

      {box && (
        <PageBoxLightbox
          renderBlobHash={box.renderBlobHash}
          width={box.width}
          height={box.height}
          boxes={box.boxes}
          caption={box.caption}
          onClose={() => setBox(null)}
        />
      )}
    </div>
  );
}
