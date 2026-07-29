// ====== Code Summary ======
// Renders an authenticated blob (page render, figure crop) as an <img>. A plain <img src> triggers
// a browser GET with no Authorization header, so under AUTH_ENABLED every blob would 401; instead we
// fetch the bytes with the Bearer (apiFetchBlob), wrap them in an object URL, and revoke it on
// unmount / hash change. Loading and broken states occupy the same box so the layout never jumps.

import { useEffect, useState } from "react";
import { apiFetchBlob } from "../api/http";
import { blobUrl } from "../api/explorer";
import { theme } from "../theme";

interface BlobImageProps {
  hash: string;
  alt: string;
  style?: React.CSSProperties;
}

export function BlobImage({ hash, alt, style }: BlobImageProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // 1. Fetch the bytes WITH the bearer, expose them as an object URL, revoke on cleanup.
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
  }, [hash]);

  // 2. Placeholder (loading / broken) fills the same box so surrounding layout stays put.
  if (!src) {
    return (
      <div
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
        {failed ? "unavailable" : "…"}
      </div>
    );
  }

  return <img src={src} alt={alt} style={style} />;
}
