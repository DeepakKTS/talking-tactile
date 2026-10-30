// The teacher's review: the figure as uploaded, the parts found, and the tactile sheet.
// Each part can be marked checked, renamed, described, merged into another or deleted, and
// a missing part added by name. Parts the system could not make touchable are listed apart,
// with the reason; publishing does not wait for them, and the publish area names each one.
// The rules report is shown before publishing; a publish the rules refuse lists every
// violation in words. After publishing: print and explore.
import { useEffect, useState } from "react";
import type { Region, RegionsFile } from "../shared/regions";
import { ApiError, type Edit, type FigureApi, type Publication, type Status, type Violation, describeViolation } from "./api";

interface Props {
  api: FigureApi;
  id: string;
  status: Status;
  onEdited: () => void;
}

export function Review({ api, id, status, onEdited }: Props) {
  const [file, setFile] = useState<RegionsFile | null>(null);
  const [report, setReport] = useState<Violation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [refused, setRefused] = useState<Violation[] | null>(null);
  const [published, setPublished] = useState<Publication | null>(null);
  const [busy, setBusy] = useState(false);

  const settled = status.job.status === "done" && status.job.edit_version === status.edit_version;
  const version = status.edit_version;

  useEffect(() => {
    if (!settled) return;
    let live = true;
    Promise.all([api.regions(id), api.report(id)])
      .then(([f, r]) => {
        if (!live) return;
        setFile(f);
        setReport(r);
      })
      .catch((err: unknown) => {
        if (live) setMessage(err instanceof Error ? err.message : "The sheet could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, [api, id, settled, version]);

  const labelOf = (rid: string) => file?.regions.find((r) => r.id === rid)?.label ?? rid;

  const send = async (what: string, call: () => Promise<unknown>) => {
    setBusy(true);
    setRefused(null);
    setPublished(null);
    setMessage(`${what}.`);
    try {
      await call();
      onEdited();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : `${what} failed.`);
    } finally {
      setBusy(false);
    }
  };

  const edit = (r: Region, e: Edit, what: string) => send(what, () => api.edit(id, r.id, e));

  const publish = async () => {
    setBusy(true);
    setRefused(null);
    setMessage("Publishing.");
    try {
      const pub = await api.publish(id);
      setPublished(pub);
      setMessage(`Published as version ${pub.version}.`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "rules_violated") {
        setRefused(err.violations);
        setMessage("Not published. The sheet breaks the tactile rules below.");
      } else {
        setMessage(err instanceof ApiError ? err.message : "Publishing failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  if (!file) return <p role="status">{message || "Loading the review."}</p>;
  const touchable = file.regions.filter((r) => r.touchable);
  const unchecked = touchable.filter((r) => !r.verified_by_teacher).length;
  const flagged = notTouchable(file);

  return (
    <section aria-label="Review">
      <h2>{file.title}</h2>
      <p>{file.summary}</p>
      <p role="status">{settled ? message : "Applying your edit."}</p>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(18rem,1fr) minmax(0,1fr)", gap: "1rem" }}>
        <figure>
          <img src={api.draftUrl(id, "source.png", 0)} alt="The figure as uploaded" style={{ maxWidth: "100%" }} />
          <figcaption>As uploaded</figcaption>
        </figure>
        <div>
          <h3>Parts</h3>
          <p>
            {unchecked === 0 ? "Every part is checked." : `${unchecked} of ${touchable.length} parts not checked yet.`}
          </p>
          <ul aria-label="Parts" style={{ listStyle: "none", padding: 0 }}>
            {touchable.map((r) => (
              // Keyed on the saved text too, so the fields start over after an edit lands.
              <PartRow key={`${r.id}\u0000${r.label}\u0000${r.description ?? ""}`} region={r} all={touchable} busy={busy || !settled} selected={selected === r.id}
                onSelect={() => { setSelected(selected === r.id ? null : r.id); }} onEdit={edit} />
            ))}
          </ul>
          {flagged.length > 0 && (
            <>
              <h3>Not touchable yet</h3>
              <p>A student cannot touch these parts. Each needs you; the reason is given.</p>
              <ul aria-label="Not touchable yet" style={{ listStyle: "none", padding: 0 }}>
                {flagged.map((f) => (
                  <li key={f.id} style={{ borderLeft: "0.4rem solid #c62828", padding: "0.25rem 0.5rem", marginBottom: "0.5rem" }}>
                    <strong>{f.label}</strong> <span>Not touchable yet.</span> {f.reason}{" "}
                    {f.region && (
                      <button type="button" onClick={() => { setSelected(selected === f.id ? null : f.id); }} aria-pressed={selected === f.id}>
                        Show the suggested outline of {f.label}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
          <AddPart busy={busy || !settled} onAdd={(name) => send(`Looking for ${name}`, () => api.add(id, name))} />
        </div>
        <figure style={{ position: "relative", margin: 0 }}>
          <img src={api.draftUrl(id, "tactile.svg", version)} alt="Preview of the tactile sheet" style={{ width: "100%", display: "block" }} />
          {selected && <Highlight file={file} id={selected} />}
          <figcaption>Tactile sheet{selected ? `, ${labelOf(selected)} outlined` : ""}</figcaption>
        </figure>
      </div>

      <h3>Tactile rules</h3>
      {report.length === 0 ? (
        <p>All tactile rules pass.</p>
      ) : (
        <ul aria-label="Rule problems">
          {report.map((v, i) => <li key={i}>{describeViolation(v, labelOf)}</li>)}
        </ul>
      )}

      {flagged.length > 0 && (
        <div>
          <p>Publishing does not wait for these. When published, these parts are not touchable:</p>
          <ul aria-label="Not touchable when published">
            {flagged.map((f) => <li key={f.id}>{f.label}: {f.reason}</li>)}
          </ul>
        </div>
      )}
      <p>
        <button type="button" onClick={() => void publish()} disabled={busy || !settled}>Publish for students</button>{" "}
        <a href={api.draftUrl(id, "print.pdf", version)}>Download the draft print PDF</a>
      </p>
      {refused && (
        <div role="alert">
          <p>Publishing was refused. Fix these with an edit, then publish again:</p>
          <ul aria-label="Refused because">
            {refused.map((v, i) => <li key={i}>{describeViolation(v, labelOf)}</li>)}
          </ul>
        </div>
      )}
      {published && <PrintPanel id={id} pub={published} />}
    </section>
  );
}

interface Flagged {
  id: string;
  label: string;
  reason: string;
  region: boolean; // has a suggested outline to show
}

const REASONS: Record<string, string> = {
  spill: "Its outline spilled onto other parts, so it is only a suggestion",
  no_points: "No usable point was found on it",
  no_mask: "No outline was found for it",
  dropped: "It was dropped as too small or too thin",
};

// Every part a student cannot touch: suggestion regions, then parts with no shape.
export function notTouchable(file: RegionsFile): Flagged[] {
  const out: Flagged[] = [];
  for (const r of file.regions) {
    if (r.touchable) continue;
    const spill = r.flags?.find((f) => f.reason === "spill");
    out.push({ id: r.id, label: r.label, region: true,
      reason: `${REASONS.spill}${spill ? ` (${spill.detail})` : ""}.` });
  }
  for (const t of file.needs_teacher ?? []) {
    out.push({ id: t.id, label: t.label, region: false, reason: `${REASONS[t.reason] ?? t.reason} (${t.detail}).` });
  }
  return out;
}

const NOTES: Record<string, string> = {
  thin: "Thin: how the sheet shows it is decided later.",
  under_point_symbol: "Smaller than a point symbol, so the sheet shows it as one.",
};

function PartRow(props: {
  region: Region;
  all: readonly Region[];
  busy: boolean;
  selected: boolean;
  onSelect: () => void;
  onEdit: (r: Region, e: Edit, what: string) => Promise<void>;
}) {
  const { region: r, all, busy, selected, onSelect, onEdit } = props;
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(r.label);
  const [description, setDescription] = useState(r.description ?? "");
  const [into, setInto] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const others = all.filter((o) => o.id !== r.id);
  const flag = r.verified_by_teacher ? "Checked" : "Not checked";
  return (
    <li style={{ borderLeft: `0.4rem solid ${r.verified_by_teacher ? "#2e7d32" : "#f0a000"}`, padding: "0.25rem 0.5rem", marginBottom: "0.5rem" }}>
      <strong>{r.label}</strong>
      {r.abbrev ? ` (braille ${r.abbrev})` : ""} <span>{r.verified_by_teacher ? "✓ " : "! "}{flag}</span>{" "}
      {(r.flags ?? []).map((f) => <span key={f.reason}>{NOTES[f.reason] ?? f.detail} </span>)}
      <button type="button" onClick={onSelect} aria-pressed={selected}>Show on sheet</button>{" "}
      {!r.verified_by_teacher && (
        <button type="button" disabled={busy} onClick={() => void onEdit(r, { op: "label", label: r.label }, `Marking ${r.label} checked`)}>
          Mark {r.label} checked
        </button>
      )}{" "}
      <button type="button" onClick={() => { setOpen(!open); }} aria-expanded={open}>Edit {r.label}</button>
      {open && (
        <div>
          <form onSubmit={(e) => { e.preventDefault(); void onEdit(r, { op: "label", label }, `Renaming ${r.label}`); }}>
            <label>New name for {r.label} <input value={label} onChange={(e) => { setLabel(e.target.value); }} maxLength={80} required /></label>{" "}
            <button type="submit" disabled={busy || !label.trim()}>Rename {r.label}</button>
          </form>
          <form onSubmit={(e) => { e.preventDefault(); void onEdit(r, { op: "describe", description }, `Saving the description of ${r.label}`); }}>
            <label>
              Description of {r.label}, spoken on "more"{" "}
              <textarea value={description} onChange={(e) => { setDescription(e.target.value); }} maxLength={600} rows={2} required />
            </label>{" "}
            <button type="submit" disabled={busy || !description.trim()}>Save description of {r.label}</button>
          </form>
          <form onSubmit={(e) => { e.preventDefault(); if (into) void onEdit(r, { op: "merge", into }, `Merging ${r.label}`); }}>
            <label>
              Merge {r.label} into{" "}
              <select value={into} onChange={(e) => { setInto(e.target.value); }}>
                <option value="">Choose a part</option>
                {others.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </label>{" "}
            <button type="submit" disabled={busy || !into}>Merge {r.label}</button>
          </form>
          {confirmDelete ? (
            <p>
              Delete {r.label}?{" "}
              <button type="button" disabled={busy} onClick={() => void onEdit(r, { op: "delete" }, `Deleting ${r.label}`)}>Yes, delete {r.label}</button>{" "}
              <button type="button" onClick={() => { setConfirmDelete(false); }}>Keep it</button>
            </p>
          ) : (
            <button type="button" onClick={() => { setConfirmDelete(true); }}>Delete {r.label}</button>
          )}
        </div>
      )}
    </li>
  );
}

function AddPart({ busy, onAdd }: { busy: boolean; onAdd: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); const n = name.trim(); if (n) void onAdd(n).then(() => { setName(""); }); }}>
      <label>
        Add a missing part by name <input value={name} onChange={(e) => { setName(e.target.value); }} maxLength={80} />
      </label>{" "}
      <button type="submit" disabled={busy || !name.trim()}>Find and add</button>
    </form>
  );
}

// The selected part's outline drawn over the preview, from regions.json polygons in page mm.
function Highlight({ file, id }: { file: RegionsFile; id: string }) {
  const r = file.regions.find((x) => x.id === id);
  if (!r) return null;
  const points = r.polygon_mm.map(([x, y]) => `${x},${y}`).join(" ");
  return (
    <svg viewBox={`0 0 ${file.page.width_mm} ${file.page.height_mm}`} aria-hidden="true"
      style={{ position: "absolute", left: 0, top: 0, width: "100%", pointerEvents: "none" }}>
      <polygon points={points} fill="none" stroke="#d500f9" strokeWidth={1.5} strokeDasharray="3 1.5" />
    </svg>
  );
}

function PrintPanel({ id, pub }: { id: string; pub: Publication }) {
  const pdf = pub.files["print.pdf"]?.url;
  return (
    <section aria-label="Print and explore">
      <h3>Print and explore</h3>
      <ol>
        <li>{pdf ? <a href={pdf} download>Download print PDF, version {pub.version}</a> : "The print PDF is missing."}</li>
        <li>Print at 100 percent, or actual size. Do not fit to page.</li>
        <li>Measure the bar at the bottom. It must be 100 mm. If not, check the printer scale and print again.</li>
        <li>Trace each outline with puffy paint, on the printed line. Let it dry overnight.</li>
        <li>Tape the sheet down under the camera so it cannot slide.</li>
        <li>
          <a href={`/explore?figure=${id}&version=${pub.version}`}>Open version {pub.version} in Explore</a>
        </li>
      </ol>
    </section>
  );
}
