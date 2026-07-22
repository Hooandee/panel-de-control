import { FC } from "react";

import { SectionView } from "../customize/blocks";
import { useFanState } from "../fans/useFanState";
import { Loading } from "../components/Loading";

export const VentiladoresSection: FC = () => {
  const { state } = useFanState();
  if (!state) return <Loading />;
  return <SectionView sectionId="fans" />;
};
