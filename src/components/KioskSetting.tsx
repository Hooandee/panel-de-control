import { FC, useEffect, useState } from "react";
import { ToggleField } from "@decky/ui";

import { getKioskState, KioskState, setKioskEnabled } from "../api";
import { useI18n } from "../i18n";
import { kioskDescriptionKey } from "../system/kioskStatus";

const POLL_MS = 4000;

export const KioskSetting: FC = () => {
  const { t } = useI18n();
  const [state, setState] = useState<KioskState | null>(null);

  useEffect(() => {
    let alive = true;
    const read = () => getKioskState().then((next) => alive && setState(next)).catch(() => {});
    read();
    const id = window.setInterval(read, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (!state?.supported) return null;

  const onChange = (enabled: boolean) => {
    setState({ ...state, enabled });
    setKioskEnabled(enabled).then(setState).catch(() => getKioskState().then(setState).catch(() => {}));
  };

  return (
    <ToggleField
      label={t("settings.kiosk")}
      description={t(kioskDescriptionKey(state))}
      checked={state.enabled}
      disabled={state.reason === "no_browser"}
      onChange={onChange}
      bottomSeparator="none"
    />
  );
};
