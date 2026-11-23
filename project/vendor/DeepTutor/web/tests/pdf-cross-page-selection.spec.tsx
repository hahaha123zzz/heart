import { afterEach, expect, it, vi } from "vitest";
import { pdfSelectionPages } from "@/lib/reading-selection";
afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });
it("keeps Chinese cross-page selection in each page's own crop box at different zooms", () => {
  document.body.innerHTML = '<div id="root"><div data-reader-unit="1"><div class="textLayer">第一行中文</div></div><div data-reader-unit="2"><div class="textLayer">第二页中文</div></div></div>';
  const root = document.getElementById("root")!;
  const pages = Array.from(root.children) as HTMLElement[];
  const range = document.createRange();
  range.setStart(pages[0].querySelector(".textLayer")!.firstChild!, 2);
  range.setEnd(pages[1].querySelector(".textLayer")!.firstChild!, 3);
  Object.defineProperty(Range.prototype, "getClientRects", { value: () => [], configurable: true, writable: true });
  for (const scale of [0.75, 1, 1.5]) {
    pages.forEach((p, i) => vi.spyOn(p, "getBoundingClientRect").mockReturnValue({ left: 20, top: 100 + i * 800 * scale, width: 500 * scale, height: 700 * scale } as DOMRect));
    vi.spyOn(Range.prototype, "getClientRects").mockImplementation(function(this: Range) {
      const page = this.startContainer.parentElement?.closest<HTMLElement>("[data-reader-unit]") ?? (this.startContainer as HTMLElement).closest<HTMLElement>("[data-reader-unit]")!;
      const box = page.getBoundingClientRect();
      return [{ left: box.left + 50 * scale, top: box.top + 70 * scale, width: 200 * scale, height: 14 * scale }] as unknown as DOMRectList;
    });
    const result = pdfSelectionPages(range, root);
    expect(result.map(p => [p.locator, p.quote])).toEqual([[1, "行中文"], [2, "第二页"]]);
    result.forEach(p => expect(p.rects).toEqual([[0.1, 0.1, 0.5, 0.12]]));
    vi.restoreAllMocks();
  }
});
