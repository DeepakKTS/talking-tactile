import { AuthorPage } from "./author/AuthorPage";
import { ExplorePage } from "./explore/ExplorePage";
import { routeFromPath } from "./route";

export function App() {
  const route = routeFromPath(window.location.pathname);
  if (route === "author") return <AuthorPage />;
  if (route === "explore") return <ExplorePage />;
  return (
    <main className="page">
      <header className="topbar">
        <img className="brand" src="/brand/logo.svg" alt="" width="351" height="45" />
      </header>
      <h1>Talking Tactile</h1>
      <p className="lede">Raised textbook figures a blind student explores by touch, with a phone that names each part and answers questions about the figure.</p>
      <ul className="home-links">
        <li><a className="glass" href="/author">Author a tactile sheet</a></li>
        <li><a className="glass" href="/explore">Explore a sheet</a></li>
      </ul>
    </main>
  );
}
