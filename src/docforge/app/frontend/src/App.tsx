// ====== Code Summary ======
// Root application component — auth gate + shell mount.
//
// Responsibilities:
//   1. Block render during token rehydration (loading state).
//   2. Render <LoginScreen> when no session is present.
//   3. Render <AppShell> (the cockpit layout) once authenticated.
//
// All layout, navigation, and tab orchestration live in AppShell.
// This file is intentionally minimal — only the auth gate lives here.

// ====== Internal Project Imports ======
import { useAuth } from './auth/AuthContext'
import { LoginScreen } from './auth/LoginScreen'
import { AppShell } from './components/layout/AppShell'
import './global.css'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Root application component for DocForge.
 *
 * Auth gate:
 *   - `loading=true` → blank screen (prevents login flash for returning users).
 *   - `user=null`    → {@link LoginScreen}.
 *   - authenticated  → {@link AppShell} (cockpit layout with all screens).
 *
 * The theme is fully managed by {@link ThemeToggle} (inside AppShell's
 * ContextBar). No theme state is hoisted here.
 */
export function App() {
  const { user, loading } = useAuth()

  // 1. While stored token is being validated, render nothing to avoid flash.
  if (loading) {
    return (
      <div className="app-loading">
        <span className="app-loading-text">Loading...</span>
      </div>
    )
  }

  // 2. No authenticated user — show the login screen.
  if (!user) return <LoginScreen />

  // 3. Authenticated — render the cockpit shell.
  return <AppShell />
}

export default App
