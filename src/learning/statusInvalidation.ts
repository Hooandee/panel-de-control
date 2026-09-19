const listeners = new Set<() => void>();
let version = 0;

export function notifyLearningStatusChanged(): void {
  version += 1;
  listeners.forEach((listener) => listener());
}

export function subscribeLearningStatus(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getLearningStatusVersion(): number {
  return version;
}
