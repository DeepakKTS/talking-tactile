// config/explore.yaml, validated once at startup. Every tunable number in Explore comes from
// here. The YAML is bundled at build time, so Explore needs no network to read it.
import { z } from "zod";
import exploreRaw from "../../../../config/explore.yaml";

export class ConfigError extends Error {
  override name = "ConfigError";
}

const posNum = z.number().positive();
const nonNegNum = z.number().nonnegative();
const posInt = z.number().int().positive();
const nonNegInt = z.number().int().nonnegative();

const ExploreSchema = z.strictObject({
  hysteresis: z.strictObject({
    enter_shrink_mm: nonNegNum,
    exit_grow_mm: nonNegNum,
    enter_hold_ms: nonNegInt,
    exit_hold_ms: nonNegInt,
  }),
  dwell: z.strictObject({ speed_below_mm_s: posNum, hold_ms: posInt }),
  earcons: z.strictObject({ max_per_second: posNum }),
  fingertip: z.strictObject({
    contact_offset_mm: nonNegNum,
    filter: z.literal("one_euro"),
    one_euro: z.strictObject({ mincutoff_hz: posNum, beta: nonNegNum, dcutoff_hz: posNum }),
  }),
  guidance: z.strictObject({ update_ms: posInt, arrive_inside_ms: nonNegInt }),
  health: z.strictObject({ no_hand_warn_ms: posInt, off_page_points_before_recal: posInt }),
});

export type ExploreConfig = z.infer<typeof ExploreSchema>;

export function loadExploreConfig(data: unknown, source = "config/explore.yaml"): ExploreConfig {
  const result = ExploreSchema.safeParse(data);
  if (result.success) return result.data;
  const problems = result.error.issues.map((issue) => {
    const keys = "keys" in issue ? issue.keys : [];
    const where = [...issue.path, ...keys].join(".") || "(top)";
    return `${where}: ${issue.message}`;
  });
  throw new ConfigError(`${source}: ${problems.join("; ")}`);
}

export const EXPLORE: ExploreConfig = loadExploreConfig(exploreRaw);
