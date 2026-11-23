"use client";

import { useEffect, useRef, useState } from "react";
import type { LegacyReaderContext } from "@/lib/legacy-reader-context";

type Chapter = {
  document_id: string;
  chapter_id: number;
  title: string;
  version: string;
  page_count: number;
  reading_material_id?: string;
  reading_material_revision?: number;
  sections: { id: number; title: string; page: number; y: number }[];
};
type ReaderAction = {
  material_id?: string;
  reader_action: string;
  locator?: number;
};
type PDFSelection = {
  document_id: string;
  version: string;
  kind: "text" | "area";
  rects: { page: number; x1: number; y1: number; x2: number; y2: number }[];
  text: string;
};
export type LegacyCitationReference = PDFSelection & { kind: "text" };
type PDFPosition = {
  chapter?: number;
  document_id?: string;
  version?: string;
  page?: number;
};
type ReaderApi = {
  mount: (
    el: HTMLElement,
    metadata: unknown,
    reference: LegacyCitationReference | null,
    onAsk?: (selection: PDFSelection) => void,
  ) => void;
  unmount: (el: HTMLElement) => void;
};

declare global {
  interface Window {
    TextbookPDF?: ReaderApi;
  }
}

type TextbookAttachment = {
  type: string;
  filename: string;
  base64: string;
  previewUrl: string;
  size: number;
  mimeType: string;
};

export function LegacyTextbook({
  onClose,
  onAsk,
  onAttach,
  onReaderContext,
  target,
}: {
  onClose: () => void;
  onAsk: (text: string, context: LegacyReaderContext) => void;
  onAttach?: (attachment: TextbookAttachment) => void;
  onReaderContext: (context: LegacyReaderContext) => void;
  target?: {
    materialId: string;
    materialRevision?: number;
    locator: number;
    reference?: LegacyCitationReference;
    nonce?: number;
  } | null;
}) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [sectionId, setSectionId] = useState(0);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [metadata, setMetadata] = useState<Record<string, unknown> | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const pendingJump = useRef<{ documentId: string; locator: number; highlight: boolean } | null>(null);
  const [pageTarget, setPageTarget] = useState<number | null>(null);
  const [readerTarget, setReaderTarget] = useState<typeof target>(target ?? null);

  useEffect(() => {
    const follow = (event: Event) => {
      const action = (event as CustomEvent<ReaderAction>).detail;
      if (action?.reader_action !== "goto" || !action.material_id || !action.locator) return;
      setReaderTarget({ materialId: action.material_id, locator: action.locator });
    };
    window.addEventListener("dt:reader-action", follow);
    return () => window.removeEventListener("dt:reader-action", follow);
  }, []);

  useEffect(() => {
    if (target) setReaderTarget(target);
  }, [target]);

  useEffect(() => {
    if (!readerTarget || !chapters.length) return;
    const matches = chapters.filter(
      (chapter) =>
        (chapter.reading_material_id || chapter.version.slice(0, 16)) ===
        readerTarget.materialId,
    );
    if (matches.length !== 1) {
      setError("引用对应的教材不存在或版本已变化。");
      return;
    }
    const chapter = matches[0];
    if (readerTarget.locator < 1 || readerTarget.locator > chapter.page_count) {
      setError("引用页码超出当前教材范围。");
      return;
    }
    setDocumentId(chapter.document_id);
    setSectionId(chapter.sections[0]?.id ?? 0);
    pendingJump.current = {
      documentId: chapter.document_id,
      locator: readerTarget.locator,
      highlight: readerTarget.reference?.version === chapter.version &&
        readerTarget.reference.document_id === chapter.document_id,
    };
    setPageTarget(readerTarget.locator);
    setError("正在定位教材引用页……");
  }, [readerTarget, chapters]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/heart/legacy-reader/chapters", {
      credentials: "include",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((items: Chapter[]) => {
        setChapters(items);
        if (items.length) {
          setDocumentId(items[0].document_id);
          setSectionId(items[0].sections[0]?.id ?? 0);
        } else {
          setError("当前账号没有可阅读的教材。");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("教材目录读取失败，请关闭后重试。");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!documentId) return;
    const controller = new AbortController();
    setMetadata(null);
    fetch(`/api/heart/legacy-reader/documents/${encodeURIComponent(documentId)}`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(setMetadata)
      .catch(() => {
        if (!controller.signal.aborted) setError("教材读取失败，请重试。");
      });
    return () => controller.abort();
  }, [documentId]);

  useEffect(() => {
    if (window.TextbookPDF) {
      setReady(true);
      return;
    }
    const script = document.createElement("script");
    script.type = "module";
    script.src = "/static/pdf-reader/reader.js";
    script.onload = () => setReady(true);
    script.onerror = () => setError("阅读器加载失败，请刷新页面重试。");
    document.body.appendChild(script);
    return () => script.remove();
  }, []);

  useEffect(() => {
    const handlePosition = (event: Event) => {
      const position = (event as CustomEvent<PDFPosition>).detail;
      const chapter = chapters.find(
        (item) =>
          item.document_id === position?.document_id &&
          item.version === position?.version,
      );
      const locator = Number(position?.page);
      if (!chapter || !Number.isSafeInteger(locator) || locator < 1) return;
      if (pendingJump.current?.documentId === chapter.document_id && pendingJump.current.locator === locator) {
        const highlight = pendingJump.current.highlight;
        pendingJump.current = null;
        setError(highlight ? "已定位到引用原文。" : "已定位到引用页。");
      }
      onReaderContext({
        materialId: chapter.reading_material_id || chapter.version.slice(0, 16),
        materialRevision: chapter.reading_material_revision || 1,
        documentId: chapter.document_id,
        version: chapter.version,
        chapterId: chapter.chapter_id,
        chapterTitle: `第${chapter.chapter_id}章 ${chapter.title}`,
        locator,
        source: "viewport",
      });
    };
    window.addEventListener("pdf-position", handlePosition);
    return () => window.removeEventListener("pdf-position", handlePosition);
  }, [chapters, onReaderContext]);

  useEffect(() => {
    const element = host.current;
    const chapter = chapters.find((item) => item.document_id === documentId);
    const section = chapter?.sections.find((item) => item.id === sectionId);
    if (!element || !ready || !metadata || metadata.document_id !== documentId || !section || !window.TextbookPDF) return;
    const reference = readerTarget?.reference;
    const activeReference = pageTarget && reference?.document_id === metadata.document_id
      && reference.version === metadata.version && reference.rects[0]?.page === pageTarget
      ? reference : null;

    window.TextbookPDF.mount(
      element,
      {
        ...metadata,
        section: pageTarget ? { ...section, page: pageTarget, y: 0 } : section,
        jumpToken: readerTarget?.nonce ?? pageTarget,
      },
      activeReference,
      async (selection) => {
        try {
          const response = await fetch("/api/heart/legacy-reader/selection", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(selection),
          });
          if (!response.ok) throw new Error();
          const result = await response.json();
          const reference = result.reference as {
            document_id: string;
            version: string;
            chapter_id: number;
            rects: PDFSelection["rects"];
          };
          const sourceChapter = chapters.find(
            (item) =>
              item.document_id === reference.document_id &&
              item.version === reference.version &&
              item.chapter_id === reference.chapter_id,
          );
          const firstRect = reference.rects?.[0];
          if (!sourceChapter || !firstRect) throw new Error();

          let attachmentFilename: string | undefined;
          if (selection.kind === "area") {
            const image = result.images?.[0];
            if (!image || !onAttach) throw new Error();
            attachmentFilename = image.filename;
            const previewUrl = `data:image/png;base64,${image.base64}`;
            onAttach({
              type: "image",
              filename: image.filename,
              base64: image.base64,
              previewUrl,
              size: Math.floor(image.base64.length * 3 / 4),
              mimeType: "image/png",
            });
          }

          const context: LegacyReaderContext = {
            materialId: sourceChapter.reading_material_id || reference.version.slice(0, 16),
            materialRevision: sourceChapter.reading_material_revision || 1,
            documentId: reference.document_id,
            version: reference.version,
            chapterId: reference.chapter_id,
            chapterTitle: `第${sourceChapter.chapter_id}章 ${sourceChapter.title}`,
            locator: firstRect.page,
            source: "selection",
            selection: {
              kind: selection.kind,
              rects: reference.rects,
              text: String(result.text || "").slice(0, 4000),
              ...(attachmentFilename ? { attachmentFilename } : {}),
            },
          };
          if (selection.kind === "area") {
            onAsk("请结合教材解释我圈出的图、公式或表格。", context);
          } else {
            if (!result.text) throw new Error();
            onAsk(`请结合教材解释这段内容：\n${result.text}`, context);
          }
        } catch {
          setError("选区验证失败，请重新选择。");
        }
      },
    );
    return () => window.TextbookPDF?.unmount(element);
  }, [chapters, documentId, metadata, onAsk, onAttach, pageTarget, readerTarget?.nonce, readerTarget?.reference, ready, sectionId]);

  const chapter = chapters.find((item) => item.document_id === documentId);
  return (
    <aside
      aria-label="教材阅读器"
      className="relative flex h-full min-h-0 w-full min-w-0 flex-col border-r border-border bg-background"
    >
      <link rel="stylesheet" href="/static/pdf-reader/reader.css" />
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <strong>教材阅读器</strong>
        <select
          aria-label="教材章节"
          value={documentId}
          onChange={(event) => {
            const item = chapters.find((row) => row.document_id === event.target.value);
            setPageTarget(null);
            setReaderTarget(null);
            setDocumentId(event.target.value);
            setSectionId(item?.sections[0]?.id ?? 0);
          }}
        >
          {chapters.map((item) => (
            <option key={item.document_id} value={item.document_id}>
              第{item.chapter_id}章 {item.title}
            </option>
          ))}
        </select>
        <select
          aria-label="教材小节"
          value={sectionId}
          onChange={(event) => {
            setPageTarget(null);
            setSectionId(Number(event.target.value));
          }}
        >
          {chapter?.sections.map((item) => (
            <option key={item.id} value={item.id}>{item.title}</option>
          ))}
        </select>
        <button type="button" onClick={onClose} className="ml-auto rounded border px-3 py-1">
          关闭
        </button>
      </div>
      {error ? <p role="status" className="p-2">{error}</p> : null}
      <div ref={host} className="relative min-h-0 flex-1" />
    </aside>
  );
}
