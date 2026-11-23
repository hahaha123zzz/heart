"use client";

import { browserStorage } from "@/shared/storage";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuthStatus } from "@/hooks/useAuthStatus";

/** 异步卡片加载后恢复各账号的学习页位置；用户开始滚动后停止恢复。 */
export function LearningScrollRestoration() {
  const marker = useRef<HTMLSpanElement>(null);
  const pathname = usePathname() ?? "";
  const query = useSearchParams()?.toString() ?? "";
  const { userId, loading, statusAvailable } = useAuthStatus();
  useEffect(() => {
    if (loading || !statusAvailable || !userId || !pathname.startsWith("/learning")) return;
    const scroller = marker.current?.closest<HTMLElement>("[data-feature-page], [data-learning-scroll]");
    if (!scroller) return;
    const key = `dt.learning.scroll:${userId}:${pathname}?${query}`;
    let target = 0;
    try { target = Number(browserStorage.readRaw("session", key) || 0); } catch { return; }
    if (!Number.isFinite(target) || target < 0) target = 0;
    let pending = target > 0;
    const save = () => { if (!pending) try { browserStorage.writeRaw("session", key, String(scroller.scrollTop)); } catch {} };
    const restore = () => {
      if (!pending) return;
      scroller.scrollTop = target;
      if (Math.abs(scroller.scrollTop - target) < 1) pending = false;
    };
    const interact = () => { pending = false; };
    const keyboard = (event: KeyboardEvent) => { if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End"].includes(event.key)) interact(); };
    restore();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(restore);
    const content = scroller.querySelector("[data-page-container]") || scroller;
    observer?.observe(content);
    scroller.addEventListener("scroll", save);
    scroller.addEventListener("wheel", interact, { passive: true });
    scroller.addEventListener("touchstart", interact, { passive: true });
    scroller.addEventListener("keydown", keyboard);
    return () => {
      save(); observer?.disconnect();
      scroller.removeEventListener("scroll", save); scroller.removeEventListener("wheel", interact);
      scroller.removeEventListener("touchstart", interact); scroller.removeEventListener("keydown", keyboard);
    };
  }, [pathname, query, userId, loading, statusAvailable]);
  return <span ref={marker} hidden aria-hidden="true" />;
}
