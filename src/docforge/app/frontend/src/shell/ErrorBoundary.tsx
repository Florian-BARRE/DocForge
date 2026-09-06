// ====== Code Summary ======
// Top-level render-error catcher. Wraps the routed view area in App.tsx so a throw in any single
// page renders the branded <ErrorFallback> instead of white-screening the whole app; the shell
// (Sidebar) sits outside this boundary and survives a view crash.

import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorFallback } from "./ErrorFallback";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional recovery beyond clearing the caught error — e.g. reset the in-memory route. */
  onReset?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary] caught a render error", error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleBackToCollections = (): void => {
    this.setState({ error: null });
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <ErrorFallback
          error={this.state.error}
          onReload={this.handleReload}
          onBackToCollections={this.props.onReset ? this.handleBackToCollections : undefined}
        />
      );
    }
    return this.props.children;
  }
}
