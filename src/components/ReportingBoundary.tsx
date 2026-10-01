import { Component, type ReactNode } from "react";

import { describeError, recordUiDiagnostic } from "../system/uiDiagnostics";

interface Props {
  where: string;
  children?: ReactNode;
}

/** Rethrows so Decky's ErrorBoundary still shows its view. React never commits a
 * boundary that rethrows, so componentDidCatch would not run: report in render. */
export class ReportingBoundary extends Component<Props, { error: unknown }> {
  state: { error: unknown } = { error: null };
  private reported: unknown = null;

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  render() {
    const { error } = this.state;
    if (error) {
      if (this.reported !== error) {
        this.reported = error;
        const { code, detail } = describeError(this.props.where, error);
        recordUiDiagnostic("frontend", code, detail);
      }
      throw error;
    }
    return this.props.children;
  }
}
