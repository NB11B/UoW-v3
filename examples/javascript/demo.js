/**
 * UoW Polyglot Architecture - JavaScript / Node.js Demonstration
 *
 * Demonstrates constructing a canonical UoWEnvelope and validating it
 * before dispatching across the wire.
 */

import { createEnvelope, validateEnvelope, canonicalJson } from '../../sdk/typescript/src/envelope.ts';

console.log('=== UoW Polyglot Interoperability Demo (JavaScript) ===');

// 1. Construct canonical wire envelope for inventory.reserve
const envelope = createEnvelope({
  operation: 'inventory.reserve',
  actor: {
    id: 'store-frontend-01',
    role: 'point-of-sale',
    claim_type: 'AUTHENTICATED',
  },
  payload: {
    sku: 'WIDGET-99',
    quantity: 5,
    order_id: 'ORD-DEMO-001',
  },
  constraints: {
    idempotency_key: 'idem-demo-ord-001',
    timeout_ms: 3000,
  },
});

console.log('Constructed Envelope:');
console.log(JSON.stringify(envelope, null, 2));

// 2. Validate envelope against protocol requirements
const validation = validateEnvelope(envelope);
console.log('Validation Status:', validation.valid ? 'VALID' : 'INVALID');

// 3. Serialize to canonical sorted-key JSON representation
const wireBytes = canonicalJson(envelope);
console.log('Canonical Wire Bytes (length):', wireBytes.length);
console.log('Wire Payload:', wireBytes);
