// ====== Code Summary ======
// <RequestForm> — the single discovery-driven form primitive.
//
// Given an EndpointDescriptor (from /api/v1/discovery) it renders, in order:
//   1. Static body fields resolved from `endpoint.input.schema_ref` against `components`.
//      Each JSON-Schema property becomes a FieldInput (scalar, enum, secret) or a
//      <StringListInput> (array of strings).  Nested $ref objects render inline as
//      sub-forms via a recursive call; arrays of objects expose a chip-list builder.
//   2. Dynamic-field overlays whose `field_path` lives in the body — delegated to
//      <ChoicePicker> (pipeline / filters / weights / metadata / etc.).
//   3. Query parameters declared by the endpoint (`endpoint.query_params`).
//
// The host view owns submit semantics: it controls `body`/`query` state and calls
// its own API client when the user clicks "submit".  No field name is hardcoded;
// adding a Pydantic field on the backend surfaces here automatically the next time
// /discovery is fetched.

import { useMemo } from 'react'
import type {
  DiscoveryResponse,
  DynamicField,
  EndpointDescriptor,
  FieldDescriptor,
  ParamSchema,
} from '../../api/types'
import { ChoicePicker } from './ChoicePicker'
import { FieldInput } from './FieldInput'
import { StringListInput } from './StringListInput'

// ── Shapes used internally for resolving a schema_ref. ────────────────────────

export interface JsonSchemaProp {
  type?: string
  title?: string
  default?: unknown
  enum?: string[]
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
  items?: JsonSchemaProp
  description?: string
  $ref?: string
  additionalProperties?: unknown
  properties?: Record<string, JsonSchemaProp>
  anyOf?: JsonSchemaProp[]
  oneOf?: JsonSchemaProp[]
  allOf?: JsonSchemaProp[]
}

export interface JsonObjectSchema {
  type?: string
  properties?: Record<string, JsonSchemaProp>
  required?: string[]
  title?: string
  description?: string
}

interface Props {
  // The endpoint descriptor straight from `discovery.endpoints`.
  endpoint: EndpointDescriptor
  // The full discovery payload (used to resolve schema_refs against components).
  discovery: DiscoveryResponse
  // Controlled body and query state owned by the host view.
  body: Record<string, unknown>
  query: Record<string, unknown>
  onBodyChange: (body: Record<string, unknown>) => void
  onQueryChange: (query: Record<string, unknown>) => void
  // Optional: body field paths to skip (the host renders them separately).
  // Path syntax matches JSON-pointer-ish dot paths ("name", "pipeline", "metadata_schema").
  excludeBodyFields?: string[]
  // Optional: dynamic-field paths to skip.
  excludeDynamicFields?: string[]
  // Optional: render only fields whose top-level body key matches one of these.
  // Used by the config editor to scope the patch.pipeline.* overlays per stage.
  includeBodyFields?: string[]
  // Optional banner shown above the form (e.g. validation issues).
  banner?: React.ReactNode
}

/**
 * Discovery-driven request body + query form.
 *
 * The host view supplies the controlled state and the submit button; this primitive
 * only renders inputs.  Designed to be the single source of truth for "how does this
 * endpoint look as a form" so every form in the app shares the same drift-proof code.
 */
export function RequestForm({
  endpoint, discovery, body, query, onBodyChange, onQueryChange,
  excludeBodyFields, excludeDynamicFields, includeBodyFields, banner,
}: Props) {
  // 1. Resolve the request-body schema and split its properties by render strategy.
  const formSpec = useMemo(
    () => buildFormSpec(endpoint, discovery, excludeBodyFields, excludeDynamicFields, includeBodyFields),
    [endpoint, discovery, excludeBodyFields, excludeDynamicFields, includeBodyFields],
  )

  function setBodyKey(key: string, value: unknown) {
    if (value === undefined) {
      const next = { ...body }
      delete next[key]
      onBodyChange(next)
    } else {
      onBodyChange({ ...body, [key]: value })
    }
  }

  function setQueryKey(key: string, value: unknown) {
    if (value === undefined || value === null || value === '') {
      const next = { ...query }
      delete next[key]
      onQueryChange(next)
    } else {
      onQueryChange({ ...query, [key]: value })
    }
  }

  return (
    <div className="request-form">
      {banner}

      {/* Static body fields */}
      {formSpec.bodyProps.length > 0 && (
        <div className="picker">
          <div className="picker-label">Request body</div>
          <div className="picker-params">
            {formSpec.bodyProps.map(prop => renderBodyProp(prop, body, setBodyKey))}
          </div>
        </div>
      )}

      {/* Dynamic-field overlays (pipeline / filters / weights / metadata / …) */}
      {formSpec.dynamicFields.map(df => (
        <ChoicePicker
          key={df.field_path}
          field={df}
          value={body[df.field_path]}
          onChange={v => setBodyKey(df.field_path, v)}
          label={labelFromPath(df.field_path)}
          discovery={discovery}
        />
      ))}

      {/* Query parameters */}
      {formSpec.queryParams.length > 0 && (
        <div className="picker">
          <div className="picker-label">Query parameters</div>
          <div className="picker-params">
            {formSpec.queryParams.map(q => (
              <FieldInput
                key={q.name}
                schema={q.schema}
                value={query[q.name]}
                onChange={v => setQueryKey(q.name, v)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Render dispatch for one body property. ─────────────────────────────────────

interface BodyProp {
  name: string
  // 'field' → FieldInput; 'list-of-strings' → StringListInput; 'nested-object' → recursive
  // body slot rendered as a sub-section; 'array-of-objects' → JSON chip builder.
  kind: 'field' | 'list-of-strings' | 'array-of-objects' | 'nested-object'
  schema: ParamSchema
  // Set for nested-object: the resolved schema for the sub-form.
  nested?: JsonObjectSchema
  // Original JSON schema property (kept for fallback rendering).
  raw: JsonSchemaProp
}

function renderBodyProp(
  prop: BodyProp,
  body: Record<string, unknown>,
  setBodyKey: (key: string, value: unknown) => void,
): React.ReactNode {
  if (prop.kind === 'list-of-strings') {
    const value = (body[prop.name] as string[] | undefined) ?? (prop.raw.default as string[] | undefined) ?? []
    return (
      <StringListInput
        key={prop.name}
        name={prop.name}
        label={prop.schema.label || prop.name}
        description={prop.schema.description ?? ''}
        value={value}
        onChange={v => setBodyKey(prop.name, v)}
      />
    )
  }

  if (prop.kind === 'array-of-objects') {
    // Defer complex array-of-objects to a JSON chip builder.  This is intentionally
    // utilitarian — a richer editor would be a dedicated overlay (e.g. metadata_schema).
    const value = body[prop.name]
    return (
      <ArrayOfObjectsInput
        key={prop.name}
        name={prop.name}
        label={prop.schema.label || prop.name}
        description={prop.schema.description ?? ''}
        value={Array.isArray(value) ? value : []}
        onChange={v => setBodyKey(prop.name, v.length > 0 ? v : undefined)}
      />
    )
  }

  if (prop.kind === 'nested-object' && prop.nested?.properties) {
    const sub = (body[prop.name] as Record<string, unknown> | undefined) ?? {}
    return (
      <div key={prop.name} className="picker" style={{ marginTop: 8 }}>
        <div className="picker-label">{prop.schema.label || prop.name}</div>
        <div className="picker-params">
          {Object.entries(prop.nested.properties).map(([childName, childProp]) => {
            const childBody = buildBodyProp(childName, childProp)
            if (!childBody) return null
            return renderBodyProp(
              childBody,
              sub,
              (k, v) => setBodyKey(prop.name, v === undefined ? undefined : { ...sub, [k]: v }),
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <FieldInput
      key={prop.name}
      schema={prop.schema}
      value={body[prop.name]}
      onChange={v => setBodyKey(prop.name, v)}
    />
  )
}

// ── Form spec extraction ───────────────────────────────────────────────────────

interface FormSpec {
  bodyProps: BodyProp[]
  dynamicFields: DynamicField[]
  queryParams: Array<{ name: string; schema: ParamSchema }>
}

/** Resolve `#/components/schemas/Name` against the discovery components block. */
export function resolveSchemaRef(
  discovery: DiscoveryResponse,
  ref: string | null | undefined,
): JsonObjectSchema | null {
  if (!ref || !ref.startsWith('#/components/schemas/')) return null
  const name = ref.slice('#/components/schemas/'.length)
  const schemas = (discovery.components?.schemas ?? {}) as Record<string, unknown>
  return (schemas[name] as JsonObjectSchema | undefined) ?? null
}

function buildFormSpec(
  endpoint: EndpointDescriptor,
  discovery: DiscoveryResponse,
  excludeBody?: string[],
  excludeDynamic?: string[],
  includeBody?: string[],
): FormSpec {
  const exclBody = new Set(excludeBody ?? [])
  const exclDyn = new Set(excludeDynamic ?? [])
  const inclBody = includeBody ? new Set(includeBody) : null

  // Dynamic field paths that overlay a TOP-LEVEL body key (we strip nested paths
  // since their parent overlay handles them — e.g. `pipeline.parse.provider` is
  // consumed by the `pipeline` overlay in CollectionStep, not as its own field).
  const dynamicFields: DynamicField[] = []
  const overlaidBodyKeys = new Set<string>()
  for (const df of endpoint.dynamic_fields ?? []) {
    if (exclDyn.has(df.field_path)) continue
    const topKey = df.field_path.split('.')[0]
    if (df.field_path === topKey) {
      // Root-level overlay (filters / weights / metadata / pipeline)
      if (inclBody && !inclBody.has(topKey)) continue
      if (exclBody.has(topKey)) continue
      dynamicFields.push(df)
      overlaidBodyKeys.add(topKey)
    }
    // Nested overlays (patch.pipeline.parse.provider …) are surfaced by the parent
    // overlay's ChoicePicker (the ConfigStep handles its own per-stage scoping).
  }

  // Static body properties
  const bodyProps: BodyProp[] = []
  const schema = resolveSchemaRef(discovery, endpoint.input?.schema_ref)
  if (schema?.properties) {
    for (const [propName, prop] of Object.entries(schema.properties)) {
      if (exclBody.has(propName)) continue
      if (inclBody && !inclBody.has(propName)) continue
      if (overlaidBodyKeys.has(propName)) continue
      const built = buildBodyProp(propName, prop, discovery)
      if (built) bodyProps.push(built)
    }
  }

  // Query params (skip path params — those come from the host context)
  const queryParams = (endpoint.query_params ?? []).map(qp => ({
    name: qp.name,
    schema: queryParamToSchema(qp),
  }))

  return { bodyProps, dynamicFields, queryParams }
}

/** Convert one JSON-Schema property into a render-ready BodyProp (or null when unsupported). */
function buildBodyProp(
  name: string,
  prop: JsonSchemaProp,
  discovery?: DiscoveryResponse,
): BodyProp | null {
  const label = prop.title || humanize(name)
  const description = prop.description ?? ''

  // Array — string list vs object list
  if (prop.type === 'array') {
    if (prop.items?.type === 'string') {
      return {
        name, kind: 'list-of-strings', raw: prop,
        schema: paramSchema(name, 'str', label, prop.default, description),
      }
    }
    // Array of objects (or refs) — chip builder
    return {
      name, kind: 'array-of-objects', raw: prop,
      schema: paramSchema(name, 'str', label, prop.default, description),
    }
  }

  // Inline nested object → recurse as sub-form
  if (prop.type === 'object' && prop.properties) {
    return {
      name, kind: 'nested-object', raw: prop, nested: prop as JsonObjectSchema,
      schema: paramSchema(name, 'str', label, prop.default, description),
    }
  }

  // Free-form object (additionalProperties true, no schema) — defer to JSON textarea
  if (prop.type === 'object') {
    return {
      name, kind: 'array-of-objects', raw: prop,
      schema: paramSchema(name, 'str', label, prop.default, description),
    }
  }

  // $ref → resolve and recurse
  if (prop.$ref && discovery) {
    const resolved = resolveSchemaRef(discovery, prop.$ref)
    if (resolved?.properties) {
      return {
        name, kind: 'nested-object', raw: prop, nested: resolved,
        schema: paramSchema(name, 'str', label, prop.default, description),
      }
    }
  }

  // Scalar — let FieldInput handle the rest
  const uiType = jsonTypeToUi(prop)
  const min = prop.minimum ?? (prop.exclusiveMinimum != null
    ? prop.exclusiveMinimum + (uiType === 'int' ? 1 : 0) : undefined)
  const max = prop.maximum ?? (prop.exclusiveMaximum != null
    ? prop.exclusiveMaximum - (uiType === 'int' ? 1 : 0) : undefined)
  return {
    name, kind: 'field', raw: prop,
    schema: {
      name, type: uiType, label, default: prop.default, description,
      min: min ?? null, max: max ?? null, enum: prop.enum ?? null,
    },
  }
}

/** Convert a query parameter's OpenAPI shape into the ParamSchema FieldInput consumes. */
function queryParamToSchema(qp: FieldDescriptor): ParamSchema {
  const uiType = qp.enum && qp.enum.length > 0
    ? 'str'
    : qp.type === 'integer' ? 'int'
    : qp.type === 'number'  ? 'float'
    : qp.type === 'boolean' ? 'bool'
    : 'str'
  return {
    name: qp.name,
    type: uiType,
    label: humanize(qp.name),
    default: qp.default,
    description: qp.description ?? '',
    min: qp.min ?? null,
    max: qp.max ?? null,
    enum: qp.enum ?? null,
  }
}

function paramSchema(
  name: string, type: string, label: string, def: unknown, description: string,
): ParamSchema {
  return { name, type, label, default: def, description, min: null, max: null, enum: null }
}

function jsonTypeToUi(prop: JsonSchemaProp): string {
  if (prop.enum && prop.enum.length > 0) return 'str'
  switch (prop.type) {
    case 'integer': return 'int'
    case 'number':  return 'float'
    case 'boolean': return 'bool'
    default:        return 'str'
  }
}

function humanize(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function labelFromPath(path: string): string {
  return humanize(path.split('.').pop() ?? path)
}

// ── Array-of-objects editor ────────────────────────────────────────────────────

/**
 * Minimal JSON-chip builder for an array of objects (e.g. heading_rules).
 * Each entry is editable as JSON; a richer editor belongs in a domain-specific overlay.
 */
function ArrayOfObjectsInput({
  name, label, description, value, onChange,
}: {
  name: string
  label: string
  description: string
  value: unknown[]
  onChange: (v: unknown[]) => void
}) {
  function setItem(idx: number, text: string) {
    try {
      const parsed = JSON.parse(text)
      onChange(value.map((v, i) => (i === idx ? parsed : v)))
    } catch {
      // Keep the previous value on invalid JSON — the input will display the bad text
      // via local state until it parses (we use uncontrolled input below to allow typing).
    }
  }

  function addItem() {
    onChange([...value, {}])
  }

  function removeItem(idx: number) {
    onChange(value.filter((_, i) => i !== idx))
  }

  return (
    <label className="field-row" title={description}>
      <span className="field-label">{label}</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
        {value.map((item, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 4 }}>
            <input
              className="input mono"
              defaultValue={JSON.stringify(item)}
              onBlur={e => setItem(idx, e.target.value)}
              placeholder='{"k": "v"}'
              style={{ flex: 1, fontSize: 11 }}
            />
            <button
              type="button"
              className="btn btn-ghost btn-danger"
              onClick={() => removeItem(idx)}
              style={{ fontSize: 11, padding: '2px 6px' }}
            >✕</button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-ghost"
          onClick={addItem}
          style={{ fontSize: 11, alignSelf: 'flex-start' }}
        >+ add {name}</button>
      </div>
    </label>
  )
}
