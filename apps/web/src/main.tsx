import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// Validates config/explore.yaml before anything renders; a bad value throws here.
import "./shared/config";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
