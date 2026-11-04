// Loads the sheet Explore runs on. Only published versions, which the API locks after the
// tactile rules pass; a draft URL is never built here. The last good copy of each version
// is kept in localStorage, so the page can reopen a sheet with the network down.
import schema from "../../../../docs/regions.schema.json";
import { RegionsError, type RegionsFile, parseRegions, touchableOnly, untouchableNames } from "../shared/regions";

export class LoadError extends Error {
  override name = "LoadError";
}

export type Version = number | "latest";

interface LoaderDeps {
  fetch: (url: string) => Promise<Response>;
  storage: Pick<Storage, "getItem" | "setItem"> | null;
}

const FIGURE_ID = /^[0-9a-f]{64}$/;
const SCHEMA_VERSION = schema.properties.schema_version.const;
export const OTHER_VERSION = "This sheet was made for another version of Explore. Ask your teacher to publish it again.";
export const DAMAGED = "The sheet is damaged. Ask your teacher to publish it again.";
const NOT_FOUND = 404;
const SERVER_ERROR = 500;

export function publishedUrl(figureId: string, version: Version): string {
  return `/api/figures/${figureId}/published/${String(version)}/regions.json`;
}

const key = (figureId: string, version: Version) => `tt-published-${figureId}-${String(version)}`;
const VERSION_HEADER = "X-Published-Version";

// The version number a load stands for: the one asked for, or what the server said "latest" was.
function versionOf(asked: Version, said: string | null): number | null {
  if (asked !== "latest") return asked;
  const n = Number(said);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

export async function loadPublished(
  figureId: string,
  version: Version,
  deps: LoaderDeps,
): Promise<Loaded> {
  if (!FIGURE_ID.test(figureId)) throw new LoadError("That is not a figure id.");
  if (version !== "latest" && !(Number.isInteger(version) && version >= 1)) {
    throw new LoadError("That is not a published version.");
  }
  const fromSaved = (): Loaded | null => {
    const saved = read(deps.storage, key(figureId, version));
    return saved ? { ...saved, version: versionOf(version, readItem(deps.storage, `${key(figureId, version)}-version`)), from: "saved" } : null;
  };
  let res: Response;
  try {
    res = await deps.fetch(publishedUrl(figureId, version));
  } catch {
    const saved = fromSaved();
    if (saved) return saved;
    throw new LoadError("The sheet could not be loaded. Check the network.");
  }
  if (res.status === NOT_FOUND) throw new LoadError("This figure is not published yet.");
  // A stopped API answers 502 through the web server's proxy: the saved copy still works.
  if (res.status >= SERVER_ERROR) {
    const saved = fromSaved();
    if (saved) return saved;
  }
  if (!res.ok) throw new LoadError(`The sheet could not be loaded (${res.status}).`);
  const text = await res.text();
  const sheet = parse(text);
  const loaded = versionOf(version, res.headers.get(VERSION_HEADER));
  try {
    deps.storage?.setItem(key(figureId, version), text);
    if (loaded !== null) deps.storage?.setItem(`${key(figureId, version)}-version`, String(loaded));
  } catch {
    // Storage full or blocked: the sheet still works, it just cannot reopen offline.
  }
  return { ...sheet, version: loaded, from: "network" };
}

export interface Loaded {
  file: RegionsFile; // touchable regions only
  notTouchable: string[]; // the names Explore says once at the start
  version: number | null; // the published version this is; null when the server did not say
  from: "network" | "saved";
}

// The file as Explore uses it: valid, touchable regions only, and the names of the rest.
// The messages are read to a student: plain words, and what to do next.
function parse(text: string): Omit<Loaded, "from" | "version"> {
  try {
    const json: unknown = JSON.parse(text);
    const version = typeof json === "object" && json !== null ? (json as { schema_version?: unknown }).schema_version : undefined;
    if (version !== undefined && version !== SCHEMA_VERSION) throw new LoadError(OTHER_VERSION);
    const file = parseRegions(json);
    return { file: touchableOnly(file), notTouchable: untouchableNames(file) };
  } catch (err) {
    if (err instanceof RegionsError || err instanceof SyntaxError) throw new LoadError(DAMAGED);
    throw err;
  }
}

function read(storage: LoaderDeps["storage"], k: string): Omit<Loaded, "from" | "version"> | null {
  try {
    const text = storage?.getItem(k);
    return text ? parse(text) : null;
  } catch {
    return null;
  }
}

function readItem(storage: LoaderDeps["storage"], k: string): string | null {
  try {
    return storage?.getItem(k) ?? null;
  } catch {
    return null;
  }
}
