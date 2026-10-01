/**
 * UoW Polyglot Architecture - TypeScript Demonstration
 *
 * Demonstrates strongly-typed envelope instantiation and client invocation.
 */

import { createEnvelope, validateEnvelope, UoWClient } from '../../sdk/typescript/src/index.ts';

interface InventoryReservePayload {
  sku: string;
  quantity: number;
  order_id: string;
}

interface InventoryReserveResult {
  sku: string;
  reserved_quantity: number;
  order_id: string;
  status: string;
}

async function main(): Promise<void> {
  console.log('=== UoW Polyglot Interoperability Demo (TypeScript) ===');

  const client = new UoWClient({
    endpointUrl: 'http://localhost:8000/v1/uow',
    defaultActor: {
      id: 'ts-order-service',
      role: 'ecommerce-backend',
      claim_type: 'AUTHENTICATED',
    },
  });

  const envelope = createEnvelope<InventoryReservePayload>({
    operation: 'inventory.reserve',
    actor: {
      id: 'ts-order-service',
      role: 'ecommerce-backend',
      claim_type: 'AUTHENTICATED',
    },
    payload: {
      sku: 'WIDGET-99',
      quantity: 10,
      order_id: 'ORD-TS-9988',
    },
    constraints: {
      idempotency_key: 'idem-ts-9988',
      timeout_ms: 5000,
    },
  });

  console.log('Created Typed Envelope for operation:', envelope.operation);
  console.log('Validating envelope structure:', validateEnvelope(envelope).valid ? 'OK' : 'FAIL');
}

main().catch(console.error);
