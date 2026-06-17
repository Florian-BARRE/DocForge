// ====== Code Summary ======
// Root application component — tab navigation between Inspect, Browse, and Search views.
// No global context; each view manages its own state. Tab switching is orchestrated here.

import { useState } from 'react'
import type { Collection, Document } from './api/types'
import { InspectView } from './components/inspect/InspectView'
import { BrowseView } from './components/browse/BrowseView'
import { SearchView } from './components/search/SearchView'
import './global.css'

type Tab = 'inspect' | 'browse' | 'search'

// Carries a pre-selected collection + document into the Inspect tab.
interface InspectTarget {
  collection: Collection
  doc: Document
}

export function App() {
  const [tab, setTab] = useState<Tab>('inspect')
  const [inspectTarget, setInspectTarget] = useState<InspectTarget | null>(null)

  // Called by BrowseView when user clicks "Inspect" on a document.
  function handleInspect(collection: Collection, doc: Document) {
    setInspectTarget({ collection, doc })
    setTab('inspect')
  }

  function switchTab(t: Tab) {
    setTab(t)
  }

  return (
    <div className="shell">
      {/* Top bar with logo and mode tabs */}
      <header className="topbar">
        <span className="topbar-logo">DocForge</span>
        <nav className="topbar-tabs">
          <button
            type="button"
            className={`topbar-tab ${tab === 'inspect' ? 'topbar-tab-active' : ''}`}
            onClick={() => switchTab('inspect')}
          >
            Inspect
          </button>
          <button
            type="button"
            className={`topbar-tab ${tab === 'browse' ? 'topbar-tab-active' : ''}`}
            onClick={() => switchTab('browse')}
          >
            Collections
          </button>
          <button
            type="button"
            className={`topbar-tab ${tab === 'search' ? 'topbar-tab-active' : ''}`}
            onClick={() => switchTab('search')}
          >
            Search
          </button>
        </nav>
      </header>

      {/* Active view */}
      <div className="main-content">
        {tab === 'inspect' && (
          <InspectView
            preloadedCollection={inspectTarget?.collection ?? null}
            preloadedDoc={inspectTarget?.doc ?? null}
            onTargetConsumed={() => setInspectTarget(null)}
          />
        )}
        {tab === 'browse' && (
          <BrowseView onInspect={handleInspect} />
        )}
        {tab === 'search' && (
          <SearchView />
        )}
      </div>
    </div>
  )
}

export default App
