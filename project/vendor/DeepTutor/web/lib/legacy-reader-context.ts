export interface LegacyReaderRect {
  page: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface LegacyReaderSelection {
  kind: "text" | "area";
  rects: LegacyReaderRect[];
  text: string;
  attachmentFilename?: string;
}

export interface LegacyReaderContext {
  materialId: string;
  materialRevision: number;
  documentId: string;
  version: string;
  chapterId: number;
  chapterTitle: string;
  locator: number;
  source: "viewport" | "selection";
  selection?: LegacyReaderSelection;
}

export function normalizeLegacyReaderContext(
  value: unknown,
): LegacyReaderContext | undefined {
  if (!value || typeof value !== "object") return undefined;
  const row = value as Record<string, unknown>;
  const materialId = String(row.materialId ?? "").toLowerCase();
  const version = String(row.version ?? "").toLowerCase();
  const documentId = String(row.documentId ?? "").trim();
  const materialRevision = Number(row.materialRevision);
  const chapterId = Number(row.chapterId);
  const locator = Number(row.locator);
  const source = row.source === "selection" ? "selection" :
    row.source === "viewport" ? "viewport" : null;
  if (
    !/^[0-9a-f]{16}$/.test(materialId) ||
    !/^[0-9a-f]{64}$/.test(version) ||
    materialId !== version.slice(0, 16) ||
    !documentId || documentId.length > 100 ||
    !Number.isSafeInteger(materialRevision) || materialRevision < 1 ||
    !Number.isSafeInteger(chapterId) || chapterId < 1 ||
    !Number.isSafeInteger(locator) || locator < 1 ||
    !source
  ) return undefined;

  const chapterTitle = String(row.chapterTitle ?? "").trim().slice(0, 240);
  let selection: LegacyReaderSelection | undefined;
  const rawSelection = row.selection;
  if (rawSelection && typeof rawSelection === "object") {
    const raw = rawSelection as Record<string, unknown>;
    const kind = raw.kind === "text" || raw.kind === "area" ? raw.kind : null;
    const rawRects = Array.isArray(raw.rects) ? raw.rects.slice(0, 128) : [];
    const rects: LegacyReaderRect[] = [];
    for (const rawRect of rawRects) {
      if (!rawRect || typeof rawRect !== "object") continue;
      const rect = rawRect as Record<string, unknown>;
      const page = Number(rect.page);
      const x1 = Number(rect.x1), y1 = Number(rect.y1);
      const x2 = Number(rect.x2), y2 = Number(rect.y2);
      if (
        !Number.isSafeInteger(page) || page < 1 ||
        ![x1, y1, x2, y2].every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ||
        x1 >= x2 || y1 >= y2
      ) continue;
      rects.push({ page, x1, y1, x2, y2 });
    }
    if (kind && rects.length) {
      const text = String(raw.text ?? "").slice(0, 4000);
      const attachmentFilename = String(raw.attachmentFilename ?? "").trim().slice(0, 240);
      selection = {
        kind,
        rects,
        text,
        ...(attachmentFilename ? { attachmentFilename } : {}),
      };
    }
  }
  return {
    materialId,
    materialRevision,
    documentId,
    version,
    chapterId,
    chapterTitle,
    locator,
    source: source === "selection" && selection ? "selection" : "viewport",
    ...(selection ? { selection } : {}),
  };
}
