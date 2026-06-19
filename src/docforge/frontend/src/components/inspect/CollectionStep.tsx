// ====== Code Summary ======
// Step 1 of Inspect mode — lists existing collections and provides a create form
// driven 100% by /api/v1/discovery via the <RequestForm> primitive.  No field name
// is hardcoded: adding a Pydantic field to CreateCollectionRequest surfaces here
// automatically the next time discovery is fetched.

import { useState, useEffect } from 'react'
import type { Collection, DiscoveryResponse, EndpointDescriptor } from '../../api/types'
import { listCollections, createCollection, deleteCollection, getDiscovery } from '../../api/client'
import { RequestForm } from '../ui/RequestForm'
import { DynamicFieldsGroup } from '../ui/DynamicFieldsGroup'

const STAGE_LABELS: Record<string, string> = {
  parse: 'S1 · Parse',
  enrich: 'S2 · Enrich',
  chunk: 'S4 · Chunk',
  embed: 'S6 · Embed',
}
const STAGE_ORDER = ['parse', 'enrich', 'chunk', 'embed']

interface Props {
  onSelect: (collection: Collection) => void
  selectedId: string | null
}

// Body keys handled outside the generic loop:
//   - `name` is the form's mandatory title field (rendered above)
//   - `pipeline` is rendered as a stage-grouped <DynamicFieldsGroup>
//   - `metadata_schema` is a system-managed collection of fields edited from the config editor
const HOST_RENDERED_KEYS = ['name', 'pipeline']
const DEFERRED_KEYS = ['metadata_schema']

export function CollectionStep({ onSelect, selectedId }: Props) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)

  // Form state — name is mandatory; the body/query maps are owned by the RequestForm primitive.
  const [name, setName] = useState('')
  const [body, setBody] = useState<Record<string, unknown>>({})
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)

  // 1. Load collections + unscoped discovery on mount.
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

  // 2. Locate the create_collection endpoint in discovery; everything else is generic.
  const createEndpoint: EndpointDescriptor | undefined = discovery?.endpoints.find(
    e => e.route_name === 'create_collection',
  )

  // 3. Submit — assemble body and POST.
  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const payload: Record<string, unknown> = { name: name.trim(), ...body }
      await createCollection(payload)
      setName('')
      setBody({})
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

          {createEndpoint && discovery && (
            <>
              <RequestForm
                endpoint={createEndpoint}
                discovery={discovery}
                body={body}
                query={{}}
                onBodyChange={setBody}
                onQueryChange={() => {}}
                excludeBodyFields={[...HOST_RENDERED_KEYS, ...DEFERRED_KEYS]}
              />

              <div className="picker" style={{ marginTop: 8 }}>
                <div className="picker-label">Pipeline</div>
                <DynamicFieldsGroup
                  fields={createEndpoint.dynamic_fields ?? []}
                  prefix="pipeline"
                  value={(body.pipeline as Record<string, unknown> | undefined) ?? {}}
                  onChange={v => setBody(prev => ({ ...prev, pipeline: v }))}
                  groupLabels={STAGE_LABELS}
                  groupOrder={STAGE_ORDER}
                  discovery={discovery}
                />
              </div>
            </>
          )}

          {DEFERRED_KEYS.length > 0 && (
            <div className="picker-note" style={{ marginTop: 8 }}>
              ℹ Custom metadata fields can be added via the config editor after creation.
            </div>
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
