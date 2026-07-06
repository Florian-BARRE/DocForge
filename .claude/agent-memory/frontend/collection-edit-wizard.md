---
name: collection-edit-wizard
description: CollectionWizard reused in edit mode (mode/initial props) to PATCH collections; fetch-wrapper page pattern for prefilling a dual-mode form
metadata:
  type: pattern
---

`CollectionWizard` (`src/features/collections/wizard/CollectionWizard.tsx`) is reused for both
create (POST) and edit (PATCH) rather than forked into a second component. Shape:

- Props: `mode?: "create" | "edit"` (default `"create"`), `initial?: Collection`, `collectionId?: string`.
- `wizardTypes.ts` carries the prefill/diff helpers: `draftFromCollection(collection)` maps a
  fetched `Collection` into the wizard's draft state (name/formats/maxSizeMb/fields as
  `DraftField[]`), and `removedFieldNames(original, current)` diffs by `field_name` to detect rows
  the user deleted in the schema step.
- Every step component (`StepIdentity`, `StepSchema`, `StepReview`) takes the same `mode` prop so
  copy/labels adapt (e.g. review step submit button: "Create collection" vs "Save changes"; name
  hint changes because renaming is allowed in edit mode but not implied at creation).
- The wizard itself never fetches — a thin wrapper page (`CollectionEditPage.tsx`) does
  `getCollection(id)` then renders `<CollectionWizard mode="edit" initial={...} collectionId={...} />`.
  This keeps the wizard a pure "given a draft, submit it" component regardless of mode.
- On submit in edit mode, the wizard always sends `name`, `supported_formats`,
  `max_file_size_bytes` AND the full `fields` list in the PATCH body (never a sparse diff at the
  HTTP layer) — the backend does its own field-name diffing server-side for `fields` (omitted
  field = deleted, along with its stored values); the other three scalars are just idempotent to
  resend.

**Navigation refetch gotcha (useful elsewhere)**: this app's hand-rolled router
(`shell/view.ts` + `App.tsx`) renders each view behind `{view.name === "x" && <Page/>}`
conditionals, so navigating away from a page and back always unmounts/remounts it — a page's
`useEffect(load, [id])` on mount is enough to guarantee fresh data after an edit. No manual
"invalidate and refresh" wiring was needed to show `needs_reindex` right after a PATCH.

Related: [[gen-types-constraint]] (same reason `Collection`/`UpdateCollectionRequest` in
`api/collections.ts` are hand-written mirrors of the backend Pydantic models, not generated).
