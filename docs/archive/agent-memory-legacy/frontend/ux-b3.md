---
name: ux-b3
description: UX consistency batch 3 — ConfirmDialog primitive, window.confirm replaced everywhere, Spinner/EmptyState standardized across DocumentsTab/ChunkBrowser/PagesTab/DocDetailView/NavRail/SearchTab
metadata:
  type: project
---

## ConfirmDialog primitive

`components/ui/ConfirmDialog.tsx` — wraps Modal, props:
`{ open, title, message, confirmLabel?, cancelLabel?, danger?, onConfirm, onCancel }`

- `danger=true` → confirm button gets `btn btn-danger` (red on hover per global.css convention)
- `autoFocus` on confirm button → Enter confirms, Esc handled by Modal → calls onCancel
- maxWidth=400

**Why:** `window.confirm()` was jarring OS chrome in a polished dark app; ConfirmDialog is styled, keyboard-friendly, and consistent.

## window.confirm replaced

Zero calls remain. The single site was:
- `DocRow.tsx` line 134 (formerly `handleDelete`) → now sets `deleteConfirmOpen` state + renders `<ConfirmDialog danger confirmLabel="Delete">`

## Loading/empty standardization rules

All loading states use `<Spinner size={14|16}>` + a `<span style color=var(--text-muted)>` label.
All empty states use `<EmptyState>` from `components/ui/primitives/EmptyState`.
Never use `<span className="spin">⟳</span>` inline or bare div text.

Files standardized (batch 3):
- `DocumentsTab.tsx` — loading list, empty list
- `DocDetailView.tsx` — loading document
- `ChunkBrowser.tsx` — loading chunks, empty filter, status-pending Spinner, status-other EmptyState
- `PagesTab.tsx` — loading pages, loading page detail, status-pending Spinner, status-other EmptyState, zero-pages EmptyState
- `SearchTab.tsx` — no-results empty state (replaced hand-rolled div.empty)
- `NavRail.tsx` — no-collections empty state (replaced bare `<li>` text)

**How to apply:** any new list/panel that fetches data must use Spinner while loading and EmptyState when empty. No bare text divs, no `⟳` spin character.
