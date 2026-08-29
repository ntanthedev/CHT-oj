function parseTimestamp(value) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function getResolverSnapshotStatus(contest, now = Date.now()) {
  if (contest?.contest_ended_at_generation === true) {
    return { kind: "final", stale: false, remainingMs: null };
  }
  if (contest?.contest_ended_at_generation !== false) {
    return { kind: "unknown", stale: false, remainingMs: null };
  }

  const generatedAt = parseTimestamp(contest.generated_at);
  const contestEndTime = parseTimestamp(contest.contest_end_time);
  const currentTime = Number(now);
  if (generatedAt === null || contestEndTime === null || !Number.isFinite(currentTime)) {
    return { kind: "unknown", stale: false, remainingMs: null };
  }

  const stale = currentTime >= contestEndTime;
  return {
    kind: stale ? "stale" : "live",
    stale,
    remainingMs: Math.max(0, contestEndTime - currentTime),
  };
}
