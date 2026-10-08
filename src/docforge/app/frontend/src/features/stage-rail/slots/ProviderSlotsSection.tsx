// ====== Code Summary ======
// The independent provider slots of a stage (embed: dense + sparse). Replaces the single-provider
// picker / chain editor for a stage that exposes `slots`. Notes when both slots share one bge_server
// so the user knows the backend makes a single combined request.

import { Chip } from "../../../components/Chip";
import type { StageView, ValidationIssue } from "../../../api/types";
import { theme } from "../../../theme";
import type { StageRailActions } from "../actions";
import { isCombinedCall } from "./combinedCall";
import { ProviderSlotCard } from "./ProviderSlotCard";
import { deployedKindsFor, useSlotCapabilities } from "./useSlotCapabilities";

interface ProviderSlotsSectionProps {
  stage: StageView;
  actions: StageRailActions;
  issues?: ValidationIssue[];
}

export function ProviderSlotsSection({ stage, actions, issues }: ProviderSlotsSectionProps) {
  const capabilities = useSlotCapabilities();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      {isCombinedCall(stage.slots) && (
        <div>
          <Chip tone="dim" title="Dense and sparse use the same bge_server: one request produces both vectors.">
            combined call (one request)
          </Chip>
        </div>
      )}
      {stage.slots.map((slotView) => (
        <ProviderSlotCard
          key={slotView.slot}
          stageKey={stage.key}
          slotView={slotView}
          deployed={deployedKindsFor(capabilities, slotView.slot)}
          actions={actions}
          issues={issues}
        />
      ))}
    </div>
  );
}
