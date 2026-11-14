// ====== Code Summary ======
// The actual ⌘K dialog — query input + grouped, fuzzy-filtered, keyboard-navigable results. Mounted
// fresh every time the palette opens (see CommandPalette.tsx), the same "conditionally-mounted
// dialog" idiom as DeleteCollectionDialog.tsx: every hook here runs unconditionally on every render
// of THIS component, and the component never returns early, so rules-of-hooks holds trivially.
// Overlay / focus trap / Escape-to-close / focus-restore-on-close are the shared `Dialog` shell (its
// `useFocusTrap` moves focus to the input, the panel's only focusable descendant, on mount).

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { listCollections, type Collection } from "../../api/collections";
import { Dialog } from "../../components/dialog/Dialog";
import { theme as t } from "../../theme";
import type { Navigate, View } from "../view";
import { buildActionItems, buildCollectionItems, buildGoToItems, filterItems, type CommandItem } from "./commandItems";
import { CommandPaletteResultList, type CommandPaletteGroup } from "./CommandPaletteResultList";

const DEFAULT_COLLECTIONS_SHOWN = 6;
const FILTERED_COLLECTIONS_SHOWN = 8;

interface CommandPaletteDialogProps {
  view: View;
  onNavigate: Navigate;
  onClose: () => void;
}

export function CommandPaletteDialog({ view, onNavigate, onClose }: CommandPaletteDialogProps) {
  const [query, setQuery] = useState("");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCollections()
      .then((loaded) => {
        if (!cancelled) setCollections(loaded);
      })
      .catch(() => {
        if (!cancelled) setCollections([]);
      })
      .finally(() => {
        if (!cancelled) setCollectionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const trimmedQuery = query.trim();
  const groups: CommandPaletteGroup[] = useMemo(() => {
    const collectionItems = filterItems(buildCollectionItems(collections, onNavigate), query)
      .slice(0, trimmedQuery ? FILTERED_COLLECTIONS_SHOWN : DEFAULT_COLLECTIONS_SHOWN);
    const goToItems = filterItems(buildGoToItems(view, onNavigate), query);
    const actionItems = filterItems(buildActionItems(view, onNavigate), query);
    return [
      { label: "Collections", items: collectionItems, loading: collectionsLoading },
      { label: "Go to", items: goToItems },
      { label: "Actions", items: actionItems },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collections, collectionsLoading, query, view, onNavigate]);

  const flatItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  // Keep the selection valid whenever the visible result set changes underneath it (a fresh
  // keystroke, or the async collections list arriving) — never leave a stale/absent id "selected".
  useEffect(() => {
    if (flatItems.length === 0) {
      setSelectedId(null);
    } else if (!flatItems.some((i) => i.id === selectedId)) {
      setSelectedId(flatItems[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flatItems]);

  const activate = (item: CommandItem) => {
    item.run();
    onClose();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (flatItems.length === 0) return;
    const currentIndex = flatItems.findIndex((i) => i.id === selectedId);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedId(flatItems[(currentIndex + 1 + flatItems.length) % flatItems.length].id);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedId(flatItems[(currentIndex - 1 + flatItems.length) % flatItems.length].id);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = flatItems[currentIndex === -1 ? 0 : currentIndex];
      if (item) activate(item);
    }
  };

  return (
    <Dialog
      onClose={onClose}
      ariaLabel="Command palette"
      placement="top"
      layer={600}
      maxWidth={560}
      panelStyle={{ padding: 0, gap: 0, overflow: "hidden" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: t.space.s, padding: t.space.m, borderBottom: `1px solid ${t.color.line}` }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Jump to a collection, a page, or an action…"
          aria-label="Command palette search"
          role="combobox"
          aria-expanded="true"
          aria-controls="command-palette-results"
          aria-activedescendant={selectedId ?? undefined}
          autoComplete="off"
          style={{
            flex: 1, background: "transparent", border: "none", outline: "none", color: t.color.text,
            fontFamily: t.font.family, fontSize: t.font.size.l,
          }}
        />
        <span
          style={{
            fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute,
            border: `1px solid ${t.color.line}`, borderRadius: t.radius.s, padding: "1px 6px",
          }}
        >
          Esc
        </span>
      </div>
      <div id="command-palette-results">
        <CommandPaletteResultList groups={groups} selectedId={selectedId} onHoverSelect={setSelectedId} onActivate={activate} />
      </div>
    </Dialog>
  );
}
