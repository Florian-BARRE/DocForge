import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./index.css";

// The theme (light/dark) is applied to <html data-theme> by an inline script in index.html before
// first paint (no flash), and toggled at runtime by the shell's ThemeToggle. Base body colour +
// typography live in index.css, driven by the palette variables — nothing hardcoded here.

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
