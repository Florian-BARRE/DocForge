// ====== Code Summary ======
// One vertical entry of the stage rail: switch + title + description + requires hint, its notes
// banner, and its content area shaped by `kind` — a provider picker, a config form, an ordered
// stack, and/or its fallback chains. Disabled stages stay fully visible (greyed) so the whole
// canonical chain is always on screen, per the fixed-shape mandate.

import { Chip } from "../../components/Chip";
import type { Palette, StageView } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { ChainSection } from "./ChainSection";
import { ProviderPicker } from "./ProviderPicker";
import { StackEditor } from "./StackEditor";
import { StageConfigForm } from "./StageConfigForm";
import { StageSwitch } from "./StageSwitch";

interface StageCardProps {
  stage: StageView;
  palette: Palette;
  actions: StageRailActions;
}

export function StageCard({ stage, palette, actions }: StageCardProps) {
  const switchTitle = !stage.removable
    ? "Always on — structural stage"
    : stage.enabled
    ? "Disable this stage"
    : "Enable this stage";

  return (
    <div
      style={{
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
        opacity: stage.enabled ? 1 : 0.65,
        display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: theme.space.m }}>
        <StageSwitch
          checked={stage.enabled}
          disabled={!stage.removable}
          title={switchTitle}
          onChange={(checked) => (checked ? actions.enableStage(stage.key) : actions.disableStage(stage.key))}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <strong style={{ fontSize: theme.font.size.l }}>{stage.title}</strong>
            {stage.requires.length > 0 && (
              <Chip tone="dim" title={`Enabling this also enables: ${stage.requires.join(", ")}`}>
                needs {stage.requires.join(", ")}
              </Chip>
            )}
          </div>
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{stage.description}</div>
        </div>
      </div>

      {stage.notes && (
        <div
          style={{
            color: theme.color.warn, background: theme.color.warnSoft, borderRadius: theme.radius.s,
            padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s,
          }}
        >
          {stage.notes}
        </div>
      )}

      {stage.enabled && stage.kind !== "fixed" && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m, paddingLeft: 34 + theme.space.m }}>
          {stage.kind === "provider" && (
            <>
              <ProviderPicker stage={stage} palette={palette} actions={actions} />
              <StageConfigForm stage={stage} palette={palette} actions={actions} />
            </>
          )}
          {stage.kind === "toggle" && <StageConfigForm stage={stage} palette={palette} actions={actions} />}
          {stage.kind === "stack" && <StackEditor stage={stage} palette={palette} actions={actions} />}
          {stage.chains.map((chain) => (
            <ChainSection key={chain.slot} stageKey={stage.key} chain={chain} palette={palette} actions={actions} />
          ))}
        </div>
      )}
    </div>
  );
}
