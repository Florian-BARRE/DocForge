// ====== Code Summary ======
// A per-mount, client-only identity for each row of a reorderable list whose items carry no
// server-issued id (stack methods, chain steps) — used ONLY as a React `key` so a row's local UI
// state (its expand/collapse) follows the item through a move/add/remove instead of leaking onto
// whichever entry now sits at the same array index after a reorder. Never sent over the wire: the
// caller mutates this in lockstep with the SAME splice it applies to the real (server-shaped) array.

import { useRef } from "react";

let counter = 0;
const nextKey = () => `k${++counter}`;

export interface StableListKeys {
  /** Current key for each index, in order — pass as the React `key` of each rendered row. */
  keys: string[];
  /** Reorder the keys the same way the caller reorders the list (`splice(from,1)` + `splice(to,0,…)`). */
  move: (from: number, to: number) => void;
  /** Drop the key at `index` — call alongside removing that index from the list. */
  remove: (index: number) => void;
  /** Append a freshly generated key — call alongside appending a new item to the list. */
  add: () => void;
}

/**
 * Owns one stable id per list slot, seeded on first mount and kept in sync by the caller's own
 * move/remove/add calls. If `length` ever drifts without going through those calls (e.g. the whole
 * list was replaced by an external, not-locally-initiated change) it reconciles defensively by
 * keeping the existing prefix and padding/trimming — never throws, always length-matches.
 */
export function useStableListKeys(length: number): StableListKeys {
  const ref = useRef<string[]>(Array.from({ length }, nextKey));
  if (ref.current.length !== length) {
    ref.current = Array.from({ length }, (_, i) => ref.current[i] ?? nextKey());
  }
  return {
    keys: ref.current,
    move: (from, to) => {
      const next = [...ref.current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      ref.current = next;
    },
    remove: (index) => {
      ref.current = ref.current.filter((_, i) => i !== index);
    },
    add: () => {
      ref.current = [...ref.current, nextKey()];
    },
  };
}
