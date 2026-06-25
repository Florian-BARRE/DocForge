// ====== Code Summary ======
// <ThemeToggle> — switches the app between dark and light themes by setting
// `data-theme` on <html>.  The current choice is persisted in localStorage so
// returning users keep their preference; first-visit users get OS preference.

import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

const KEY = 'docforge.theme'

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem(KEY)
  if (stored === 'dark' || stored === 'light') return stored
  // Dark-first: default to dark regardless of OS preference (the cockpit is designed dark);
  // users can still opt into light via the toggle (persisted).
  return 'dark'
}

function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-theme', t)
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readInitialTheme)

  // Apply on mount and whenever the user toggles.
  useEffect(() => {
    applyTheme(theme)
    try { window.localStorage.setItem(KEY, theme) } catch { /* ignore quota errors */ }
  }, [theme])

  return (
    <button
      type="button"
      className="btn btn-ghost"
      onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      style={{ fontSize: 14 }}
    >
      {theme === 'dark' ? '☀' : '☾'}
    </button>
  )
}
