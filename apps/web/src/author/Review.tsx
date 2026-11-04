// The teacher's review: the figure as uploaded, the parts found, and the tactile sheet.
// Each part can be marked checked, renamed, described, merged into another or deleted, and
// a missing part added by name. Parts the system could not make touchable are listed under
// Needs you, with the reason; publishing does not wait for them, and the publish area names
// each one. For your information lists what needs no action: line parts and what each
// separates, parts nested in another, and parts shown as a point symbol. Each merge proposal
// is one button: merges into the largest of its parts, then the suggested name.
// The rules report is shown before publishing; a publish the rules refuse lists every
// violation in words. After publishing: print and explore.
import { useEffect, useState } from "react";
import { type MergeProposal, partId, type Region, type RegionsFile } from "../shared/regions";
import { ApiError, type Edit, type FigureApi, type FixPreview, type OverlapWarning, type Point, type Repair, type Publication, type Status, type Violation, describeViolation } from "./api";

interface Props {
  api: FigureApi;
  id: string;
  status: Status;
  onEdited: () => void;
}

export function Review({ api, id, status, onEdited }: Props) {
  const [file, setFile] = useState<RegionsFile | null>(null);
  const [report, setReport] = useState<Violation[]>([]);
  const [warnings, setWarnings] = useState<OverlapWarning[]>([]);
  const [repairs, setRepairs] = useState<Repair[]>([]);
  const [area, setArea] = useState<OverlapWarning | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [refused, setRefused] = useState<Violation[] | null>(null);
  const [published, setPublished] = useState<Publication | null>(null);
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState<{ region: string; label: string } | null>(null);

  const settled = status.job.status === "done" && status.job.edit_version === status.edit_version;
  const version = status.edit_version;

  useEffect(() => {
    if (!settled) return;
    let live = true;
    Promise.all([api.regions(id), api.report(id), api.warnings(id), api.repairs(id)])
      .then(([f, r, w, fixes]) => {
        if (!live) return;
        setFile(f);
        setReport(r);
        setWarnings(w);
        setRepairs(fixes);
        setArea(null);
      })
      .catch((err: unknown) => {
        if (live) setMessage(err instanceof Error ? err.message : "The sheet could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, [api, id, settled, version]);

  const labelOf = (rid: string) => file?.regions.find((r) => r.id === rid)?.label ?? rid;

  /** True when the call went through; on a failure the message says why. */
  const send = async (what: string, call: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    setRefused(null);
    setPublished(null);
    setMessage(`${what}.`);
    try {
      await call();
      onEdited();
      return true;
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : `${what} failed.`);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const edit = async (r: Region, e: Edit, what: string) => { await send(what, () => api.edit(id, r.id, e)); };

  const merge = (m: MergeProposal) =>
    send(`Merging ${joined(m.region_ids.map(labelOf))} as ${m.name}`, async () => {
      const into = largest(file?.regions ?? [], m.region_ids);
      for (const rid of m.region_ids) {
        if (rid !== into) await api.edit(id, rid, { op: "merge", into });
      }
      await api.edit(id, into, { op: "label", label: m.name });
    });

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
  const parts = file.regions.filter((r) => !isSuggestion(r));
  const unchecked = parts.filter((r) => !r.verified_by_teacher).length;
  const flagged = notTouchable(file);
  const waiting = notCheckedYet(file);
  const unchecking = new Set(waiting.map((r) => partId(r.id)));
  const warned = warnings.filter((w) => unchecking.has(partId(w.region_id)));
  const notes = [
    ...forYourInformation(file),
    ...repairs.map((x, i) => ({ key: `repair ${String(i)}`, label: x.part, text: `${capitalize(x.text)}.` })),
  ];

  return (
    <section aria-label="Review" className="review">
      <h2>{file.title}</h2>
      <p className="review-summary">{file.summary}</p>
      <p role="status">{settled ? message : "Applying your edit."}</p>
      <div className="review-grid">
        {fixing ? (
          <FixPanel key={`${fixing.region}\u0000${version}`} api={api} id={id} region={fixing.region} label={fixing.label}
            busy={busy || !settled}
            onClose={() => { setFixing(null); }}
            onAccept={async (positive, negative) => {
              // A failed accept keeps the panel and its points, so the teacher can try again.
              const ok = await send(`Setting the outline of ${fixing.label}`, () => api.edit(id, fixing.region, { op: "outline", positive, negative }));
              if (ok) setFixing(null);
            }} />
        ) : (
          <figure className="glass">
            <img src={api.draftUrl(id, "source.png", 0)} alt="The figure as uploaded" />
            <figcaption>As uploaded</figcaption>
          </figure>
        )}
        <div className="glass panel">
          <h3>Parts</h3>
          <p>
            {unchecked === 0
              ? "Every part is checked."
              : `${unchecked} of ${parts.length} parts not checked yet. A student can touch a part only once you check it.`}
          </p>
          {waiting.length > 0 && !confirmAll && (
            <p><button type="button" className="btn-primary" disabled={busy || !settled} onClick={() => { setConfirmAll(true); }}>Mark all parts checked</button></p>
          )}
          {confirmAll && (
            <section aria-label="Confirm marking all parts checked" className="confirm">
              <p>Mark all {waiting.length} parts checked? A student can then touch each of them.</p>
              {warned.length > 0 ? (
                <>
                  <p>These parts carry a warning. Look at them first:</p>
                  <ul aria-label="Parts with a warning">
                    {warned.map((w) => <li key={`${w.region_id} ${w.other}`}>{w.part}: {w.text}.</li>)}
                  </ul>
                </>
              ) : <p>No part carries a warning.</p>}
              <p className="actions">
              <button type="button" className="btn-primary" disabled={busy || !settled} onClick={() => {
                setConfirmAll(false);
                const ids = waiting.map((r) => partId(r.id));
                void send(`Marking ${ids.length} parts checked`, () => api.edit(id, ids[0] ?? "", { op: "check", also: ids.slice(1) }));
              }}>Yes, mark all {waiting.length} checked</button>{" "}
              <button type="button" onClick={() => { setConfirmAll(false); }}>Cancel</button>
              </p>
            </section>
          )}
          <ul aria-label="Parts" className="items">
            {parts.map((r) => (
              // Keyed on the saved text too, so the fields start over after an edit lands.
              <PartRow key={`${r.id}\u0000${r.label}\u0000${r.description ?? ""}`} region={r} all={parts} busy={busy || !settled} selected={selected === r.id}
                onSelect={() => { setSelected(selected === r.id ? null : r.id); }} onEdit={edit}
                warnings={warnings.filter((w) => w.region_id === r.id)} shown={area}
                onShowArea={(w) => { setArea(area === w ? null : w); setSelected(area === w ? null : r.id); }}
                onFix={() => { setFixing({ region: r.id, label: r.label }); }} />
            ))}
          </ul>
          {(file.merge_proposals ?? []).length > 0 && (
            <>
              <h3>Suggested merges</h3>
              <p>These parts are drawn as one shape with no line between them.</p>
              <ul aria-label="Suggested merges" className="items">
                {(file.merge_proposals ?? []).map((m) => (
                  <li key={m.region_ids.join(" ")} data-tone="info">
                    <button type="button" className="btn-primary" disabled={busy || !settled} onClick={() => void merge(m)}>
                      Merge {joined(m.region_ids.map(labelOf))} as &apos;{m.name}&apos;
                    </button>{" "}
                    <span>{capital(m.why)}.</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {flagged.length > 0 && (
            <>
              <h3>Needs you</h3>
              <p>A student cannot touch these parts yet. Each needs you; the reason is given.</p>
              <ul aria-label="Needs you" className="items">
                {flagged.map((f) => (
                  <li key={f.id} data-tone="danger">
                    <strong>{f.label}</strong> <span className="flag" data-tone="danger">Not touchable yet.</span> {f.reason}{" "}
                    {f.outlines.length > 0 && (
                      <button type="button" onClick={() => { setSelected(selected === f.id ? null : f.id); }} aria-pressed={selected === f.id}>
                        Show the suggested outline of {f.label}
                      </button>
                    )}{" "}
                    <button type="button" disabled={busy || !settled} onClick={() => { setFixing({ region: f.id, label: f.label }); }}>
                      Fix outline of {f.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {notes.length > 0 && (
            <>
              <h3>For your information</h3>
              <p>Nothing to do here. This is how the sheet shows these parts.</p>
              <ul aria-label="For your information" className="items">
                {notes.map((n) => (
                  <li key={n.key} data-tone="info">
                    <strong>{n.label}</strong> <span>{n.text}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <AddPart busy={busy || !settled} onAdd={async (name) => { await send(`Looking for ${name}`, () => api.add(id, name)); }} />
        </div>
        <figure className="glass sheet">
          <div style={{ position: "relative" }}>
            <img src={api.draftUrl(id, "tactile.svg", version)} alt="Preview of the tactile sheet" />
            {selected && <Highlight file={file} ids={flagged.find((f) => f.id === selected)?.outlines ?? [selected]} areas={area?.area_mm ?? []} />}
          </div>
          <figcaption>Tactile sheet{selected ? `, ${labelOf(selected)} outlined` : ""}</figcaption>
        </figure>
      </div>

      <div className="glass card publish">
      <h3>Tactile rules</h3>
      {report.length === 0 ? (
        <p>All tactile rules pass.</p>
      ) : (
        <ul aria-label="Rule problems">
          {report.map((v, i) => <li key={i}>{describeViolation(v, labelOf)}</li>)}
        </ul>
      )}

      {flagged.length + waiting.length > 0 && (
        <div>
          <p>Publishing does not wait for these. When published, these parts are not touchable:</p>
          <ul aria-label="Not touchable when published">
            {flagged.map((f) => <li key={f.id}>{f.label}: {f.reason}</li>)}
            {waiting.map((r) => <li key={r.id}>{r.label}: Not checked yet.</li>)}
          </ul>
        </div>
      )}
      <p className="actions">
        <button type="button" className="btn-primary" onClick={() => void publish()} disabled={busy || !settled}>Publish for students</button>{" "}
        <a href={api.draftUrl(id, "print.pdf", version)}>Download the draft print PDF</a>
      </p>
      {refused && (
        <div role="alert" className="notice notice-danger">
          <div className="notice-body">
          <p>Publishing was refused. Fix these with an edit, then publish again:</p>
          <ul aria-label="Refused because">
            {refused.map((v, i) => <li key={i}>{describeViolation(v, labelOf)}</li>)}
          </ul>
          </div>
        </div>
      )}
      {published && <PrintPanel id={id} pub={published} />}
      </div>
    </section>
  );
}

interface Flagged {
  id: string;
  label: string;
  reason: string;
  outlines: string[]; // ids of the suggested outline pieces, if any
}

const REASONS: Record<string, string> = {
  spill: "Its outline spilled onto other parts, so it is only a suggestion",
  no_points: "No usable point was found on it",
  no_mask: "No outline was found for it",
  dropped: "It was dropped as too small or too thin",
};

// A teacher suggestion: a spill outline, never raised on the sheet.
export const isSuggestion = (r: Region) => r.flags?.some((f) => f.reason === "spill") ?? false;

// Parts drawn on the sheet that the teacher has not checked yet, one entry per part.
export function notCheckedYet(file: RegionsFile): Region[] {
  const seen = new Set<string>();
  return file.regions.filter((r) => {
    if (isSuggestion(r) || r.verified_by_teacher || seen.has(partId(r.id))) return false;
    seen.add(partId(r.id));
    return true;
  });
}

// Every part that needs the teacher: suggestion regions, then parts with no shape.
export function notTouchable(file: RegionsFile): Flagged[] {
  const out: Flagged[] = [];
  for (const r of file.regions) {
    if (!isSuggestion(r)) continue;
    const same = out.find((f) => f.label === r.label && f.outlines.length > 0);
    if (same) {
      same.outlines.push(r.id); // another piece of the same suggestion
      continue;
    }
    const spill = r.flags?.find((f) => f.reason === "spill");
    out.push({ id: r.id, label: r.label, outlines: [r.id],
      reason: `${REASONS.spill}${spill ? ` (${spill.detail})` : ""}.` });
  }
  for (const t of file.needs_teacher ?? []) {
    out.push({ id: t.id, label: t.label, outlines: [], reason: `${REASONS[t.reason] ?? t.reason} (${t.detail}).` });
  }
  return out;
}

interface Note {
  key: string;
  label: string;
  text: string;
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function joined(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1] ?? ""}`;
}

function polygonArea(r: Region): number {
  let s = 0;
  const pts = r.polygon_mm;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i];
    const b = pts[j];
    if (a && b) s += b[0] * a[1] - a[0] * b[1];
  }
  return Math.abs(s) / 2;
}

// The proposal's part whose regions cover the most of the sheet: the others merge into it.
export function largest(regions: readonly Region[], ids: readonly string[]): string {
  const area = (rid: string) => regions.filter((r) => partId(r.id) === rid).reduce((a, r) => a + polygonArea(r), 0);
  return [...ids].sort((a, b) => area(b) - area(a))[0] ?? ids[0] ?? "";
}

// What needs no action: line parts and what each separates, parts nested in another, and
// parts too small for anything but a point symbol. Once per part.
export function forYourInformation(file: RegionsFile): Note[] {
  const label = (rid: string) => file.regions.find((r) => r.id === rid)?.label ?? rid;
  const out: Note[] = [];
  // regions.json names a line's regions only once they are touchable; before the teacher
  // checks them, the line's labels say which parts it will sit between.
  const drawn = new Set(file.regions.filter((r) => !isSuggestion(r)).map((r) => r.label));
  for (const l of file.lines ?? []) {
    const crossing = l.separates
      ? "Explore says it when a finger crosses from one to the other"
      : l.between && drawn.has(l.between[0]) && drawn.has(l.between[1])
        ? "Explore says it when a finger crosses from one to the other, once you check both"
        : "listed in the key";
    const text = l.between
      ? `A line between ${l.between[0]} and ${l.between[1]}. Not raised; ${crossing}.`
      : `A line${l.parent ? ` in ${label(l.parent)}` : ""}. Not raised; listed in the key.`;
    out.push({ key: l.id, label: l.label, text });
  }
  const groups = new Map<string, string[]>();
  for (const r of file.regions) {
    if (isSuggestion(r) || !r.group) continue;
    const members = groups.get(r.group) ?? [];
    if (!members.includes(r.label)) members.push(r.label);
    groups.set(r.group, members);
  }
  for (const [group, members] of groups) {
    out.push({ key: `group ${group}`, label: group, text: `A group of ${joined(members)}. Not raised; Explore says it with each of them.` });
  }
  const seen = new Set<string>();
  for (const r of file.regions) {
    if (isSuggestion(r) || seen.has(partId(r.id))) continue;
    if (r.parent) {
      seen.add(partId(r.id));
      out.push({ key: `nested ${r.id}`, label: r.label, text: `Inside ${label(r.parent)}, raised within its outline.` });
    }
  }
  const small = new Set<string>();
  for (const r of file.regions) {
    if (isSuggestion(r) || small.has(partId(r.id))) continue;
    if (r.flags?.some((f) => f.reason === "under_point_symbol")) {
      small.add(partId(r.id));
      out.push({ key: `small ${r.id}`, label: r.label, text: "Smaller than a point symbol, so the sheet shows it as one." });
    }
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
  onFix: () => void;
  warnings: readonly OverlapWarning[];
  shown: OverlapWarning | null;
  onShowArea: (w: OverlapWarning) => void;
}) {
  const { region: r, all, busy, selected, onSelect, onEdit, onFix, warnings, shown, onShowArea } = props;
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(r.label);
  const [description, setDescription] = useState(r.description ?? "");
  const [into, setInto] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const others = all.filter((o) => o.id !== r.id);
  const flag = r.verified_by_teacher ? "Checked" : "Not checked";
  return (
    <li data-tone={r.verified_by_teacher ? "ok" : "warn"}>
      <strong>{r.label}</strong>
      {r.abbrev ? ` (braille ${r.abbrev})` : ""} <span className="flag" data-tone={r.verified_by_teacher ? "ok" : "warn"}>{r.verified_by_teacher ? "✓ " : "! "}{flag}</span>{" "}
      {(r.flags ?? []).map((f) => <span key={f.reason}>{NOTES[f.reason] ?? f.detail} </span>)}
      <button type="button" onClick={onSelect} aria-pressed={selected}>Show on sheet</button>{" "}
      {!r.verified_by_teacher && (
        <button type="button" disabled={busy} onClick={() => void onEdit(r, { op: "label", label: r.label }, `Marking ${r.label} checked`)}>
          Mark {r.label} checked
        </button>
      )}{" "}
      {r.source === "teacher" && <span>Outline set by teacher. </span>}
      {warnings.map((w) => (
        <span key={w.other} className="note-warn">
          {w.text}.{" "}
          <button type="button" aria-label={`Show where ${w.other} is on the sheet`} aria-pressed={shown === w} onClick={() => { onShowArea(w); }}>
            Show on sheet
          </button>
        </span>
      ))}
      <button type="button" onClick={() => { setOpen(!open); }} aria-expanded={open}>Edit {r.label}</button>{" "}
      <button type="button" disabled={busy} onClick={onFix}>Fix outline of {r.label}</button>
      {open && (
        <div className="edit-box">
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

// Fix outline: each click on the figure adds a point, positive, or negative with the
// Negative points toggle or Shift held, and asks SAM for the part's outline from all points.
// The preview shows the new mask over the faded figure, the old outline in magenta, and the
// points. Accept stores the points as an outline edit.
function FixPanel(props: {
  api: FigureApi;
  id: string;
  region: string;
  label: string;
  busy: boolean;
  onClose: () => void;
  onAccept: (positive: Point[], negative: Point[]) => Promise<void>;
}) {
  const { api, id, region, label, busy, onClose, onAccept } = props;
  const [positive, setPositive] = useState<Point[]>([]);
  const [negative, setNegative] = useState<Point[]>([]);
  const [order, setOrder] = useState<("positive" | "negative")[]>([]);
  const [negativeMode, setNegativeMode] = useState(false);
  const [view, setView] = useState<FixPreview | null>(null);
  const [pending, setPending] = useState(true);
  const [message, setMessage] = useState("Loading the figure.");

  const ask = async (pos: Point[], neg: Point[], kinds: ("positive" | "negative")[]) => {
    setPending(true);
    setMessage(pos.length ? "Asking SAM for the outline." : "Loading the figure.");
    try {
      const v = await api.fixPreview(id, region, pos, neg);
      setPositive(pos);
      setNegative(neg);
      setOrder(kinds);
      setView(v);
      setMessage(describeFix(v));
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "The outline could not be fetched.");
    } finally {
      setPending(false);
    }
  };

  useEffect(() => {
    let live = true;
    api.fixPreview(id, region, [], [])
      .then((v) => {
        if (!live) return;
        setView(v);
        setMessage(describeFix(v));
        setPending(false);
      })
      .catch((err: unknown) => {
        if (!live) return;
        setMessage(err instanceof ApiError ? err.message : "The figure could not be loaded.");
        setPending(false);
      });
    return () => {
      live = false;
    };
  }, [api, id, region]);

  const click = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!view || pending) return;
    const box = e.currentTarget.getBoundingClientRect();
    const p: Point = [
      Math.min(view.width - 1, Math.max(0, Math.round(((e.clientX - box.left) / box.width) * view.width))),
      Math.min(view.height - 1, Math.max(0, Math.round(((e.clientY - box.top) / box.height) * view.height))),
    ];
    if (negativeMode || e.shiftKey) void ask(positive, [...negative, p], [...order, "negative"]);
    else void ask([...positive, p], negative, [...order, "positive"]);
  };

  const undo = () => {
    const last = order[order.length - 1];
    if (!last) return;
    const kinds = order.slice(0, -1);
    if (last === "positive") void ask(positive.slice(0, -1), negative, kinds);
    else void ask(positive, negative.slice(0, -1), kinds);
  };

  const ready = view !== null && positive.length > 0 && !view.empty && !pending;
  const spills = view !== null && view.spill.length > 0;
  return (
    <section aria-label={`Fix outline of ${label}`} className="fix">
      <h3>Fix outline of {label}</h3>
      <p>Click inside {label} to add a point. Turn on Negative points, or hold Shift, to mark what is not {label}.</p>
      {view && (
        <img src={view.image} alt={`${label}: the new outline over the faded figure, the old outline in magenta`}
          onClick={click} className="fix-image" data-pending={pending} />
      )}
      <p role="status" aria-live="polite">{message}</p>
      {view?.warnings.map((w, i) => <p key={i}>Warning: {w}</p>)}
      {spills && (
        <p role="alert">
          This outline holds the points of {view.spill.join(", ")}. You may accept it anyway; it will be marked as set by you.
        </p>
      )}
      <p>
        Positive points: {positive.length ? positive.map(([x, y]) => `(${x}, ${y})`).join(", ") : "none"}.
        Negative points: {negative.length ? negative.map(([x, y]) => `(${x}, ${y})`).join(", ") : "none"}.
      </p>
      <p className="actions">
        <button type="button" aria-pressed={negativeMode} onClick={() => { setNegativeMode(!negativeMode); }}>Negative points</button>{" "}
        <button type="button" disabled={pending || order.length === 0} onClick={undo}>Undo last point</button>{" "}
        <button type="button" className="btn-primary" disabled={!ready || busy} onClick={() => void onAccept(positive, negative)}>
          {spills ? `Accept the outline of ${label} anyway` : `Accept the outline of ${label}`}
        </button>{" "}
        <button type="button" onClick={onClose}>Cancel</button>
      </p>
    </section>
  );
}

function describeFix(v: FixPreview): string {
  if (v.outcome === null) return `Click inside ${v.part} to add a point.`;
  if (v.empty) return "SAM found no outline at these points. Add another point or undo.";
  const how = v.outcome === "cached" ? "From the cache, no new call." : `SAM answered in ${Math.round(v.latency_ms ?? 0)} ms.`;
  const calls = v.calls === null ? "" : ` Fix calls for this version: ${v.calls} of ${v.call_cap}.`;
  return `${how}${calls}`;
}

function AddPart({ busy, onAdd }: { busy: boolean; onAdd: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  return (
    <form className="add-part" onSubmit={(e) => { e.preventDefault(); const n = name.trim(); if (n) void onAdd(n).then(() => { setName(""); }); }}>
      <label>
        Add a missing part by name <input value={name} onChange={(e) => { setName(e.target.value); }} maxLength={80} />
      </label>{" "}
      <button type="submit" disabled={busy || !name.trim()}>Find and add</button>
    </form>
  );
}

// The selected part's outline drawn over the preview, from regions.json polygons in page mm.
// A suggestion may have several pieces; each is drawn.
// With an overlap warning shown, the area it names is filled in orange too.
function Highlight({ file, ids, areas = [] }: { file: RegionsFile; ids: string[]; areas?: readonly [number, number][][] }) {
  const shown = file.regions.filter((x) => ids.includes(x.id));
  if (shown.length === 0 && areas.length === 0) return null;
  return (
    <svg viewBox={`0 0 ${file.page.width_mm} ${file.page.height_mm}`} aria-hidden="true"
      style={{ position: "absolute", left: 0, top: 0, width: "100%", pointerEvents: "none" }}>
      {shown.map((r) => (
        <polygon key={r.id} points={r.polygon_mm.map(([x, y]) => `${x},${y}`).join(" ")}
          fill="none" stroke="#d500f9" strokeWidth={1.5} strokeDasharray="3 1.5" />
      ))}
      {areas.map((ring, i) => (
        <polygon key={`area ${String(i)}`} data-kind="overlap" points={ring.map(([x, y]) => `${x},${y}`).join(" ")}
          fill="#ff9800" fillOpacity={0.45} stroke="#e65100" strokeWidth={0.8} />
      ))}
    </svg>
  );
}

function PrintPanel({ id, pub }: { id: string; pub: Publication }) {
  const pdf = pub.files["print.pdf"]?.url;
  return (
    <section aria-label="Print and explore" className="print">
      <h3>Print and explore</h3>
      <ol className="print-steps">
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

const capitalize = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
