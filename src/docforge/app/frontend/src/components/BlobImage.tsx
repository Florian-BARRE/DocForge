// ====== Code Summary ======
// Renders an authenticated blob (page render, figure crop) as an <img>. A plain <img src> triggers
// a browser GET with no Authorization header, so under AUTH_ENABLED every blob would 401; instead we
// fetch the bytes with the Bearer (apiFetchBlob), wrap them in an object URL, and revoke it on
// unmount / hash change. Loading and broken states occupy the same box so the layout never jumps.

import { useEffect, useRef, useState } from "react";
import { apiFetchBlob } from "../api/http";
import { blobUrl } from "../api/explorer";
import { theme } from "../theme";

interface BlobImageProps {
  hash: string;
  alt: string;
  style?: React.CSSProperties;
  /** Defer the authenticated fetch until this image scrolls near the viewport (IntersectionObserver,
   *  600px lookahead). Opt-in — used by views that render many page renders at once (the Layout tab)
   *  so opening a long document doesn't fire one fetch per page simultaneously. Default `false` keeps
   *  every other caller (single-image views) fetching immediately, as before. */
  lazy?: boolean;
}

export function BlobImage({ hash, alt, style, lazy = false }: BlobImageProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(!lazy);
  const placeholderRef = useRef<HTMLDivElement | null>(null);

  // 1. When lazy, only start fetching once the placeholder is about to enter the viewport.
  useEffect(() => {
    if (visible) return;
    const el = placeholderRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setVisible(true);
      },
      { rootMargin: "600px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  // 2. Fetch the bytes WITH the bearer, expose them as an object URL, revoke on cleanup.
  useEffect(() => {
    if (!visible) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    setSrc(null);
    setFailed(false);
    apiFetchBlob(blobUrl(hash))
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [hash, visible]);

  // 3. Placeholder (not-yet-visible / loading / broken) fills the same box so layout never jumps.
  if (!src) {
    return (
      <div
        ref={placeholderRef}
        style={{
          ...style,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: theme.color.dim,
          fontSize: theme.font.size.xs,
          background: theme.color.panel,
        }}
      >
        {failed ? "unavailable" : visible ? "…" : ""}
      </div>
    );
  }

  return <img src={src} alt={alt} style={style} />;
}
