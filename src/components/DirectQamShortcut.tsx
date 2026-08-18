import { FC, PropsWithChildren } from "react";

import { QamPanelGate } from "./QamPanelGate";

export const DirectQamShortcut: FC<PropsWithChildren<{
  lifecycle: AbortSignal;
}>> = ({ children, lifecycle }) => (
  <QamPanelGate lifecycle={lifecycle}>
    {children}
  </QamPanelGate>
);
