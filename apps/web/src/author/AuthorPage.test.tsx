// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import heart from "../../../../fixtures/pipeline/heart_regions.json";
import synthetic from "../../../../fixtures/synthetic/regions.json";
import type { RegionsFile } from "../shared/regions";
import { FigureApi, type OverlapWarning, type Repair, type Violation, describeViolation } from "./api";
import { AuthorPage } from "./AuthorPage";

const ID = "b".repeat(64);

interface Call {
  method: string;
  url: string;
  body: unknown;
}

/** The figure API in memory: jobs finish on the second status poll after they start. */
class FakeServer {
  calls: Call[] = [];
  regions: RegionsFile = draft(synthetic as unknown as RegionsFile);
  report: Violation[] = [];
  warnings: OverlapWarning[] | null = null; // null: a draft from before warnings, 404
  repairs: Repair[] | null = null;
  refuse: Violation[] | null = null;
  editVersion = 0;
  jobVersion = 0;
  polls = 0;
  stage = "s2";
  describeOnly: string | null = null; // Spark's reason, for a describe_only job
  created = true; // false: the same image was uploaded before
  refuseEdit: string | null = null; // a PATCH answers 409 with this message
  published = 0;
  fixCalls = 0;

  fetch = (url: string, init?: RequestInit): Promise<Response> => Promise.resolve(this.answer(url, init));

  private answer(url: string, init?: RequestInit): Response {
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : init?.body ?? null;
    this.calls.push({ method, url, body });
    const path = url.split("?")[0] ?? url;
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (method === "POST" && path === "/api/figures") {
      this.polls = 0;
      return json({ figure_id: ID, created: this.created, job: this.job() }, this.created ? 202 : 200);
    }
    if (method === "GET" && path === `/api/figures/${ID}`) {
      this.polls++;
      return json({ figure_id: ID, job: this.job(), edit_version: this.editVersion, published: [] });
    }
    if (path === `/api/figures/${ID}/regions.json`) return json(this.regions);
    if (path === `/api/figures/${ID}/report.json`) return json(this.report);
    if (path === `/api/figures/${ID}/repairs.json`) {
      return this.repairs ? json(this.repairs) : json({ error: { code: "not_found", message: "x", retryable: false } }, 404);
    }
    if (path === `/api/figures/${ID}/warnings.json`) {
      return this.warnings ? json(this.warnings) : json({ error: { code: "not_found", message: "x", retryable: false } }, 404);
    }
    const fix = new RegExp(`^/api/figures/${ID}/regions/(\\w+)/fix$`).exec(path);
    if (method === "POST" && fix) {
      const { positive, negative } = body as { positive: number[][]; negative: number[][] };
      this.fixCalls++;
      return json({ part: "septum", region: fix[1], width: 1000, height: 800, scale: 0.9, image: "data:image/png;base64,AA==",
        warnings: positive.length > 1 ? ["The positive point at (500, 400) is on label text."] : [],
        spill: positive.length && !negative.length ? ["mitral valve"] : [], empty: false, area_px: positive.length ? 900 : 0,
        outcome: positive.length ? "ran" : null, latency_ms: positive.length ? 1234 : null, calls: this.fixCalls - 1, call_cap: 30 });
    }
    const edit = new RegExp(`^/api/figures/${ID}/regions/(\\w+)$`).exec(path);
    if (method === "PATCH" && edit && this.refuseEdit) {
      return json({ error: { code: "edit_conflict", message: this.refuseEdit, retryable: true } }, 409);
    }
    if (method === "PATCH" && edit) {
      const r = this.regions.regions.find((x) => x.id === edit[1]);
      const e = body as { op: string; label?: string; description?: string };
      if (r && e.op === "label" && e.label) Object.assign(r, { label: e.label, verified_by_teacher: true });
      if (r && e.op === "describe") Object.assign(r, { description: e.description, verified_by_teacher: true });
      if (e.op === "delete" || e.op === "merge") this.regions.regions = this.regions.regions.filter((x) => x !== r);
      this.editVersion++;
      this.polls = 0;
      return json({ edit_version: this.editVersion, job: this.job() }, 202);
    }
    if (method === "POST" && path === `/api/figures/${ID}/regions`) {
      this.editVersion++;
      this.polls = 0;
      return json({ edit_version: this.editVersion, job: this.job() }, 202);
    }
    if (method === "POST" && path === `/api/figures/${ID}/publish`) {
      if (this.refuse) {
        return json({ error: { code: "rules_violated", message: "This version breaks 1 tactile rule.", retryable: false,
          edit_version: this.editVersion, violations: this.refuse } }, 409);
      }
      this.published++;
      const base = `/api/figures/${ID}/published/${this.published}`;
      return json({ created: true, version: this.published, edit_version: this.editVersion,
        files: { "print.pdf": { url: `${base}/print.pdf`, sha256: "x" } } }, 201);
    }
    return json({ error: { code: "not_found", message: `no ${path}`, retryable: false } }, 404);
  }

  private job() {
    const done = this.polls >= 2;
    if (done) this.jobVersion = this.editVersion;
    const describe = done && this.describeOnly !== null;
    return {
      id: `job${this.editVersion}`,
      status: describe ? "describe_only" : done ? "done" : "running",
      stage: done ? null : this.stage,
      edit_version: done ? this.editVersion : this.editVersion,
      stages: done ? [] : [{ stage: "s0", outcome: "ran", ms: 40, cost_usd: 0 }],
      error: describe ? { code: "describe_only", message: this.describeOnly, retryable: false } : null,
    };
  }
}

let server: FakeServer;

beforeEach(() => {
  server = new FakeServer();
  window.history.replaceState(null, "", "/author");
});
afterEach(cleanup);

const page = () => render(<AuthorPage api={new FigureApi(server.fetch)} pollMs={5} />);

async function upload() {
  page();
  const input = screen.getByLabelText(/Figure \(PNG, JPEG or a PDF page\)/);
  fireEvent.change(input, { target: { files: [new File([new Uint8Array([137, 80])], "figure.png", { type: "image/png" })] } });
  fireEvent.change(screen.getByLabelText("Grade band"), { target: { value: "k5" } });
  fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
  await screen.findByRole("heading", { name: synthetic.title });
}

// A draft as the pipeline writes it: no part checked by the teacher, so none touchable.
function draft(file: RegionsFile): RegionsFile {
  const out = structuredClone(file);
  for (const r of out.regions) Object.assign(r, { touchable: false, verified_by_teacher: false });
  return out;
}

describe("author page", () => {
  it("uploads with the options, shows the stages, then the review", async () => {
    page();
    const input = screen.getByLabelText(/Figure \(PNG, JPEG or a PDF page\)/);
    fireEvent.change(input, { target: { files: [new File([new Uint8Array([1])], "figure.png", { type: "image/png" })] } });
    fireEvent.change(screen.getByLabelText("Grade band"), { target: { value: "k5" } });
    fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
    expect(await screen.findByText("Outlining each part.")).toBeTruthy();
    expect(screen.getByText("Reading the file: done in 40 ms")).toBeTruthy();
    await screen.findByRole("heading", { name: synthetic.title });
    const form = server.calls.find((c) => c.method === "POST")?.body as FormData;
    expect(form.get("grade_band")).toBe("k5");
    expect(form.get("page")).toBe("letter");
    expect(form.get("page_index")).toBe("0");
    expect(window.location.search).toBe(`?figure=${ID}`);
  });

  it("flags every part not checked, in words, not only by color", async () => {
    await upload();
    const parts = screen.getByRole("list", { name: "Parts" });
    expect(within(parts).getAllByText(/Not checked/)).toHaveLength(synthetic.regions.length);
    expect(screen.getByText(`${synthetic.regions.length} of ${synthetic.regions.length} parts not checked yet. A student can touch a part only once you check it.`)).toBeTruthy();
  });

  it("lists parts that are not touchable apart, with the reason, and publish still goes ahead", async () => {
    const first = server.regions.regions[0];
    if (!first) throw new Error("the fixture has regions");
    server.regions.regions.push({ ...structuredClone(first), id: "s1", label: "septum", touchable: false,
      verified_by_teacher: false, flags: [{ reason: "spill", detail: "holds points of mitral valve after a retry" }] });
    server.regions.needs_teacher = [{ id: "n1", label: "okinawa", reason: "no_points", detail: "every point was dropped by the guard" }];
    first.flags = [{ reason: "thin", detail: "Spark marked it thin" }];
    await upload();
    const parts = screen.getByRole("list", { name: "Parts" });
    expect(within(parts).queryByText("septum")).toBeNull();
    expect(within(parts).getByText("Thin: how the sheet shows it is decided later.")).toBeTruthy();
    const flagged = screen.getByRole("list", { name: "Needs you" });
    expect(within(flagged).getAllByText("Not touchable yet.")).toHaveLength(2);
    expect(within(flagged).getByText(/spilled onto other parts, so it is only a suggestion \(holds points of mitral valve after a retry\)/)).toBeTruthy();
    expect(within(flagged).getByText(/No usable point was found on it \(every point was dropped by the guard\)/)).toBeTruthy();
    expect(within(flagged).getByRole("button", { name: "Show the suggested outline of septum" })).toBeTruthy();
    expect(within(flagged).queryByRole("button", { name: /Edit/ })).toBeNull();
    const atPublish = screen.getByRole("list", { name: "Not touchable when published" });
    // Needs you first, then every part not checked yet: none is touchable until checked.
    const listed = within(atPublish).getAllByRole("listitem").map((li) => li.textContent);
    expect(listed.slice(0, 2).map((t) => t.split(":")[0])).toEqual(["septum", "okinawa"]);
    expect(listed.slice(2)).toHaveLength(synthetic.regions.length);
    expect(listed.slice(2).every((t) => t.endsWith(": Not checked yet."))).toBe(true);
    expect(screen.getByText(`${synthetic.regions.length} of ${synthetic.regions.length} parts not checked yet. A student can touch a part only once you check it.`)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    expect(await screen.findByText("Published as version 1.")).toBeTruthy();
  });

  it("splits the live heart's parts into needs you and for your information, and merges a proposal in one press", async () => {
    server.regions = structuredClone(heart) as unknown as RegionsFile;
    page();
    const input = screen.getByLabelText(/Figure \(PNG, JPEG or a PDF page\)/);
    fireEvent.change(input, { target: { files: [new File([new Uint8Array([137, 80])], "heart.png", { type: "image/png" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
    await screen.findByRole("heading", { name: heart.title });
    expect(within(screen.getByRole("list", { name: "Parts" })).getAllByRole("listitem")).toHaveLength(14);
    const needs = within(screen.getByRole("list", { name: "Needs you" })).getAllByRole("listitem");
    expect(needs.map((li) => li.querySelector("strong")?.textContent)).toEqual(["septum"]);
    const info = within(screen.getByRole("list", { name: "For your information" })).getAllByRole("listitem");
    expect(info.map((li) => li.textContent)).toEqual([
      "tricuspid valve A line between right atrium and right ventricle. Not raised; Explore says it when a finger crosses from one to the other, once you check both.",
      "chordae tendineae A line. Not raised; listed in the key.",
      "semilunar valves A line between left ventricle and aorta. Not raised; Explore says it when a finger crosses from one to the other, once you check both.",
      "mitral valve A line between left atrium and left ventricle. Not raised; Explore says it when a finger crosses from one to the other, once you check both.",
      "left pulmonary veins Smaller than a point symbol, so the sheet shows it as one.", // thin: under the area floor
    ]);
    const atPublish = within(screen.getByRole("list", { name: "Not touchable when published" })).getAllByRole("listitem");
    expect(atPublish.map((li) => li.textContent.split(":")[0])[0]).toBe("septum");
    expect(atPublish).toHaveLength(15); // the septum, then the 14 parts not checked yet
    fireEvent.click(screen.getByRole("button", { name: "Show the suggested outline of septum" }));
    expect(document.querySelectorAll("figure svg polygon")).toHaveLength(1);
    const before = server.calls.length;
    fireEvent.click(screen.getByRole("button", {
      name: "Merge brachiocephalic artery, left common carotid artery, left subclavian artery and aorta as 'aortic arch'",
    }));
    await screen.findByRole("heading", { name: heart.title });
    await waitFor(() => { expect(server.calls.slice(before).filter((c) => c.method === "PATCH")).toHaveLength(4); });
    const sent = server.calls.slice(before).filter((c) => c.method === "PATCH").map((c) => [c.url.split("/").at(-1), c.body]);
    expect(sent).toEqual([
      ["r1", { op: "merge", into: "r10" }],
      ["r8", { op: "merge", into: "r10" }],
      ["r9", { op: "merge", into: "r10" }],
      ["r10", { op: "label", label: "aortic arch" }],
    ]);
    // The review reloads after the rename; publish from the reloaded page, once enabled.
    await screen.findByRole("button", { name: "Edit aortic arch" });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Publish for students" }).hasAttribute("disabled")).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    expect(await screen.findByText("Published as version 1.")).toBeTruthy();
  });

  it("lists nested parts and point symbols for the teacher's information", async () => {
    const [a, b] = server.regions.regions;
    if (!a || !b) throw new Error("the fixture has regions");
    Object.assign(b, { parent: a.id, flags: [{ reason: "under_point_symbol", detail: "small" }] });
    await upload();
    const info = within(screen.getByRole("list", { name: "For your information" })).getAllByRole("listitem");
    const texts = info.map((li) => li.textContent);
    expect(texts).toContain(`${b.label} Inside ${a.label}, raised within its outline.`);
    expect(texts).toContain(`${b.label} Smaller than a point symbol, so the sheet shows it as one.`);
  });

  it("warns on an outline that covers another part's area, and shows that area on the sheet", async () => {
    const [a, b] = server.regions.regions;
    if (!a || !b) throw new Error("the fixture has regions");
    server.warnings = [{ region_id: a.id, part: a.label, other: b.label, text: `This outline also covers the area where ${b.label} is`,
      area_mm: [[[10, 10], [20, 10], [20, 20]]] }];
    await upload();
    const row = within(screen.getByRole("list", { name: "Parts" })).getAllByRole("listitem")[0];
    if (!row) throw new Error("no row");
    expect(row.textContent).toContain(`This outline also covers the area where ${b.label} is.`);
    fireEvent.click(within(row).getByRole("button", { name: `Show where ${b.label} is on the sheet` }));
    expect(document.querySelectorAll("figure svg polygon[data-kind='overlap']")).toHaveLength(1);
    expect(document.querySelectorAll("figure svg polygon")).toHaveLength(2); // and the part's outline
  });

  it("lists S4's repairs for the teacher's information", async () => {
    server.repairs = [{ region_id: "r1", part: "aorta", text: "1 piece smaller than a 6.4 mm point symbol left out; the part keeps its main piece" }];
    await upload();
    const info = within(screen.getByRole("list", { name: "For your information" })).getAllByRole("listitem");
    expect(info.map((li) => li.textContent)).toContain("aorta 1 piece smaller than a 6.4 mm point symbol left out; the part keeps its main piece.");
  });

  it("marks every part checked in one edit, after a confirm that lists the parts with a warning", async () => {
    const [a, b] = server.regions.regions;
    if (!a || !b) throw new Error("the fixture has regions");
    server.warnings = [{ region_id: a.id, part: a.label, other: b.label, text: `This outline also covers the area where ${b.label} is`, area_mm: [] }];
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Mark all parts checked" }));
    const confirm = screen.getByRole("region", { name: "Confirm marking all parts checked" });
    expect(within(confirm).getByRole("list", { name: "Parts with a warning" }).textContent)
      .toBe(`${a.label}: This outline also covers the area where ${b.label} is.`);
    const before = server.calls.length;
    fireEvent.click(within(confirm).getByRole("button", { name: `Yes, mark all ${synthetic.regions.length} checked` }));
    await waitFor(() => { expect(server.calls.slice(before).some((c) => c.method === "PATCH")).toBe(true); });
    const ids = [...new Set(synthetic.regions.map((r) => r.id.split("_")[0]))];
    const sent = server.calls.slice(before).filter((c) => c.method === "PATCH");
    expect(sent.map((c) => [c.url.split("/").at(-1), c.body])).toEqual([[ids[0], { op: "check", also: ids.slice(1) }]]);
  });

  it("cancels marking all parts checked", async () => {
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Mark all parts checked" }));
    expect(screen.getByText("No part carries a warning.")).toBeTruthy();
    const before = server.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("region", { name: "Confirm marking all parts checked" })).toBeNull();
    expect(server.calls.slice(before).some((c) => c.method === "PATCH")).toBe(false);
  });

  it("lists each group with its members for the teacher's information, never as a part", async () => {
    const [a, b, c] = server.regions.regions;
    if (!a || !b || !c) throw new Error("the fixture has regions");
    Object.assign(a, { group: "stamen" });
    Object.assign(b, { group: "stamen" });
    await upload();
    const info = within(screen.getByRole("list", { name: "For your information" })).getAllByRole("listitem");
    expect(info.map((li) => li.textContent)).toContain(
      `stamen A group of ${a.label} and ${b.label}. Not raised; Explore says it with each of them.`,
    );
    const parts = within(screen.getByRole("list", { name: "Parts" })).getAllByRole("listitem");
    expect(parts.some((li) => li.textContent.includes("stamen"))).toBe(false);
  });

  it("fixes an outline by clicks, shows the spill warning, and accepts the points as an edit", async () => {
    server.regions.needs_teacher = [{ id: "n1", label: "septum", reason: "no_mask", detail: "SAM's mask holds none of the part's points" }];
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Fix outline of septum" }));
    const panel = await screen.findByRole("region", { name: "Fix outline of septum" });
    const img = await within(panel).findByRole("img");
    img.getBoundingClientRect = () => ({ left: 0, top: 0, width: 500, height: 400, right: 500, bottom: 400, x: 0, y: 0, toJSON: () => ({}) });
    expect(within(panel).getByRole("button", { name: "Accept the outline of septum" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(img, { clientX: 250, clientY: 200 });
    expect(await within(panel).findByText("SAM answered in 1234 ms. Fix calls for this version: 1 of 30.")).toBeTruthy();
    expect(within(panel).getByRole("alert").textContent).toContain("holds the points of mitral valve");
    expect(within(panel).getByText(/Positive points: \(500, 400\)/)).toBeTruthy();
    fireEvent.click(img, { clientX: 100, clientY: 100, shiftKey: true });
    await within(panel).findByText(/Negative points: \(200, 200\)/);
    expect(within(panel).queryByRole("alert")).toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Undo last point" }));
    await within(panel).findByText(/Negative points: none/);
    fireEvent.click(within(panel).getByRole("button", { name: "Negative points" }));
    fireEvent.click(img, { clientX: 50, clientY: 50 });
    await within(panel).findByText(/Negative points: \(100, 100\)/);
    fireEvent.click(within(panel).getByRole("button", { name: "Accept the outline of septum" }));
    await waitFor(() => { expect(server.calls.some((c) => c.method === "PATCH")).toBe(true); });
    const patch = server.calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(`/api/figures/${ID}/regions/n1`);
    expect(patch?.body).toEqual({ op: "outline", positive: [[500, 400]], negative: [[100, 100]] });
    await waitFor(() => { expect(screen.queryByRole("region", { name: "Fix outline of septum" })).toBeNull(); });
  });

  it("a failed accept keeps the Fix outline panel and its points, and says why", async () => {
    server.regions.needs_teacher = [{ id: "n1", label: "septum", reason: "no_mask", detail: "SAM's mask holds none of the part's points" }];
    server.refuseEdit = "The figure changed. Reload it and try again.";
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Fix outline of septum" }));
    const panel = await screen.findByRole("region", { name: "Fix outline of septum" });
    const img = await within(panel).findByRole("img");
    img.getBoundingClientRect = () => ({ left: 0, top: 0, width: 500, height: 400, right: 500, bottom: 400, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.click(img, { clientX: 250, clientY: 200 });
    await within(panel).findByText("SAM answered in 1234 ms. Fix calls for this version: 1 of 30.");
    fireEvent.click(within(panel).getByRole("button", { name: "Accept the outline of septum anyway" })); // it spills
    expect(await screen.findByText("The figure changed. Reload it and try again.")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Fix outline of septum" })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Fix outline of septum" })).getByText(/Positive points: \(500, 400\)/)).toBeTruthy();
  });

  it("marks a part checked, renames one and describes one, each as an edit", async () => {
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Mark left lobe checked" }));
    await waitFor(() => { expect(screen.queryByRole("button", { name: "Mark left lobe checked" })).toBeNull(); });
    const patch = server.calls.filter((c) => c.method === "PATCH");
    expect(patch[0]).toMatchObject({ url: `/api/figures/${ID}/regions/r7`, body: { op: "label", label: "left lobe" } });

    fireEvent.click(screen.getByRole("button", { name: "Edit stem" }));
    fireEvent.change(screen.getByLabelText("New name for stem"), { target: { value: "stalk" } });
    fireEvent.click(screen.getByRole("button", { name: "Rename stem" }));
    expect(await screen.findByText("stalk")).toBeTruthy();
    expect(server.calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({ op: "label", label: "stalk" });

    fireEvent.click(screen.getByRole("button", { name: "Edit stalk" }));
    fireEvent.change(screen.getByLabelText(/Description of stalk/), { target: { value: "It holds the lobes up." } });
    fireEvent.click(screen.getByRole("button", { name: "Save description of stalk" }));
    await waitFor(() => {
      expect(server.calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({ op: "describe", description: "It holds the lobes up." });
    });
  });

  it("merges, deletes after a confirm, and adds a part by name", async () => {
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Edit pore" }));
    fireEvent.change(screen.getByLabelText("Merge pore into"), { target: { value: "r8" } });
    fireEvent.click(screen.getByRole("button", { name: "Merge pore" }));
    await waitFor(() => { expect(screen.queryByRole("button", { name: "Edit pore" })).toBeNull(); });
    expect(server.calls.filter((c) => c.method === "PATCH").at(-1)).toMatchObject({ body: { op: "merge", into: "r8" } });

    fireEvent.click(screen.getByRole("button", { name: "Edit stem" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete stem" }));
    expect(server.calls.filter((c) => c.method === "PATCH")).toHaveLength(1); // nothing sent yet
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete stem" }));
    await waitFor(() => { expect(screen.queryByRole("button", { name: "Edit stem" })).toBeNull(); });

    fireEvent.change(screen.getByLabelText("Add a missing part by name"), { target: { value: "aorta" } });
    fireEvent.click(screen.getByRole("button", { name: "Find and add" }));
    await waitFor(() => { expect(server.calls.some((c) => c.url === `/api/figures/${ID}/regions` && c.method === "POST")).toBe(true); });
    expect(server.calls.find((c) => c.url === `/api/figures/${ID}/regions`)?.body).toEqual({ name: "aorta" });
  });

  it("shows the rules report before publishing", async () => {
    server.report = [{ regions: ["r7", "r8"], rule: "min_gap", measured: 2.01, limit: 3.2, message: "x" }];
    await upload();
    const list = screen.getByRole("list", { name: "Rule problems" });
    expect(list.textContent).toBe("Gap between raised lines: left lobe and right lobe. Measured 2.01 mm, limit 3.2 mm.");
  });

  it("a refused publish lists each violation, and no link to Explore appears", async () => {
    server.refuse = [{ regions: ["r9"], rule: "point_symbol", measured: 4.04, limit: 6.4 }];
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    const refused = await screen.findByRole("list", { name: "Refused because" });
    expect(refused.textContent).toBe("Point symbol size: pore. Measured 4.04 mm, limit 6.4 mm.");
    expect(screen.queryByRole("link", { name: /Explore/ })).toBeNull();
  });

  it("a publish gives the print PDF, the print steps and the Explore link for that version", async () => {
    await upload();
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    const pdf = await screen.findByRole("link", { name: "Download print PDF, version 1" });
    expect(pdf.getAttribute("href")).toBe(`/api/figures/${ID}/published/1/print.pdf`);
    expect(screen.getByRole("link", { name: "Open version 1 in Explore" }).getAttribute("href")).toBe(`/explore?figure=${ID}&version=1`);
    expect(screen.getByText(/Print at 100 percent/)).toBeTruthy();
  });

  it("reopens a figure's review from ?figure=", async () => {
    server.polls = 5;
    window.history.replaceState(null, "", `/author?figure=${ID}`);
    page();
    expect(await screen.findByRole("heading", { name: synthetic.title })).toBeTruthy();
    expect(server.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("says when a figure is better described in words, with Spark's reason, and offers no review", async () => {
    server.describeOnly = "A photo of a lab bench with no labeled parts.";
    page();
    fireEvent.change(screen.getByLabelText(/Figure \(PNG/), { target: { files: [new File([new Uint8Array([1])], "bench.png")] } });
    fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
    expect(await screen.findByText(
      "This figure is better described in words than made into a tactile sheet. A photo of a lab bench with no labeled parts.",
    )).toBeTruthy();
    expect(screen.queryByText("Ready for review.")).toBeNull();
    expect(screen.queryByRole("list", { name: "Parts" })).toBeNull();
  });

  it("says when the same figure was uploaded before, and only then", async () => {
    const upload = async () => {
      fireEvent.change(screen.getByLabelText(/Figure \(PNG/), { target: { files: [new File([new Uint8Array([1])], "heart.png")] } });
      fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
      await screen.findByRole("link", { name: "Upload another figure" });
    };
    page();
    await upload();
    expect(screen.queryByText(/You uploaded this figure before/)).toBeNull();
    cleanup();
    window.history.replaceState(null, "", "/author");
    server.created = false;
    page();
    await upload();
    expect(screen.getByText("You uploaded this figure before. Its review, edits and published versions are below.")).toBeTruthy();
  });

  it("says what went wrong with an upload", async () => {
    const api = new FigureApi(() => Promise.resolve(new Response(
      JSON.stringify({ error: { code: "too_large", message: "The file is over 10 MB.", retryable: false } }), { status: 413 })));
    render(<AuthorPage api={api} pollMs={5} />);
    fireEvent.change(screen.getByLabelText(/Figure \(PNG/), { target: { files: [new File([new Uint8Array([1])], "big.png")] } });
    fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
    expect(await screen.findByText("The file is over 10 MB.")).toBeTruthy();
  });
});

describe("violations in words", () => {
  it("names the rule, the parts, the measure and the limit", () => {
    const label = (id: string) => ({ r1: "outer chamber" })[id] ?? id;
    expect(describeViolation({ regions: [], rule: "texture_count", measured: 5, limit: 3 }, label)).toBe(
      "Number of area textures: the sheet. Measured 5, limit 3.",
    );
    expect(describeViolation({ regions: ["r1"], rule: "new_rule", measured: 1, limit: 2 }, label)).toBe(
      "new_rule: outer chamber. Measured 1, limit 2.",
    );
  });
});
