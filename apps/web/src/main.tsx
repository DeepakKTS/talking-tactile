import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// The design tokens and the self-hosted fonts, shared by Author and Explore.
import "./styles/tokens.css";
// Validates config/explore.yaml before anything renders; a bad value throws here.
import "./shared/config";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
