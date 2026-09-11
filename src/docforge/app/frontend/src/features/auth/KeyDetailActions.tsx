// ====== Code Summary ======
// The API key detail page's header actions cluster (Rotate/Revoke) — owns its own confirm/root-gate
// state so KeyDetailPage stays a data-fetch + layout shell. Mirrors ApiKeyRow's write-action gating:
// `writesDisabled` (auth off) hides the cluster entirely, and the root/bootstrap key (see rootKey.ts)
// requires RootKeyConfirmGate's typed confirmation instead of the plain single-click confirm.

import { useState } from "react";
import { revokeKey, type ApiKeyInfo } from "../../api/auth";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import { isRootKey } from "./rootKey";
import { RootKeyConfirmGate } from "./RootKeyConfirmGate";

interface KeyDetailActionsProps {
  apiKey: ApiKeyInfo;
  /** True when auth is off — hide the cluster entirely, never just disable it. */
  writesDisabled: boolean;
  /** True while the rotate form is open (owned by the parent) — hide the cluster meanwhile. */
  rotating: boolean;
  onRevoked: () => void;
  onStartRotate: () => void;
}

export function KeyDetailActions({ apiKey, writesDisabled, rotating, onRevoked, onStartRotate }: KeyDetailActionsProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [confirmingRotate, setConfirmingRotate] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const revoked = Boolean(apiKey.revoked_at);
  const isRoot = isRootKey(apiKey);

  if (writesDisabled || revoked || rotating) return null;

  const handleRevoke = async () => {
    setRevoking(true);
    try {
      await revokeKey(apiKey.id);
      toast.success(`Key “${apiKey.name}” revoked`);
      onRevoked();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(`Revoke failed — ${message}`);
      setRevoking(false);
    }
  };

  if (confirmingRotate) {
    return (
      <RootKeyConfirmGate
        expectedText={apiKey.name}
        actionLabel="Continue to rotate"
        onConfirm={() => { setConfirmingRotate(false); onStartRotate(); }}
        onCancel={() => setConfirmingRotate(false)}
      />
    );
  }

  if (confirming) {
    return isRoot ? (
      <RootKeyConfirmGate
        expectedText={apiKey.name}
        actionLabel="Confirm revoke"
        busy={revoking}
        onConfirm={handleRevoke}
        onCancel={() => setConfirming(false)}
      />
    ) : (
      <>
        <Button variant="danger" disabled={revoking} onClick={handleRevoke}>{revoking ? "revoking…" : "Confirm revoke"}</Button>
        <Button onClick={() => setConfirming(false)}>Cancel</Button>
      </>
    );
  }

  return (
    <>
      <Button variant="secondary" onClick={() => (isRoot ? setConfirmingRotate(true) : onStartRotate())}>Rotate</Button>
      <Button variant="danger" onClick={() => setConfirming(true)}>Revoke</Button>
    </>
  );
}
