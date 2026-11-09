import { ModalRoot, SliderField } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

import { captureUpscalerFrame } from "../api";
import { useI18n } from "../i18n";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";
import { setCompareGhost } from "./overlays";
import { ActionButton, Label, Note, Row, SegmentRow, Spinner } from "./parts";
import { holdPage } from "./pageMemory";
import { upscalerErrorCode } from "./errorCode";


export interface Shot {
  id: string;
  build: string;
  resolution?: { render: number[]; output: number[] } | null;
  upscaler?: string | null;
  image: string;
}

const GHOST_LEVELS = { soft: 0.3, strong: 0.55 } as const;
type Ghost = "off" | keyof typeof GHOST_LEVELS;

// The comparison modal remounts the panel (pageMemory.ts); the shots wait here until Close.
let kept: { appid: string; first: Shot | null; second: Shot | null; ghost: Ghost } | null = null;

export const isComparing = (appid: string): boolean => kept?.appid === appid;

const UPSCALER_NAMES: Record<string, string> = { "FSR 3.X": "FSR", fsr31: "FSR", fsr31_12: "FSR", fsr22: "FSR 2", xess: "XeSS", xess_12: "XeSS", dlss: "DLSS" };

/** Panel only knows what it installed; a switch made in OptiScaler's own menu shows up as the log's upscaler. */
function shotLabel(t: (key: string) => string, order: "first" | "second", shot: Shot): string {
  const name = shot.upscaler ? UPSCALER_NAMES[shot.upscaler] ?? shot.upscaler : null;
  return name ? `${t(`up.compare.${order}`)}, ${name}` : t(`up.compare.${order}`);
}

/** Two shots of the same scene; the user pulls a curtain between them. */
const CompareModal: FC<{ first: Shot; second: Shot; closeModal?: () => void }> = ({ first, second, closeModal }) => {
  const { t } = useI18n();
  const [split, setSplit] = useState(50);
  const tag = (text: string, side: "left" | "right") => (
    <span style={{
      position: "absolute", top: 10, [side]: 10, padding: "3px 10px", borderRadius: 999,
      background: "rgba(10,12,18,.78)", color: "#fff", fontWeight: 700, fontSize: 13,
    }}>
      {text}
    </span>
  );
  return (
    <ModalRoot closeModal={closeModal} bAllowFullSize>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={{ position: "relative", width: "100%", aspectRatio: "16 / 10", overflow: "hidden", borderRadius: theme.radius.sm, background: "#000" }}>
          <img src={second.image} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} />
          <img
            src={first.image}
            style={{
              position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain",
              clipPath: `inset(0 ${100 - split}% 0 0)`,
            }}
          />
          <div style={{ position: "absolute", top: 0, bottom: 0, left: `${split}%`, width: 2, background: "rgba(255,255,255,.9)", boxShadow: "0 0 8px rgba(0,0,0,.6)" }} />
          {tag(shotLabel(t, "first", first), "left")}
          {tag(shotLabel(t, "second", second), "right")}
        </div>
        <SliderField label={t("up.compare.curtain")} value={split} min={0} max={100} step={1} onChange={setSplit} />
      </div>
    </ModalRoot>
  );
};

/** Guided two-shot comparison: shoot, switch upscaler, line the scene up over a ghost, shoot again. */
export const CompareView: FC<{
  appid: string;
  gameRunning: boolean;
  onClose: () => void;
}> = ({ appid, gameRunning, onClose }) => {
  const { t } = useI18n();
  const resumed = kept?.appid === appid ? kept : null;
  const [first, setFirst] = useState<Shot | null>(resumed?.first ?? null);
  const [second, setSecond] = useState<Shot | null>(resumed?.second ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ghost, setGhost] = useState<Ghost>(resumed?.ghost ?? "soft");

  useEffect(() => {
    kept = { appid, first, second, ghost };
  }, [appid, first, second, ghost]);
  const close = () => {
    kept = null;
    onClose();
  };

  useEffect(() => {
    setCompareGhost(first && !second && ghost !== "off" ? { image: first.image, opacity: GHOST_LEVELS[ghost] } : null);
  }, [first, second, ghost]);
  useEffect(() => () => setCompareGhost(null), []);

  const shoot = async (assign: (shot: Shot) => void) => {
    setBusy(true);
    setError(null);
    try {
      assign(await captureUpscalerFrame(appid));
    } catch (e) {
      const code = upscalerErrorCode(e);
      setError(t(code === "not_running" ? "up.compare.needGame" : "up.compare.failed"));
    } finally {
      setBusy(false);
    }
  };

  const open = (a: Shot, b: Shot) => {
    holdPage();
    showModal(<CompareModal first={a} second={b} />, window);
  };

  return (
    <div style={{ ...theme.card, padding: theme.space.sm, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <Label>{t("up.compare.title")}</Label>
      {!gameRunning && !second && <Note tone="warn">{t("up.compare.needGame")}</Note>}
      {error && <Note tone="warn">{error}</Note>}

      {!first && (
        <>
          <Note>{t("up.compare.stepFirst")}</Note>
          <Row>
            <ActionButton primary label={t("up.compare.shootFirst")} onPress={() => shoot(setFirst)} busy={busy} disabled={!gameRunning} />
          </Row>
        </>
      )}

      {first && !second && (
        <>
          <div style={{ display: "flex", gap: theme.space.sm, alignItems: "center" }}>
            <img src={first.image} style={{ width: 96, borderRadius: 6, flexShrink: 0 }} />
            <span style={{ fontSize: theme.font.caption, color: theme.color.textPrimary }}>{shotLabel(t, "first", first)}</span>
          </div>
          <Note>{t("up.compare.stepSwitch")}</Note>
          <Label>{t("up.compare.ghost")}</Label>
          <SegmentRow<Ghost>
            value={ghost}
            onChange={setGhost}
            options={[
              { value: "off", label: t("up.compare.ghost.off") },
              { value: "soft", label: t("up.compare.ghost.soft") },
              { value: "strong", label: t("up.compare.ghost.strong") },
            ]}
          />
          <Row>
            <ActionButton primary label={t("up.compare.shootSecond")} onPress={() => shoot(setSecond)} busy={busy} disabled={!gameRunning} />
          </Row>
        </>
      )}

      {first && second && (
        <>
          <Row>
            <ActionButton primary label={t("up.compare.show")} onPress={() => open(first, second)} />
          </Row>
          <Row>
            <ActionButton label={t("up.compare.again")} onPress={() => { setFirst(null); setSecond(null); }} />
          </Row>
        </>
      )}

      {busy && (
        <div style={{ display: "flex", gap: theme.space.xs, alignItems: "center", fontSize: theme.font.caption, color: theme.color.textMuted }}>
          <Spinner size={12} /> {t("up.compare.shooting")}
        </div>
      )}
      <Row><ActionButton label={t("up.compare.close")} onPress={close} /></Row>
    </div>
  );
};
