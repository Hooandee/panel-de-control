import qrcode from "qrcode-generator";

/** QR modules as one SVG path, drawn locally: no markup string is injected into Steam's page. */
export function qrPath(text: string): { size: number; path: string } {
  const code = qrcode(0, "M");
  code.addData(text, "Byte");
  code.make();
  const size = code.getModuleCount();
  let path = "";
  for (let row = 0; row < size; row++) {
    for (let col = 0; col < size; col++) if (code.isDark(row, col)) path += `M${col} ${row}h1v1h-1z`;
  }
  return { size, path };
}
