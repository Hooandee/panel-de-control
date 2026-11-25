import { useEffect, useRef, useState, type FC } from "react";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { downloadPace, megabytes, type PaceSample } from "./model";
import { Spinner } from "./parts";
import type { UpscalerJob } from "./types";

export const JobProgress: FC<{ job: UpscalerJob }> = ({ job }) => {
  const { t } = useI18n();
  const downloading = job.phase === "download";
  const determinate = downloading && job.total > 0;
  const ratio = determinate ? Math.min(1, job.done / job.total) : 0;
  const sample = useRef<PaceSample | null>(null);
  const [pace, setPace] = useState<{ rate: number; eta: number | null } | null>(null);
  const shown = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    shown.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, []);
  useEffect(() => {
    if (!downloading) return;
    const now = { done: job.done, at: Date.now() };
    if (sample.current && now.at - sample.current.at >= 900) {
      setPace((last) => downloadPace(sample.current!, now, job.total, last?.rate ?? 0));
      sample.current = now;
    } else if (!sample.current) {
      sample.current = now;
    }
  }, [downloading, job.done, job.total]);
  const phaseKey = `up.phase.${job.phase}`;
  const label = determinate
    ? t("up.phase.download", { done: megabytes(job.done), total: megabytes(job.total) })
    : downloading ? t("up.phase.downloading")
    : t(phaseKey) === phaseKey ? t("up.phase.prepare") : t(phaseKey);
  const rate = pace ? (pace.rate / (1024 * 1024)).toFixed(1) : "";
  const step = !downloading || !pace ? null
    : pace.rate < 1024 ? t("up.phase.stalled")
    : determinate && pace.eta !== null && pace.eta < 3600 ? t("up.phase.pace", { rate, eta: formatEta(pace.eta) })
    : t("up.phase.rate", { rate });
  return (
    <div ref={shown} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, animation: "pdc-up-in 200ms ease" }} data-pdc-up-motion>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.caption + 1 }}>
        <Spinner size={12} /> {label}
      </div>
      {step && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{step}</span>}
      <div style={{ height: 4, borderRadius: 2, background: theme.color.hairline, overflow: "hidden" }}>
        <div
          data-pdc-up-motion
          data-progress={determinate ? "determinate" : "indeterminate"}
          style={{
            height: "100%", width: determinate ? `${ratio * 100}%` : "35%", background: theme.color.accent,
            transition: "width 200ms linear", animation: determinate ? "none" : "pdc-up-shimmer 1.2s ease-in-out infinite",
          }}
        />
      </div>
    </div>
  );
};

function formatEta(seconds: number): string {
  return seconds < 60 ? `${seconds} s` : `${Math.ceil(seconds / 60)} min`;
}
