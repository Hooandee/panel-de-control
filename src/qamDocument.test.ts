import { describe, expect, it } from "vitest";

import { getQamDocument, setQamDocument } from "./qamDocument";

describe("getQamDocument", () => {
  it("returns the document published by the panel shell", () => {
    const doc = { hidden: false } as Document;
    setQamDocument(doc);

    expect(getQamDocument()).toBe(doc);
  });
});
