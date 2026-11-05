// Decky raises backend errors with an empty message on some versions; the code
// then only survives as the last line of the Python traceback.
export function upscalerErrorCode(error: unknown): string {
  if (typeof error === "string") return error || "generic";
  const fields = error && typeof error === "object" ? error as Record<string, unknown> : {};
  const message = typeof fields.message === "string" ? fields.message.trim() : "";
  if (message) return message;
  for (const key of ["pythonTraceback", "stack"]) {
    const text = fields[key];
    const code = typeof text === "string" ? text.match(/Exception: ([a-z0-9_]+)\s*$/)?.[1] : undefined;
    if (code) return code;
  }
  return "generic";
}
