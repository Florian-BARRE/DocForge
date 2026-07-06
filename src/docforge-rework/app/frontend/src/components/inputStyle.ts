// ====== Code Summary ======
// The shared text/number/select input look, reused by every form outside the generic schema
// form (which keeps its own local copy in components/schema-form/SchemaField.tsx).

import { theme } from "../theme";

export const inputStyle: React.CSSProperties = {
  background: theme.color.bg,
  border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.s,
  padding: "4px 7px",
  fontSize: theme.font.size.m,
  color: theme.color.text,
  width: "100%",
};
