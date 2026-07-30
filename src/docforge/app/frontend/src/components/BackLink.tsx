// ====== Code Summary ======
// A small "← back" affordance shared by every page nested under Collections (detail, pipeline
// studio, jobs, job detail) — one consistent way to step back up the navigation stack.

import { theme } from "../theme";

interface BackLinkProps {
  label: string;
  onClick: () => void;
}

export function BackLink({ label, onClick }: BackLinkProps) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "none", border: "none", cursor: "pointer",
        color: theme.color.dim, fontSize: theme.font.size.s,
        padding: `${theme.space.xs}px 0`, textAlign: "left",
      }}
    >
      ← {label}
    </button>
  );
}
