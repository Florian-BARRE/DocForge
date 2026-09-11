// ====== Code Summary ======
// TypeScript mirror of the public deployment self-description (GET /capabilities — outside the
// /api/v1 prefix, credential-free even when auth is on, see the backend router's own docstring).
// The UI only needs `auth_enabled` today (the auth-off banner); the rest of the payload is mirrored
// for completeness but currently unconsumed.

import { apiFetch } from "./http";

/** One infra store or optional sidecar of the deployment. */
export interface CapabilityService {
  name: string;
  role: string;
  reachable: boolean;
  device: string | null;
  provides: string[];
  detail: string | null;
}

/** The available pipeline kinds per family — "what can this deployment do NOW". */
export interface CapabilityMatrix {
  parsers: string[];
  ocr: string[];
  embed: string[];
  chunkers: string[];
  vlm: string[];
  llm: string[];
  rerank: string[];
  contextualize: string[];
  metagen: string[];
}

/** The deployment capabilities snapshot returned by GET /capabilities. */
export interface CapabilitiesResponse {
  version: string;
  /** Whether API-key bearer auth gates /api/v1 on this deployment. */
  auth_enabled: boolean;
  gpu_present: boolean | null;
  services: CapabilityService[];
  capabilities: CapabilityMatrix;
}

/** Fetches the deployment's public self-description — no auth required, lives at the bare origin. */
export function getCapabilities(): Promise<CapabilitiesResponse> {
  return apiFetch("/capabilities");
}
