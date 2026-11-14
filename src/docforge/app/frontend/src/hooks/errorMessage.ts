// ====== Code Summary ======
// Shared error-to-string helper: the `e instanceof Error ? e.message : String(e)` idiom every
// fetch/poll hook repeated inline before R-29.

/** The display string of a thrown value: an Error's message, otherwise its String() form. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
