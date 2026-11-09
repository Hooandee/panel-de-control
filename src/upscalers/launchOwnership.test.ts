import { describe, expect, it } from "vitest";
import { planLaunchOverlay } from "./launchOwnership";

describe("launch ownership", () => {
  it("keeps a custom profile and Mako wrapper arguments on apply and removal", () => {
    const input = 'LSFGVK_PROFILE="my profile" ~/.local/bin/mako-launch --preset quality %command% -dx12';
    const next = planLaunchOverlay(input, { env: { LSFGVK_PROFILE: "pdc-123" }, wrappers: ["~/.local/bin/mako-run"] })!;
    expect(next.value).toBe(input);
    expect(next.receipt.env).toEqual([]);
    expect(next.receipt.wrappers.added).toEqual([]);
    expect(next.preserved.env).toEqual(["LSFGVK_PROFILE"]);
    expect(next.preserved.wrappers).toContain("~/.local/bin/mako-launch");
    expect(planLaunchOverlay(next.value, {}, next.receipt)?.value).toBe(input);
  });

  it("restores explicitly replaced values with their original quotes", () => {
    const input = 'ENABLE_GAMESCOPE_WSI="1" mangohud %command% -dx12';
    const next = planLaunchOverlay(input, { env: { ENABLE_GAMESCOPE_WSI: "0" }, replaceEnv: ["ENABLE_GAMESCOPE_WSI"] })!;
    expect(next.value).toBe('ENABLE_GAMESCOPE_WSI=0 mangohud %command% -dx12');
    expect(next.receipt.env).toEqual([{ name: "ENABLE_GAMESCOPE_WSI", before: '"1"', applied: "0" }]);
    expect(planLaunchOverlay(next.value, {}, next.receipt)?.value).toBe(input);
  });

  it("preserves user edits after installation instead of deleting them or reapplying over them", () => {
    const desired = { env: { LSFGVK_PROFILE: "pdc-123" }, wrappers: ["~/.local/bin/mako-run"] };
    const next = planLaunchOverlay("%command% -dx12", desired)!;
    const edited = next.value.replace("pdc-123", '"custom profile"').replace("mako-run", "mako-run --preset quality");
    for (const intent of [{}, desired]) {
      const restored = planLaunchOverlay(edited, intent, next.receipt)!;
      expect(restored.value).toBe(edited);
      expect(restored.preserved.env).toContain("LSFGVK_PROFILE");
      expect(restored.preserved.wrappers).toContain("~/.local/bin/mako-run");
    }
  });

  it("reapplies without losing original ownership and switches wrappers without leftovers", () => {
    const input = 'WINEDLLOVERRIDES="winmm=b;dxgi=n,b" %command% --skip';
    const desired = { env: { ENABLE_GAMESCOPE_WSI: "0" }, wrappers: ["~/.local/bin/mako-run"] };
    const first = planLaunchOverlay(input, desired)!;
    const second = planLaunchOverlay(first.value, desired, first.receipt)!;
    expect(second).toEqual(first);
    const switched = planLaunchOverlay(second.value, { wrappers: ["~/lsfg"] }, second.receipt)!;
    expect(switched.value).toBe('WINEDLLOVERRIDES="winmm=b;dxgi=n,b" ~/lsfg %command% --skip');
    expect(planLaunchOverlay(switched.value, {}, switched.receipt)?.value).toBe(input);
  });

  it("leaves preexisting Mako variants and lsfg wrappers untouched", () => {
    for (const wrapper of ['"/home/user/mako-framegen"', "mako-run", "~/lsfg"]) {
      const input = `${wrapper} --custom 3 %command%`;
      const target = wrapper.includes("mako") ? "~/.local/bin/mako-run" : "~/lsfg";
      const applied = planLaunchOverlay(input, { wrappers: [target] })!;
      expect(applied.value).toBe(input);
      expect(planLaunchOverlay(input, {}, applied.receipt)?.value).toBe(input);
    }
  });

  it("adds wrappers outside Armada and removes only its addition", () => {
    const input = "/usr/libexec/armada/armada-game-launch %command%";
    const next = planLaunchOverlay(input, { wrappers: ["~/.local/bin/mako-run"] })!;
    expect(next.value).toBe("~/.local/bin/mako-run /usr/libexec/armada/armada-game-launch %command%");
    expect(planLaunchOverlay(next.value, {}, next.receipt)?.value).toBe(input);
  });

  it("rejects ambiguous input and invalid desired tokens without changing its receipt", () => {
    const previous = planLaunchOverlay("", { env: { LSFGVK_PROFILE: "pdc-123" } })!.receipt;
    const saved = structuredClone(previous);
    for (const input of ['sh -c "%command%"', "X=1 X=2 %command%", "%command% | tee out", 'X="unterminated %command%']) {
      expect(planLaunchOverlay(input, {}, previous)).toBeNull();
    }
    expect(planLaunchOverlay("%command%", { env: { X: "1; touch nope" } }, previous)).toBeNull();
    expect(planLaunchOverlay("%command%", { wrappers: ["mako-run --bad"] }, previous)).toBeNull();
    expect(previous).toEqual(saved);
  });
});


it("preserves deliberate removal after a confirmed installation", () => {
  const active = planLaunchOverlay("%command%", { env: { MAKO_CONFIG: "owned" }, wrappers: ["mako-run"] })!;
  const next = planLaunchOverlay("%command%", { env: { MAKO_CONFIG: "owned" }, wrappers: ["mako-run"] }, active.receipt)!;
  expect(next.value).toBe("%command%");
  expect(next.preserved).toEqual({ env: ["MAKO_CONFIG"], wrappers: ["mako-run"] });
});

it("can retry an unapplied pending intent without classifying it as a user edit", () => {
  const active = planLaunchOverlay("%command%", { env: { MAKO_CONFIG: "owned" }, wrappers: ["mako-run"] })!;
  const next = planLaunchOverlay("%command%", { env: { MAKO_CONFIG: "owned" }, wrappers: ["mako-run"] }, { ...active.receipt, pending: true })!;
  expect(next.value).toBe("MAKO_CONFIG=owned mako-run %command%");
  expect(next.preserved).toEqual({ env: [], wrappers: [] });
});

it("removes its own wrapper after another section appended one, so it can be enabled again", () => {
  const mako = "/home/deck/.local/bin/mako-launch";
  const active = planLaunchOverlay("%command%", { wrappers: [mako] })!;
  const withHud = `${mako} mangohud %command%`;
  const disabled = planLaunchOverlay(withHud, {}, active.receipt)!;
  expect(disabled.value).toBe("mangohud %command%");
  expect(disabled.preserved.wrappers).toEqual([]);
  const again = planLaunchOverlay(disabled.value, { wrappers: [mako] }, disabled.receipt)!;
  expect(again.value).toBe(`mangohud ${mako} %command%`);
  expect(again.receipt.wrappers.added).toEqual([mako]);
  expect(planLaunchOverlay(again.value, {}, again.receipt)?.value).toBe("mangohud %command%");
});

it("removes its own wrapper after the user removed one that was there before", () => {
  const active = planLaunchOverlay("gamemoderun mangohud %command% -dx12", { wrappers: ["mako-run"] })!;
  expect(active.value).toBe("gamemoderun mangohud mako-run %command% -dx12");
  const disabled = planLaunchOverlay("gamemoderun mako-run %command% -dx12", {}, active.receipt)!;
  expect(disabled.value).toBe("gamemoderun %command% -dx12");
  expect(disabled.preserved.wrappers).toEqual([]);
  expect(planLaunchOverlay(disabled.value, {}, disabled.receipt)?.value).toBe(disabled.value);
});
