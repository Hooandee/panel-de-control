import { Focusable, ModalRoot } from "@decky/ui";
import { useState, type FC } from "react";

import type { GameCompat } from "../api";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import type { GameEntry } from "../launch/steamApi";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";
import { BULK_ACTIONS, bulkSteps, cancelBulk, runBulk, type BulkAction, type BulkProgress, type BulkStep } from "./bulk";
import { ActionButton, Label, Note, Row } from "./parts";
import type { UpscalersOverview } from "./types";

const PickModal: FC<{
  action: BulkAction;
  steps: BulkStep[];
  onStart: (steps: BulkStep[]) => void;
  closeModal?: () => void;
}> = ({ action, steps, onStart, closeModal }) => {
  const { t } = useI18n();
  const [picked, setPicked] = useState<Set<string>>(() => new Set(steps.map((s) => s.game.instanceKey)));
  const toggle = (key: string) => setPicked((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });
  const chosen = steps.filter((s) => picked.has(s.game.instanceKey));
  return (
    <ModalRoot closeModal={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={{ fontSize: theme.font.body + 2, fontWeight: 700, color: theme.color.textPrimary }}>{t(`up.bulk.${action}.title`)}</div>
        <Note>{t(`up.bulk.${action}.hint`)}</Note>
        <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 300, overflowY: "auto" }}>
          {steps.map((step) => {
            const on = picked.has(step.game.instanceKey);
            return (
              <Focusable
                key={step.game.instanceKey}
                onActivate={() => toggle(step.game.instanceKey)}
                onClick={() => toggle(step.game.instanceKey)}
                style={{
                  ...theme.card, display: "flex", alignItems: "center", gap: theme.space.sm,
                  padding: `6px ${theme.space.sm}px`, opacity: on ? 1 : 0.5,
                }}
              >
                <GameCover urls={step.game.coverUrls} name={step.game.name} width={24} />
                <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {step.game.name}
                </span>
                <span style={{
                  width: 18, height: 18, borderRadius: 5, flexShrink: 0,
                  boxShadow: `inset 0 0 0 2px ${on ? theme.color.accent : theme.color.outline}`,
                  background: on ? theme.color.accent : "transparent",
                }} />
              </Focusable>
            );
          })}
        </Focusable>
        <Row>
          <ActionButton label={t("up.bulk.cancel")} onPress={() => closeModal?.()} />
          <ActionButton
            primary={action !== "remove"}
            danger={action === "remove"}
            disabled={!chosen.length}
            label={t("up.bulk.start", { count: chosen.length })}
            onPress={() => { closeModal?.(); onStart(chosen); }}
          />
        </Row>
      </div>
    </ModalRoot>
  );
};

/** Install, update, repair or remove across many games at once, one after another. */
export const BulkPanel: FC<{
  games: GameEntry[];
  overview: UpscalersOverview;
  compat: Record<string, GameCompat>;
  onChanged: () => void;
}> = ({ games, overview, compat, onChanged }) => {
  const { t } = useI18n();
  const [progress, setProgress] = useState<BulkProgress | null>(null);
  const running = !!progress && progress.index < progress.total;
  const counts = Object.fromEntries(BULK_ACTIONS.map((a) => [a, bulkSteps(a, games, overview, compat)])) as Record<BulkAction, BulkStep[]>;
  if (!running && !progress && BULK_ACTIONS.every((a) => !counts[a].length)) return null;

  const start = async (action: BulkAction, steps: BulkStep[]) => {
    const end = await runBulk(action, steps, (next) => { setProgress(next); onChanged(); });
    setProgress(end);
    onChanged();
  };
  const open = (action: BulkAction) => showModal(
    <PickModal action={action} steps={counts[action]} onStart={(steps) => void start(action, steps)} />, window,
  );

  return (
    <>
      <Label>{t("up.bulk.title")}</Label>
      {running ? (
        <div style={{ ...theme.card, padding: `${theme.space.sm}px ${theme.space.md}px`, display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
            {t("up.bulk.progress", { index: progress!.index + 1, total: progress!.total, name: progress!.current ?? "" })}
          </span>
          <div style={{ height: 4, borderRadius: 2, background: theme.color.hairline, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${(progress!.index / Math.max(1, progress!.total)) * 100}%`, background: theme.color.accent, transition: "width 300ms ease" }} />
          </div>
          <Row><ActionButton label={t("up.bulk.stop")} onPress={cancelBulk} /></Row>
        </div>
      ) : (
        <>
          <Row>
            {(["install", "update"] as const).map((action) => (
              <ActionButton key={action} label={t(`up.bulk.${action}`, { count: counts[action].length })}
                disabled={!counts[action].length} onPress={() => open(action)} />
            ))}
          </Row>
          <Row>
            {(["repair", "remove"] as const).map((action) => (
              <ActionButton key={action} danger={action === "remove"} label={t(`up.bulk.${action}`, { count: counts[action].length })}
                disabled={!counts[action].length} onPress={() => open(action)} />
            ))}
          </Row>
          {progress && (
            <Note tone={progress.skipped.length ? "warn" : undefined}>
              {progress.skipped.length
                ? t("up.bulk.doneSkipped", { done: progress.done, skipped: progress.skipped.map((s) => s.name).join(", ") })
                : t("up.bulk.done", { done: progress.done })}
            </Note>
          )}
        </>
      )}
    </>
  );
};
