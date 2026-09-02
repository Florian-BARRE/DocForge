// ====== Code Summary ======
// The shared text/number/select input look, reused by every form outside the generic schema
// form (which keeps its own local copy in components/schema-form/SchemaField.tsx).

import { theme } from "../theme";

export const inputStyle: React.CSSProperties = {
  background: theme.color.surface2,
  // lineStrong, not line — the plain hairline token is near-invisible against surface-2, especially
  // on ink (see theme.ts / index.css comments). lineStrong is documented for exactly this ("inputs,
  // strong dividers") and was bumped to a real 3:1+ UI-component contrast in this pass.
  border: `1px solid ${theme.color.lineStrong}`,
  borderRadius: theme.radius.m,
  padding: "8px 10px",
  fontSize: theme.font.size.l,
  color: theme.color.text,
  width: "100%",
};
