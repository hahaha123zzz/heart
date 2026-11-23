"use client";

import { usePathname } from "next/navigation";

import { READING_HOME } from "@/lib/learning-routes";
import { useCapabilityAccess } from "./CapabilityAccessContext";

import { capabilityForPath } from "@/lib/capability-routes";

import { RequireCapability } from "./RequireCapability";

/**
 * Route-level gate: derives the required model capability from the current
 * pathname and locks the page when the user lacks it. Mounted once per authed
 * layout group, so direct-URL access to a gated feature is covered too.
 */
export default function CapabilityGate({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const { isLearningAccount } = useCapabilityAccess();
  const isReading = pathname === READING_HOME || pathname.startsWith(`${READING_HOME}/`);
  const capability = isLearningAccount && isReading ? null : capabilityForPath(pathname);
  return (
    <RequireCapability capability={capability}>{children}</RequireCapability>
  );
}
