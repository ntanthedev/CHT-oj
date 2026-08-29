import assert from "node:assert/strict";
import test from "node:test";

import { getResolverSnapshotStatus } from "../snapshot.js";

const generatedAt = "2026-08-29T12:00:00+07:00";
const contestEndTime = "2026-08-29T13:00:00+07:00";

test("a snapshot generated after contest end remains a valid immutable final snapshot", () => {
  assert.deepEqual(
    getResolverSnapshotStatus(
      {
        generated_at: generatedAt,
        contest_end_time: contestEndTime,
        contest_ended_at_generation: true,
      },
      Date.parse("2026-08-30T00:00:00Z"),
    ),
    { kind: "final", stale: false, remainingMs: null },
  );
});

test("a live snapshot becomes stale at the server-provided contest end timestamp", () => {
  const metadata = {
    generated_at: generatedAt,
    contest_end_time: contestEndTime,
    contest_ended_at_generation: false,
  };
  assert.deepEqual(getResolverSnapshotStatus(metadata, Date.parse("2026-08-29T05:30:00Z")), {
    kind: "live",
    stale: false,
    remainingMs: 30 * 60 * 1000,
  });
  assert.deepEqual(getResolverSnapshotStatus(metadata, Date.parse("2026-08-29T06:00:00Z")), {
    kind: "stale",
    stale: true,
    remainingMs: 0,
  });
});

test("legacy or malformed snapshot metadata fails open without inventing local time semantics", () => {
  assert.deepEqual(getResolverSnapshotStatus({}), {
    kind: "unknown",
    stale: false,
    remainingMs: null,
  });
  assert.deepEqual(
    getResolverSnapshotStatus({
      generated_at: "invalid",
      contest_end_time: contestEndTime,
      contest_ended_at_generation: false,
    }),
    { kind: "unknown", stale: false, remainingMs: null },
  );
});
