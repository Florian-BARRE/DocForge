// ====== Code Summary ======
// FigureCropImage — renders a single figure-crop block as an image. The crop is stored in the
// object store (content-addressed); the backend hands back a short-lived presigned URL via
// getBlockFigure, which this component fetches (with auth) and then loads as a plain <img>.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getBlockFigure } from '../../../api/client'

interface FigureCropImageProps {
  collectionId: string
  docId: string
  blockId: string
}

/**
 * Fetches the presigned URL for a figure block's crop and renders it as an image.
 *
 * Args:
 *   collectionId: Owning collection id.
 *   docId:        Owning document id.
 *   blockId:      The figure block id (composite, e.g. "<doc>:#/pictures/0").
 */
export function FigureCropImage({ collectionId, docId, blockId }: FigureCropImageProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  // 1. Resolve the presigned crop URL on mount / when the block changes.
  useEffect(() => {
    let cancelled = false
    setUrl(null)
    setError(false)
    getBlockFigure(collectionId, docId, blockId)
      .then(res => { if (!cancelled) setUrl(res.url) })
      .catch(() => { if (!cancelled) setError(true) })
    return () => { cancelled = true }
  }, [collectionId, docId, blockId])

  // 2. Render state: error / loading / image.
  if (error) {
    return <span className="text-dim" style={{ fontSize: 10 }}>(figure unavailable)</span>
  }
  if (!url) {
    return <span className="text-dim" style={{ fontSize: 10 }}><span className="spin">⟳</span> figure…</span>
  }
  return <img src={url} alt="figure crop" className="figure-crop-thumb" loading="lazy" />
}
