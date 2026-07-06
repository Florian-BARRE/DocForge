# Frontend Agent — Memory Index

- [Hand-rolled shell routing](shell-hand-rolled-routing.md) — View union + useState in App.tsx, no router dep; onNavigate prop pattern
- [Backend enum gotchas](backend-enum-gotchas.md) — FieldType has no "enum" value; JobStatus is "pending" not "queued" (jobs.ts fixed)
- [CollectionModel created_at gap](collection-model-created-at-gap.md) — API never exposes created_at despite DB column; hand off to backend agent before showing it in the UI
- [Empty group blob validates](empty-group-blob-validates.md) — `{nodes:[]}` is NOT a 422 repro (validator skips checks with zero children); use an unbound required slot instead
