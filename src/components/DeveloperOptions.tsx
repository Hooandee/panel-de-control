import { FC, useEffect, useState } from "react";
import { ButtonItem, Focusable, ToggleField } from "@decky/ui";

import {
  answerRemoteAccessPairing,
  closeRemoteAccessPairing,
  forgetRemoteAccessKeys,
  getRemoteAccessState,
  openRemoteAccessPairing,
  RemoteAccessState,
  setRemoteAccessEnabled,
} from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";

const IDLE_POLL_MS = 4000;
const PAIRING_POLL_MS = 1000;

const mono = { fontFamily: "monospace", fontSize: theme.font.caption, wordBreak: "break-all" as const };

function remoteAccessStatusKey(state: RemoteAccessState): string | null {
  if (!state.supported) return "dev.ssh.unsupported";
  if (!state.enabled) return null;
  if (!state.user) return "dev.ssh.noUser";
  if (state.running) return "dev.ssh.running";
  return state.error ? "dev.ssh.error" : "dev.ssh.starting";
}

export const DeveloperOptions: FC<{ onHide: () => void }> = ({ onHide }) => {
  const { t } = useI18n();
  const [state, setState] = useState<RemoteAccessState | null>(null);
  const [confirmForget, setConfirmForget] = useState(false);
  const pairing = state?.pairing ?? null;

  useEffect(() => {
    let alive = true;
    const read = () => getRemoteAccessState().then((next) => { if (alive) setState(next); }).catch(() => {});
    read();
    const id = window.setInterval(read, pairing ? PAIRING_POLL_MS : IDLE_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [pairing !== null]);

  const apply = (call: Promise<RemoteAccessState>) => {
    call.then(setState).catch(() => getRemoteAccessState().then(setState).catch(() => {}));
  };

  const hide = (
    <ButtonItem layout="below" onClick={onHide}>
      {t("dev.hide")}
    </ButtonItem>
  );
  const title = (
    <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, fontWeight: 600 }}>
      {t("dev.title")}
    </div>
  );
  if (!state) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {title}
        {hide}
      </div>
    );
  }

  const address = state.addresses[0] ?? "<ip>";
  const statusKey = remoteAccessStatusKey(state);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {title}

      <ToggleField
        label={t("dev.ssh")}
        description={t("dev.ssh.desc", { port: state.port })}
        checked={state.enabled}
        disabled={!state.supported}
        onChange={(enabled) => {
          setState({ ...state, enabled });
          apply(setRemoteAccessEnabled(enabled));
        }}
        bottomSeparator="none"
      />

      {statusKey && (
        <div style={statusKey === "dev.ssh.running" ? mono : { fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t(statusKey, { port: state.port, user: state.user ?? "", address, error: state.error ?? "" })}
        </div>
      )}

      {state.enabled && state.running && !pairing && (
        <ButtonItem layout="below" description={t("dev.ssh.pair.desc")} onClick={() => apply(openRemoteAccessPairing())}>
          {t("dev.ssh.pair")}
        </ButtonItem>
      )}

      {pairing && !pairing.pending && (
        <>
          <div style={mono}>
            {t("dev.ssh.pair.waiting", { seconds: pairing.expires_in, address, port: pairing.port })}
          </div>
          <ButtonItem layout="below" onClick={() => apply(closeRemoteAccessPairing())}>
            {t("dev.ssh.pair.cancel")}
          </ButtonItem>
        </>
      )}

      {pairing?.pending && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textPrimary }}>
            {t("dev.ssh.pair.request", { peer: pairing.pending.peer })}
          </div>
          <div style={mono}>{pairing.pending.fingerprint}</div>
          {pairing.pending.comment && <div style={mono}>{pairing.pending.comment}</div>}
          <Focusable style={{ display: "flex", gap: theme.space.sm }} flow-children="horizontal">
            <ButtonItem layout="below" onClick={() => apply(answerRemoteAccessPairing(true))}>
              {t("dev.ssh.pair.accept")}
            </ButtonItem>
            <ButtonItem layout="below" onClick={() => apply(answerRemoteAccessPairing(false))}>
              {t("dev.ssh.pair.reject")}
            </ButtonItem>
          </Focusable>
        </>
      )}

      {state.keys.length > 0 && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("dev.ssh.keys", { count: state.keys.length })}
          </div>
          {state.keys.map((key) => (
            <div key={key.fingerprint} style={mono}>{key.comment || key.fingerprint}</div>
          ))}
          <ButtonItem
            layout="below"
            onClick={() => {
              if (!confirmForget) {
                setConfirmForget(true);
                return;
              }
              setConfirmForget(false);
              apply(forgetRemoteAccessKeys());
            }}
          >
            {t(confirmForget ? "dev.ssh.forget.confirm" : "dev.ssh.forget")}
          </ButtonItem>
        </>
      )}

      {hide}
    </div>
  );
};
