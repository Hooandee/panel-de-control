import { FC, PropsWithChildren } from "react";

import { QamPanelGate } from "./QamPanelGate";

interface StandardDeckyContentProps extends PropsWithChildren {
  lifecycle: AbortSignal;
}

export const StandardDeckyContent: FC<StandardDeckyContentProps> = ({
  children,
  lifecycle,
}) => (
  <QamPanelGate lifecycle={lifecycle} fallback={children}>
    {children}
  </QamPanelGate>
);
