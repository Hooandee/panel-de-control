// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { forwardRef, type FC, type HTMLAttributes, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SectionDef } from "../sections/types";

type FocusableProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode;
  focusClassName?: string;
  onActivate?: () => void;
  preferredFocus?: boolean;
  navEntryPreferPosition?: number;
};

vi.mock("@decky/ui", () => ({
  NavEntryPositionPreferences: { PREFERRED_CHILD: 4 },
  Focusable: forwardRef<HTMLDivElement, FocusableProps>(function Focusable(
    { children, focusClassName, onActivate, onClick, preferredFocus, navEntryPreferPosition, ...props },
    ref,
  ) {
    return (
      <div
        ref={ref}
        data-preferred-focus={preferredFocus ? "true" : undefined}
        data-nav-entry-prefer-position={navEntryPreferPosition}
        data-focus-class-name={focusClassName}
        onClick={(event) => {
          onActivate?.();
          onClick?.(event);
        }}
        {...props}
      >
        {children}
      </div>
    );
  }),
}));

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));

import { Dashboard } from "./Dashboard";

const NullBody: FC = () => null;
const icon = () => <span data-testid="dashboard-test-icon" aria-hidden="true" />;

function sections(Power: FC = NullBody, Settings: FC = NullBody): SectionDef[] {
  return [
    {
      id: "power",
      labelKey: "nav.power",
      descriptionKey: "nav.power.desc",
      accent: "#287d8c",
      icon,
      Component: Power,
    },
    {
      id: "settings",
      labelKey: "nav.settings",
      descriptionKey: "nav.settings.desc",
      accent: "#626b73",
      icon,
      Component: Settings,
    },
  ];
}

describe("Dashboard", () => {
  const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

  beforeEach(() => {
    window.localStorage.setItem("panel-de-control-lang", "es");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: originalScrollIntoView,
    });
  });

  it("renders resolved sections in source order without mounting their bodies", () => {
    const Power = vi.fn(() => <div>power body</div>);
    const Settings = vi.fn(() => <div>settings body</div>);

    render(<Dashboard sections={sections(Power, Settings)} activeId="power" onOpenSection={vi.fn()} />);

    expect(screen.getAllByTestId("dashboard-card").map((card) => card.dataset.sectionId)).toEqual(["power", "settings"]);
    expect(Power).not.toHaveBeenCalled();
    expect(Settings).not.toHaveBeenCalled();
  });

  it("opens a destination once when Decky raises activation and click together", () => {
    const onOpenSection = vi.fn();

    render(<Dashboard sections={sections()} activeId="power" onOpenSection={onOpenSection} />);

    fireEvent.click(screen.getByRole("button", { name: /Potencia\. Rendimiento y consumo del dispositivo\./ }));

    expect(onOpenSection).toHaveBeenCalledExactlyOnceWith("power");
  });

  it("exposes the complete section description in each card name", () => {
    render(<Dashboard sections={sections()} activeId="power" onOpenSection={vi.fn()} />);

    expect(screen.getAllByTestId("dashboard-card")[0].getAttribute("aria-label")).toBe(
      "Potencia. Rendimiento y consumo del dispositivo.",
    );
  });

  it("uses the localized label when a custom view has an empty label", () => {
    const customView: SectionDef = {
      id: "custom-view",
      label: "",
      labelKey: "customize.views.namePlaceholder",
      descriptionKey: "customize.views.cardDesc",
      accent: "#287d8c",
      icon,
      Component: NullBody,
    };

    render(<Dashboard sections={[customView]} activeId="custom-view" onOpenSection={vi.fn()} />);

    expect(screen.getByRole("button", { name: /^Mi vista\./ })).toBeTruthy();
  });

  it("uses the grid's preferred-child entry contract for the active section", () => {
    const scrollIntoView = HTMLElement.prototype.scrollIntoView as ReturnType<typeof vi.fn>;

    render(<Dashboard sections={sections()} activeId="settings" onOpenSection={vi.fn()} />);

    expect(screen.getByTestId("dashboard-grid").dataset.navEntryPreferPosition).toBe("4");
    expect(screen.getAllByTestId("dashboard-card")[0].dataset.preferredFocus).toBeUndefined();
    expect(screen.getAllByTestId("dashboard-card")[1].dataset.preferredFocus).toBe("true");
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
  });

  it("reveals the newly focused card without taking focus itself", () => {
    render(<Dashboard sections={sections()} activeId="power" onOpenSection={vi.fn()} />);
    const laterCard = screen.getAllByTestId("dashboard-card")[1];
    const scrollIntoView = vi.fn();
    Object.defineProperty(laterCard, "scrollIntoView", { configurable: true, value: scrollIntoView });

    fireEvent.focus(laterCard);

    expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ block: "nearest" });
  });

  it("keeps the settings badge alongside its card text", () => {
    render(
      <Dashboard
        sections={sections()}
        activeId="power"
        settingsBadge={<span>Actualización disponible</span>}
        onOpenSection={vi.fn()}
      />,
    );

    expect(screen.getByText("Actualización disponible")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ajustes\. Personalización, actualizaciones e información\./ })).toBeTruthy();
  });

  it("starts directly with the launcher grid without a second navigation choice", () => {
    const { container } = render(<Dashboard sections={sections()} activeId="power" onOpenSection={vi.fn()} />);
    const grid = container.querySelector('[data-testid="dashboard-grid"]');

    expect(screen.queryByText("Inicio")).toBeNull();
    expect(screen.queryByText("Elige una herramienta")).toBeNull();
    expect(screen.queryByRole("button", { name: "Vista de pestañas" })).toBeNull();
    expect(grid).toBeTruthy();
  });

  it("uses flat launcher cells with white glyphs and compact descriptions", () => {
    render(<Dashboard sections={sections()} activeId="power" onOpenSection={vi.fn()} />);

    const card = screen.getAllByTestId("dashboard-card")[0];
    const surface = card.firstElementChild as HTMLElement;
    const glyph = screen.getAllByTestId("dashboard-test-icon")[0];
    const description = screen.getByText("Rendimiento y consumo del dispositivo.");

    expect(surface.style.background).toBe("transparent");
    expect(glyph.parentElement?.style.color).toBe("white");
    expect(description.style.maxHeight).toBe("30px");
  });

  it("gives each launcher cell a section-coloured focus surface", () => {
    render(<Dashboard sections={sections()} activeId="power" onOpenSection={vi.fn()} />);

    const card = screen.getAllByTestId("dashboard-card")[0];
    const surface = card.firstElementChild as HTMLElement;

    expect(card.classList.contains("pdc-dashboard-card")).toBe(true);
    expect(card.dataset.focusClassName).toBe("pdc-dashboard-card-focused");
    expect(card.style.getPropertyValue("--pdc-card-accent")).toBe("#287d8c");
    expect(surface.classList.contains("pdc-dashboard-card-surface")).toBe(true);
  });

  it("renders no cards for an empty resolved list", () => {
    render(<Dashboard sections={[]} activeId={null} onOpenSection={vi.fn()} />);

    expect(screen.queryAllByTestId("dashboard-card")).toHaveLength(0);
  });
});
