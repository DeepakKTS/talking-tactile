export type Route = "author" | "explore" | "home";

// Maps a URL path to one of the app's routes. Unknown paths go home.
export function routeFromPath(path: string): Route {
  const first = path.split("/").filter(Boolean)[0];
  if (first === "author" || first === "explore") return first;
  return "home";
}
