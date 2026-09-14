// ====== Code Summary ======
// The deployment scope's admin surface: Keys | Audit | Deployment, URL-driven (`view.section`, see
// shell/view.ts), same convention as ActivityPage's `tab`. Keys hosts key lifecycle management
// (AuthKeysPage's content); Audit surfaces the append-only audit trail; Deployment renders the
// GET /capabilities self-description.

import { TopContentBar } from "../../shell/TopContentBar";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { AuditTab } from "./AuditTab";
import { AuthKeysPage } from "./AuthKeysPage";
import { DeploymentTab } from "./DeploymentTab";
import { SettingsSectionTabs, type SettingsSection } from "./SettingsSectionTabs";

interface SettingsPageProps {
  section: SettingsSection;
  onNavigate: Navigate;
}

const SUBTITLE: Record<SettingsSection, string> = {
  keys: "Bearer API keys — create, rotate, and revoke access to the REST API.",
  audit: "Who did what, to what, and when — every mutating request against this deployment.",
  deployment: "This deployment's version, hardware, reachable services, and available pipeline kinds.",
};

export function SettingsPage({ section, onNavigate }: SettingsPageProps) {
  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <TopContentBar page="Settings" subtitle={SUBTITLE[section]} onNavigate={onNavigate} />
      <div style={{ marginBottom: theme.space.l }}>
        <SettingsSectionTabs active={section} onSelect={(next) => onNavigate({ name: "settings", section: next })} />
      </div>
      {section === "keys" && <AuthKeysPage onNavigate={onNavigate} />}
      {section === "audit" && <AuditTab />}
      {section === "deployment" && <DeploymentTab />}
    </div>
  );
}
