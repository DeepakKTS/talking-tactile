// Generated from docs/regions.schema.json by scripts/gen-regions-types.ts.
// Do not edit by hand. Run npm run gen:types after changing the schema.

/**
 * The contract between Author and Explore. Explore must run from this file alone for labels, earcons and guidance.
 */
export interface TalkingTactileRegionsFile {
  schema_version: 3;
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
    /**
     * False for a teacher suggestion: not raised on the sheet, and Explore never speaks it or guides to it.
     */
    touchable: boolean;
    /**
     * Why the region needs a look. spill: SAM's mask held another part's prompt point; it is a suggestion and never touchable. thin and under_point_symbol leave the region touchable.
     */
    flags?: {
      reason: "spill" | "thin" | "under_point_symbol";
      detail: string;
    }[];
  }[];
  /**
   * The whole object the figure shows, and its outline: the silhouette. Explore says the label once each time a finger rests inside it on no part.
   */
  subject?: {
    label: string;
    /**
     * @minItems 3
     * @maxItems 200
     */
    polygon_mm: [[number, number], [number, number], [number, number], ...[number, number][]];
  };
  /**
   * Parts that are lines, such as a sulcus or a border: never raised as areas and never touchable. Explore says a line's label when the finger crosses from one region it separates into the other.
   */
  lines?: {
    id: string;
    label: string;
    /**
     * The touchable regions on either side, each by its part's main region id
     *
     * @minItems 2
     * @maxItems 2
     */
    separates?: [string, string];
    /**
     * The labels of the two parts it separates, for the teacher
     *
     * @minItems 2
     * @maxItems 2
     */
    between?: [string, string];
    /**
     * The region the line lies in, when it separates no two touchable regions
     */
    parent?: string | null;
  }[];
  /**
   * Touchable regions drawn as one unbroken shape, which the teacher may merge under the suggested name.
   */
  merge_proposals?: {
    name: string;
    /**
     * @minItems 2
     */
    region_ids: [string, string, ...string[]];
    why: string;
  }[];
  /**
   * Listed parts with no shape to touch: no prompt point survived, SAM gave no mask, or S3 dropped the part.
   */
  needs_teacher?: {
    id: string;
    label: string;
    reason: "no_points" | "no_mask" | "dropped";
    detail: string;
  }[];
}
