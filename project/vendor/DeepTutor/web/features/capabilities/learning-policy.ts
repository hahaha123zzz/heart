import type { CapabilityDescriptor } from "./model";

/** Capabilities that are reached through their own surface, not the composer. */
const HIDDEN_FOR_LEARNERS = new Set([
  "immersive_reading",
  "mastery_path",
  "course_study",
]);

/**
 * Learner accounts only see capabilities their learning policy allows.
 * Visualizing stays in the same composer menu because it is a normal chat turn.
 */
export function filterAllowedCapabilities(
  catalog: CapabilityDescriptor[],
  allowedCapabilities: readonly string[] | null | undefined,
): CapabilityDescriptor[] {
  if (!allowedCapabilities) return catalog;
  const keep = new Set(
    allowedCapabilities.filter((id) => !HIDDEN_FOR_LEARNERS.has(id)),
  );
  return catalog.filter((item) => keep.has(item.id));
}
