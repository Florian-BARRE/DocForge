// ====== Code Summary ======
// Settings' own section tabs — Keys / Audit / Deployment. Same real-tablist idiom as
// ActivitySectionTabs (three distinct panels, not a filter over one list).

import { TabNav } from "../../components/TabNav";
import type { View } from "../../shell/view";

export type SettingsSection = NonNullable<Extract<View, { name: "settings" }>["section"]>;

const TABS: { key: SettingsSection; label: string }[] = [
  { key: "keys", label: "Keys" },
  { key: "audit", label: "Audit" },
  { key: "deployment", label: "Deployment" },
];

interface SettingsSectionTabsProps {
  active: SettingsSection;
  onSelect: (section: SettingsSection) => void;
}

export function SettingsSectionTabs({ active, onSelect }: SettingsSectionTabsProps) {
  return (
    <TabNav
      tabs={TABS}
      active={active}
      onSelect={onSelect}
      navId="settings-sections"
      ariaLabel="Settings sections"
    />
  );
}
