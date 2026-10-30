// regions.json in the browser. docs/regions.schema.json is the source of truth:
// the types are generated from it (regions.gen.ts) and parseRegions validates against it.
import Ajv2020 from "ajv/dist/2020";
import schema from "../../../../docs/regions.schema.json";
import type { TalkingTactileRegionsFile } from "./regions.gen";

export type RegionsFile = TalkingTactileRegionsFile;
export type Region = RegionsFile["regions"][number];
export type Texture = RegionsFile["textures"][number];
export type Neighbor = NonNullable<Region["neighbors"]>[number];
export type Direction = Neighbor["direction"];
export type PointMm = Region["polygon_mm"][number];
export type Line = NonNullable<RegionsFile["lines"]>[number];
export type Subject = NonNullable<RegionsFile["subject"]>;
export type MergeProposal = NonNullable<RegionsFile["merge_proposals"]>[number];

/** The part a region belongs to: a part's further pieces are <part id>_<k>. */
export function partId(regionId: string): string {
  return regionId.split("_")[0] ?? regionId;
}

export class RegionsError extends Error {
  override name = "RegionsError";
}

const ajv = new Ajv2020({ allErrors: true, allowUnionTypes: true });
const validate = ajv.compile<RegionsFile>(schema);

// Returns the input typed as a RegionsFile, or throws RegionsError listing every problem.
export function parseRegions(data: unknown): RegionsFile {
  if (validate(data)) return data;
  const problems = (validate.errors ?? []).map(
    (e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`,
  );
  throw new RegionsError(`regions.json is invalid: ${problems.join("; ")}`);
}

// Explore runs on touchable regions only. A teacher suggestion (touchable false) is never
// spoken, hit or guided to; parts in needs_teacher have no shape at all. Lines and the
// subject stay: they name touchable regions only.
export function touchableOnly(file: RegionsFile): RegionsFile {
  return { ...file, regions: file.regions.filter((r) => r.touchable) };
}

// The parts a student cannot touch, once each, in file order: suggestion regions (a part's
// pieces share its label), then parts with no shape.
export function untouchableNames(file: RegionsFile): string[] {
  const names = [
    ...file.regions.filter((r) => !r.touchable).map((r) => r.label),
    ...(file.needs_teacher ?? []).map((t) => t.label),
  ];
  return [...new Set(names)];
}
