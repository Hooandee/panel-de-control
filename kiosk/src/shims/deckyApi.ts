import type { ReactNode } from "react";

export const KIOSK_TOKEN_HEADER = "X-PDC-Kiosk";

export function kioskToken(search: string = window.location.search): string {
  return new URLSearchParams(search).get("k") ?? "";
}

export class KioskRpcError extends Error {
  constructor(readonly method: string, readonly status: number, detail: string) {
    super(`${method}: ${status} ${detail}`.trim());
  }
}

export const callable =
  <Args extends unknown[] = [], Return = void>(method: string) =>
  async (...args: Args): Promise<Return> => {
    const response = await fetch("/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json", [KIOSK_TOKEN_HEADER]: kioskToken() },
      body: JSON.stringify({ method, args }),
    });
    const body = (await response.json().catch(() => ({}))) as { result?: Return; error?: string };
    if (!response.ok || body.error !== undefined) {
      throw new KioskRpcError(method, response.status, body.error ?? "");
    }
    return body.result as Return;
  };

export interface KioskToast {
  id: number;
  title?: ReactNode;
  body?: ReactNode;
}

let toasts: KioskToast[] = [];
let toastSeq = 0;
const toastListeners = new Set<() => void>();
const TOAST_MS = 3500;

export function subscribeToasts(listener: () => void): () => void {
  toastListeners.add(listener);
  return () => toastListeners.delete(listener);
}

export const currentToasts = (): KioskToast[] => toasts;

function setToasts(next: KioskToast[]): void {
  toasts = next;
  toastListeners.forEach((l) => l());
}

export const toaster = {
  toast(input: { title?: ReactNode; body?: ReactNode; duration?: number }) {
    const id = ++toastSeq;
    setToasts([...toasts, { id, title: input.title, body: input.body }]);
    const dismiss = () => setToasts(toasts.filter((t) => t.id !== id));
    setTimeout(dismiss, input.duration ?? TOAST_MS);
    return { dismiss };
  },
};

export const definePlugin = <T>(factory: () => T): (() => T) => factory;
