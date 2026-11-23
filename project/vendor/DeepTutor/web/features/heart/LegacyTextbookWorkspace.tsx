"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ReadingPanelSeparator } from "@/components/reading/workspace/ReadingPanelSeparator";
import { useReadingPanelLayout } from "@/components/reading/workspace/useReadingPanelLayout";

export function LegacyTextbookWorkspace({
  open,
  reader,
  onClose,
  children,
}: {
  open: boolean;
  reader: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [desktopWide, setDesktopWide] = useState(false);
  const { gridRef, ...panels } = useReadingPanelLayout({
    enabled: open,
    navigatorOpen: false,
    companionOpen: open,
  });

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1280px)");
    const update = () => setDesktopWide(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  if (!open) return <>{children}</>;

  return (
    <div
      ref={gridRef}
      data-testid="textbook-chat-split"
      className="relative grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)] overflow-hidden xl:grid-cols-[minmax(0,1fr)_5px_minmax(330px,420px)]"
      style={desktopWide ? panels.gridStyle : undefined}
    >
      <div className="relative min-h-0 min-w-0 overflow-hidden">{reader}</div>
      {desktopWide && panels.showCompanionHandle && (
        <ReadingPanelSeparator
          label={t("Resize reading companion")}
          width={panels.companionWidth}
          min={panels.companionMin}
          max={panels.companionMax}
          direction={-1}
          onResize={panels.resizeCompanion}
        />
      )}
      {!desktopWide && (
        <button
          type="button"
          className="absolute inset-0 z-20 bg-[var(--overlay)]"
          onClick={onClose}
          aria-label={t("Close panels")}
        />
      )}
      <section
        aria-label={t("Reading companion")}
        className={
          desktopWide
            ? "relative z-0 flex min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--card)] dark:bg-[var(--background)]"
            : "absolute inset-y-0 right-0 z-30 flex w-[min(420px,100%)] min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--card)] shadow-[-18px_0_42px_rgba(0,0,0,.12)] dark:bg-[var(--background)]"
        }
      >
        {children}
      </section>
    </div>
  );
}
