// ====== Code Summary ======
// The stage rail: the FIXED-SHAPE view of the ingestion pipeline — the whole canonical ordered
// chain as vertical stage cards, always fully visible (disabled stages greyed, never hidden).
// Owns the blob AND its derived StageView[] together; every mutating gesture sends ONE `/apply`
// action to the server, which recompiles + validates + re-derives the stage view in a single
// round-trip — the UI never re-implements cascade/healing semantics. The one exception is TYPING
// (a config field, a chain's score threshold): a local, ephemeral mirror of `stages` keeps
// keystrokes instant while the actual `/apply` call is debounced. Reusable standalone
// (fetches the product default) OR embedded in a collection page (seeded with `initialBlob`,
// saved via `onSave`). All state/effects live in `useStageRailPage` — this component is pure render.

import { Fragment } from "react";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { NoticesBar } from "./NoticesBar";
import { StageCard } from "./StageCard";
import { StageConnector } from "./StageConnector";
import { StageRailHeader } from "./StageRailHeader";
import { useStageRailPage, type UseStageRailPageProps } from "./state/useStageRailPage";

export type StageRailPageProps = UseStageRailPageProps;

export function StageRailPage(props: StageRailPageProps) {
  const rail = useStageRailPage(props);

  if (rail.loadError) return <ErrorState message={rail.loadError} />;
  if (!rail.palette || !rail.stages) return <LoadingState label="loading pipeline stages…" />;
  const { palette, stages } = rail;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: theme.color.bg }}>
      <div
        className="df-rise"
        style={{
          maxWidth: 860, margin: "0 auto", padding: `0 ${theme.space.l}px ${theme.space.l}px`,
          display: "flex", flexDirection: "column",
        }}
      >
        <StageRailHeader
          valid={rail.valid}
          busy={rail.busy}
          debouncePending={rail.debouncePending}
          issueCount={rail.issues.length}
          onSave={props.onSave ? rail.handleSave : undefined}
          saving={rail.saving}
          saveError={rail.saveError}
        />
        {(rail.notices.length > 0 || rail.issues.length > 0 || rail.applyError) && (
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, margin: `${theme.space.m}px 0` }}>
            <NoticesBar notices={rail.notices} issues={rail.issues} />
            {rail.applyError && (
              <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>⚠ {rail.applyError}</div>
            )}
          </div>
        )}
        <div className="df-stagger" style={{ marginTop: theme.space.m, display: "flex", flexDirection: "column" }}>
          {stages.map((stage, index) => (
            <Fragment key={stage.key}>
              {index > 0 && <StageConnector />}
              <StageCard stage={stage} palette={palette} actions={rail.actions} />
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
