import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Load Inter font weights 400/500/600 — body text, labels, headings.
// Mono (JetBrains Mono / system ui-monospace) handles IDs/hashes/code.
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'

// React Flow base styles — imported before global.css so our tokens override them.
import '@xyflow/react/dist/style.css'
import './global.css'
import App from './App'
import { AuthProvider } from './auth/AuthContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
