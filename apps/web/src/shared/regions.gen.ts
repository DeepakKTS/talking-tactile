// Generated from docs/regions.schema.json by scripts/gen-regions-types.ts.
// Do not edit by hand. Run npm run gen:types after changing the schema.

/**
 * The contract between Author and Explore. Explore must run from this file alone for labels, earcons and guidance.
 */
export interface TalkingTactileRegionsFile {
  schema_version: 1;
  /**
   * sha256 of the normalized source image
   */
  figure_id: string;
  title: string;
  figure_type: "labeled_diagram" | "bar_chart" | "line_graph" | "map" | "flow_diagram" | "other";
  grade_band?: "k5" | "6_8" | "9_12" | "college";
  page: {
    size: "letter" | "a4";
    width_mm: number;
    height_mm: number;
  };
  /**
   * Spoken on first open. Two sentences at most.
   */
  summary: string;
  /**
   * @maxItems 5
   */
  textures: {
    id: "dots" | "lines" | "cross" | "grid" | "solid";
    meaning: string;
    earcon_hz: number;
  }[];
  regions: {
    id: string;
    /**
     * Spoken on dwell. The label only.
     */
    label: string;
    /**
     * Braille key abbreviation when the full label does not fit
     */
    abbrev?: string;
    /**
     * Spoken on 'more'. One or two sentences, from the figure or its caption.
     */
    description?: string;
    /**
     * @minItems 3
     * @maxItems 200
     */
    polygon_mm: [[number, number], [number, number], [number, number], ...[number, number][]];
    /**
     * @minItems 2
     * @maxItems 2
     */
    centroid_mm?: [number, number];
    texture?: string;
    parent?: string | null;
    /**
     * Computed in code. Direction is from this region to the neighbor.
     */
    neighbors?: {
      id: string;
      direction:
        | "up"
        | "down"
        | "left"
        | "right"
        | "up_left"
        | "up_right"
        | "down_left"
        | "down_right"
        | "inside"
        | "around";
    }[];
    source: "sam" | "teacher";
    confidence?: number;
    verified_by_teacher: boolean;
  }[];
}
