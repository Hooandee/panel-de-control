import type { FC } from "react";
import { ErrorBoundary } from "@decky/ui";

import type { QamEntryToken } from "../qam/layout";
import type { QamViewTarget } from "../qam/viewCatalog";
import { I18nProvider } from "../i18n";
import { ControlCenter } from "./ControlCenter";
import { QamPanelGate } from "./QamPanelGate";
import { ReportingBoundary } from "./ReportingBoundary";

export const PinnedQamView: FC<{
  token: QamEntryToken;
  target: QamViewTarget;
  lifecycle: AbortSignal;
}> = ({ token, target, lifecycle }) => (
  <QamPanelGate surfaceId={token} lifecycle={lifecycle}>
    <I18nProvider>
      <ErrorBoundary>
        <ReportingBoundary where={`pinned:${token}`}>
          <ControlCenter target={target} />
        </ReportingBoundary>
      </ErrorBoundary>
    </I18nProvider>
  </QamPanelGate>
);
