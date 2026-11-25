import { DialogButton, Focusable, ModalRoot, TextField } from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import { LuLocateFixed, LuMapPin } from "react-icons/lu";

import { locateAccessoryCity, searchAccessoryCities, WeatherCity } from "../api";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { FocusRoot } from "../components/FocusRoot";
import { theme } from "../theme";

const SEARCH_DELAY_MS = 450;

const CityBody: FC<{ onPick: (city: WeatherCity) => void; closeModal?: () => void }> = ({ onPick, closeModal }) => {
  const { t, lang } = useI18n();
  const [query, setQuery] = useState("");
  const [cities, setCities] = useState<WeatherCity[]>([]);
  const [searching, setSearching] = useState(false);
  const [locating, setLocating] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const request = useRef(0);
  const open = useRef(true);
  useEffect(() => () => { open.current = false; }, []);
  const pick = (city: WeatherCity) => {
    // A lookup that answers after the dialog was closed must not change the scene.
    if (!open.current) return;
    onPick(city);
    closeModal?.();
  };
  const locate = () => {
    if (locating) return;
    setLocating(true);
    setNotFound(false);
    locateAccessoryCity()
      .then((result) => { if (result?.city) pick(result.city); else setNotFound(true); })
      .catch(() => setNotFound(true))
      .finally(() => setLocating(false));
  };

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      request.current += 1;
      setCities([]);
      setSearching(false);
      return undefined;
    }
    const id = ++request.current;
    const timer = window.setTimeout(() => {
      setSearching(true);
      searchAccessoryCities(text, lang.slice(0, 2))
        .then((result) => { if (request.current === id) setCities(result?.cities ?? []); })
        .catch(() => { if (request.current === id) setCities([]); })
        .finally(() => { if (request.current === id) setSearching(false); });
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [query, lang]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm }}>
      <div style={{ fontSize: 20, fontWeight: 700, color: theme.color.textPrimary }}>{t("accessories.city.title")}</div>
      <DialogButton onClick={locate}
        style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.sm, fontWeight: 700 }}>
        <LuLocateFixed size={16} color={theme.color.accent} />
        {locating ? t("accessories.city.locating") : t("accessories.city.locate")}
      </DialogButton>
      {notFound && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("accessories.city.locateFailed")}</span>}
      <TextField value={query} onChange={(e) => setQuery(e.target.value)} />
      <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        {cities.map((city) => (
          <DialogButton key={`${city.lat},${city.lon}`} onClick={() => pick(city)}
            style={{ display: "flex", alignItems: "center", gap: theme.space.sm, textAlign: "left", padding: "10px 14px" }}>
            <LuMapPin size={16} color={theme.color.accent} />
            <span style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontWeight: 700 }}>{city.name}</span>
              <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{city.detail}</span>
            </span>
          </DialogButton>
        ))}
        {!cities.length && query.trim().length >= 2 && !searching && (
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.city.none")}</span>
        )}
      </Focusable>
    </div>
  );
};

const CityModal: FC<{ onPick: (city: WeatherCity) => void; closeModal?: () => void }> = ({ onPick, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <CityBody onPick={onPick} closeModal={closeModal} />
    </FocusRoot>
  </ModalRoot>
);

export function openCityModal(onPick: (city: WeatherCity) => void): void {
  showModal(<CityModal onPick={onPick} />, window);
}
