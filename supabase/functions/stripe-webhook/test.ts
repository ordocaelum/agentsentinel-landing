/**
 * Unit tests for stripe-webhook idempotency logic.
 *
 * These tests exercise the deduplication contract without a real Stripe
 * signature or Supabase backend by mocking the relevant dependencies.
 *
 * Run with:
 *   deno test supabase/functions/stripe-webhook/test.ts --allow-env
 */

import { assertEquals, assertExists } from "https://deno.land/std@0.220.1/assert/mod.ts";

// ─── Minimal mocks ────────────────────────────────────────────────────────────

/**
 * A minimal in-memory Supabase mock that tracks inserts/updates to
 * webhook_events so we can assert idempotency behaviour.
 */
function makeSupabaseMock() {
  const webhookEvents: Map<string, Record<string, unknown>> = new Map();

  function from(table: string) {
    if (table !== "webhook_events") {
      // Return a no-op builder for other tables
      const noop = {
        insert: () => noop,
        update: () => noop,
        select: () => noop,
        eq: () => noop,
        maybeSingle: async () => ({ data: null, error: null }),
        then: (_ok: unknown, _err: unknown) => Promise.resolve(),
      };
      return noop;
    }

    return {
      _table: table,
      _body: {} as Record<string, unknown>,
      _count: "exact" as "exact" | undefined,

      insert(body: Record<string, unknown>, opts?: { count?: "exact" }) {
        this._body = body;
        this._count = opts?.count;
        // Simulate ON CONFLICT DO NOTHING: if the stripe_event_id already
        // exists, return count=0; otherwise insert and return count=1.
        const eventId = body.stripe_event_id as string;
        if (webhookEvents.has(eventId)) {
          return {
            count: 0,
            error: null,
            data: null,
          };
        }
        webhookEvents.set(eventId, { ...body });
        return {
          count: 1,
          error: null,
          data: [body],
        };
      },

      update(fields: Record<string, unknown>) {
        return {
          eq: (col: string, val: unknown) => {
            if (col === "stripe_event_id") {
              const existing = webhookEvents.get(val as string);
              if (existing) {
                webhookEvents.set(val as string, { ...existing, ...fields });
              }
            }
            return {
              then: (ok: (v: unknown) => void, _err: unknown) => {
                ok(null);
                return Promise.resolve();
              },
            };
          },
        };
      },
    };
  }

  return {
    from,
    _webhookEvents: webhookEvents,
  };
}

// ─── Idempotency logic (extracted for testing) ────────────────────────────────

/**
 * Implements the idempotency INSERT logic from the webhook handler.
 * Returns { deduplicated: true } if the event was already in the store,
 * otherwise inserts with status='pending' and returns null (caller should
 * proceed to process).
 */
async function tryClaimEvent(
  supabase: ReturnType<typeof makeSupabaseMock>,
  eventId: string,
  eventType: string,
): Promise<{ deduplicated: true } | null> {
  const { count: insertCount, error: insertError } = supabase.from("webhook_events").insert(
    {
      stripe_event_id: eventId,
      event_type: eventType,
      payload: {},
      processed: false,
      status: "pending",
    },
    { count: "exact" },
  ) as { count: number; error: null };

  if (insertError && (insertError as { code?: string }).code !== "23505") {
    console.warn("Insert error (non-duplicate):", insertError);
  }

  if (insertCount === 0) {
    return { deduplicated: true };
  }
  return null;
}

async function markProcessed(
  supabase: ReturnType<typeof makeSupabaseMock>,
  eventId: string,
  metadata: Record<string, unknown> = {},
): Promise<void> {
  await supabase
    .from("webhook_events")
    .update({
      processed: true,
      processed_at: new Date().toISOString(),
      status: "processed",
      metadata: Object.keys(metadata).length > 0 ? metadata : null,
    })
    .eq("stripe_event_id", eventId);
}

async function markFailed(
  supabase: ReturnType<typeof makeSupabaseMock>,
  eventId: string,
  errorMessage: string,
): Promise<void> {
  await supabase
    .from("webhook_events")
    .update({
      status: "failed",
      error_message: errorMessage,
      processed: false,
    })
    .eq("stripe_event_id", eventId);
}

// ─── Tests ────────────────────────────────────────────────────────────────────

Deno.test("first occurrence of an event_id is accepted (not deduplicated)", async () => {
  const supabase = makeSupabaseMock();
  const eventId = "evt_test_first_001";

  const result = await tryClaimEvent(supabase, eventId, "checkout.session.completed");

  assertEquals(result, null, "First event should not be deduplicated");
  assertEquals(supabase._webhookEvents.has(eventId), true, "Event should be stored");
  assertEquals(supabase._webhookEvents.get(eventId)?.status, "pending");
});

Deno.test("second occurrence of the same event_id returns { deduplicated: true }", async () => {
  const supabase = makeSupabaseMock();
  const eventId = "evt_test_dedup_001";

  // First send
  const first = await tryClaimEvent(supabase, eventId, "checkout.session.completed");
  assertEquals(first, null, "First send should not be deduplicated");

  // Simulate processing success
  await markProcessed(supabase, eventId, { subscription_id: "sub_abc" });
  assertEquals(supabase._webhookEvents.get(eventId)?.status, "processed");

  // Stripe retries — second send with same event_id
  const second = await tryClaimEvent(supabase, eventId, "checkout.session.completed");
  assertEquals(second, { deduplicated: true }, "Second send must be deduplicated");
});

Deno.test("DB has only one row after two sends of the same event_id", async () => {
  const supabase = makeSupabaseMock();
  const eventId = "evt_test_single_row";

  await tryClaimEvent(supabase, eventId, "invoice.payment_failed");
  await markProcessed(supabase, eventId);

  await tryClaimEvent(supabase, eventId, "invoice.payment_failed");
  // The Map is keyed by event_id — size check confirms no duplicate row.
  assertEquals(supabase._webhookEvents.size, 1, "Exactly one row in webhook_events");
});

Deno.test("failed event has status=failed and error_message set", async () => {
  const supabase = makeSupabaseMock();
  const eventId = "evt_test_failure_001";

  await tryClaimEvent(supabase, eventId, "checkout.session.completed");
  await markFailed(supabase, eventId, "Simulated processing error\nat line 42");

  const row = supabase._webhookEvents.get(eventId);
  assertExists(row, "Row must exist after failure");
  assertEquals(row?.status, "failed");
  assertEquals((row?.error_message as string).includes("Simulated"), true);
  assertEquals(row?.processed, false);
});

Deno.test("processed event has status=processed and processed_at set", async () => {
  const supabase = makeSupabaseMock();
  const eventId = "evt_test_processed_001";

  await tryClaimEvent(supabase, eventId, "customer.subscription.deleted");
  await markProcessed(supabase, eventId, { subscription_id: "sub_xyz" });

  const row = supabase._webhookEvents.get(eventId);
  assertExists(row, "Row must exist after processing");
  assertEquals(row?.status, "processed");
  assertEquals(row?.processed, true);
  assertExists(row?.processed_at, "processed_at must be set");
  assertEquals((row?.metadata as Record<string, unknown>)?.subscription_id, "sub_xyz");
});

Deno.test("different event_ids are independent — no cross-contamination", async () => {
  const supabase = makeSupabaseMock();

  const result1 = await tryClaimEvent(supabase, "evt_a", "checkout.session.completed");
  const result2 = await tryClaimEvent(supabase, "evt_b", "invoice.payment_failed");

  assertEquals(result1, null);
  assertEquals(result2, null);
  assertEquals(supabase._webhookEvents.size, 2);
});

Deno.test("replaying event_a does not affect event_b's status", async () => {
  const supabase = makeSupabaseMock();

  await tryClaimEvent(supabase, "evt_a", "checkout.session.completed");
  await markProcessed(supabase, "evt_a");

  await tryClaimEvent(supabase, "evt_b", "invoice.payment_failed");
  // Do not process evt_b

  // Replay evt_a
  const replay = await tryClaimEvent(supabase, "evt_a", "checkout.session.completed");
  assertEquals(replay, { deduplicated: true });

  // evt_b should still be pending
  assertEquals(supabase._webhookEvents.get("evt_b")?.status, "pending");
  assertEquals(supabase._webhookEvents.get("evt_a")?.status, "processed");
});
