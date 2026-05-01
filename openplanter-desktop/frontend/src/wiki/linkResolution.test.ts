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
    expect(
      resolveWikiMarkdownHref("wiki/Q1%20notes%20%28draft%29.md", {
        decodePercentEncoding: true,
      }),
    ).toBe("wiki/Q1 notes (draft).md");
  });

  it("decodes generated investigation homepage links relative to wiki root", () => {
    expect(
      resolveWikiMarkdownHref("../docs/wire%20transfer%20records%28v2%29.md", {
        baseWikiPath: "wiki/investigations/acme.md",
        decodePercentEncoding: true,
      }),
    ).toBe("wiki/docs/wire transfer records(v2).md");
  });

  it("preserves literal percent-hex text in wiki path segments by default", () => {
    expect(resolveWikiMarkdownHref("wiki/revenue%20growth.md")).toBe(
      "wiki/revenue%20growth.md",
    );
  });

  it("preserves literal percent signs in wiki path segments", () => {
    expect(resolveWikiMarkdownHref("wiki/revenue%growth.md")).toBe("wiki/revenue%growth.md");
  });

  it("preserves literal encoded delimiters by default", () => {
    expect(resolveWikiMarkdownHref("wiki/report%23draft.md")).toBe("wiki/report%23draft.md");
    expect(resolveWikiMarkdownHref("wiki/report%3Fdraft.md")).toBe("wiki/report%3Fdraft.md");
    expect(resolveWikiMarkdownHref("wiki/folder%2Fsecret.md")).toBe(
      "wiki/folder%2Fsecret.md",
    );
    expect(resolveWikiMarkdownHref("wiki/folder%5Csecret.md")).toBe(
      "wiki/folder%5Csecret.md",
    );
  });

  it("decodes encoded literal percent signs for generated links", () => {
    expect(
      resolveWikiMarkdownHref("wiki/revenue%2520growth.md", {
        decodePercentEncoding: true,
      }),
    ).toBe("wiki/revenue%20growth.md");
  });

  it("decodes generated percent-encoded literal percent paths", () => {
    expect(
      resolveWikiMarkdownHref("../docs/revenue%2520growth.md", {
        baseWikiPath: "wiki/investigations/acme.md",
        decodePercentEncoding: true,
      }),
    ).toBe("wiki/docs/revenue%20growth.md");
  });

  it("rejects non-wiki or unsafe links", () => {
    expect(resolveWikiMarkdownHref("https://example.com/doc.md")).toBeNull();
    expect(resolveWikiMarkdownHref("/tmp/doc.md")).toBeNull();
    expect(resolveWikiMarkdownHref("javascript:alert(1)")).toBeNull();
    expect(resolveWikiMarkdownHref("contracts/usaspending.txt")).toBeNull();
    expect(resolveWikiMarkdownHref("#summary")).toBeNull();
    expect(resolveWikiMarkdownHref("../../secret.md")).toBeNull();
    expect(resolveWikiMarkdownHref("contracts/usaspending.md?raw=1")).toBeNull();
    expect(
      resolveWikiMarkdownHref("wiki/%2Fsecret.md", {
        decodePercentEncoding: true,
      }),
    ).toBeNull();
    expect(
      resolveWikiMarkdownHref("wiki/folder%5Csecret.md", {
        decodePercentEncoding: true,
      }),
    ).toBeNull();
  });
});
