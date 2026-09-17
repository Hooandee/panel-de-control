interface SurfaceClaim {
  id: string;
  token: symbol;
}

const claims: SurfaceClaim[] = [];
const listeners = new Set<() => void>();
let activeSurface: symbol | null = null;

function publishIfChanged(): void {
  const next = claims[claims.length - 1]?.token ?? null;
  if (next === activeSurface) return;
  activeSurface = next;
  listeners.forEach((listener) => listener());
}

export function claimQamSurface(id: string, token = Symbol(id)): () => void {
  const claim = { id, token };
  claims.push(claim);
  publishIfChanged();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    const index = claims.findIndex((candidate) => candidate.token === claim.token);
    if (index >= 0) claims.splice(index, 1);
    publishIfChanged();
  };
}

export function getActiveQamSurface(): symbol | null {
  return activeSurface;
}

export function subscribeActiveQamSurface(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
