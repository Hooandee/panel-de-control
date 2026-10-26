import { FC } from "react";
import { LuThermometer } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { thermalZone } from "../fans/suggestLogic";
import { ZONE_COLOR } from "./ThermalScale";
import { Collapsible } from "./Collapsible";
import { Sparkline } from "./Sparkline";

const Row: FC<{ label: string; celsius: number | null; history: number[] }> = ({ label, celsius, history }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{label}</span>
      <span style={{ fontSize: theme.font.body, fontWeight: 700, color: celsius === null ? theme.color.textMuted : ZONE_COLOR[thermalZone(celsius)] }}>
        {celsius === null ? "—" : `${Math.round(celsius)} °C`}
      </span>
    </div>
    <Sparkline values={history} height={30} color={celsius === null ? theme.color.textMuted : ZONE_COLOR[thermalZone(celsius)]} />
  </div>
);

export const ConsoleTempsCard: FC<{ apu: number | null; ssd: number | null; apuHistory: number[]; ssdHistory: number[] }> = ({ apu, ssd, apuHistory, ssdHistory }) => {
  const { t } = useI18n();
  const summary = [apu !== null ? `APU ${Math.round(apu)}°` : null, ssd !== null ? `SSD ${Math.round(ssd)}°` : null]
    .filter(Boolean).join(" · ") || "—";
  return (
    <Collapsible id="console-temps" icon={<LuThermometer size={16} />} title={t("console.temps.title")} summary={summary}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <Row label={t("console.temps.apu")} celsius={apu} history={apuHistory} />
        {ssd !== null && <Row label={t("console.temps.ssd")} celsius={ssd} history={ssdHistory} />}
      </div>
    </Collapsible>
  );
};
