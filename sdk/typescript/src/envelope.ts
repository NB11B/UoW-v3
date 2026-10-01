/**
 * Canonical UoW Wire Protocol Envelope & Types (TypeScript).
 *
 * Implements the wire representation for UoWEnvelope and UoWResult according to
 * spec/schemas/uow_envelope.json and spec/schemas/uow_result.json.
 */

export type ClaimType = 'UNVERIFIED_CLAIM' | 'AUTHENTICATED' | 'DELEGATED' | 'QUORUM_CERTIFIED';
export type UoWStatus = 'SUCCESS' | 'REJECTED' | 'ERROR' | 'PENDING';

export interface Actor {
  id: string;
  role?: string;
  claim_type?: ClaimType;
  key_fingerprint?: string;
  [key: string]: unknown;
}

export interface DelegationSpec {
  delegator: string;
  delegatee: string;
  scope: string;
  signature: string;
}

export interface AuthorityContext {
  tokens?: string[];
  delegations?: DelegationSpec[];
  signature?: string;
  [key: string]: unknown;
}

export interface Constraints {
  timeout_ms?: number;
  idempotency_key?: string;
  causal_epoch?: number;
  deadline?: string;
  [key: string]: unknown;
}

export interface EvidenceContext {
  parent_evidence_hash?: string;
  require_hash_chain?: boolean;
  trace_id?: string;
  [key: string]: unknown;
}

export interface UoWEnvelope<T = Record<string, unknown>> {
  protocol_version: string;
  operation: string;
  operation_version: string;
  request_id: string;
  correlation_id: string;
  actor: Actor;
  authority_context?: AuthorityContext;
  payload: T;
  constraints?: Constraints;
  evidence_context?: EvidenceContext;
  reply_to?: string;
}

export interface EvidenceRecord {
  evidence_hash: string;
  prev_record_hash: string;
  certificate_hash: string;
  pre_state_hash?: string;
  post_state_hash?: string;
  proposal_hash?: string;
  ledger_index: number;
  signatures?: string[];
  [key: string]: unknown;
}

export interface ExecutionMetadata {
  duration_ms: number;
  host_node: string;
  execution_backend: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface UoWError {
  code: string;
  message: string;
  path?: string;
  retryable?: boolean;
  [key: string]: unknown;
}

export interface UoWResult<R = Record<string, unknown>> {
  request_id: string;
  correlation_id?: string;
  operation: string;
  status: UoWStatus;
  result: R;
  evidence: EvidenceRecord;
  execution_metadata: ExecutionMetadata;
  errors: UoWError[];
}

/**
 * Deterministic JSON serialization with sorted keys and compact formatting,
 * matching Python canonical_json.
 */
export function canonicalJson(obj: unknown): string {
  if (obj === null || typeof obj === 'boolean' || typeof obj === 'number' || typeof obj === 'string') {
    return JSON.stringify(obj);
  }
  if (Array.isArray(obj)) {
    return '[' + obj.map(canonicalJson).join(',') + ']';
  }
  if (typeof obj === 'object') {
    const record = obj as Record<string, unknown>;
    const keys = Object.keys(record)
      .filter((k) => record[k] !== undefined)
      .sort();
    const parts = keys.map((key) => {
      const val = record[key];
      return JSON.stringify(key) + ':' + canonicalJson(val);
    });
    return '{' + parts.join(',') + '}';
  }
  throw new TypeError(`Cannot serialize type ${typeof obj} to canonical JSON`);
}

/**
 * Creates a valid UoWEnvelope with sensible defaults.
 */
export function createEnvelope<T = Record<string, unknown>>(params: {
  operation: string;
  operation_version?: string;
  actor: Actor;
  payload: T;
  request_id?: string;
  correlation_id?: string;
  authority_context?: AuthorityContext;
  constraints?: Constraints;
  evidence_context?: EvidenceContext;
  reply_to?: string;
}): UoWEnvelope<T> {
  const reqId = params.request_id || `req-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  return {
    protocol_version: '1.0.0',
    operation: params.operation,
    operation_version: params.operation_version || '1.0.0',
    request_id: reqId,
    correlation_id: params.correlation_id || reqId,
    actor: {
      claim_type: 'UNVERIFIED_CLAIM',
      ...params.actor,
    },
    authority_context: params.authority_context,
    payload: params.payload,
    constraints: params.constraints,
    evidence_context: params.evidence_context,
    reply_to: params.reply_to,
  };
}

/**
 * Validates envelope structural invariants.
 */
export function validateEnvelope(envelope: unknown): { valid: boolean; error?: string } {
  if (!envelope || typeof envelope !== 'object') {
    return { valid: false, error: 'Envelope must be a non-null object' };
  }
  const e = envelope as Record<string, unknown>;
  const required = ['protocol_version', 'operation', 'operation_version', 'request_id', 'correlation_id', 'actor', 'payload'];
  for (const field of required) {
    if (e[field] === undefined || e[field] === null) {
      return { valid: false, error: `Missing required field: ${field}` };
    }
  }
  if (typeof e.actor !== 'object' || !(e.actor as Record<string, unknown>).id) {
    return { valid: false, error: 'Actor must be an object with an id property' };
  }
  return { valid: true };
}
