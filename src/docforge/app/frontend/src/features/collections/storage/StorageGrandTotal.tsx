// ====== Code Summary ======
// The panel's headline number — the collection's grand total footprint across all three stores.

import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";

export function StorageGrandTotal({ bytes }: { bytes: number }) {
  return (
    <div>
      <div style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: t.font.weight.bold, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Total footprint
      </div>
      <div style={{ fontFamily: t.font.mono, fontWeight: t.font.weight.bold, fontSize: t.font.size.display, color: t.color.text, marginTop: 4, lineHeight: 1.1 }}>
        {formatBytes(bytes)}
      </div>
    </div>
  );
}
