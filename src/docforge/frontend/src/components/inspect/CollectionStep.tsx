// ====== Code Summary ======
// Step 1 of Inspect mode — lists existing collections and provides a create form
// driven entirely by the discovery endpoint's dynamic_fields for create_collection.

import { useState, useEffect } from 'react'
import type { Collection, DiscoveryResponse, DynamicField } from '../../api/types'
import { listCollections, createCollection, deleteCollection, getDiscovery } from '../../api/client'
import { ChoicePicker } from '../ui/ChoicePicker'

interface Props {
  // Called when the user selects a collection to continue.
  onSelect: (collection: Collection) => void
  // Currently selected collection id (for highlighting).
  selectedId: string | null
}

/**
 * Discovery-driven collection listing and creation step.
 * Builds the create form from discovery dynamic_fields without hardcoding any field names.
 */
export function CollectionStep({ onSelect, selectedId }: Props) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)

  // Create form state
  const [name, setName] = useState('')
  const [pipelineValue, setPipelineValue] = useState<unknown>(undefined)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)

  // 1. Load collections and unscoped discovery on mount.
  useEffect(() => {
    void load()
    void loadDiscovery()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await listCollections()
      setCollections(res.collections)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  async function loadDiscovery() {
    try {
      setDiscovery(await getDiscovery())
    } catch { /* non-critical */ }
  }

  // 2. Extract dynamic field for pipeline from the create_collection endpoint.
  const createEndpoint = discovery?.endpoints.find(e => e.route_name === 'create_collection')
  const pipelineField: DynamicField | undefined = createEndpoint?.dynamic_fields.find(
    df => df.field_path === 'pipeline'
  )

  // 3. Submit form.
  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const body: Record<string, unknown> = { name: name.trim() }
      if (pipelineValue !== undefined && pipelineValue !== null) {
        body.pipeline = pipelineValue
      }
      await createCollection(body)
      setName('')
      setPipelineValue(undefined)
      setShowCreate(false)
      await load()
    } catch (err) {
      setCreateError(String(err))
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this collection and all its documents?')) return
    setDeleteId(id)
    try {
      await deleteCollection(id)
      await load()
    } catch (err) {
      setError(String(err))
    } finally {
      setDeleteId(null)
    }
  }

  return (
    <div className="panel fadein">
      <div className="panel-header">
        <div className="panel-title">Collections</div>
        <button
          type="button"
          className="btn"
          onClick={() => setShowCreate(v => !v)}
        >
          {showCreate ? '✕ Cancel' : '+ New collection'}
        </button>
      </div>

      {/* Create form — fields derived from discovery */}
      {showCreate && (
        <form className="create-form fadein" onSubmit={handleCreate}>
          <div style={{ marginBottom: 12 }}>
            <div className="section-title">Name</div>
            <input
              className="input"
              type="text"
              placeholder="My collection"
              value={name}
              onChange={e => setName(e.target.value)}
              autoFocus
            />
          </div>

          {pipelineField && (
            <ChoicePicker
              field={pipelineField}
              value={pipelineValue}
              onChange={setPipelineValue}
              label="Pipeline"
            />
          )}

          {createError && <div className="error-banner">{createError}</div>}

          <div className="row-end" style={{ marginTop: 14 }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={creating || !name.trim()}
            >
              {creating ? <span className="spin">⟳</span> : null}
              {creating ? ' Creating…' : 'Create'}
            </button>
          </div>
        </form>
      )}

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="text-muted" style={{ padding: '16px 0' }}>
          <span className="spin">⟳</span> Loading collections…
        </div>
      ) : collections.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">📁</div>
          <div>No collections yet. Create one to get started.</div>
        </div>
      ) : (
        <div className="collection-list">
          {collections.map(col => (
            <div
              key={col.id}
              className={`collection-row ${col.id === selectedId ? 'collection-row-active' : ''}`}
              onClick={() => onSelect(col)}
            >
              <div className="collection-row-main">
                <div className="collection-name">{col.name}</div>
                <div className="text-dim" style={{ fontSize: 11 }}>
                  {col.locality_policy}
                  {' · '}
                  {col.embedding_model}
                  {' · '}
                  <span className="mono">{col.pipeline_version}</span>
                </div>
              </div>
              <span className="tag">{col.supported_formats.join(', ')}</span>
              <button
                type="button"
                className="btn-icon btn-icon-danger"
                title="Delete collection"
                disabled={deleteId === col.id}
                onClick={e => { e.stopPropagation(); void handleDelete(col.id) }}
              >
                {deleteId === col.id ? <span className="spin">⟳</span> : '✕'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
