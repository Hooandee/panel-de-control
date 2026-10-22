import { DialogButton, Focusable, TextField } from "@decky/ui";
import { FC, ReactNode, useEffect, useRef, useState } from "react";
import { LuApple, LuGamepad2, LuHeart, LuMoon, LuSmile, LuSun, LuZap } from "react-icons/lu";

import { accessoryPetAction, getAccessoryPet, PetAction, PetNeeds, PetState, renameAccessoryPet } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { forgetPreviews } from "./useAccessories";

const POLL_MS = 30_000;
const RENAME_DELAY_MS = 700;
const TRAIT_SHOWN = 0.62;

const NEED_STYLE: Record<keyof PetNeeds, { icon: ReactNode; colour: string }> = {
  hunger: { icon: <LuApple size={14} />, colour: "#ff6b7a" },
  energy: { icon: <LuZap size={14} />, colour: "#ffd166" },
  fun: { icon: <LuGamepad2 size={14} />, colour: "#5ad1ff" },
  love: { icon: <LuHeart size={14} />, colour: "#ff8fc8" },
};

const NeedBar: FC<{ need: keyof PetNeeds; value: number }> = ({ need, value }) => {
  const { t } = useI18n();
  const { icon, colour } = NEED_STYLE[need];
  const low = value < 0.3;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ color: colour, display: "flex", width: 16 }}>{icon}</span>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, width: 76 }}>{t(`accessories.pet.need.${need}`)}</span>
      <span style={{ flex: 1, height: 7, borderRadius: 4, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
        <span style={{ display: "block", height: "100%", width: `${Math.round(value * 100)}%`, borderRadius: 4,
          background: low ? theme.color.warn : colour, boxShadow: `0 0 8px ${low ? theme.color.warn : colour}66`,
          transition: "width 400ms ease" }} />
      </span>
    </div>
  );
};

const ActionButton: FC<{ icon: ReactNode; label: string; onPress: () => void; busy: boolean }> = ({ icon, label, onPress, busy }) => (
  <DialogButton onClick={onPress} onOKButton={onPress} disabled={busy}
    style={{ flex: 1, minWidth: 0, padding: "8px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      fontSize: 11, fontWeight: 700 }}>
    <span style={{ display: "flex", fontSize: 18 }}>{icon}</span>
    {label}
  </DialogButton>
);

export const PetCare: FC = () => {
  const { t } = useI18n();
  const [pet, setPet] = useState<PetState | null>(null);
  const [reaction, setReaction] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const renameTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let live = true;
    const load = () => void getAccessoryPet().then((next) => { if (live && next) setPet(next); }).catch(() => undefined);
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => { live = false; window.clearInterval(timer); window.clearTimeout(renameTimer.current); };
  }, []);

  if (!pet) return null;
  const act = (kind: PetAction) => {
    if (busy) return;
    setBusy(true);
    void accessoryPetAction(kind)
      .then((result) => {
        if (result?.ok && result.pet) {
          setPet(result.pet);
          setReaction(result.reaction ?? null);
          forgetPreviews("pet");
        }
      })
      .catch(() => undefined)
      .finally(() => setBusy(false));
  };
  const rename = (value: string) => {
    setName(value);
    window.clearTimeout(renameTimer.current);
    renameTimer.current = window.setTimeout(() => {
      void renameAccessoryPet(value).then((next) => { if (next) setPet(next); }).catch(() => undefined);
    }, RENAME_DELAY_MS);
  };
  const traits = Object.entries(pet.traits).filter(([, value]) => value >= TRAIT_SHOWN)
    .sort((a, b) => b[1] - a[1]).slice(0, 2).map(([trait]) => t(`accessories.pet.trait.${trait}`));
  const age = pet.age_days === 0 ? t("accessories.pet.newborn") : t("accessories.pet.age", { days: String(pet.age_days) });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: theme.font.body, fontWeight: 800, color: theme.color.textPrimary }}>{pet.name}</span>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{age}</span>
      </div>
      {(traits.length > 0 || pet.favourite) && (
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, display: "flex", alignItems: "center", gap: 6 }}>
          <LuSmile size={13} />
          {[...traits, pet.favourite ? t("accessories.pet.favourite", { genre: t(`accessories.pet.genre.${pet.favourite}`) }) : null]
            .filter(Boolean).join(" · ")}
        </span>
      )}
      {(Object.keys(NEED_STYLE) as (keyof PetNeeds)[]).map((need) => <NeedBar key={need} need={need} value={pet.needs[need]} />)}
      <Focusable flow-children="row" style={{ display: "flex", gap: 6 }}>
        <ActionButton icon={<LuApple />} label={t("accessories.pet.action.feed")} busy={busy} onPress={() => act("feed")} />
        <ActionButton icon={<LuGamepad2 />} label={t("accessories.pet.action.play")} busy={busy} onPress={() => act("play")} />
        <ActionButton icon={<LuHeart />} label={t("accessories.pet.action.pet")} busy={busy} onPress={() => act("pet")} />
        {pet.asleep
          ? <ActionButton icon={<LuSun />} label={t("accessories.pet.action.wake")} busy={busy} onPress={() => act("wake")} />
          : <ActionButton icon={<LuMoon />} label={t("accessories.pet.action.sleep")} busy={busy} onPress={() => act("sleep")} />}
      </Focusable>
      {reaction && (
        <span style={{ fontSize: theme.font.caption, color: theme.color.textPrimary, textAlign: "center", fontWeight: 650 }}>
          {t(`accessories.pet.reaction.${reaction}`)}
        </span>
      )}
      <TextField label={t("accessories.pet.name")} value={name ?? pet.name} onChange={(e) => rename(e.target.value.slice(0, 15))} />
    </div>
  );
};
