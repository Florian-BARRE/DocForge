import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./index.css";
import { theme } from "./theme";

// Base document styling is driven from the theme tokens (not hardcoded in index.css, which would
// silently drift) — applied synchronously before first render so there is no unstyled flash.
Object.assign(document.body.style, {
  background: theme.color.bg,
  color: theme.color.text,
  fontFamily: theme.font.family,
  fontSize: `${theme.font.size.l}px`,
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
