import { ModalRoot, TextField } from "@decky/ui";
import { useEffect, useRef, useState, type FC } from "react";

import { searchUpscalerGames, setUpscalerIdentity } from "../api";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";
import { ActionButton, Note, Spinner } from "./parts";
import type { GameDetail } from "./types";
import { holdPage } from "./pageMemory";

const SEARCH_DELAY_MS = 450;

const IdentityModal: FC<{ appid: string; initial: string; onDone: (detail: GameDetail) => void; closeModal?: () => void }> = ({ appid, initial, onDone, closeModal }) => {
  const { t } = useI18n();
  const [term, setTerm] = useState(initial);
  const [results, setResults] = useState<{ id: number; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const request = useRef(0);

  useEffect(() => {
    const query = term.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const ticket = ++request.current;
    const timer = window.setTimeout(async () => {
      setBusy(true);
      const found = await searchUpscalerGames(query).catch(() => []);
      if (ticket === request.current) {
        setResults(found);
        setBusy(false);
      }
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [term]);

  const choose = async (id: number | null, name?: string) => {
    onDone(await setUpscalerIdentity(appid, id, name ?? null));
    closeModal?.();
  };

  return (
    <ModalRoot closeModal={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={{ fontWeight: 700, fontSize: theme.font.body + 2 }}>{t("up.identity.title")}</div>
        <TextField label={t("up.identity.search")} value={term} onChange={(e) => setTerm(e.target.value)} />
        {busy && <div style={{ display: "flex", gap: theme.space.xs, alignItems: "center" }}><Spinner size={12} /></div>}
        {!busy && term.trim().length >= 2 && results.length === 0 && <Note>{t("up.identity.none")}</Note>}
        {results.map((item) => (
          <ActionButton key={item.id} label={item.name} onPress={() => choose(item.id, item.name)} />
        ))}
        <ActionButton label={t("up.identity.auto")} onPress={() => choose(null)} />
      </div>
    </ModalRoot>
  );
};

export function openIdentityModal(appid: string, initial: string, onDone: (detail: GameDetail) => void): void {
  holdPage();
  showModal(<IdentityModal appid={appid} initial={initial} onDone={onDone} />, window);
}
