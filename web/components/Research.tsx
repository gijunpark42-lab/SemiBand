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
    if (line.startsWith("# ")) { blocks.push(<h3 key={k++}>{inline(line.slice(2), `h${k}`)}</h3>); i++; continue; }
    if (line.startsWith("## ")) { blocks.push(<h4 key={k++} id={`r-${k}`}>{inline(line.slice(3), `h${k}`)}</h4>); i++; continue; }
    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        if (!/^\|?\s*-{2,}/.test(lines[i].trim().replace(/^\|/, ""))) rows.push(cells(lines[i]));
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div className="scroll" key={k++}>
          <table className="md">
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c, `th${k}-${j}`)}</th>)}</tr></thead>
            <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} className={/^[+−-]?\d/.test(c) ? "num" : ""}>{inline(c, `td${k}-${ri}-${j}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>);
      continue;
    }
    if (/^\s*[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && (/^\s*[-*] /.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (/^\s*[-*] /.test(lines[i])) items.push(lines[i].replace(/^\s*[-*] /, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      blocks.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `li${k}-${j}`)}</li>)}</ul>);
      continue;
    }
    if (line.trim() === "") { i++; continue; }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("#") && !lines[i].trim().startsWith("|") && !/^\s*[-*] /.test(lines[i])) {
      para.push(lines[i].trim()); i++;
    }
    blocks.push(<p key={k++}>{inline(para.join(" "), `p${k}`)}</p>);
  }
  return <div className="md">{blocks}</div>;
}
