---
name: object-list-picker
description: ObjectListPicker — generic repeater for ConfigNode kind="object_list"; last-segment key extraction mirrors ChainLadder
metadata:
  type: reference
---

## ObjectListPicker pattern

`components/ui/pickers/ObjectListPicker.tsx`

### Design
- Triggered by `kind === 'object_list'` dispatch in RecursiveFieldRenderer (same level as chain/provider_union)
- Receives `node.item_schema: ConfigNode[]` describing one item's fields
- Item-local read/write: extract last path segment from abs path (e.g. `patch.pipeline.metagen.targets[].field` → `field`), look up / mutate in flat item object
- This is the same approach as `ChainLadder.writeEntryParam` — intentional consistency
- Uses the `renderChildren` render-prop from RecursiveFieldRenderer to render item fields — no duplicate field logic

### Key constraint
GENERIC — never hardcode field names, model names, or domain semantics inside ObjectListPicker.
The `renderChildren` prop handles all field rendering; the picker only manages the array.

### Add entry defaults
`blankItem(itemSchema)` collects nodes with non-null defaults into a flat object.
