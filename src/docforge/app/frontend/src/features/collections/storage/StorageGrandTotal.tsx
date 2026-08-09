// ====== Code Summary ======
// The panel's headline number — the collection's grand total footprint across all three stores,
// with the document count it was accounted over for scale.

import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";

interface StorageGrandTotalProps {
  bytes: number;
  documentCount: number;
}

export function StorageGrandTotal({ bytes, documentCount }: StorageGrandTotalProps) {
  return (
    <div>
      <div style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: t.font.weight.bold, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Total footprint
      </div>
      <div style={{ fontFamily: t.font.mono, fontWeight: t.font.weight.bold, fontSize: t.font.size.display, color: t.color.text, marginTop: 4, lineHeight: 1.1 }}>
        {formatBytes(bytes)}
      </div>
      <div style={{ color: t.color.mute, fontSize: t.font.size.s, marginTop: 4 }}>
        across {documentCount} document{documentCount === 1 ? "" : "s"}
      </div>
    </div>
  );
}
