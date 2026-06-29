---
name: s5b-metagen-ui
description: S5b LLM-generated metadata UI wiring — all files modified/created, type overlay approach, warning-banner pattern
metadata:
  type: project
---

## What was implemented (S5b metagen UI, 2026-06-28)

### Type overlays (api/types.ts — no gen:types needed)
- `MetaField` extended with `origin?: 'user' | 'system' | 'generated' | null`
- `ConfigNode.kind` union extended with `'object_list'`
- `ConfigNode.item_schema?: ConfigNode[] | null` added
- `MetagenPreviewRequest` / `MetagenPreviewResponse` hand-written interfaces

### New files
- `components/ui/pickers/ObjectListPicker.tsx` — generic repeater for kind="object_list"
- `components/inspect/MetagenPreview.tsx` — dry-run preview: field picker + sample-text or chunk-picker → previewMetagen → value + cost/token

### Modified files
- `api/client.ts` — `previewMetagen(collectionId, body)` added
- `components/ui/FieldInput.tsx` — `type === 'text'` branch renders `<textarea>` (for prompt fields with `ui: "text"` hint)
- `components/ui/RecursiveFieldRenderer.tsx` — `object_list` dispatch → ObjectListPicker
- `components/pipeline/panels/IngestionConditionsPanel.tsx` — Gen. checkbox column, tag-llm pill, no-prompt badge
- `components/pipeline/stages.ts` — s5b added between s5 and s6 (optional: true)
- `components/pipeline/panels/StageConfigPanel.tsx` — s5b section: warning-banner + MetagenPreview
- `global.css` — .warning-banner (amber), .meta-tag-llm, .meta-tag-no-prompt, .object-list-picker-*, .metagen-preview-*

**Why:** `gen:types` needs a running backend, so all new backend types live as overlay intersections in types.ts; generated.ts is never hand-edited.

**How to apply:** When new backend fields appear after a backend deploy, update types.ts overlays → then run `npm run gen:types` once the backend is live and remove the overlays.
