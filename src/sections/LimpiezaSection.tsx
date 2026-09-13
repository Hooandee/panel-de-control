import { FC } from "react";
import { SteamCleanerView } from "../cleaner/SteamCleanerView";
import { useSteamCleaner } from "../cleaner/useSteamCleaner";

export const LimpiezaSection: FC = () => <SteamCleanerView controller={useSteamCleaner()} />;
