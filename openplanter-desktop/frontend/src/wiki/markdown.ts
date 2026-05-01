import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

function safeHeadingComponent(text: string): string {
  const component = text
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[.-]+|[.-]+$/g, "");
  return component || "artifact";
}

function markdownHeadingId(text: string): string {
  const trimmed = text.trim();
  const todoMatch = /^TODO\s+(.+)$/i.exec(trimmed);
  if (todoMatch) {
    return `todo-${safeHeadingComponent(todoMatch[1].toLowerCase())}`;
  }
  return safeHeadingComponent(trimmed.toLowerCase());
}

function stripSafeTodoAnchors(markdown: string): string {
  return markdown.replace(/^<a id="todo-[A-Za-z0-9._-]+"><\/a>\r?\n?/gm, "");
}

export function createWikiMarkdownRenderer(): MarkdownIt {
  const md = new MarkdownIt({
    html: false,
    linkify: true,
    typographer: false,
    highlight(str: string, lang: string) {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(str, { language: lang }).value;
        } catch {
          // Fall through to markdown-it default escaping.
        }
      }
      return "";
    },
  });

  const defaultHeadingOpenRenderer =
    md.renderer.rules.heading_open ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
  md.renderer.rules.heading_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const inlineToken = tokens[idx + 1];
    if (!token.attrGet("id") && inlineToken?.type === "inline") {
      const id = markdownHeadingId(inlineToken.content);
      if (id) {
        token.attrSet("id", id);
      }
    }
    return defaultHeadingOpenRenderer(tokens, idx, options, env, self);
  };

  return md;
}

export function renderWikiMarkdown(md: MarkdownIt, markdown: string): string {
  return md.render(stripSafeTodoAnchors(markdown));
}
