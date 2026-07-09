// ====== Code Summary ======
// A chunk's structural role as a small badge — explains WHY a chunk defaults on/off (only `body`
// is searchable by default; header/footer, table-of-contents and boilerplate chunks default off).

import { Chip, type ChipTone } from "../../../components/Chip";
import type { ChunkRole } from "../../../api/explorer";

const TONE_BY_ROLE: Record<ChunkRole, ChipTone> = {
  body: "ok",
  header_footer: "dim",
  toc: "dim",
  boilerplate: "dim",
};

const LABEL_BY_ROLE: Record<ChunkRole, string> = {
  body: "body",
  header_footer: "header/footer",
  toc: "toc",
  boilerplate: "boilerplate",
};

export function ChunkRoleBadge({ role }: { role: ChunkRole }) {
  return (
    <Chip
      tone={TONE_BY_ROLE[role]}
      title={role === "body" ? "Body content — searchable by default" : "Structural furniture — hidden from search by default"}
    >
      {LABEL_BY_ROLE[role]}
    </Chip>
  );
}
