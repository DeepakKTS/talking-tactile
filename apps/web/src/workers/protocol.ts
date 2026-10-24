// Messages between the page and the hand tracking worker. Only landmarks come back; no
// pixels ever leave the worker.

export interface WorkerHand {
  /** 21 landmarks, x and y normalized to the frame (0 to 1). */
  landmarks: [number, number][];
  label: "Left" | "Right" | null;
  score: number | null;
}

export type ToWorker =
  | { type: "init"; modelUrl: string; maxHands: number; delegate?: "GPU" | "CPU"; stubMs?: number }
  | { type: "frame"; id: number; bitmap: ImageBitmap; ts: number };

export type FromWorker =
  | { type: "ready"; backend: string; loadMs: number; errors: string[] }
  | { type: "error"; message: string }
  /** brightness: mean of a 16 x 12 sample of the frame, 0 to 1, to tell a covered camera. */
  | { type: "result"; id: number; hands: WorkerHand[]; inferMs: number; brightness: number };
