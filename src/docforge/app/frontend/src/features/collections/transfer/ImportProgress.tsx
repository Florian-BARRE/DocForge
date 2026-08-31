// ====== Code Summary ======
// Renders one import transfer's live state: a stage label + progress bar while it runs, an error
// chip on failure, and — once done — a link straight to the freshly created collection. Polls via
// useTransfer; purely presentational otherwise.

import { useEffect, useRef } from "react";
import { Button } from "../../../components/Button";
import { Chip } from "../../../components/Chip";
import type { Navigate } from "../../../shell/view";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { TransferProgressBar } from "./TransferProgressBar";
import { useTransfer } from "./useTransfer";

interface ImportProgressProps {
  transferId: string;
  onNavigate: Navigate;
}

export function ImportProgress({ transferId, onNavigate }: ImportProgressProps) {
  const toast = useToast();
  const { transfer, error } = useTransfer(transferId);

  // Fire the terminal toast exactly once per transfer, however many poll ticks land on it.
  const notifiedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!transfer || notifiedRef.current === transfer.transfer_id) return;
    if (transfer.status === "done") {
      notifiedRef.current = transfer.transfer_id;
      toast.success(`Collection “${transfer.collection_name ?? "imported"}” is ready`);
    } else if (transfer.status === "failed") {
      notifiedRef.current = transfer.transfer_id;
      toast.error(`Import failed — ${transfer.error ?? "unknown error"}`);
    }
  }, [transfer, toast]);

  if (error) return <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>;
  if (!transfer) return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>uploading bundle…</div>;

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

      {transfer.status === "failed" && <Chip tone="error">Import failed — {transfer.error ?? "unknown error"}</Chip>}

      {transfer.status === "done" && transfer.collection_id && (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, marginTop: theme.space.xs }}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onNavigate({ name: "collection", collectionId: transfer.collection_id! })}
          >
            Open “{transfer.collection_name ?? "collection"}”
          </Button>
        </div>
      )}
    </div>
  );
}
