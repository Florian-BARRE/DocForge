---
name: ui5-auth-admin-scoping
description: UI-5 — auth/admin UI re-architected by scope: AccountMenu, ImpersonationBanner, Access tab, AdminView simplified to Users-only
metadata:
  type: project
---

## UI-5 auth/admin scope split (2026-06-26)

The monolithic AdminView 3-tab lump was replaced with proper scoping:

1. **Personal (API Keys)** → `AccountMenu` (components/layout/AccountMenu.tsx)  
   - User badge in ContextBar top-right now opens a dropdown  
   - Items: "API Keys" (Drawer with ApiKeysPanel) + "Sign out"  
   - Replaces the old "Sign out" button inline + the "API Keys" admin tab

2. **Per-collection (Access/Collaborators)** → `CollectionAccessPanel` in ContextBar "Access" sub-tab  
   - `CollectionTab` type extended to include `'access'`  
   - Tab shows when `isCollectionAdmin` (canAdmin(user, grants, collectionId)) — root always sees it  
   - AppShell passes `isCollectionAdmin` to ContextBar; ContextBar conditionally shows the tab  
   - On click, `handleTabChange('access')` skips `setActiveView()` (no GlobalView counterpart)

3. **Instance (Users)** → `AdminView` simplified to Users-only  
   - Old 3-tab structure retired; AdminView now just wraps UsersPanel  
   - "Act as" button in UsersPanel rows (non-root, active, non-self, only when not already impersonating)

## Impersonation flow (AuthContext)

`AuthContext` now carries `stashedToken` (in-memory, not localStorage):
- `actAs(userId)`: calls `impersonateUser(userId)`, stashes current root token, switches to impersonation token + refetches /auth/me as target
- `exitImpersonation()`: restores stashed root token + refetches /auth/me as root  
- `isImpersonating = stashedToken !== null`
- `impersonatedUser = isImpersonating ? user : null` (current user when impersonating)
- `clearSession()` also clears stashedToken

**Why:** Prevents nested impersonation: UsersPanel hides "Act as" when `onActAs` prop is absent (AdminView passes it undefined when isImpersonating). NavRail Admin entry hidden while impersonating (`showAdmin = isRoot && !isImpersonating`).

## ImpersonationBanner

Full-width amber bar at top of `app-main` (above ContextBar), renders nothing when !isImpersonating.  
CSS classes: `.impersonation-banner`, `.impersonation-banner-user`, `.impersonation-banner-note` — all in global.css using CSS vars (no hardcoded colors except alpha-transparent backgrounds).

## CSS additions (global.css)

`.account-menu-wrapper`, `.account-menu-trigger`, `.account-menu-item`, `.account-menu-item-danger` — account dropdown styling.  
`.impersonation-banner`, `.impersonation-banner-user`, `.impersonation-banner-note` — warning bar.

## What was retired

AdminView's 3-tab structure with API Keys + Collaborators tabs. The "Sign out" button from ContextBar (moved into AccountMenu). `AdminViewProps.activeCollectionId` prop removed.

**How to apply:** When adding new user-scoped features, put them in AccountMenu. Per-collection admin features go in the Access tab. Instance-wide root features go in AdminView.
