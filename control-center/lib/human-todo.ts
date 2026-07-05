// lib/human-todo.ts — pure parser for HUMAN_TODO.md's "## N. Title" sections (CC2 /brief item
// 1's "HUMAN_TODO.md unchecked items"). The file has no checkbox syntax — items are numbered
// headings ("## 1. ANTHROPIC_API_KEY ...", "## 3b. ~~Apply migration 005~~ — DONE (...)"), so
// "done" is detected the way this project has already marked completed items twice today:
// strikethrough (~~...~~) around the title, or the literal word DONE in the heading. A
// trailing "## Reference: ..." section (not a numbered item) is excluded by requiring the
// heading to start with a number.

export type HumanTodoItem = { number: string; title: string; done: boolean };

const HEADING_RE = /^##\s+(\d+[a-z]?)\.\s+(.+)$/;

export function parseHumanTodoItems(markdown: string): HumanTodoItem[] {
  const items: HumanTodoItem[] = [];
  for (const line of markdown.split(/\r?\n/)) {
    const m = HEADING_RE.exec(line.trim());
    if (!m) continue;
    const [, number, title] = m;
    const done = /~~.*~~/.test(title) || /\bDONE\b/i.test(title);
    items.push({ number, title: title.replace(/~~/g, "").trim(), done });
  }
  return items;
}

export function unchecked(items: HumanTodoItem[]): HumanTodoItem[] {
  return items.filter((i) => !i.done);
}
