"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type FileLink = { filename: string; label: string };

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  files?: FileLink[];
  isError?: boolean;
};

function newId() {
  return Math.random().toString(36).slice(2);
}

const SUGGESTIONS = [
  "What's the match rate?",
  "Triage exceptions",
  "Forecast cash for 14 days",
  "Bank reconciliation status",
  "Tax reconciliation",
];

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingLedger, setPendingLedger] = useState<File | null>(null);
  const [pendingSettlement, setPendingSettlement] = useState<File | null>(null);
  const [tolerancePct, setTolerancePct] = useState("");
  const [showUploader, setShowUploader] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const ledgerInputRef = useRef<HTMLInputElement>(null);
  const settlementInputRef = useRef<HTMLInputElement>(null);
  const sessionRequested = useRef(false);

  useEffect(() => {
    // Guards against React StrictMode's dev-mode double-invoke, which would
    // otherwise create two session directories on the backend per page load.
    if (sessionRequested.current) return;
    sessionRequested.current = true;
    fetch(`${API_BASE}/api/sessions`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => setSessionId(data.session_id))
      .catch(() =>
        setMessages([
          {
            id: newId(),
            role: "assistant",
            isError: true,
            content:
              `Couldn't reach the backend at ${API_BASE}. Make sure it's running ` +
              "(uvicorn backend.main:app --port 8000) and try refreshing.",
          },
        ]),
      );
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  function pushMessage(msg: Omit<Message, "id">) {
    setMessages((prev) => [...prev, { ...msg, id: newId() }]);
  }

  async function fetchFiles(sid: string): Promise<FileLink[]> {
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sid}/files`);
      const data = await res.json();
      return data.files ?? [];
    } catch {
      return [];
    }
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!sessionId || busy) return;
    if (!text && !(pendingLedger && pendingSettlement)) return;

    setBusy(true);

    if (pendingLedger && pendingSettlement) {
      pushMessage({
        role: "user",
        content: text || `Uploaded ${pendingLedger.name} + ${pendingSettlement.name}`,
      });
      setInput("");
      const ledger = pendingLedger;
      const settlement = pendingSettlement;
      setPendingLedger(null);
      setPendingSettlement(null);
      setShowUploader(false);

      try {
        const form = new FormData();
        form.append("ledger", ledger);
        form.append("settlement", settlement);
        if (tolerancePct.trim()) {
          form.append("tolerance_pct", String(Number(tolerancePct) / 100));
        }
        setTolerancePct("");
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/upload`, {
          method: "POST",
          body: form,
        });
        const data = await res.json();
        if (!res.ok) {
          pushMessage({ role: "assistant", isError: true, content: data.detail ?? "Upload failed." });
        } else {
          const files = await fetchFiles(sessionId);
          pushMessage({ role: "assistant", content: data.reply, files });
        }
      } catch {
        pushMessage({ role: "assistant", isError: true, content: "Upload failed -- couldn't reach the backend." });
      } finally {
        setBusy(false);
      }
      return;
    }

    pushMessage({ role: "user", content: text });
    setInput("");
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      pushMessage({ role: "assistant", content: data.reply ?? data.detail ?? "No response." });
    } catch {
      pushMessage({ role: "assistant", isError: true, content: "Couldn't reach the backend." });
    } finally {
      setBusy(false);
    }
  }

  async function handleDemo() {
    if (!sessionId || busy) return;
    setBusy(true);
    pushMessage({ role: "user", content: "Load a synthetic demo batch" });
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/demo`, { method: "POST" });
      const data = await res.json();
      const files = await fetchFiles(sessionId);
      pushMessage({ role: "assistant", content: data.reply, files });
    } catch {
      pushMessage({ role: "assistant", isError: true, content: "Couldn't reach the backend." });
    } finally {
      setBusy(false);
    }
  }

  const canSend = !busy && sessionId && (input.trim().length > 0 || (pendingLedger && pendingSettlement));

  return (
    <div className="flex h-full flex-1 flex-col bg-neutral-50 dark:bg-neutral-950">
      <header className="border-b border-neutral-200 dark:border-neutral-800 px-6 py-4">
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          AI Finance Controller
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Upload your ledger and settlement CSVs, or try synthetic demo data -- everything you see is scoped to
          this session only.
        </p>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">
          {messages.length === 0 && (
            <EmptyState onDemo={handleDemo} onUpload={() => setShowUploader(true)} disabled={!sessionId} />
          )}

          {messages.map((m) => (
            <Bubble key={m.id} message={m} sessionId={sessionId} />
          ))}

          {busy && (
            <div className="flex items-center gap-1 self-start rounded-2xl bg-neutral-100 dark:bg-neutral-800 px-4 py-3">
              <Dot delay="0ms" />
              <Dot delay="150ms" />
              <Dot delay="300ms" />
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 px-4 py-4">
        <div className="mx-auto max-w-3xl">
          {messages.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSend(s)}
                  disabled={busy || !sessionId}
                  className="rounded-full border border-neutral-300 dark:border-neutral-700 px-3 py-1 text-xs text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-40"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {showUploader && (
            <UploaderPanel
              ledgerInputRef={ledgerInputRef}
              settlementInputRef={settlementInputRef}
              pendingLedger={pendingLedger}
              pendingSettlement={pendingSettlement}
              setPendingLedger={setPendingLedger}
              setPendingSettlement={setPendingSettlement}
              tolerancePct={tolerancePct}
              setTolerancePct={setTolerancePct}
              onClose={() => {
                setShowUploader(false);
                setPendingLedger(null);
                setPendingSettlement(null);
                setTolerancePct("");
              }}
            />
          )}

          <div className="flex items-end gap-2 rounded-2xl border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-2 shadow-sm">
            <button
              type="button"
              title="Attach ledger + settlement CSVs"
              onClick={() => setShowUploader((v) => !v)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              <PaperclipIcon />
            </button>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              rows={1}
              placeholder={sessionId ? "Ask about your data..." : "Connecting..."}
              className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => handleSend()}
              disabled={!canSend}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white disabled:bg-neutral-300 dark:disabled:bg-neutral-700"
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  onDemo,
  onUpload,
  disabled,
}: {
  onDemo: () => void;
  onUpload: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-2xl font-bold text-white">
        ₹
      </div>
      <div>
        <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          Run the books and the cash position
        </h2>
        <p className="mt-1 max-w-md text-sm text-neutral-500 dark:text-neutral-400">
          Reconciliation, bank matching, tax matching, forecasting, and claim verification -- grounded only in
          real data from your upload.
        </p>
      </div>
      <div className="flex gap-3">
        <button
          onClick={onDemo}
          disabled={disabled}
          className="rounded-full bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Try synthetic demo data
        </button>
        <button
          onClick={onUpload}
          disabled={disabled}
          className="rounded-full border border-neutral-300 dark:border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-50"
        >
          Upload your CSVs
        </button>
      </div>
    </div>
  );
}

function UploaderPanel({
  ledgerInputRef,
  settlementInputRef,
  pendingLedger,
  pendingSettlement,
  setPendingLedger,
  setPendingSettlement,
  tolerancePct,
  setTolerancePct,
  onClose,
}: {
  ledgerInputRef: React.RefObject<HTMLInputElement | null>;
  settlementInputRef: React.RefObject<HTMLInputElement | null>;
  pendingLedger: File | null;
  pendingSettlement: File | null;
  setPendingLedger: (f: File | null) => void;
  setPendingSettlement: (f: File | null) => void;
  tolerancePct: string;
  setTolerancePct: (v: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="mb-2 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
          Attach both files, then send
        </span>
        <button onClick={onClose} className="text-xs text-neutral-400 hover:text-neutral-600">
          Cancel
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <FilePickerChip
          label="Ledger CSV"
          file={pendingLedger}
          inputRef={ledgerInputRef}
          onPick={setPendingLedger}
        />
        <FilePickerChip
          label="Settlement CSV"
          file={pendingSettlement}
          inputRef={settlementInputRef}
          onPick={setPendingSettlement}
        />
        <label className="flex items-center gap-1.5 rounded-full border border-dashed border-neutral-300 dark:border-neutral-700 px-3 py-1.5 text-xs text-neutral-500">
          Match tolerance
          <input
            type="number"
            min={0}
            max={20}
            step={0.5}
            value={tolerancePct}
            onChange={(e) => setTolerancePct(e.target.value)}
            placeholder="2 (default)"
            className="w-16 bg-transparent text-neutral-900 dark:text-neutral-100 focus:outline-none"
          />
          %
        </label>
      </div>
    </div>
  );
}

function FilePickerChip({
  label,
  file,
  inputRef,
  onPick,
}: {
  label: string;
  file: File | null;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onPick: (f: File | null) => void;
}) {
  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className={`rounded-full border px-3 py-1.5 text-xs ${
          file
            ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
            : "border-dashed border-neutral-300 text-neutral-500 dark:border-neutral-700"
        }`}
      >
        {file ? `${label}: ${file.name}` : `Choose ${label}`}
      </button>
    </div>
  );
}

function Bubble({ message, sessionId }: { message: Message; sessionId: string | null }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-blue-600 text-white"
            : message.isError
              ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
              : "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
        }`}
      >
        {message.content}
        {message.files && message.files.length > 0 && sessionId && (
          <div className="mt-3 flex flex-wrap gap-2 border-t border-neutral-200 dark:border-neutral-700 pt-2">
            {message.files.map((f) => (
              <a
                key={f.filename}
                href={`${API_BASE}/api/sessions/${sessionId}/files/${f.filename}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 rounded-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-700 px-3 py-1 text-xs text-neutral-700 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-800"
              >
                <DownloadIcon />
                {f.label}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-2 w-2 animate-bounce rounded-full bg-neutral-400"
      style={{ animationDelay: delay }}
    />
  );
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
    </svg>
  );
}
