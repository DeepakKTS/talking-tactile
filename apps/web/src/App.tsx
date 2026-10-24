import { routeFromPath } from "./route";

export function App() {
  const route = routeFromPath(window.location.pathname);
  if (route === "author") return <main><h1>Author</h1></main>;
  if (route === "explore") return <main><h1>Explore</h1></main>;
  return (
    <main>
      <h1>Talking Tactile</h1>
      <ul>
        <li><a href="/author">Author a tactile sheet</a></li>
        <li><a href="/explore">Explore a sheet</a></li>
      </ul>
    </main>
  );
}
