// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
  Dropdown: ({ rgOptions, selectedOption, onChange }: {
    rgOptions: { data: string; label: string }[];
    selectedOption?: string;
    onChange: (option: { data: string }) => void;
  }) => (
    <select
      aria-label="key-picker"
      value={selectedOption ?? ""}
      onChange={(event) => onChange({ data: event.target.value })}
    >
      {rgOptions.map((option) => (
        <option key={option.data} value={option.data}>{option.label}</option>
      ))}
    </select>
  ),
  Focusable: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ModalRoot: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  showModal: vi.fn(),
}));

vi.mock("../components/FocusRoot", () => ({
  FocusRoot: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import { addChordKey, KeyboardChordEditorBody } from "./KeyboardChordEditor";

const targets = ["KeyLeftCtrl", "KeyTab", "KeyA", "KeyB", "KeyC"];

describe("KeyboardChordEditor", () => {
  afterEach(cleanup);

  it("builds an ordered Ctrl+Tab chord and saves it", () => {
    const onSave = vi.fn();
    render(<KeyboardChordEditorBody initialKeys={[]} keyTargets={targets} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "mandos.shortcut.add" }));
    fireEvent.change(screen.getByRole("combobox", { name: "key-picker" }), {
      target: { value: "KeyTab" },
    });
    fireEvent.click(screen.getByRole("button", { name: "mandos.shortcut.add" }));
    fireEvent.click(screen.getByRole("button", { name: "mandos.shortcut.save" }));

    expect(onSave).toHaveBeenCalledWith(["KeyLeftCtrl", "KeyTab"]);
  });

  it("removes selected keys from the picker and rejects duplicates", () => {
    render(<KeyboardChordEditorBody initialKeys={["KeyLeftCtrl"]} keyTargets={targets} onSave={vi.fn()} />);

    expect(screen.queryByRole("option", { name: "Ctrl" })).toBeNull();
    const existing = ["KeyLeftCtrl"];
    expect(addChordKey(existing, "KeyLeftCtrl")).toBe(existing);
  });

  it("caps chords at four keys", () => {
    render(<KeyboardChordEditorBody
      initialKeys={targets.slice(0, 4)}
      keyTargets={targets}
      onSave={vi.fn()}
    />);

    expect((screen.getByRole("button", { name: "mandos.shortcut.add" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(addChordKey(targets.slice(0, 4), "KeyC")).toEqual(targets.slice(0, 4));
  });

  it("cancels without saving", () => {
    const onSave = vi.fn();
    const closeModal = vi.fn();
    render(<KeyboardChordEditorBody
      initialKeys={["KeyA"]}
      keyTargets={targets}
      onSave={onSave}
      closeModal={closeModal}
    />);

    fireEvent.click(screen.getByRole("button", { name: "mandos.shortcut.cancel" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(closeModal).toHaveBeenCalledOnce();
  });
});
