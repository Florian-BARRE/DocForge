// ====== Code Summary ======
// The Layout tab's page-zoom control — one shared setting above every page render: two fit presets
// ("Fit width" / "Fit page") plus a -/+ zoom step and its live percentage, replacing the old fixed
// `86vh` cap (see pageZoom.ts for the sizing math this drives). File-explorer-style segmented
// buttons, same visual family as ViewModeToggle — the active preset carries the forge accent, the
// rest stay steel/muted.

import { theme as t } from "../../../theme";
import { zoomPercentLabel } from "./pageZoom";
import type { PageZoomControls } from "./usePageZoom";

function presetButtonStyle(active: boolean) {
  return {
    cursor: "pointer",
    padding: `4px ${t.space.s}px`,
    borderRadius: t.radius.s,
    border: "none",
    fontFamily: t.font.family,
    fontSize: t.font.size.xs,
    fontWeight: t.font.weight.medium,
    background: active ? t.color.accentSoft : "transparent",
    color: active ? t.color.accentSafe : t.color.mute,
    whiteSpace: "nowrap" as const,
  };
}

function stepButtonStyle(disabled: boolean) {
  return {
    cursor: disabled ? "default" : "pointer",
    width: 22,
    height: 22,
    display: "grid",
    placeItems: "center",
    borderRadius: t.radius.s,
    border: "none",
    background: "transparent",
    color: disabled ? t.color.line : t.color.mute,
    fontFamily: t.font.mono,
    fontSize: t.font.size.s,
  };
}

export function PageZoomControl({ zoom, setPreset, zoomIn, zoomOut, canZoomIn, canZoomOut }: PageZoomControls) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: t.space.xs,
        padding: 2,
        background: t.color.surface,
        border: `1px solid ${t.color.line}`,
        borderRadius: t.radius.m,
      }}
    >
      <button
        type="button"
        aria-pressed={zoom.preset === "fit-width"}
        onClick={() => setPreset("fit-width")}
        style={presetButtonStyle(zoom.preset === "fit-width")}
      >
        Fit width
      </button>
      <button
        type="button"
        aria-pressed={zoom.preset === "fit-page"}
        onClick={() => setPreset("fit-page")}
        style={presetButtonStyle(zoom.preset === "fit-page")}
      >
        Fit page
      </button>
      <div style={{ width: 1, height: 16, background: t.color.line, flex: "none" }} aria-hidden="true" />
      <button
        type="button"
        aria-label="Zoom out"
        disabled={!canZoomOut}
        onClick={zoomOut}
        style={stepButtonStyle(!canZoomOut)}
      >
        −
      </button>
      <span
        style={{
          minWidth: 34,
          textAlign: "center",
          fontFamily: t.font.mono,
          fontSize: t.font.size.xs,
          color: t.color.dim,
        }}
      >
        {zoomPercentLabel(zoom.step)}
      </span>
      <button
        type="button"
        aria-label="Zoom in"
        disabled={!canZoomIn}
        onClick={zoomIn}
        style={stepButtonStyle(!canZoomIn)}
      >
        +
      </button>
    </div>
  );
}
