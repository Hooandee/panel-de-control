import { FC } from "react";
import { PanelSectionRow } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { usePantalla } from "../display/pantallaContext";
import { ProfileSelector } from "../components/ProfileSelector";
import { SectionView } from "../customize/blocks";
import { PantallaProviderMount } from "./providerMounts";

const PantallaBody: FC = () => {
  const { t } = useI18n();
  const { color } = usePantalla();
  const { state, scope, game, onScope } = color;

  if (!state) return null;
  if (!state.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("display.unsupported")}
        </div>
      </PanelSectionRow>
    );
  }

  return (
    <>
      <PanelSectionRow>
        <ProfileSelector
          scope={scope}
          gameName={game?.name ?? null}
          hasGameProfile={state.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("display.inherit")}
          onScope={onScope}
        />
      </PanelSectionRow>
      <SectionView sectionId="display" />
    </>
  );
};

export const PantallaSection: FC = () => (
  <PantallaProviderMount>
    <PantallaBody />
  </PantallaProviderMount>
);
