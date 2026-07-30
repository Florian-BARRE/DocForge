// ====== Code Summary ======
// The shared text/number/select input look, reused by every form outside the generic schema
// form (which keeps its own local copy in components/schema-form/SchemaField.tsx).

import { theme } from "../theme";

export const inputStyle: React.CSSProperties = {
  background: theme.color.surface2,
  border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.m,
  padding: "8px 10px",
  fontSize: theme.font.size.l,
  color: theme.color.text,
  width: "100%",
};
