// Turns a quick capture into a Bear note via Bear's x-callback-url scheme.
// Bear lives on the device, so the browser hands the note to the Bear app
// directly; nothing is sent to a server.

// #tag or #nested/tag (Bear's simple tag form). "# Heading" has a space, so it isn't matched.
const TAG_RE = /(^|\s)#([\p{L}\p{N}_-]+(?:\/[\p{L}\p{N}_-]+)*)/gu;

export type Capture = {
  title: string;
  text: string;
  /** Tags pulled out of the first line, passed to Bear explicitly. */
  tags: string[];
  /** Every tag in the note, for showing as chips. */
  allTags: string[];
};

export function parseCapture(content: string, url = ""): Capture {
  const lines = content.trim().split("\n");
  const first = lines[0] ?? "";
  // Tags on the first line would otherwise end up inside the title heading,
  // so lift them out and hand them to Bear separately.
  const tags = [...first.matchAll(TAG_RE)].map((m) => m[2]);
  const title = first.replace(TAG_RE, "$1").replace(/\s+/g, " ").trim() || "Untitled";
  const body = lines.slice(1).join("\n").trim();
  const bodyTags = [...body.matchAll(TAG_RE)].map((m) => m[2]);
  const text = [body, url.trim()].filter(Boolean).join("\n\n");
  return { title, text, tags, allTags: [...new Set([...tags, ...bodyTags])] };
}

export function bearCreateUrl(c: Capture, returnTo?: string): string {
  const params = new URLSearchParams({ title: c.title, open_note: "no", show_window: "no" });
  if (c.text) params.set("text", c.text);
  if (c.tags.length) params.set("tags", c.tags.join(","));
  if (returnTo) params.set("x-success", returnTo);
  // Bear expects %20 rather than + for spaces.
  return "bear://x-callback-url/create?" + params.toString().replace(/\+/g, "%20");
}
