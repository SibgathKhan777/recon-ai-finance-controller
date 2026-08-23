"use client";

import { useState } from "react";

export type Bucket = {
  ledger_amount: number;
  ledger_count: number;
  settlement_amount: number;
  settlement_count: number;
  difference: number;
};

export type MatchRow = {
  ledger_id: string;
  settlement_id: string;
  txn_ref: string;
  ledger_amount: string;
  settlement_amount: string;
  category: string;
  confidence: string;
};

export type ExceptionRow = {
  ledger_id: string;
  settlement_id: string;
  txn_ref: string;
  amount: string;
  date: string;
  category: string;
};

export type ReportData = {
  total: Bucket;
  fully_matched: Bucket & { rows: MatchRow[] };
  partially_matched: Bucket & { rows: MatchRow[] };
  unmatched: Bucket & { ledger_rows: ExceptionRow[]; settlement_rows: ExceptionRow[] };
};

function money(n: number) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function SummaryCard({ title, bucket, highlight }: { title: string; bucket: Bucket; highlight?: boolean }) {
  const diffColor =
    Math.abs(bucket.difference) < 0.01
      ? "text-emerald-600"
      : Math.abs(bucket.difference) < bucket.ledger_amount * 0.05
        ? "text-amber-600"
        : "text-rose-600";
  return (
    <div
      className={`rounded-xl border bg-white p-4 ${highlight ? "border-teal-400 ring-1 ring-teal-100" : "border-slate-200"}`}
    >
      <div className="mb-3 text-sm font-medium text-slate-500">{title}</div>
      <Row label="Ledger" amount={bucket.ledger_amount} count={bucket.ledger_count} />
      <Row label="Settlement" amount={bucket.settlement_amount} count={bucket.settlement_count} />
      <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2 text-sm">
        <span className="text-slate-500">Difference</span>
        <span className={`font-semibold ${diffColor}`}>{money(bucket.difference)}</span>
      </div>
    </div>
  );
}

function Row({ label, amount, count }: { label: string; amount: number; count: number }) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between">
      <span className="text-xs text-slate-400">{label}</span>
      <span className="text-right">
        <span className="text-sm font-semibold text-slate-900">{money(amount)}</span>
        <span className="ml-1.5 text-xs text-slate-400">{count} txn{count === 1 ? "" : "s"}</span>
      </span>
    </div>
  );
}

export function ReportView({ report }: { report: ReportData }) {
  const defaultTab = report.unmatched.ledger_count + report.unmatched.settlement_count > 0 ? "unmatched" : "fully";
  const [tab, setTab] = useState<"fully" | "partial" | "unmatched">(defaultTab);

  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCard title="Total" bucket={report.total} />
        <SummaryCard title="Fully matched" bucket={report.fully_matched} />
        <SummaryCard title="Partially matched" bucket={report.partially_matched} />
        <SummaryCard title="Unmatched" bucket={report.unmatched} highlight />
      </div>

      <div className="mb-3 flex gap-1 border-b border-slate-200">
        <TabButton active={tab === "fully"} onClick={() => setTab("fully")}>
          Fully matched
        </TabButton>
        <TabButton active={tab === "partial"} onClick={() => setTab("partial")}>
          Partially matched
        </TabButton>
        <TabButton active={tab === "unmatched"} onClick={() => setTab("unmatched")}>
          Unmatched
        </TabButton>
      </div>

      {tab === "fully" && <MatchTable rows={report.fully_matched.rows} />}
      {tab === "partial" && <MatchTable rows={report.partially_matched.rows} />}
      {tab === "unmatched" && (
        <div className="grid gap-4 md:grid-cols-2">
          <ExceptionTable title="Unmatched -- Ledger" rows={report.unmatched.ledger_rows} />
          <ExceptionTable title="Unmatched -- Settlement" rows={report.unmatched.settlement_rows} />
        </div>
      )}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
        active ? "border-teal-600 text-teal-700" : "border-transparent text-slate-500 hover:text-slate-700"
      }`}
    >
      {children}
    </button>
  );
}

function MatchTable({ rows }: { rows: MatchRow[] }) {
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-slate-400">No rows in this category.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Reference</th>
            <th className="px-3 py-2">Ledger</th>
            <th className="px-3 py-2">Settlement</th>
            <th className="px-3 py-2">Category</th>
            <th className="px-3 py-2">Confidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.slice(0, 50).map((r, i) => (
            <tr key={`${r.ledger_id}-${r.settlement_id}-${i}`}>
              <td className="px-3 py-2 font-mono text-xs text-slate-600">{r.txn_ref || "(none)"}</td>
              <td className="px-3 py-2 text-slate-900">{money(Number(r.ledger_amount))}</td>
              <td className="px-3 py-2 text-slate-900">{money(Number(r.settlement_amount))}</td>
              <td className="px-3 py-2 text-slate-500">{r.category}</td>
              <td className="px-3 py-2 text-slate-500">{r.confidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 50 && (
        <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-400">
          Showing 50 of {rows.length} -- download the full CSV for the rest.
        </div>
      )}
    </div>
  );
}

function ExceptionTable({ title, rows }: { title: string; rows: ExceptionRow[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-3 py-2 text-sm font-medium text-slate-700">
        {title} <span className="font-normal text-slate-400">({rows.length})</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">Nothing here.</p>
      ) : (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2">Amount</th>
                <th className="px-3 py-2">Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.slice(0, 50).map((r, i) => (
                <tr key={`${r.ledger_id || r.settlement_id}-${i}`}>
                  <td className="px-3 py-2 text-slate-600">{r.date}</td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">{r.txn_ref || "(none)"}</td>
                  <td className="px-3 py-2 text-slate-900">{money(Number(r.amount))}</td>
                  <td className="px-3 py-2 text-slate-500">{r.category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
