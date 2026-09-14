// Renders RESEARCH.md (the research log: every idea tried, its numbers, the verdict) without a markdown
// dependency: headings, tables, bullet lists, paragraphs, **bold**, `code`, _italics_. Anything fancier
// falls through as plain text.
import type { ReactNode } from "react";

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<b key={`${key}-${i++}`}>{t.slice(2, -2)}</b>);
    else if (t.startsWith("`")) out.push(<code key={`${key}-${i++}`}>{t.slice(1, -1)}</code>);
    else out.push(<i key={`${key}-${i++}`}>{t.slice(1, -1)}</i>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export default function Research({ markdown }: { markdown: string }) {
  const lines = markdown.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0, k = 0;
  while (i < lines.length) {
    const line = lines[i];
    const heading = /^(#{1,6}) (.*)$/.exec(line);
    if (heading) {
      // "# " -> h3, "## " -> h4 (anchored), deeper levels -> h5. Every line must advance `i`: a line the loop
      // cannot consume (an unknown heading level once made this loop spin until the server ran out of memory).
      const level = heading[1].length, text = inline(heading[2], `h${k + 1}`);
      if (level === 1) blocks.push(<h3 key={k++}>{text}</h3>);
      else if (level === 2) blocks.push(<h4 key={k++} id={`r-${k}`}>{text}</h4>);
      else blocks.push(<h5 key={k++}>{text}</h5>);
      i++; continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        if (!/^\|?\s*-{2,}/.test(lines[i].trim().replace(/^\|/, ""))) rows.push(cells(lines[i]));
        i++;
      }
      const [head, ...body] = rows;
      if (!head) continue;                       // a separator-only block has nothing to render
      blocks.push(
        <div className="scroll" key={k++}>
          <table className="md">
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c, `th${k}-${j}`)}</th>)}</tr></thead>
            <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} className={/^[+−-]?\d/.test(c) ? "num" : ""}>{inline(c, `td${k}-${ri}-${j}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>);
      continue;
    }
    if (/^\s*([-*]|\d+\.) /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && (/^\s*([-*]|\d+\.) /.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (/^\s*([-*]|\d+\.) /.test(lines[i])) items.push(lines[i].replace(/^\s*([-*]|\d+\.) /, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      blocks.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `li${k}-${j}`)}</li>)}</ul>);
      continue;
    }
    if (line.trim() === "") { i++; continue; }
    const para: string[] = [line.trim()];       // always consume the current line, whatever it looks like
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !/^#{1,6} /.test(lines[i]) && !lines[i].trim().startsWith("|") && !/^\s*([-*]|\d+\.) /.test(lines[i])) {
      para.push(lines[i].trim()); i++;
    }
    blocks.push(<p key={k++}>{inline(para.join(" "), `p${k}`)}</p>);
  }
  return <div className="md">{blocks}</div>;
}
