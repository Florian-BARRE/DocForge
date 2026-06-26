---
name: warning-swallowed-on-unmount
description: React form that sets a local warning state THEN calls onSaved (which closes the form) never shows the warning
metadata:
  type: feedback
---

# Local warning/info state lost when onSaved closes the form

Pattern seen in `ChunkEditForm`: `save()` does `setWarning(res.warning)` then
`onSaved(res)`. The parent's `onSaved` (`ChunkRow`) switches the active tab away from
`edit`, which UNMOUNTS the form before its warning banner can render. The backend
warning (e.g. "reindex queued asynchronously") is silently swallowed.

**Why:** a requirement to "surface the backend warning" is not met by storing it in
the soon-to-unmount child's local state. Setting state then triggering a parent
re-render that unmounts the child discards that state.

**How to apply:** when reviewing an inline edit/save form, check whether `onSaved`
(or equivalent) closes/unmounts the form. If it does, any warning/info the form
intends to show must be LIFTED to a surface that persists after close (pass it up
through the callback to the parent/list), or the auto-close must be suppressed while
a warning is present. Same trap applies to success toasts set locally right before
an unmounting callback.
