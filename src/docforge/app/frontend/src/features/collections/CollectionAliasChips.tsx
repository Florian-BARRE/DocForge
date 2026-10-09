// ====== Code Summary ======
// A collection's alias names as small mono chips in muted ink (never orange — an alias is a stable
// name at rest, not the one active thing). Each chip is a link to the collection's Settings ▸ Aliases
// sub-tab; its click stops propagation so it never fires an enclosing card's own navigate. Renders
// nothing for an un-aliased collection.

import type { MouseEvent } from "react";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";

const MAX_ALIASES_SHOWN = 3;

interface CollectionAliasChipsProps {
  collectionId: string;
  aliases: string[];
  onNavigate: Navigate;
}

export function CollectionAliasChips({ collectionId, aliases, onNavigate }: CollectionAliasChipsProps) {
  if (aliases.length === 0) return null;

  const shown = aliases.slice(0, MAX_ALIASES_SHOWN);
  const hidden = aliases.slice(MAX_ALIASES_SHOWN);
  const open = (event: MouseEvent) => {
    event.stopPropagation();
    onNavigate({ name: "collection-settings", collectionId, section: "aliases" });
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      {shown.map((alias) => (
        <button
          key={alias}
          type="button"
          onClick={open}
          title={`Alias "${alias}" — manage in Settings ▸ Aliases`}
          aria-label={`Alias ${alias}`}
          style={{
            fontFamily: t.font.mono, fontSize: t.font.size.xs, fontWeight: t.font.weight.medium,
            color: t.color.mute, background: "transparent", border: `1px solid ${t.color.line}`,
            borderRadius: t.radius.s, padding: "0 5px", lineHeight: "16px", cursor: "pointer",
          }}
        >
          {alias}
        </button>
      ))}
      {hidden.length > 0 && (
        <button
          type="button"
          onClick={open}
          title={hidden.join(", ")}
          style={{
            fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute,
            background: "transparent", border: "none", padding: 0, cursor: "pointer",
          }}
        >
          +{hidden.length}
        </button>
      )}
    </span>
  );
}
