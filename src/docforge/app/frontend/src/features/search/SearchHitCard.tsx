// ====== Code Summary ======
// One search hit: its score (as a premium ember badge, tooltip explains what it is), a human
// citation (document title/filename · page · section path — SearchHitCitation), the chunk text
// (reusing the explorer's truncatable ChunkText), and a small mono meta line (short document id,
// chunk index, token count) demoted below the text. When the hit carries a block location, a "view
// page" action opens the hit's source page with the matched block(s) boxed — the render blob is
// looked up lazily (GET /documents/{id}/pages) on click, and degrades gracefully (text-only
// lightbox) when the page has no render.

import { useState } from "react";
import { getDocumentPages } from "../../api/explorer";
import { HttpError } from "../../api/http";
import type { BlockLocationModel, SearchHitModel } from "../../api/search";
import { PageBoxLightbox } from "../../components/PageBoxLightbox";
import type { OverlayBox } from "../../components/PageBoxOverlay";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { displayPage } from "../explorer/format";
import { SearchHitCitation } from "./SearchHitCitation";
import { SearchHitText } from "./SearchHitText";

/** What the score actually is — a rank-fused signal, not a raw similarity, so it doesn't read
 *  as a plain [0,1] confidence and near-top ties are expected. */
const SCORE_TOOLTIP =
  "Fused rank-based relevance score (Reciprocal Rank Fusion across the searched semantic/lexical " +
  "targets, reranked when the collection has a reranker configured) — higher is better. Not a raw " +
  "similarity, so it is not directly comparable across different queries or target selections.";

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

/** The hit's block locations on its primary page — from block_locations, or the single primary bbox.
 *  The PRIMARY (leading) block — `hit.bbox` when present, else the first located one — is flagged
 *  `primary: true` so PageBoxOverlay draws it in full forge-orange while the chunk's other spanned
 *  blocks (same chunk, secondary context) draw muted: only ONE thing reads as "the match". */
function primaryPageBoxes(hit: SearchHitModel): { page: number; boxes: OverlayBox[] } | null {
  const locations: BlockLocationModel[] = hit.block_locations ?? [];
  if (locations.length) {
    const page = hit.page ?? locations[0].page;
    const onPage = locations.filter((loc) => loc.page === page);
    const boxed = onPage.length ? onPage : [locations[0]];
    return {
      page,
      boxes: boxed.map((loc, index) => ({
        bbox: loc.bbox,
        primary: hit.bbox ? loc.bbox.join(",") === hit.bbox.join(",") : index === 0,
      })),
    };
  }
  if (hit.page != null && hit.bbox) return { page: hit.page, boxes: [{ bbox: hit.bbox, primary: true }] };
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
      <div style={{ display: "flex", alignItems: "flex-start", gap: theme.space.s }}>
        <strong
          title={SCORE_TOOLTIP}
          style={{
            fontFamily: theme.font.mono, fontSize: theme.font.size.m, fontWeight: 700,
            color: theme.color.accentSafe, background: theme.color.accentSoft,
            borderRadius: theme.radius.pill, padding: "2px 10px", whiteSpace: "nowrap", cursor: "help",
          }}
        >
          {hit.score.toFixed(4)}
        </strong>
        <div style={{ flex: 1, minWidth: 0 }}>
          <SearchHitCitation hit={hit} />
        </div>
        {located && (
          <button
            onClick={handleViewPage}
            disabled={locating}
            title="Show this hit on its source page"
            style={{
              marginLeft: "auto", background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
              // accentStrongOnSurface, not accentSafe — this link sits on the surface-2 card
              // background where accentSafe's paper-tuned contrast falls under AA at this size.
              borderRadius: theme.radius.s, color: theme.color.accentStrongOnSurface, cursor: locating ? "default" : "pointer",
              fontSize: theme.font.size.xs, padding: "3px 8px", whiteSpace: "nowrap", flexShrink: 0,
            }}
          >
            {locating ? "loading…" : "view page"}
          </button>
        )}
      </div>
      <SearchHitText text={hit.text} />
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
        doc {hit.document_id.slice(0, 8)} · chunk #{hit.chunk_index} · {hit.token_count} tokens
      </span>

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
