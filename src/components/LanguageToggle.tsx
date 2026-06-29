import { FC } from "react";
import { DropdownItem, PanelSectionRow } from "@decky/ui";
import { useI18n, Lang } from "../i18n";

export const LanguageToggle: FC = () => {
  const { lang, setLang, t } = useI18n();
  return (
    <PanelSectionRow>
      <DropdownItem
        rgOptions={[
          { label: t("lang.spanish"), data: "es" },
          { label: t("lang.english"), data: "en" },
        ]}
        selectedOption={lang}
        onChange={(opt) => setLang(opt.data as Lang)}
      />
    </PanelSectionRow>
  );
};
