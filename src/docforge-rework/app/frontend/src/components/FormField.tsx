// ====== Code Summary ======
// A labeled form row — name, optional hint/description, and the control itself. The shared
// vertical form layout for wizard steps and dialogs outside the pipeline studio.

import type { ReactNode } from "react";
import { theme } from "../theme";

interface FormFieldProps {
  label: string;
  hint?: string;
  children: ReactNode;
}

export function FormField({ label, hint, children }: FormFieldProps) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: theme.font.size.s }}>
      <span style={{ color: theme.color.dim, fontWeight: theme.font.weight.semibold }}>{label}</span>
      {children}
      {hint && <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{hint}</span>}
    </label>
  );
}
