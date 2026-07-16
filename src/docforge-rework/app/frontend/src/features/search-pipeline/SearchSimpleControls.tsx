// ====== Code Summary ======
// The non-technical top section of the search editor: a static "fusion is always on" summary row
// plus the one control a non-technical user actually needs — the Reranking on/off Switch. Every
// other knob (candidate_multiplier, candidate_floor, rescore_pool_size…) lives one level down, in
// the "Advanced" rail — see SearchPipelineEditor.

import { Switch } from "../../components/Switch";
import { theme } from "../../theme";
import { SearchControlRow } from "./SearchControlRow";

interface SearchSimpleControlsProps {
  rerankEnabled: boolean;
  onToggleRerank: (next: boolean) => void;
  disabled?: boolean;
}

export function SearchSimpleControls({ rerankEnabled, onToggleRerank, disabled }: SearchSimpleControlsProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <SearchControlRow
        title="Recherche hybride (fusion)"
        description="Lexical + sémantique, fusionnés (RRF)."
        control={<span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>toujours activé</span>}
      />
      <SearchControlRow
        title="Reranking"
        description="Re-note les meilleurs résultats avec un cross-encoder (BGE)."
        control={<Switch checked={rerankEnabled} onChange={onToggleRerank} disabled={disabled} />}
      />
    </div>
  );
}
