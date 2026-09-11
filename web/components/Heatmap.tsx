// Diverging heatmap: rows x cols of signed numbers, neutral surface at zero, the value printed in every
// cell so identity never depends on colour alone. Hover on a cell shows the full label as a title.
type Props = {
  rows: string[];
  cols: string[];
  values: (number | null | undefined)[][];   // values[row][col]
  fmt: (v: number) => string;
  max?: number;                               // |value| that saturates the colour (default: the grid's max)
  colLabel?: (c: string) => string;
};

export default function Heatmap({ rows, cols, values, fmt, max, colLabel }: Props) {
  const flat = values.flat().filter((v): v is number => v != null && isFinite(v));
  const sat = max ?? Math.max(1e-9, ...flat.map((v) => Math.abs(v)));
  const bg = (v: number) => {
    const a = Math.round(Math.min(1, Math.abs(v) / sat) * 72);
    return `color-mix(in srgb, var(${v >= 0 ? "--up" : "--down"}) ${a}%, var(--surface))`;
  };
  return (
    <div className="scroll">
      <table className="heat">
        <thead>
          <tr><th></th>{cols.map((c) => <th key={c} className="num">{colLabel ? colLabel(c) : c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r}>
              <td className="rowlabel">{r}</td>
              {cols.map((c, j) => {
                const v = values[i]?.[j];
                return v == null || !isFinite(v)
                  ? <td key={c} className="cell empty">—</td>
                  : <td key={c} className="cell" style={{ background: bg(v) }} title={`${r} · ${c}: ${fmt(v)}`}>{fmt(v)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
