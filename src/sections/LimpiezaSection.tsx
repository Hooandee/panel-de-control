import { useEffect, useRef } from "react";
import type { FC } from "react";
import { CleanupHubView } from "../cleaner/CleanupHubView";
import { useMediaCleaner } from "../cleaner/useMediaCleaner";
import { useProtonCleaner } from "../cleaner/useProtonCleaner";
import { useSteamCleaner } from "../cleaner/useSteamCleaner";

export const LimpiezaSection: FC = () => {
  const games = useSteamCleaner();
  const media = useMediaCleaner();
  const proton = useProtonCleaner();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    proton.queueScan();
    void games.scan().then(() => {
      if (mounted.current) void proton.scan();
    });
    return () => { mounted.current = false; };
  }, []);

  const refreshAll = () => {
    void media.scan();
    proton.queueScan();
    void games.scan().then(() => {
      if (mounted.current) void proton.scan();
    });
  };

  return <CleanupHubView
    games={games}
    media={media}
    proton={proton}
    onRefresh={refreshAll}
    refreshing={games.busy || media.loading || media.cleaning || proton.busy}
  />;
};
