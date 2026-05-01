import { describe, expect, it } from "vitest";
import {
  createWikiMarkdownRenderer,
  renderGeneratedInvestigationHomepageMarkdown,
  renderWikiMarkdown,
} from "./markdown";

describe("wiki markdown rendering", () => {
  it("adds stable ids to generated to-do headings", () => {
    const md = createWikiMarkdownRenderer();

    const html = renderWikiMarkdown(md, "### TODO .todo");

    expect(html).toContain('<h3 id="todo-todo">TODO .todo</h3>');
  });

  it("strips generated to-do anchor markers before rendering", () => {
    const md = createWikiMarkdownRenderer();

    const html = renderGeneratedInvestigationHomepageMarkdown(
      md,
      ['<a id="todo-todo_2"></a>', "### TODO todo_2"].join("\n"),
    );

    expect(html).not.toContain('<a id="todo-todo_2"');
    expect(html).not.toContain("&lt;a");
    expect(html).toContain('<h3 id="todo-todo_2">TODO todo_2</h3>');
  });

  it("preserves safe manual to-do anchor markers", () => {
    const md = createWikiMarkdownRenderer();

    const html = renderWikiMarkdown(md, ['<a id="todo-manual"></a>', "### Manual anchor"].join("\n"));

    expect(html).toContain('<a id="todo-manual" class="wiki-anchor"></a>');
    expect(html).not.toContain("&lt;a");
  });
});
