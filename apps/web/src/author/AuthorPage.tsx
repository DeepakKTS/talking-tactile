// /author: upload a figure, watch the stages, review what was found, publish, print.
// /author?figure=<id> reopens a figure's review. Everything works from the keyboard, and
// nothing is told by color alone: an unchecked part says "Not checked" next to its flag.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, FigureApi, type Job, STAGE_WORDS, type StageName, type Status } from "./api";
import { Review } from "./Review";

const POLL_MS = 400;
const STAGES: StageName[] = ["s0", "s1", "s2", "s3", "s4", "s5"];
const FINISHED = new Set<Job["status"]>(["done", "failed", "describe_only"]);
// Spark's verdict on a figure with nothing to make tactile; its reason follows.
const DESCRIBE_ONLY = "This figure is better described in words than made into a tactile sheet.";
// The server's upload guard, config/tactile_rules.yaml pipeline.max_upload_mb (a test keeps
// the two equal). The server checks it; this is only said on the card.
export const MAX_UPLOAD_MB = 10;

export function figureFromUrl(): string | null {
  const id = new URLSearchParams(window.location.search).get("figure");
  return id && /^[0-9a-f]{64}$/.test(id) ? id : null;
}

/** Polls the figure until its newest job has finished every edit made so far. */
export function useFigureStatus(api: FigureApi, id: string | null, pollMs = POLL_MS) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!id) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const s = await api.status(id);
        if (!live) return;
        setStatus(s);
        setError(null);
        const settled = FINISHED.has(s.job.status) && s.job.edit_version === s.edit_version;
        if (!settled) timer = setTimeout(() => void poll(), pollMs);
      } catch (err) {
        if (live) setError(err instanceof Error ? err.message : "The figure could not be found.");
      }
    };
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [api, id, pollMs, tick]);
  const refresh = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  return { status, error, refresh };
}

export function AuthorPage({ api = new FigureApi(), pollMs = POLL_MS }: { api?: FigureApi; pollMs?: number }) {
  const [apiRef] = useState(api);
  const [id, setId] = useState<string | null>(figureFromUrl);
  const { status, error, refresh } = useFigureStatus(apiRef, id, pollMs);
  // Once a figure has a finished sheet, the review stays up while later edits apply.
  const [reviewable, setReviewable] = useState<string | null>(null);
  if (id && reviewable !== id && status?.figure_id === id && status.job.status === "done") setReviewable(id);

  // The same image uploaded again opens its earlier review (the server keys a figure by its
  // pixels): say so, since the edits and published versions there are the earlier ones.
  const [again, setAgain] = useState(false);

  const opened = (figureId: string, created: boolean) => {
    window.history.replaceState(null, "", `/author?figure=${figureId}`);
    setAgain(!created);
    setId(figureId);
  };

  return (
    <main className="page author">
      <header className="topbar">
        <a className="brand" href="/">
          <img src="/brand/logo.svg" alt="Talking Tactile, home" width="351" height="45" />
        </a>
      </header>
      <h1>Author a tactile sheet</h1>
      {!id && <UploadPanel api={apiRef} onUploaded={opened} />}
      {id && again && <p role="status">{UPLOADED_BEFORE}</p>}
      {id && error && <p role="alert" className="notice notice-danger">{error}</p>}
      {id && status && <Progress status={status} />}
      {id && status && reviewable === id && <Review api={apiRef} id={id} status={status} onEdited={refresh} />}
      {id && (
        <p>
          <a href="/author">Upload another figure</a>
        </p>
      )}
    </main>
  );
}

const UPLOADED_BEFORE = "You uploaded this figure before. Its review, edits and published versions are below.";

function UploadPanel({ api, onUploaded }: { api: FigureApi; onUploaded: (id: string, created: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [refused, setRefused] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  // A file dropped on the card. Choosing one with Browse replaces it.
  const dropped = useRef<File | null>(null);

  const submit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const file = fileInput.current?.files?.[0] ?? dropped.current;
    setRefused(null);
    if (!file) {
      setMessage("Choose a PNG, JPEG or PDF file first.");
      return;
    }
    setBusy(true);
    setMessage("Uploading.");
    try {
      const band = form.get("grade_band");
      const gradeBand = typeof band === "string" ? band : "";
      const r = await api.upload(file, file.name, {
        page: form.get("page") === "a4" ? "a4" : "letter",
        gradeBand: gradeBand || null,
        pageIndex: Math.max(0, Number(form.get("page_index") ?? 1) - 1),
      });
      onUploaded(r.figure_id, r.created);
    } catch (err) {
      setMessage("");
      setRefused(err instanceof ApiError ? err.message : "The upload failed.");
    } finally {
      setBusy(false);
    }
  };

  const drop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    dropped.current = file;
    if (fileInput.current) fileInput.current.value = "";
    setChosen(file.name);
    setRefused(null);
    setMessage("");
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-label="Upload a figure" className="glass card upload">
      <div className="card-head">
        <span className="tile" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 3h8l4 4v14H6z" />
            <path d="M14 3v4h4" />
            <circle cx="10" cy="12" r="1.1" fill="currentColor" />
            <circle cx="10" cy="16" r="1.1" fill="currentColor" />
            <circle cx="14" cy="12" r="1.1" fill="currentColor" />
          </svg>
        </span>
        <div>
          <h2 className="card-title">New tactile sheet</h2>
          <p className="card-desc">Upload a textbook figure. You check the parts it finds, then print the sheet.</p>
        </div>
      </div>

      <div className="dropzone" data-over={over}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => { setOver(false); }}
        onDrop={drop}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 15V4" />
          <path d="M7.5 8.5 12 4l4.5 4.5" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>
        <p className="drop-title" id="tt-file-label">Figure (PNG, JPEG or a PDF page)</p>
        <p className="drop-meta" id="tt-file-hint">Drop the file here, or browse. Up to {MAX_UPLOAD_MB} MB.</p>
        <input ref={fileInput} id="tt-file" className="file-input" name="file" type="file" accept="image/png,image/jpeg,application/pdf"
          aria-labelledby="tt-file-label" aria-describedby="tt-file-hint tt-file-chosen"
          onChange={(e) => { dropped.current = null; setChosen(e.target.files?.[0]?.name ?? null); setRefused(null); }} />
        <label htmlFor="tt-file" className="browse">Browse</label>
        <p className="drop-file" id="tt-file-chosen">{chosen ? `Chosen: ${chosen}` : "No file chosen."}</p>
      </div>

      <div className="fields">
        <label className="field">
          <span className="field-label">PDF page number</span>
          <input name="page_index" type="number" min={1} defaultValue={1} inputMode="numeric" />
        </label>
        <label className="field">
          <span className="field-label">Grade band</span>
          <select name="grade_band" defaultValue="">
            <option value="">Not set</option>
            <option value="k5">K to 5</option>
            <option value="6_8">6 to 8</option>
            <option value="9_12">9 to 12</option>
            <option value="college">College</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">Paper</span>
          <select name="page" defaultValue="letter">
            <option value="letter">US Letter</option>
            <option value="a4">A4</option>
          </select>
        </label>
      </div>

      {refused && (
        <div role="alert" className="notice notice-danger">
          <AlertIcon />
          <div className="notice-body">
            <p><strong>Not uploaded.</strong> {refused}</p>
          </div>
        </div>
      )}

      <div className="card-foot">
        <p role="status">{message}</p>
        <button type="submit" className="btn-primary" disabled={busy}>Make a tactile sheet</button>
      </div>
    </form>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 7v6" />
      <circle cx="12" cy="16.5" r="0.6" fill="currentColor" />
    </svg>
  );
}

function Progress({ status }: { status: Status }) {
  const job = status.job;
  const done = new Map(job.stages.map((s) => [s.stage, s]));
  const applying = job.edit_version !== status.edit_version || !FINISHED.has(job.status);
  return (
    <section aria-label="Progress">
      <p role="status">
        {job.status === "failed"
          ? `Stopped at ${job.stage ? STAGE_WORDS[job.stage].toLowerCase() : "a stage"}: ${job.error?.message ?? "an error"}`
          : job.status === "describe_only" && !applying
            ? `${DESCRIBE_ONLY}${job.error?.message ? ` ${job.error.message}` : ""}`
            : applying
            ? job.stage
              ? `${STAGE_WORDS[job.stage]}.`
              : "Waiting to start."
            : "Ready for review."}
      </p>
      {applying && (
        <ol>
          {STAGES.map((s) => {
            const run = done.get(s);
            const state = run ? `done in ${Math.round(run.ms)} ms${run.outcome === "cached" ? ", from cache" : ""}` : job.stage === s ? "working" : "waiting";
            return (
              <li key={s}>
                {STAGE_WORDS[s]}: {state}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
