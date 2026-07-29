// ====== Code Summary ======
// Pure ISO-conversion helpers for the expiration picker — kept side-effect-free (no Date.now()
// inside component render) so CreateKeyForm computes the absolute timestamp once, at submit time.

/** The picker's value model — "never" (null on the wire), a day-count preset, or a custom date. */
export type ExpiryChoice =
  | { kind: "never" }
  | { kind: "preset"; days: number }
  | { kind: "custom"; date: string };

/**
 * Resolve an `ExpiryChoice` into the absolute ISO instant the backend expects.
 *
 * @param choice - The picker's current value.
 * @param now - The reference instant presets count forward from (injectable for tests).
 * @returns An ISO-8601 instant, or `null` for "never expires" / an empty custom date.
 */
export function expiryToIso(choice: ExpiryChoice, now: Date = new Date()): string | null {
  if (choice.kind === "never") return null;

  if (choice.kind === "preset") {
    const resolved = new Date(now);
    resolved.setDate(resolved.getDate() + choice.days);
    return resolved.toISOString();
  }

  if (!choice.date) return null;
  // End-of-day UTC on the chosen calendar date, so picking "today" still yields a future expiry.
  return new Date(`${choice.date}T23:59:59.999Z`).toISOString();
}

/**
 * Map a stored `expires_at` back into a picker value — used to pre-fill the rotate form.
 *
 * @param iso - The key's current `expires_at`, or `null` for "never expires".
 * @returns `{ kind: "never" }` for `null`, otherwise a `"custom"` choice on that calendar date.
 */
export function isoToExpiryChoice(iso: string | null): ExpiryChoice {
  if (!iso) return { kind: "never" };
  return { kind: "custom", date: iso.slice(0, 10) };
}
