import type { FC } from "react";
import { ErrorBoundary } from "@decky/ui";

import type { QamEntryToken } from "../qam/layout";
import type { QamViewTarget } from "../qam/viewCatalog";
import { I18nProvider } from "../i18n";
import { ControlCenter } from "./ControlCenter";
import { QamPanelGate } from "./QamPanelGate";

export const PinnedQamView: FC<{
  token: QamEntryToken;
  target: QamViewTarget;
  lifecycle: AbortSignal;
}> = ({ token, target, lifecycle }) => (
  <QamPanelGate surfaceId={token} lifecycle={lifecycle}>
    <I18nProvider>
      <ErrorBoundary>
        <ControlCenter target={target} />
      </ErrorBoundary>
    </I18nProvider>
  </QamPanelGate>
);
