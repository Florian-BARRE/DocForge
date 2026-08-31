// ====== Code Summary ======
// Renders one export transfer's live state: a stage label + progress bar while it runs, an error
// chip on failure, and — once done — the authenticated Download action (bundle size shown in
// mono, expiry respected). Polls via useTransfer; purely presentational otherwise.

import { useEffect, useRef, useState } from "react";
import { downloadTransfer } from "../../../api/transfers";
import { Button } from "../../../components/Button";
import { Chip } from "../../../components/Chip";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { formatBytes } from "./transferFormat";
import { TransferProgressBar } from "./TransferProgressBar";
import { useTransfer } from "./useTransfer";

interface ExportProgressProps {
  transferId: string;
  collectionName: string;
}

export function ExportProgress({ transferId, collectionName }: ExportProgressProps) {
  const toast = useToast();
  const { transfer, error } = useTransfer(transferId);
  const [downloading, setDownloading] = useState(false);

  // Fire the terminal toast exactly once per transfer, however many poll ticks land on it.
  const notifiedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!transfer || notifiedRef.current === transfer.transfer_id) return;
    if (transfer.status === "done") {
      notifiedRef.current = transfer.transfer_id;
      toast.success("Export ready to download");
    } else if (transfer.status === "failed") {
      notifiedRef.current = transfer.transfer_id;
      toast.error(`Export failed — ${transfer.error ?? "unknown error"}`);
    }
  }, [transfer, toast]);

  if (error) return <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>;
  if (!transfer) return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>opening export…</div>;

  const expired = transfer.expires_at !== null && new Date(transfer.expires_at) < new Date();

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadTransfer(transfer.transfer_id, `${collectionName}.dcexport`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      {transfer.status !== "failed" && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.size.s, color: theme.color.dim }}>
            <span>{transfer.stage ?? (transfer.status === "done" ? "done" : "starting…")}</span>
            <span style={{ fontFamily: theme.font.mono }}>{transfer.progress}%</span>
          </div>
          <TransferProgressBar progress={transfer.progress} status={transfer.status} />
        </>
      )}

      {transfer.status === "failed" && <Chip tone="error">Export failed — {transfer.error ?? "unknown error"}</Chip>}

      {transfer.status === "done" && !expired && (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, marginTop: theme.space.xs }}>
          <Button variant="primary" size="sm" disabled={downloading} onClick={handleDownload}>
            {downloading ? "downloading…" : "Download"}
          </Button>
          {transfer.size_bytes !== null && (
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.dim }}>
              {formatBytes(transfer.size_bytes)}
            </span>
          )}
        </div>
      )}

      {transfer.status === "done" && expired && (
        <Chip tone="warn">Bundle expired — start a new export</Chip>
      )}
    </div>
  );
}
