// The figure API as the teacher's screens use it. Every Meta call happens behind it, on
// the backend; this file only speaks HTTP to /api/figures.
import { type RegionsFile, parseRegions } from "../shared/regions";

export type StageName = "s0" | "s1" | "s2" | "s3" | "s4" | "s5";

export interface StageRun {
  stage: StageName;
  outcome: "ran" | "cached" | "skipped";
  ms: number;
  cost_usd: number;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed" | "describe_only";
  stage: StageName | null;
  edit_version: number;
  stages: StageRun[];
  error: { code: string; message: string; retryable: boolean } | null;
}

export interface Status {
  figure_id: string;
  job: Job;
  edit_version: number;
  published: number[];
}

export interface Violation {
  regions: string[];
  rule: string;
  measured: number;
  limit: number;
  message?: string;
}

export interface Publication {
  created: boolean;
  version: number;
  edit_version: number;
  files: Record<string, { url: string; sha256: string }>;
}

export type Edit =
  | { op: "label"; label: string }
  | { op: "describe"; description: string }
  | { op: "merge"; into: string }
  | { op: "delete" };

export class ApiError extends Error {
  override name = "ApiError";
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly violations: Violation[] = [],
  ) {
    super(message);
  }
}

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

interface ErrorBody {
  error?: { code?: string; message?: string; violations?: Violation[] };
}

export class FigureApi {
  constructor(private readonly fetchFn: Fetch = (u, i) => fetch(u, i)) {}

  private async json<T>(url: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await this.fetchFn(url, init);
    } catch {
      throw new ApiError(0, "network", "The server cannot be reached. Check that it is running.");
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as ErrorBody;
      throw new ApiError(
        res.status,
        body.error?.code ?? "http_error",
        body.error?.message ?? `The server answered ${res.status}.`,
        body.error?.violations ?? [],
      );
    }
    return (await res.json()) as T;
  }

  upload(file: Blob, name: string, opts: { page: "letter" | "a4"; gradeBand: string | null; pageIndex: number }) {
    const form = new FormData();
    form.append("file", file, name);
    form.append("page", opts.page);
    form.append("page_index", String(opts.pageIndex));
    if (opts.gradeBand) form.append("grade_band", opts.gradeBand);
    return this.json<{ figure_id: string; created: boolean; job: Job }>("/api/figures", { method: "POST", body: form });
  }

  status(id: string) {
    return this.json<Status>(`/api/figures/${id}`);
  }

  async regions(id: string): Promise<RegionsFile> {
    return parseRegions(await this.json<unknown>(`/api/figures/${id}/regions.json`));
  }

  report(id: string) {
    return this.json<Violation[]>(`/api/figures/${id}/report.json`);
  }

  edit(id: string, region: string, edit: Edit) {
    return this.json<{ edit_version: number; job: Job }>(`/api/figures/${id}/regions/${region}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edit),
    });
  }

  add(id: string, name: string) {
    return this.json<{ edit_version: number; job: Job }>(`/api/figures/${id}/regions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  }

  publish(id: string) {
    return this.json<Publication>(`/api/figures/${id}/publish`, { method: "POST" });
  }

  /** Draft files change with each edit; the version in the query makes the browser fetch anew. */
  draftUrl(id: string, name: "tactile.svg" | "print.pdf" | "source.png", editVersion: number) {
    return `/api/figures/${id}/${name}?v=${editVersion}`;
  }
}

export const STAGE_WORDS: Record<StageName, string> = {
  s0: "Reading the file",
  s1: "Finding the parts",
  s2: "Outlining each part",
  s3: "Sorting out overlaps",
  s4: "Laying out the sheet",
  s5: "Drawing the sheet and checking the rules",
};

export const RULE_WORDS: Record<string, { name: string; unit: string }> = {
  min_gap: { name: "Gap between raised lines", unit: "mm" },
  point_symbol: { name: "Point symbol size", unit: "mm" },
  texture_count: { name: "Number of area textures", unit: "" },
  texture_on_point: { name: "Texture on a point symbol", unit: "" },
  texture_unknown: { name: "Unknown texture", unit: "" },
  braille_clearance: { name: "Braille too close to a line", unit: "mm" },
  braille_gap: { name: "Braille blocks too close", unit: "mm" },
  braille_overlap: { name: "Braille on another part", unit: "" },
  inside_page: { name: "Outside the figure area", unit: "mm" },
  polygon: { name: "Outline shape", unit: "" },
  ids: { name: "Region ids", unit: "" },
  svg_ids: { name: "Sheet and regions file disagree", unit: "" },
};

export function describeViolation(v: Violation, labelOf: (id: string) => string): string {
  const words = RULE_WORDS[v.rule] ?? { name: v.rule, unit: "" };
  const unit = words.unit ? ` ${words.unit}` : "";
  const parts = v.regions.map(labelOf).join(" and ");
  return `${words.name}: ${parts || "the sheet"}. Measured ${round(v.measured)}${unit}, limit ${round(v.limit)}${unit}.`;
}

const round = (x: number) => String(Math.round(x * 100) / 100);
