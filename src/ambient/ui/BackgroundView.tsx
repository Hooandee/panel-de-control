import { Focusable } from "@decky/ui";
import { useEffect, type FC, type ReactNode } from "react";
import { LuChevronLeft, LuChevronRight, LuLibrary } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { AmbientSettings } from "../core/types";
import type { CollectionEntry } from "../steam/rpc";
import { gameName, type AmbientRuntime, type AmbientSnapshot } from "../steam/runtime";
import { Button, Caption, ChoiceRow, ToggleRow, MoreSettings, Tile, TileStrip, ValueRow, cardStyle } from "./primitives";
import { RoundButton } from "./NowPlaying";
import { openBackgroundLibrary } from "./BackgroundLibrary";
import { visualSources } from "./libraryModel";

const Hint: FC<{ children: ReactNode }> = ({ children }) => (
  <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4, padding: "0 2px", marginTop: -4 }}>{children}</span>
);
const INTERVALS = [30, 60, 300, 900, 3600] as const;

const SWATCHES: Record<string, string> = {
  known: "linear-gradient(160deg,#1c2350,#6b3c6e 55%,#e0875a)",
  screenshots: "linear-gradient(160deg,#2b2b2b,#555 50%,#1a1a1a)",
  "suggested.library": "radial-gradient(70% 90% at 75% 40%,#d65a3a,#6d1e2a 60%,#1a0a10)",
  "suggested.nasa": "radial-gradient(50% 60% at 60% 45%,rgba(160,110,255,.7),transparent 70%),#07071a",
  "suggested.bing": "linear-gradient(180deg,#8ec5ff 0,#cfe6ff 45%,#6f8f6a 46%,#3f5c3a 100%)",
  folder: "linear-gradient(135deg,#1b3b5a,#2c6a8a 50%,#0e1d2c)",
  favorite: "linear-gradient(135deg,#3a2a60,#8a4a8a)",
};

function tileFor(entry: CollectionEntry, t: (k: string) => string): { label: string; background: string; image?: string } {
  switch (entry.id) {
    case "known.images": return { label: t("ambient.tile.known"), background: SWATCHES.known };
    case "known.music": return { label: t("ambient.music.mine"), background: SWATCHES.known };
    case "screenshots": return { label: t("ambient.tile.screenshots"), background: SWATCHES.screenshots };
    case "suggested.library": return { label: t("ambient.tile.library"), background: SWATCHES[entry.id] };
    case "suggested.nasa": return { label: t("ambient.tile.nasa"), background: SWATCHES[entry.id] };
    case "suggested.bing": return { label: t("ambient.tile.bing"), background: SWATCHES[entry.id] };
    default:
      return entry.kind === "folder"
        ? { label: entry.name ?? entry.id, background: SWATCHES.folder }
        : { label: entry.name ?? entry.id, background: SWATCHES.favorite, image: entry.url };
  }
}

const Preview: FC<{ url: string | null; kind: string | undefined; label: string; frozen: boolean; onStep?: (direction: 1 | -1) => void; previousLabel: string; nextLabel: string }> = ({ url, kind, label, frozen, onStep, previousLabel, nextLabel }) => (
  <div style={{ position: "relative", borderRadius: 14, overflow: "hidden", aspectRatio: "16 / 9", background: "#0a0b0e", boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
    {url && kind === "video"
      ? <video src={url} muted preload="metadata" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
      : url && <div style={{ position: "absolute", inset: 0, background: `center / cover no-repeat url("${url}")` }} />}
    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg,rgba(0,0,0,0) 45%,rgba(0,0,0,.6))" }} />
    <span style={{ position: "absolute", left: 10, bottom: 9, fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,.9)" }}>
      {frozen ? "❚❚ " : ""}{label}
    </span>
    {onStep && (
      <Focusable flow-children="row" style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 6px", pointerEvents: "none" }}>
        <span style={{ pointerEvents: "auto" }}><RoundButton glass label={previousLabel} onActivate={() => onStep(-1)} size={32}><LuChevronLeft size={16} /></RoundButton></span>
        <span style={{ pointerEvents: "auto" }}><RoundButton glass label={nextLabel} onActivate={() => onStep(1)} size={32}><LuChevronRight size={16} /></RoundButton></span>
      </Focusable>
    )}
  </div>
);

export const BackgroundView: FC<{ snapshot: AmbientSnapshot; runtime: AmbientRuntime }> = ({ snapshot, runtime }) => {
  const { t } = useI18n();
  const state = snapshot.state!;
  const bg = state.settings.background;
  const update = (change: (b: AmbientSettings["background"]) => AmbientSettings["background"]) =>
    void runtime.updateSettings((s) => ({ ...s, background: change(s.background) }));
  const game = snapshot.selectedGame;
  const hasOwn = !!game && !!bg.perGame[game.appid];
  const intervalValue = bg.onReturnHome ? "home" : String(bg.intervalSec);
  const fixed = !!bg.pinned;
  useEffect(() => runtime.loadPreviews(), [runtime, state.collections, snapshot.scan]);

  return (
    <div style={cardStyle}>
      <ToggleRow label={t("ambient.bg.enabled")} checked={bg.enabled} onChange={(enabled) => update((b) => ({ ...b, enabled }))} />
      {bg.enabled && (
        <>
          <Preview
            url={snapshot.previewUrl}
            kind={snapshot.current?.kind}
            label={fixed && snapshot.current ? snapshot.current.name : snapshot.items.length ? t("ambient.bg.count", { n: snapshot.items.length }) : t("ambient.bg.empty")}
            frozen={snapshot.motion === "freeze"}
            onStep={snapshot.items.length > 1 ? (direction) => runtime.stepBackground(direction) : undefined}
            previousLabel={t("ambient.bg.previous")}
            nextLabel={t("ambient.player.next")}
          />
          <Button label={<><LuLibrary size={14} /> {t("ambient.lib.open")}</>} onActivate={() => openBackgroundLibrary()} />
          {snapshot.coveredBy.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, fontSize: theme.font.caption, color: theme.color.textMuted }}>
              <span style={{ flex: 1 }}>{t("ambient.covered.note")}</span>
              <Button label={t("ambient.covered.action")} onActivate={() => void runtime.showMineOver(snapshot.coveredBy)} style={{ height: 28 }} />
            </div>
          )}
          {snapshot.optimizing && <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("ambient.bg.optimizing")}</div>}
          {snapshot.error === "no_space" && (
            <div role="status" style={{ fontSize: theme.font.caption, color: theme.color.warn }}>
              <div>{t("ambient.error.noSpace")}</div>
              <Button label={t("ambient.retry")} onActivate={() => void runtime.reload()} />
            </div>
          )}
          <ChoiceRow
            label={t("ambient.bg.change")}
            value={fixed ? "fixed" : "auto"}
            options={[{ value: "fixed", label: t("ambient.bg.change.fixed") }, { value: "auto", label: t("ambient.bg.change.auto") }]}
            onChange={(v) => void runtime.setPinned(v === "fixed")}
          />
          {fixed
            ? <Hint>{t("ambient.bg.fixed.hint")}</Hint>
            : (
              <ValueRow
                label={t("ambient.bg.interval")}
                value={intervalValue}
                options={[...INTERVALS.map((s) => ({ value: String(s), label: t(`ambient.interval.${s}`) })), { value: "home", label: t("ambient.interval.home") }]}
                onChange={(v) => update((b) => v === "home" ? { ...b, onReturnHome: true } : { ...b, onReturnHome: false, intervalSec: Number(v) as typeof b.intervalSec })}
              />
            )}

          {!fixed && <>
          <Caption style={{ marginTop: 4 }}>{t("ambient.bg.shown")}</Caption>
          {bg.selectedRefs?.length ? <>
            <Hint>{t("ambient.lib.selectedPhotos", { n: String(bg.selectedRefs.length) })}</Hint>
            <Button label={t("ambient.lib.wholeFolders")} onActivate={() => update((b) => ({ ...b, selectedRefs: [] }))} />
          </> : <TileStrip>
            {visualSources(state.collections, snapshot.scan, state.settings.collections.favorites, state.settings.radio.favorites).map((entry) => {
              const tile = tileFor(entry, t);
              const on = bg.collections.includes(entry.id);
              const toggle = () => void runtime.toggleCollection(entry.id, !on);
              const actions = [
                { label: on ? t("ambient.menu.exclude") : t("ambient.menu.include"), onSelect: toggle },
                { label: t("ambient.menu.only"), onSelect: () => update((b) => ({ ...b, selectedRefs: [], collections: [entry.id] })) },
              ];
              return (
                <Tile
                  key={entry.id}
                  label={tile.label}
                  background={tile.background}
                  image={snapshot.previews[entry.id] ?? tile.image}
                  selected={on}
                  selectable
                  activateHint={on ? t("ambient.menu.exclude") : t("ambient.menu.include")}
                  menu={{ title: tile.label, hint: t("ambient.menu.options"), actions }}
                  onActivate={toggle}
                />
              );
            })}
          </TileStrip>}
          </>}

          <ChoiceRow
            label={t("ambient.bg.gameArtRow")}
            value={bg.gameArt}
            options={[{ value: "mine", label: t("ambient.short.gameArt.mine") }, { value: "blend", label: t("ambient.short.gameArt.blend") }, { value: "game", label: t("ambient.short.gameArt.game") }]}
            onChange={(gameArt) => update((b) => ({ ...b, gameArt }))}
          />
          <Hint>{t(`ambient.bg.gameArt.desc.${bg.gameArt}`)}</Hint>
          <ToggleRow label={t("ambient.game.trailers")} description={t("ambient.game.trailers.desc")} checked={bg.gameTrailers} onChange={(gameTrailers) => update((b) => ({ ...b, gameTrailers }))} />

          <MoreSettings id="ambient-bg-more" label={t("ambient.more")}>
            {!fixed && <>
              <ChoiceRow
                label={t("ambient.bg.order")}
                value={bg.order}
                options={[{ value: "shuffle", label: t("ambient.short.order.shuffle") }, { value: "sequential", label: t("ambient.short.order.sequential") }]}
                onChange={(order) => update((b) => ({ ...b, order }))}
              />
              <ChoiceRow
                label={t("ambient.bg.transition")}
                value={bg.transition}
                options={[{ value: "fade", label: t("ambient.transition.fade") }, { value: "kenburns", label: t("ambient.transition.kenburns") }]}
                onChange={(transition) => update((b) => ({ ...b, transition }))}
              />
            </>}
            <ToggleRow label={t("ambient.bg.library")} checked={bg.library} onChange={(library) => update((b) => ({ ...b, library }))} />
            <ToggleRow label={t("ambient.bg.optimize")} description={t("ambient.bg.optimize.desc")} checked={bg.optimizeVideos} onChange={(optimizeVideos) => update((b) => ({ ...b, optimizeVideos }))} />
            {bg.optimizeVideos && (
              <ChoiceRow
                label={t("ambient.bg.videoQuality")}
                value={bg.videoQuality}
                options={(["fluid", "saver", "sharp"] as const).map((q) => ({ value: q, label: t(`ambient.videoQuality.${q}`) }))}
                onChange={(videoQuality) => update((b) => ({ ...b, videoQuality }))}
              />
            )}
            <Caption>{t("ambient.perGame.title")}</Caption>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {Object.keys(bg.perGame).length ? t("ambient.perGame.count", { n: Object.keys(bg.perGame).length }) : t("ambient.perGame.none")}
            </div>
            {Object.keys(bg.perGame).filter((appid) => appid !== game?.appid).map((appid) => <Button key={appid} label={t("ambient.perGame.clear", { game: gameName(appid) })} onActivate={() => void runtime.clearGameBackground(appid)} />)}
            {game && (hasOwn
              ? <Button label={t("ambient.perGame.clear", { game: game.name })} onActivate={() => void runtime.clearSelectedGame()} />
              : snapshot.current && <Button label={t("ambient.perGame.assign", { game: game.name })} onActivate={() => void runtime.assignCurrentToSelectedGame()} />)}
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", marginTop: 4, flexShrink: 0, background: snapshot.motion === "freeze" ? theme.color.warn : theme.color.ok }} />
              {snapshot.motion === "freeze" ? t("ambient.power.frozen") : t("ambient.power.note", { percent: bg.lowBatteryPercent })}
            </div>
          </MoreSettings>
        </>
      )}
    </div>
  );
};
