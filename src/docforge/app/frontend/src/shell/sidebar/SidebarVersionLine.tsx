// ====== Code Summary ======
// The rail footer's always-visible deployment info line — a quiet mono version stamp, only mounted
// once expanded (no room in the ~72px collapsed rail, same rule as ThemeToggle/TokenControl's
// compact stand-ins). Machine value (a version string) so it uses the mono face per brand.md.

import { theme as t } from "../../theme";
import { useDeploymentVersion } from "../useDeploymentVersion";

export function SidebarVersionLine() {
  const version = useDeploymentVersion();
  return (
    <div
      style={{
        fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute,
        padding: `0 ${t.space.xs}px`, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}
    >
      DocForge {version ? `v${version}` : "…"}
    </div>
  );
}
