import { FC } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { HdrState, HdrPatch } from "../api";

interface Props {
  state: HdrState;
  onChange: (patch: HdrPatch) => void;
}

/** HDR on/off toggle. The color lab stays active (it colors all SDR content); only a
 *  native-HDR game's own image is beyond our reach. */
export const HdrPanel: FC<Props> = ({ state, onChange }) => {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, margin: `${theme.space.sm}px 0`, overflow: "hidden" }}>
        <ToggleField
          label={t("display.hdr")}
          description={t("display.hdr.desc")}
          checked={state.enabled}
          onChange={(v) => onChange({ enabled: v })}
          bottomSeparator="none"
        />
      </div>
    </PanelSectionRow>
  );
};
