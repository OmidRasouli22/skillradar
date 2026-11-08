"use client";

import { useRef, useState } from "react";
import { readPdf, type CvStatus, type ShowcaseItem } from "@/lib/cv";

type Tab = "upload" | "paste" | "examples";

// The CV as text: from a PDF, pasted, or one of the example CVs; then read it.
export function CvSource(props: {
  status: CvStatus | null;
  text: string;
  onText: (text: string, from: string) => void;
  showcases: ShowcaseItem[];
  example: string | null;
  onExample: (id: string) => void;
  onRead: (mode: "claude" | "keywords") => void;
  reading: "claude" | "keywords" | null;
  error: string | null;
}) {
  const { status, text, onText, showcases, example, onExample, onRead, reading, error } = props;
  const [tab, setTab] = useState<Tab>("upload");
  const [fileError, setFileError] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const limits = status?.limits ?? { pdf_mb: 5, min_chars: 200, max_chars: 30000 };
  const chars = text.trim().length;
  const tooShort = chars > 0 && chars < limits.min_chars;
  const tooLong = chars > limits.max_chars;
  const ready = chars >= limits.min_chars && !tooLong;
  const roomForClaude = !!status && status.room_left_usd >= status.typical_cost_usd * 4;

  async function open(file: File) {
    setFileError(null);
    const name = file.name.toLowerCase();
    if (file.size > limits.pdf_mb * 1_000_000) {
      setFileError(`The file is larger than ${limits.pdf_mb} MB.`);
      return;
    }
    setLoadingFile(true);
    try {
      if (name.endsWith(".pdf")) {
        const data = await asBase64(file);
        const result = await readPdf(data);
        onText(result.text, `${file.name} · ${result.pages} page${result.pages === 1 ? "" : "s"}`);
      } else if (name.endsWith(".txt") || name.endsWith(".md")) {
        onText(await file.text(), file.name);
      } else {
        setFileError("Choose a PDF, .txt or .md file, or paste the text.");
      }
    } catch (err) {
      setFileError((err as Error).message);
    } finally {
      setLoadingFile(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="cv-source">
      <div className="cv-tabs" role="tablist" aria-label="Where the CV comes from">
        {(
          [
            ["upload", "Upload"],
            ["paste", "Paste text"],
            ["examples", `Examples${showcases.length ? ` (${showcases.length})` : ""}`],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`cv-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`cv-panel-${id}`}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "upload" && (
        <div id="cv-panel-upload" role="tabpanel" aria-labelledby="cv-tab-upload">
          <label
            className={`cv-drop${dragging ? " dragging" : ""}${loadingFile ? " busy" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files[0];
              if (file) void open(file);
            }}
          >
            <input
              ref={input}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void open(file);
              }}
            />
            <strong>{loadingFile ? "Reading the file…" : "Drop your CV here or choose a file"}</strong>
            <small>PDF with text (not a scan), .txt or .md · up to {limits.pdf_mb} MB</small>
          </label>
          {fileError && (
            <p className="note" role="alert">
              {fileError}
            </p>
          )}
        </div>
      )}

      {tab === "examples" && (
        <div id="cv-panel-examples" role="tabpanel" aria-labelledby="cv-tab-examples">
          <p className="cv-muted">Fictional people, each built to test one thing. Loading one costs nothing.</p>
          <ul className="cv-examples">
            {showcases.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={example === item.id ? "active" : ""}
                  aria-pressed={example === item.id}
                  onClick={() => onExample(item.id)}
                >
                  <strong>{item.title}</strong>
                  <span>
                    {item.person} · CV in {item.language}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="cv-text">
        <label htmlFor="cv-text">
          CV text{" "}
          <small>
            {chars.toLocaleString("en-GB")} / {limits.max_chars.toLocaleString("en-GB")} characters
          </small>
        </label>
        <textarea
          id="cv-text"
          value={text}
          rows={tab === "paste" ? 12 : 5}
          placeholder="Paste your CV here…"
          spellCheck={false}
          onChange={(event) => onText(event.target.value, "pasted")}
          aria-invalid={tooShort || tooLong}
          aria-describedby="cv-text-hint"
        />
        <p id="cv-text-hint" className={tooShort || tooLong ? "cv-hint warn" : "cv-hint"}>
          {tooShort
            ? `Too short: at least ${limits.min_chars} characters.`
            : tooLong
              ? `Too long: at most ${limits.max_chars.toLocaleString("en-GB")} characters.`
              : "Before the text goes to Claude, email addresses, phone numbers, links and your name are replaced. Nothing is saved."}
        </p>
      </div>

      <div className="cv-actions">
        <button
          type="button"
          className="button"
          disabled={!ready || !status?.claude || !roomForClaude || reading !== null}
          onClick={() => onRead("claude")}
        >
          {reading === "claude" ? "Reading…" : "Read with Claude"}
        </button>
        <button
          type="button"
          className="toggle cv-quick"
          disabled={!ready || reading !== null}
          onClick={() => onRead("keywords")}
        >
          {reading === "keywords" ? "Reading…" : "Quick read (free)"}
        </button>
        <span className="cv-cost">
          {!status
            ? ""
            : !status.claude
              ? "Claude is off: no ANTHROPIC_API_KEY in .env. The quick read finds skill names only."
              : !roomForClaude
                ? `This month's Claude budget is used up ($${status.room_left_usd.toFixed(2)} left).`
                : `About $${status.typical_cost_usd.toFixed(3)} with ${status.model} · $${status.room_left_usd.toFixed(2)} of $${status.budget_usd.toFixed(2)} left this month`}
        </span>
      </div>
      {error && (
        <p className="note" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function asBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error("The file could not be read."));
    reader.readAsDataURL(file);
  });
}
