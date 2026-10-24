// /author: upload a figure, watch the stages, review what was found, publish, print.
// /author?figure=<id> reopens a figure's review. Everything works from the keyboard, and
// nothing is told by color alone: an unchecked part says "Not checked" next to its flag.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, FigureApi, type Job, STAGE_WORDS, type StageName, type Status } from "./api";
import { Review } from "./Review";

const POLL_MS = 400;
const STAGES: StageName[] = ["s0", "s1", "s2", "s3", "s4", "s5"];
const FINISHED = new Set<Job["status"]>(["done", "failed", "describe_only"]);

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

  const opened = (figureId: string) => {
    window.history.replaceState(null, "", `/author?figure=${figureId}`);
    setId(figureId);
  };

  return (
    <main>
      <h1>Author a tactile sheet</h1>
      {!id && <UploadPanel api={apiRef} onUploaded={opened} />}
      {id && error && <p role="alert">{error}</p>}
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

function UploadPanel({ api, onUploaded }: { api: FigureApi; onUploaded: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const submit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const file = fileInput.current?.files?.[0];
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
      onUploaded(r.figure_id);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "The upload failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} aria-label="Upload a figure">
      <p>
        <label>
          Figure (PNG, JPEG or a PDF page){" "}
          <input ref={fileInput} name="file" type="file" accept="image/png,image/jpeg,application/pdf" />
        </label>
      </p>
      <p>
        <label>
          PDF page number <input name="page_index" type="number" min={1} defaultValue={1} />
        </label>
      </p>
      <p>
        <label>
          Grade band{" "}
          <select name="grade_band" defaultValue="">
            <option value="">Not set</option>
            <option value="k5">K to 5</option>
            <option value="6_8">6 to 8</option>
            <option value="9_12">9 to 12</option>
            <option value="college">College</option>
          </select>
        </label>{" "}
        <label>
          Paper{" "}
          <select name="page" defaultValue="letter">
            <option value="letter">US Letter</option>
            <option value="a4">A4</option>
          </select>
        </label>
      </p>
      <button type="submit" disabled={busy}>Make a tactile sheet</button>
      <p role="status">{message}</p>
    </form>
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
