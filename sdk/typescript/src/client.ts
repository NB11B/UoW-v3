/**
 * Canonical UoW Wire Protocol Client (TypeScript).
 *
 * Dispatches envelopes to HTTP endpoints or local runtime bridges.
 */

import type { UoWEnvelope, UoWResult } from './envelope.ts';
import { createEnvelope, validateEnvelope } from './envelope.ts';

export interface UoWClientOptions {
  endpointUrl?: string;
  defaultActor?: {
    id: string;
    role?: string;
    claim_type?: 'UNVERIFIED_CLAIM' | 'AUTHENTICATED' | 'DELEGATED' | 'QUORUM_CERTIFIED';
    key_fingerprint?: string;
  };
  headers?: Record<string, string>;
  fetchFn?: typeof fetch;
}

export class UoWClient {
  private endpointUrl: string;
  private defaultActor?: UoWClientOptions['defaultActor'];
  private headers: Record<string, string>;
  private fetchFn: typeof fetch;

  constructor(options: UoWClientOptions = {}) {
    this.endpointUrl = (options.endpointUrl || 'http://localhost:8000/v1/uow').replace(/\/$/, '');
    this.defaultActor = options.defaultActor;
    this.headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...options.headers,
    };
    this.fetchFn = options.fetchFn || (typeof fetch !== 'undefined' ? fetch : (() => {
      throw new Error('No fetch implementation available. Provide fetchFn in UoWClientOptions.');
    }) as unknown as typeof fetch);
  }

  /**
   * Dispatches a single-shot execution request across the wire.
   */
  async execute<T = Record<string, unknown>, R = Record<string, unknown>>(
    envelope: UoWEnvelope<T>
  ): Promise<UoWResult<R>> {
    const validation = validateEnvelope(envelope);
    if (!validation.valid) {
      throw new Error(`Invalid UoWEnvelope: ${validation.error}`);
    }

    const response = await this.fetchFn(`${this.endpointUrl}/execute`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(envelope),
    });

    if (!response.ok && response.status >= 500) {
      throw new Error(`UoW server error: ${response.status} ${response.statusText}`);
    }

    return (await response.json()) as UoWResult<R>;
  }

  /**
   * Helper method to invoke an operation directly with typed payload.
   */
  async invoke<T = Record<string, unknown>, R = Record<string, unknown>>(
    operation: string,
    payload: T,
    options: {
      operationVersion?: string;
      actorId?: string;
      idempotencyKey?: string;
      timeoutMs?: number;
      correlationId?: string;
      tokens?: string[];
    } = {}
  ): Promise<UoWResult<R>> {
    const actor = {
      id: options.actorId || this.defaultActor?.id || 'anonymous-client',
      role: this.defaultActor?.role || 'client',
      claim_type: this.defaultActor?.claim_type || 'UNVERIFIED_CLAIM',
      key_fingerprint: this.defaultActor?.key_fingerprint,
    };

    const envelope = createEnvelope<T>({
      operation,
      operation_version: options.operationVersion,
      actor,
      payload,
      correlation_id: options.correlationId,
      authority_context: options.tokens ? { tokens: options.tokens } : undefined,
      constraints: {
        idempotency_key: options.idempotencyKey,
        timeout_ms: options.timeoutMs,
      },
    });

    return this.execute<T, R>(envelope);
  }
}
