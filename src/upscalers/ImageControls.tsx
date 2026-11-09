import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { getUpscalerImageSettings, restoreUpscalerImageSettings, setUpscalerImageSettings,
  type UpscalerImagePatch, type UpscalerImageSettings } from "../api";
import { ContainedSlider } from "../components/ContainedSlider";
import { useI18n } from "../i18n";
import { recordUiEvent } from "../system/uiEvents";
import { ActionButton, Label, ListCard, ListRow, Note, Row, SegmentRow } from "./parts";
import { upscalerErrorCode } from "./errorCode";

export interface ImageControlsHandle {
  save: () => Promise<boolean>;
  discard: () => void;
}

/** With `onDirty`, the page owns the single Save/Discard row and drives these through the handle. */
export const ImageControls = forwardRef<ImageControlsHandle, {
  appid: string; disabled: boolean; gameRunning: boolean; revision: string; onSavedForNextLaunch?: () => void;
  onDirty?: (dirty: boolean) => void;
}>(({ appid, disabled, gameRunning, revision, onSavedForNextLaunch, onDirty }, handle) => {
  const { t } = useI18n();
  const [state, setState] = useState<UpscalerImageSettings | null>(null);
  const [patch, setPatch] = useState<UpscalerImagePatch>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const generation = useRef(0);
  const saving = useRef(false);
  const alive = useRef(true);
  const currentAppid = useRef(appid);
  currentAppid.current = appid;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const load = async () => {
    const current = ++generation.current;
    setFailed(false);
    try {
      const next = await getUpscalerImageSettings(appid);
      if (current !== generation.current) return;
      setState(next);
      setPatch({});
    } catch {
      if (current === generation.current) setFailed(true);
    }
  };
  useEffect(() => {
    setState(null);
    setBusy(saving.current);
    setPatch({});
    setMessage(null);
    void load();
    return () => { generation.current++; };
  }, [appid, revision]);
  const edit = (change: (value: UpscalerImagePatch) => UpscalerImagePatch) => {
    setMessage(null);
    setPatch(change);
  };
  const blocked = disabled || busy;
  const save = async (restore = false): Promise<boolean> => {
    if (blocked || saving.current) return false;
    saving.current = true;
    setBusy(true);
    setMessage(null);
    const current = generation.current;
    const action = restore ? "image_restore" : "image_settings";
    recordUiEvent("upscalers", action, { appid, stage: "intent" });
    try {
      const next = restore ? await restoreUpscalerImageSettings(appid) : await setUpscalerImageSettings(appid, patch);
      if (current !== generation.current) return true;
      setState(next);
      setPatch({});
      if (gameRunning && onSavedForNextLaunch) onSavedForNextLaunch();
      else if (!onDirty) setMessage(t("up.image.saved"));
      recordUiEvent("upscalers", action, { appid, stage: "result" }, true);
      return true;
    } catch (error) {
      if (current !== generation.current) return false;
      const key = `up.error.${upscalerErrorCode(error)}`;
      setMessage(t(key) === key ? t("up.error.generic") : t(key));
      recordUiEvent("upscalers", action, { appid, stage: "result" }, false);
      return false;
    } finally {
      saving.current = false;
      if (alive.current && currentAppid.current === appid) {
        if (current !== generation.current) await load();
        setBusy(false);
      }
    }
  };
  const dirtyNow = Object.keys(patch).length > 0;
  useEffect(() => { onDirty?.(dirtyNow); }, [dirtyNow]);
  useImperativeHandle(handle, () => ({
    save: () => dirtyNow ? save() : Promise.resolve(true),
    discard: () => { setPatch({}); setMessage(null); },
  }));
  if (failed) return <Row><ActionButton label={t("up.image.retry")} onPress={() => void load()} /></Row>;
  if (!state?.supported) return null;
  const sharpness = patch.sharpness ?? state.sharpness;
  const int8 = patch.int8 ?? state.int8;
  const dirty = Object.keys(patch).length > 0;
  return <>
    <ListCard>
      {sharpness && <ContainedSlider
        label={<span style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
          <span>{t("up.image.sharpness")}</span>
          {sharpness.enabled === null && <span>{t("up.image.auto")}</span>}
        </span>}
        value={sharpness.enabled === true ? Math.round((sharpness.value ?? 0) * 100) : 0}
        min={0} max={100} step={1} showValue={sharpness.enabled !== null}
        disabled={blocked} bottomSeparator="none"
        onChange={value => {
          if (blocked) return;
          const amount = Math.max(0, Math.min(100, Math.round(value))) / 100;
          edit(p => ({ ...p, sharpness: { enabled: amount > 0, value: amount } }));
        }} />}
      {int8 !== null && <>
        <Label>{t("up.image.int8")}</Label>
        <SegmentRow value={int8} disabled={blocked}
          options={(["auto", "on", "off"] as const).map(value => ({ value, label: t(`up.image.${value}`) }))}
          onChange={value => edit(p => ({ ...p, int8: value }))} />
      </>}
    </ListCard>
    {dirty && !onDirty && <Row>
      <ActionButton label={t("up.discard")} disabled={busy} onPress={() => { setPatch({}); setMessage(null); }} />
      <ActionButton primary label={t("up.save")} disabled={blocked} busy={busy} onPress={() => void save()} />
    </Row>}
    {!dirty && state.managed && <ListRow label={t("up.image.restore")} disabled={blocked}
      busy={busy} onPress={() => void save(true)} />}
    {message && <Note>{message}</Note>}
  </>;
});
