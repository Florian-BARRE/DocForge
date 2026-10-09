// ====== Code Summary ======
// The collection shell's in-content sub-nav — equal-depth sub-tabs under ONE rail entry. Pipelines
// shows Ingestion | Search; Settings shows General | Aliases | History | Transfer. Renders nothing on
// every other page. The two strips share the look (TabNav) and the routing convention (an optional
// sub-key on the page's View).

import { TabNav, type TabItem } from "../../components/TabNav";
import type { CollectionSettingsSection, Navigate } from "../../shell/view";

/** Which pipeline editor is showing. */
export type PipelineStage = "ingestion" | "search";

const PIPELINE_STAGES: TabItem<PipelineStage>[] = [
  { key: "ingestion", label: "Ingestion" },
  { key: "search", label: "Search" },
];

const SETTINGS_SECTIONS: TabItem<CollectionSettingsSection>[] = [
  { key: "general", label: "General" },
  { key: "aliases", label: "Aliases" },
  { key: "history", label: "History" },
  { key: "transfer", label: "Transfer" },
];

interface CollectionSubNavProps {
  collectionId: string;
  onNavigate: Navigate;
  pipelineStage?: PipelineStage;
  settingsSection?: CollectionSettingsSection;
}

export function CollectionSubNav({ collectionId, onNavigate, pipelineStage, settingsSection }: CollectionSubNavProps) {
  if (pipelineStage) {
    return (
      <TabNav
        tabs={PIPELINE_STAGES}
        active={pipelineStage}
        onSelect={(stage) => onNavigate({ name: "collection-pipelines", collectionId, stage })}
        navId="collection-pipeline-stage"
        ariaLabel="Pipeline editors"
        panelId="collection-panel"
      />
    );
  }
  if (settingsSection) {
    return (
      <TabNav
        tabs={SETTINGS_SECTIONS}
        active={settingsSection}
        onSelect={(section) => onNavigate({ name: "collection-settings", collectionId, section })}
        navId="collection-settings-section"
        ariaLabel="Settings sections"
        panelId="collection-panel"
      />
    );
  }
  return null;
}
