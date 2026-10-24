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
const gain = z.number().positive().max(1);

const ExploreSchema = z.strictObject({
  hysteresis: z.strictObject({
    enter_shrink_mm: nonNegNum,
    exit_grow_mm: nonNegNum,
    enter_hold_ms: nonNegInt,
    exit_hold_ms: nonNegInt,
  }),
  dwell: z.strictObject({ speed_below_mm_s: posNum, hold_ms: posInt, speed_window_ms: posInt }),
  earcons: z.strictObject({
    max_per_second: posNum,
    texture_hz: z.strictObject({
      dots: posNum,
      lines: posNum,
      grid: posNum,
      cross: posNum,
      solid: posNum,
    }),
    default_hz: posNum,
    tone_ms: posInt,
    gain,
    exit_tick_hz: posNum,
    exit_tick_ms: posInt,
    exit_tick_gain: gain,
  }),
  fingertip: z.strictObject({
    contact_offset_mm: nonNegNum,
    filter: z.literal("one_euro"),
    one_euro: z.strictObject({ mincutoff_hz: posNum, beta: nonNegNum, dcutoff_hz: posNum }),
    lost_reset_ms: posInt,
  }),
  hands: z.strictObject({
    max_hands: z.number().int().min(1).max(2),
    min_curled: z.number().int().min(1).max(3), // of middle, ring and pinky
    require_pointing: z.boolean(),
  }),
  guidance: z
    .strictObject({
      update_ms: posInt,
      arrive_inside_ms: nonNegInt,
      beep_hz: posNum,
      beep_ms: posInt,
      beeps_per_s_far: posNum,
      beeps_per_s_near: posNum,
      far_mm: posNum,
      chime_hz: z.array(posNum).min(1),
      chime_note_ms: posInt,
    })
    .refine((g) => g.beeps_per_s_near > g.beeps_per_s_far, {
      message: "beeps_per_s_near must be above beeps_per_s_far",
      path: ["beeps_per_s_near"],
    }),
  intents: z.strictObject({ min_label_similarity: z.number().positive().max(1) }),
  health: z.strictObject({ no_hand_warn_ms: posInt, off_page_points_before_recal: posInt }),
  registration: z.strictObject({ mark_inset_mm: posNum }),
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
