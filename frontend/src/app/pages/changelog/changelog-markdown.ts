/** Minimal, dependency-free renderer for the specific Keep-a-Changelog markdown subset
 * CHANGELOG.md actually uses (#/##/### headings, "- " bullet lists - including ones hand-wrapped
 * across several source lines, **bold**, `code`, [text](url) links, plain paragraphs) -
 * deliberately not a general markdown parser, so no new npm dependency for one page. Escapes
 * HTML first so the file's own content can never inject markup; only the tags this function
 * itself emits ever reach the DOM unescaped. */
export function renderChangelogMarkdown(markdown: string): string {
  const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const inline = (s: string) =>
    escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const html: string[] = [];
  let inList = false;
  // A bullet or plain paragraph is often hand-wrapped across several source lines (each
  // continuation line indented, with no "- " of its own) - buffer lines until something ends it
  // (a blank line, a new bullet, a heading, or end of input), then join with spaces and emit.
  let paragraphBuf: string[] | null = null;
  let listItemBuf: string[] | null = null;

  const flushListItem = () => {
    if (listItemBuf !== null) {
      html.push(`<li>${inline(listItemBuf.join(' '))}</li>`);
      listItemBuf = null;
    }
  };
  const flushParagraph = () => {
    if (paragraphBuf !== null) {
      html.push(`<p>${inline(paragraphBuf.join(' '))}</p>`);
      paragraphBuf = null;
    }
  };
  const closeList = () => {
    flushListItem();
    if (inList) {
      html.push('</ul>');
      inList = false;
    }
  };

  for (const rawLine of markdown.split('\n')) {
    const line = rawLine.trim();
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);

    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (bullet) {
      flushParagraph();
      flushListItem();
      if (!inList) {
        html.push('<ul>');
        inList = true;
      }
      listItemBuf = [bullet[1]];
    } else if (line === '') {
      flushParagraph();
      flushListItem();
    } else if (listItemBuf !== null) {
      listItemBuf.push(line); // continuation of the current bullet
    } else {
      paragraphBuf = paragraphBuf ?? [];
      paragraphBuf.push(line); // continuation of the current paragraph (or its first line)
    }
  }
  flushParagraph();
  closeList();
  return html.join('\n');
}
