// ====== Code Summary ======
// One independent provider slot (embed: dense or sparse): title + description, the kind picker, a
// "Turn off" control (the server refuses it with a notice when it would leave the stage with no
// provider at all) and the picked provider's schema-driven config form.

import { Button } from "../../../components/Button";
import { Chip } from "../../../components/Chip";
import type { ProviderSlotView, ValidationIssue } from "../../../api/types";
import { theme } from "../../../theme";
import type { StageRailActions } from "../actions";
import { SlotConfigForm } from "./SlotConfigForm";
import { SlotKindSelect } from "./SlotKindSelect";

interface ProviderSlotCardProps {
  stageKey: string;
  slotView: ProviderSlotView;
  deployed: string[] | null;
  actions: StageRailActions;
  issues?: ValidationIssue[];
}

export function ProviderSlotCard({ stageKey, slotView, deployed, actions, issues }: ProviderSlotCardProps) {
  const off = slotView.provider === null;
  return (
    <section
      aria-label={slotView.title}
      style={{
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, padding: theme.space.m,
        background: off ? theme.color.surface2 : theme.color.surface,
        display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ fontFamily: theme.font.display, fontWeight: 700, color: theme.color.text }}>{slotView.title}</strong>
        {off && <Chip tone="dim">off</Chip>}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: theme.space.s }}>
          <SlotKindSelect
            label={`${slotView.title} provider`}
            value={slotView.provider}
            available={slotView.available}
            deployed={deployed}
            onSelect={(kind) => actions.setSlotProvider(stageKey, slotView.slot, kind)}
          />
          {!off && (
            <Button size="sm" variant="secondary" onClick={() => actions.setSlotProvider(stageKey, slotView.slot, null)}>
              Turn off
            </Button>
          )}
        </div>
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{slotView.description}</div>
      <SlotConfigForm
        slotView={slotView}
        issues={issues}
        onChange={(field, value) => actions.setSlotConfig(stageKey, slotView.slot, field, value)}
      />
    </section>
  );
}
