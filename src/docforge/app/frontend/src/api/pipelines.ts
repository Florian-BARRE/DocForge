// ====== Code Summary ======
// Typed HTTP client for the pipeline design endpoints. The ONLY hardcoded URL in the whole
// app is the discovery root (`/api/v1/pipelines`) — every design/inspect/edit/stage call uses the
// URL the discovery payload handed back, so a renamed or additional pipeline design needs zero UI
// change.

import { apiFetch, jsonInit } from "./http";
import type {
  DesignResponse, EditOperation, EditResponse, GroupBlob, InspectResponse,
  StageAction, StageApplyResponse, StageViewResponse,
} from "./types";

const DISCOVERY_URL = "/api/v1/pipelines";

export interface PipelineDescriptor {
  key: string;
  title: string;
  description: string;
  design_url: string;
  inspect_url: string;
  edit_url: string;
  /** POST a blob here to get its full ordered stage view + validity (the rail's one-call open). */
  stages_view_url: string;
  /** POST a blob + ONE StageAction here to get the recompiled blob + refreshed stage view. */
  stages_apply_url: string;
}

/** The one hardcoded call: which design surfaces exist, and where to reach each of them. */
export function listPipelineDesigns(): Promise<{ pipelines: PipelineDescriptor[] }> {
  return apiFetch(DISCOVERY_URL);
}

/** Load the lean design payload: palette families + default blob + issues — everything the
 *  stage rail needs. Advanced (headless) tooling appends `?full=true` to the same URL to get
 *  the full palette (run_inputs, mechanics, artefacts). */
export function getDesign(designUrl: string): Promise<DesignResponse> {
  return apiFetch(designUrl);
}

/** ADVANCED client (headless — no UI consumer): send a blob, get back validity + issues (+ the
 *  described tree on the wire). The rail folds validity into `viewStages` instead. */
export function inspect(inspectUrl: string, blob: GroupBlob, signal?: AbortSignal): Promise<InspectResponse> {
  return apiFetch(inspectUrl, { ...jsonInit("POST", { blob }), signal });
}

/**
 * ADVANCED client (headless — kept for a future advanced mode, no UI consumer today): apply
 * graph operations to a blob server-side, then build + validate + describe the result.
 *
 * The editing/healing semantics live on the server, next to the invariants — the client never
 * re-implements them. An impossible operation comes back as DATA (`edit_error` set, the
 * ORIGINAL blob echoed), never an HTTP error; a merely invalid result is returned with its
 * `issues`, exactly like `inspect`.
 */
export function editPipeline(
  editUrl: string,
  blob: GroupBlob,
  operations: EditOperation[],
  signal?: AbortSignal,
): Promise<EditResponse> {
  return apiFetch(editUrl, { ...jsonInit("POST", { blob, operations }), signal });
}

/** Derive the full ordered stage skeleton (10 canonical stages, disabled ones greyed) of a blob,
 *  WITH its validity verdict folded in — the ONLY call the stage rail needs to render itself
 *  from scratch. */
export function viewStages(viewUrl: string, blob: GroupBlob, signal?: AbortSignal): Promise<StageViewResponse> {
  return apiFetch(viewUrl, { ...jsonInit("POST", { blob }), signal });
}

/**
 * Compile ONE stage-level action into a blob transformation, then view + validate the result.
 *
 * Mirrors `editPipeline`'s contract at the stage-rail's coarser grain: the server always returns
 * a buildable blob (dependency cascades handled server-side); `issues` are expected/shown, never
 * a hard failure, and `notices` surface what the compiler did beyond the literal action.
 */
export function applyStageAction(
  applyUrl: string,
  blob: GroupBlob,
  action: StageAction,
  signal?: AbortSignal,
): Promise<StageApplyResponse> {
  return apiFetch(applyUrl, { ...jsonInit("POST", { blob, action }), signal });
}
