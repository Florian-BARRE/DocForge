// ====== Code Summary ======
// Shared dot-path read/write utilities for nested config value objects.
// Extracted from DynamicFieldsGroup so RecursiveFieldRenderer and any future
// nested-config component can reuse the same logic without re-implementing it.

/**
 * Read a value at a dot-delimited path from a nested object.
 *
 * Args:
 *   root: The top-level object to read from.
 *   path: Dot-delimited path string, e.g. "gate.min_score". Empty string
 *         returns the root itself.
 *
 * Returns:
 *   unknown: The value found at the path, or undefined if any segment is missing.
 */
export function readPath(root: Record<string, unknown>, path: string): unknown {
  if (!path) return root
  const keys = path.split('.')
  let cursor: unknown = root
  for (const k of keys) {
    if (cursor && typeof cursor === 'object') {
      cursor = (cursor as Record<string, unknown>)[k]
    } else {
      return undefined
    }
  }
  return cursor
}

/**
 * Produce a new object with the value at a dot-delimited path updated.
 * All ancestor objects are shallow-cloned; nothing else is mutated.
 *
 * Args:
 *   root: The top-level object to derive from.
 *   path: Dot-delimited path string, e.g. "gate.min_score". Must be non-empty.
 *   value: The new value to write at that path.
 *
 * Returns:
 *   Record<string, unknown>: A new object with the path updated.
 */
export function setPath(
  root: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const keys = path.split('.')
  const next = { ...root }
  let cursor: Record<string, unknown> = next
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    cursor[k] = { ...(cursor[k] as Record<string, unknown> ?? {}) }
    cursor = cursor[k] as Record<string, unknown>
  }
  cursor[keys[keys.length - 1]] = value
  return next
}
