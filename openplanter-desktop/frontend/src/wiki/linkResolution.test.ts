import { describe, expect, it } from "vitest";
import { resolveWikiMarkdownHref } from "./linkResolution";

describe("resolveWikiMarkdownHref", () => {
  it("normalizes root-relative wiki links", () => {
    expect(resolveWikiMarkdownHref("contracts/usaspending.md")).toBe("wiki/contracts/usaspending.md");
  });

  it("preserves canonical wiki paths", () => {
    expect(resolveWikiMarkdownHref("wiki/contracts/usaspending.md")).toBe("wiki/contracts/usaspending.md");
  });

  it("resolves relative links from the current drawer document", () => {
    expect(resolveWikiMarkdownHref("./other-file.md", {
      baseWikiPath: "wiki/contracts/usaspending.md",
    })).toBe("wiki/contracts/other-file.md");

    expect(resolveWikiMarkdownHref("../corporate/sec-edgar.md", {
      baseWikiPath: "wiki/contracts/usaspending.md",
    })).toBe("wiki/corporate/sec-edgar.md");
  });

  it("ignores fragments when resolving markdown docs", () => {
    expect(resolveWikiMarkdownHref("contracts/usaspending.md#summary")).toBe("wiki/contracts/usaspending.md");
  });

  it("decodes percent-encoded wiki path segments", () => {
    expect(resolveWikiMarkdownHref("wiki/Q1%20notes%20%28draft%29.md")).toBe(
      "wiki/Q1 notes (draft).md",
    );
  });

  it("preserves literal percent signs in wiki path segments", () => {
    expect(resolveWikiMarkdownHref("wiki/revenue%growth.md")).toBe("wiki/revenue%growth.md");
  });

  it("rejects non-wiki or unsafe links", () => {
    expect(resolveWikiMarkdownHref("https://example.com/doc.md")).toBeNull();
    expect(resolveWikiMarkdownHref("/tmp/doc.md")).toBeNull();
    expect(resolveWikiMarkdownHref("javascript:alert(1)")).toBeNull();
    expect(resolveWikiMarkdownHref("contracts/usaspending.txt")).toBeNull();
    expect(resolveWikiMarkdownHref("#summary")).toBeNull();
    expect(resolveWikiMarkdownHref("../../secret.md")).toBeNull();
    expect(resolveWikiMarkdownHref("contracts/usaspending.md?raw=1")).toBeNull();
    expect(resolveWikiMarkdownHref("wiki/%2Fsecret.md")).toBeNull();
    expect(resolveWikiMarkdownHref("wiki/folder%5Csecret.md")).toBeNull();
  });
});
