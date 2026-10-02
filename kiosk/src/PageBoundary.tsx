import { Component, ReactNode } from "react";

import { ReportingBoundary } from "../../src/components/ReportingBoundary";

interface Props {
  where: string;
  fallback: (retry: () => void) => ReactNode;
  children?: ReactNode;
}

/** One failing page must not blank the whole screen; ReportingBoundary still logs it. */
export class PageBoundary extends Component<Props, { failed: boolean; attempt: number }> {
  state = { failed: false, attempt: 0 };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  private retry = () => this.setState(({ attempt }) => ({ failed: false, attempt: attempt + 1 }));

  render() {
    if (this.state.failed) return this.props.fallback(this.retry);
    return (
      <ReportingBoundary key={this.state.attempt} where={this.props.where}>
        {this.props.children}
      </ReportingBoundary>
    );
  }
}
