import { Component, type ReactNode } from "react";

import { describeError, recordUiDiagnostic } from "../system/uiDiagnostics";

interface Props {
  where: string;
  children?: ReactNode;
}

/** Records a render error in the diary, then hands it on unchanged so Decky's
 * ErrorBoundary around it keeps showing its usual error view. Rethrowing from
 * render means React never commits this boundary, so componentDidCatch would not
 * run: the error is recorded here, once. */
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
