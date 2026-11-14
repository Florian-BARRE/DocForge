// ====== Code Summary ======
// The dialog heading (`<h2>`) — one source for the display-font title every dialog used to repeat.
// `Dialog` renders it for its `title` prop; a dialog with a custom header (icon row, subtitle) uses
// it directly and hands its `id` to `Dialog`'s `labelledBy`.

import type { ReactNode } from "react";
import { theme } from "../../theme";

interface DialogTitleProps {
  id?: string;
  children: ReactNode;
}

export function DialogTitle({ id, children }: DialogTitleProps) {
  return (
    <h2 id={id} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.bold, color: theme.color.text, margin: 0 }}>
      {children}
    </h2>
  );
}
