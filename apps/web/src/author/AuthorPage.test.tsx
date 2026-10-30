// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import heart from "../../../../fixtures/pipeline/heart_regions.json";
import synthetic from "../../../../fixtures/synthetic/regions.json";
import type { RegionsFile } from "../shared/regions";
import { FigureApi, type Violation, describeViolation } from "./api";
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
  regions: RegionsFile = structuredClone(synthetic) as unknown as RegionsFile;
  report: Violation[] = [];
  refuse: Violation[] | null = null;
  editVersion = 0;
  jobVersion = 0;
  polls = 0;
  stage = "s2";
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
      return json({ figure_id: ID, created: true, job: this.job() }, 202);
    }
    if (method === "GET" && path === `/api/figures/${ID}`) {
      this.polls++;
      return json({ figure_id: ID, job: this.job(), edit_version: this.editVersion, published: [] });
    }
    if (path === `/api/figures/${ID}/regions.json`) return json(this.regions);
    if (path === `/api/figures/${ID}/report.json`) return json(this.report);
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
    return {
      id: `job${this.editVersion}`,
      status: done ? "done" : "running",
      stage: done ? null : this.stage,
      edit_version: done ? this.editVersion : this.editVersion,
      stages: done ? [] : [{ stage: "s0", outcome: "ran", ms: 40, cost_usd: 0 }],
      error: null,
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
    expect(screen.getByText(`${synthetic.regions.length} of ${synthetic.regions.length} parts not checked yet.`)).toBeTruthy();
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
    const flagged = screen.getByRole("list", { name: "Not touchable yet" });
    expect(within(flagged).getAllByText("Not touchable yet.")).toHaveLength(2);
    expect(within(flagged).getByText(/spilled onto other parts, so it is only a suggestion \(holds points of mitral valve after a retry\)/)).toBeTruthy();
    expect(within(flagged).getByText(/No usable point was found on it \(every point was dropped by the guard\)/)).toBeTruthy();
    expect(within(flagged).getByRole("button", { name: "Show the suggested outline of septum" })).toBeTruthy();
    expect(within(flagged).queryByRole("button", { name: /Edit/ })).toBeNull();
    const atPublish = screen.getByRole("list", { name: "Not touchable when published" });
    expect(within(atPublish).getAllByRole("listitem").map((li) => li.textContent.split(":")[0])).toEqual(["septum", "okinawa"]);
    expect(screen.getByText(`${synthetic.regions.length} of ${synthetic.regions.length} parts not checked yet.`)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    expect(await screen.findByText("Published as version 1.")).toBeTruthy();
  });

  it("shows the live heart's spill parts as not touchable and still publishes", async () => {
    server.regions = structuredClone(heart) as unknown as RegionsFile;
    page();
    const input = screen.getByLabelText(/Figure \(PNG, JPEG or a PDF page\)/);
    fireEvent.change(input, { target: { files: [new File([new Uint8Array([137, 80])], "heart.png", { type: "image/png" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Make a tactile sheet" }));
    await screen.findByRole("heading", { name: heart.title });
    expect(within(screen.getByRole("list", { name: "Parts" })).getAllByRole("listitem")).toHaveLength(17);
    const flagged = within(screen.getByRole("list", { name: "Not touchable yet" })).getAllByRole("listitem");
    expect(flagged.map((li) => li.querySelector("strong")?.textContent)).toEqual(["aorta", "mitral valve", "left ventricle", "septum"]);
    expect(within(screen.getByRole("list", { name: "Not touchable when published" })).getAllByRole("listitem")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Show the suggested outline of aorta" }));
    expect(document.querySelectorAll("figure svg polygon")).toHaveLength(2); // both pieces
    fireEvent.click(screen.getByRole("button", { name: "Publish for students" }));
    expect(await screen.findByText("Published as version 1.")).toBeTruthy();
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
