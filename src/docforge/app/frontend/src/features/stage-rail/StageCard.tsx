// ====== Code Summary ======
// One vertical entry of the stage rail: switch + title + description + requires hint, its notes
// banner, and its content area shaped by `kind` — a provider picker, a config form, an ordered
// stack, and/or its fallback chains. Every chain-bearing stage renders `ChainSection` GENERICALLY
// (parse/embed's own chain, metagen chunk/document's structgen ladder, enrich's per-figure sites) —
// EXCEPT the stack stage (contextualize): its `chains` entries are informational duplicates of each
// `llm` method's OWN chain, rendered instead inline inside StackEditor/StackMethodCard, because the
// compiler has no slot to accept a direct edit there. Disabled stages stay fully visible (greyed)
// so the whole canonical chain is always on screen, per the fixed-shape mandate.

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
  // A chain-capable provider stage (parse/embed) IS its own chain — see StageViewer.__provider —
  // so ProviderPicker + StageConfigForm below would just duplicate the chain's own step 0 (same
  // provider identity, same config, TWO editors for one value). ChainSection renders that single
  // step as the provider picker itself (ChainStepList's `primaryKindEditable`), so those two are
  // skipped entirely for this case; every other provider stage (chunk) keeps them.
  const ownChain = stage.chains.length === 1 && stage.chains[0].slot === stage.key;

  return (
    <div
      style={{
        position: "relative", overflow: "hidden",
        background: theme.color.surface, border: `1px solid ${stage.enabled ? theme.color.line : theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.l,
        opacity: stage.enabled ? 1 : 0.6,
        display: "flex", flexDirection: "column", gap: theme.space.s,
        boxShadow: theme.shadow.sm,
        transition: "opacity .15s ease, border-color .15s ease",
      }}
    >
      {/* Left hairline — reads "this stage is part of the pipeline" at a glance. Steel, not forge:
          several stages are enabled at once, and orange is reserved for the one thing actively
          being worked (a running job, the primary action) — not every at-rest "on" state. */}
      <div
        style={{
          position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
          background: stage.enabled ? theme.color.dim : "transparent",
        }}
      />
      <div style={{ display: "flex", alignItems: "flex-start", gap: theme.space.m }}>
        <StageSwitch
          checked={stage.enabled}
          disabled={!stage.removable}
          title={switchTitle}
          onChange={(checked) => (checked ? actions.enableStage(stage.key) : actions.disableStage(stage.key))}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700 }}>{stage.title}</strong>
            {stage.requires.length > 0 && (
              <Chip tone="dim" title={`Enabling this also enables: ${stage.requires.join(", ")}`}>
                needs {stage.requires.join(", ")}
              </Chip>
            )}
          </div>
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginTop: 2 }}>{stage.description}</div>
        </div>
      </div>

      {stage.notes && (
        <div
          style={{
            color: theme.color.warn, background: theme.color.warnSoft, borderRadius: theme.radius.m,
            padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s,
          }}
        >
          ⚠ {stage.notes}
        </div>
      )}

      {stage.enabled && stage.kind !== "fixed" && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m, paddingLeft: 34 + theme.space.m }}>
          {stage.kind === "provider" && !ownChain && (
            <>
              <ProviderPicker stage={stage} palette={palette} actions={actions} />
              <StageConfigForm stage={stage} palette={palette} actions={actions} />
            </>
          )}
          {stage.kind === "toggle" && <StageConfigForm stage={stage} palette={palette} actions={actions} />}
          {stage.kind === "stack" && <StackEditor stage={stage} palette={palette} actions={actions} />}
          {stage.kind !== "stack" && stage.chains.map((chain) => (
            <ChainSection key={chain.slot} stageKey={stage.key} chain={chain} palette={palette} actions={actions} />
          ))}
        </div>
      )}
    </div>
  );
}
