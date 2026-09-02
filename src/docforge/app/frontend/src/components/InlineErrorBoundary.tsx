// ====== Code Summary ======
// A LOCAL render-error catcher, scoped to one section of a page rather than the whole routed view
// (the app-wide `shell/ErrorBoundary` already covers that, full-screen). Wrap a data-shaped list or
// card grid that could throw on a contract drift — e.g. a field renamed/removed upstream — so the
// rest of the page (header, filters, unrelated panels) stays usable and only that one section
// degrades to a compact inline notice.

import { Component, type ErrorInfo, type ReactNode } from "react";
import { theme } from "../theme";

interface InlineErrorBoundaryProps {
  children: ReactNode;
  /** Shown above the raw error message — name the section that failed (e.g. "the job list"). */
  label: string;
}

interface InlineErrorBoundaryState {
  error: Error | null;
}

export class InlineErrorBoundary extends Component<InlineErrorBoundaryProps, InlineErrorBoundaryState> {
  state: InlineErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): InlineErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[InlineErrorBoundary] caught a render error", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div
        role="alert"
        style={{
          border: `1px dashed ${theme.color.error}`, background: theme.color.errorSoft,
          borderRadius: theme.radius.l, padding: theme.space.l, color: theme.color.text,
        }}
      >
        <div style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.semibold, fontSize: theme.font.size.m, marginBottom: theme.space.xs }}>
          Couldn't render {this.props.label}
        </div>
        <div className="mono" style={{ color: theme.color.dim, fontSize: theme.font.size.s, wordBreak: "break-word" }}>
          {error.message || String(error)}
        </div>
      </div>
    );
  }
}
