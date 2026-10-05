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
    let id: number | undefined;
    const read = () => getKioskState().then((next) => {
      if (!alive) return;
      setState(next);
      // Machines without a second screen never gain one: stop asking.
      if (!next.supported && id !== undefined) window.clearInterval(id);
    }).catch(() => {});
    read();
    id = window.setInterval(read, POLL_MS);
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
      disabled={state.reason === "no_runtime"}
      onChange={onChange}
      bottomSeparator="none"
    />
  );
};
