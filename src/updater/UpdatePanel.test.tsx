// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, ...props }: any) => <button type="button" {...props}>{children}</button>,
  ModalRoot: ({ children }: any) => <section>{children}</section>,
  showModal: vi.fn(),
}));

vi.mock("./useUpdate", () => ({
  useUpdate: () => ({
    info: null,
    status: "idle",
    hasUpdate: false,
    check: vi.fn(async () => null),
    install: vi.fn(async () => null),
    restart: vi.fn(),
  }),
}));

vi.mock("../components/FocusRoot", () => ({
  FocusRoot: ({ children }: any) => <div>{children}</div>,
}));

import { UpdateModal } from "./UpdateModal";
import { UpdatePanel } from "./UpdatePanel";

afterEach(cleanup);

describe("Italian updater", () => {
  it("renders the panel chrome in Italian", () => {
    expect(() => render(<UpdatePanel lang="it" version="0.34.0" />)).not.toThrow();

    expect(screen.getByText(/Versione 0\.34\.0/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cerca aggiornamenti" })).toBeTruthy();
  });

  it("renders the update modal chrome in Italian", () => {
    expect(() => render(
      <UpdateModal lang="it" latest="0.35.0" notes="" />,
    )).not.toThrow();

    expect(screen.getByText("Novità v0.35.0")).toBeTruthy();
    expect(screen.getByText("Nessuna nota per questa versione.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Installa aggiornamento" })).toBeTruthy();
  });
});
