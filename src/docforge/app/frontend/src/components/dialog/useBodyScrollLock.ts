// ====== Code Summary ======
// Body scroll lock for modal dialogs — while at least one dialog is mounted, the page behind the
// overlay stops scrolling. Reference-counted so stacked dialogs (a confirm opened over the command
// palette, say) neither unlock early nor restore a stale value: the original `overflow` is captured
// by the first lock and put back by the last unlock.

// ====== Third-Party Library Imports ======
import { useEffect } from "react";

let lockCount = 0;
let savedOverflow = "";

export function useBodyScrollLock(): void {
  useEffect(() => {
    if (lockCount === 0) {
      savedOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    lockCount += 1;
    return () => {
      lockCount -= 1;
      if (lockCount === 0) document.body.style.overflow = savedOverflow;
    };
  }, []);
}
