// ====== Code Summary ======
// Inspect mode — 4-step rail: Collection → Config → Ingest → Inspector.
// Each step is a separate component. State flows downward via props.

import { useState, useEffect } from 'react'
import type { Collection, Document } from '../../api/types'
import { CollectionStep } from './CollectionStep'
import { ConfigStep } from './ConfigStep'
import { IngestStep } from './IngestStep'
import { PipelineInspector } from './PipelineInspector'

type Step = 1 | 2 | 3 | 4

interface Props {
  // Pre-selected collection injected from BrowseView "Inspect" button.
  preloadedCollection: Collection | null
  // Pre-selected document injected from BrowseView.
  preloadedDoc: Document | null
  // Called once the pre-loaded target has been consumed (to reset parent state).
  onTargetConsumed: () => void
}

interface StepNodeProps {
  step: Step
  label: string
  current: Step
  done: boolean
  onClick: () => void
}

function StepNode({ step, label, current, done, onClick }: StepNodeProps) {
  const isActive = step === current
  const classes = [
    'step-node',
    isActive ? 'step-node-active' : '',
    done && !isActive ? 'step-node-done' : '',
  ].filter(Boolean).join(' ')

  return (
    <button type="button" className={classes} onClick={onClick}>
      <span className="step-number">
        {done && !isActive ? <span className="step-check">✓</span> : step}
      </span>
      {label}
    </button>
  )
}

/**
 * 4-step Inspect view. Manages which step is active and passes state downward.
 * Preloaded collection/doc from BrowseView "Inspect" is applied on mount.
 */
export function InspectView({ preloadedCollection, preloadedDoc, onTargetConsumed }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [collection, setCollection] = useState<Collection | null>(null)
  const [inspectDoc, setInspectDoc] = useState<Document | null>(null)

  // Apply preloaded target when it arrives (from BrowseView "Inspect" button).
  useEffect(() => {
    if (preloadedCollection && preloadedDoc) {
      setCollection(preloadedCollection)
      setInspectDoc(preloadedDoc)
      setStep(4)
      onTargetConsumed()
    }
  }, [preloadedCollection, preloadedDoc])

  function selectCollection(col: Collection) {
    setCollection(col)
    setStep(2)
  }

  function handleIngested(doc: Document) {
    setInspectDoc(doc)
    setStep(4)
  }

  function canNavigateTo(s: Step): boolean {
    if (s === 1) return true
    if (s === 2) return collection !== null
    if (s === 3) return collection !== null
    if (s === 4) return collection !== null && inspectDoc !== null
    return false
  }

  function navigate(s: Step) {
    if (canNavigateTo(s)) setStep(s)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Step rail */}
      <div className="step-rail-wrapper">
        <div className="step-rail">
          <StepNode
            step={1}
            label={collection ? `Collection: ${collection.name}` : 'Collection'}
            current={step}
            done={collection !== null}
            onClick={() => navigate(1)}
          />
          <span className="step-arrow">→</span>
          <StepNode
            step={2}
            label="Config"
            current={step}
            done={step > 2 && collection !== null}
            onClick={() => navigate(2)}
          />
          <span className="step-arrow">→</span>
          <StepNode
            step={3}
            label="Ingest"
            current={step}
            done={step > 3 && inspectDoc !== null}
            onClick={() => navigate(3)}
          />
          <span className="step-arrow">→</span>
          <StepNode
            step={4}
            label={inspectDoc ? `Inspector: ${inspectDoc.filename}` : 'Inspector'}
            current={step}
            done={false}
            onClick={() => navigate(4)}
          />
        </div>
      </div>

      {/* Active step content */}
      <div className="inspect-scroll">
        {step === 1 && (
          <CollectionStep
            onSelect={selectCollection}
            selectedId={collection?.id ?? null}
          />
        )}
        {step === 2 && collection && (
          <ConfigStep collection={collection} />
        )}
        {step === 3 && collection && (
          <IngestStep
            collection={collection}
            onIngested={handleIngested}
          />
        )}
        {step === 4 && collection && inspectDoc && (
          <PipelineInspector
            collection={collection}
            initialDoc={inspectDoc}
            onBack={() => setStep(3)}
          />
        )}
        {step === 2 && !collection && (
          <div className="empty">
            <div className="text-dim">Select a collection first.</div>
          </div>
        )}
        {step === 4 && (!collection || !inspectDoc) && (
          <div className="empty">
            <div className="text-dim">Ingest a document first.</div>
          </div>
        )}
      </div>
    </div>
  )
}
