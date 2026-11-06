"use client";

import { useState } from "react";

// A section card with a title, a one-line answer, and a switch between the chart and a
// table with the same numbers (the accessible version of every chart).

export type Table = { columns: string[]; rows: (string | number)[][] };

export function ChartCard(props: {
  id: string;
  question: string;
  answer: React.ReactNode;
  legend?: React.ReactNode;
  table?: Table;
  loading?: boolean;
  children: React.ReactNode;
}) {
  const { id, question, answer, legend, table, loading, children } = props;
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card" aria-labelledby={`${id}-title`} aria-busy={loading}>
      <div className="card-head">
        <div>
          <h2 id={`${id}-title`}>{question}</h2>
          <p>{answer}</p>
        </div>
        {table && (
          <button
            type="button"
            className="toggle"
            aria-pressed={asTable}
            onClick={() => setAsTable(!asTable)}
          >
            {asTable ? "Chart" : "Table"}
          </button>
        )}
      </div>
      {legend && !asTable && <div className="legend">{legend}</div>}
      <div className={loading ? "card-body loading" : "card-body"}>
        {asTable && table ? <DataTable table={table} /> : children}
      </div>
    </section>
  );
}

function DataTable({ table }: { table: Table }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, column) => (
                <td key={column}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Swatch({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="swatch">
      <i style={{ background: tone }} />
      {label}
    </span>
  );
}
