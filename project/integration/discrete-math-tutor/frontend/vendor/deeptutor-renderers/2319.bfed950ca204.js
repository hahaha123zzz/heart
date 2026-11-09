"use strict";
(self["webpackChunk"] = self["webpackChunk"] || []).push([[2319],{

/***/ 2319:
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

// ESM COMPAT FLAG
__webpack_require__.r(__webpack_exports__);

// EXPORTS
__webpack_require__.d(__webpack_exports__, {
  "default": () => (/* binding */ MathAnimatorViewer)
});

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\react\jsx-runtime.js
var D_deeptutor_web_node_modules_react_jsx_runtime = __webpack_require__(8839);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\react\index.js
var D_deeptutor_web_node_modules_react_index = __webpack_require__(2079);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lucide-react\dist\esm\createLucideIcon.js + 3 modules
var D_deeptutor_web_node_modules_lucide_react_dist_esm_createLucideIcon = __webpack_require__(3242);
;// D:\deeptutor\web\node_modules\lucide-react\dist\esm\icons\video.js
/**
 * @license lucide-react v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */



const __iconNode = [
  [
    "path",
    {
      d: "m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5",
      key: "ftymec"
    }
  ],
  ["rect", { x: "2", y: "6", width: "14", height: "12", rx: "2", key: "158x01" }]
];
const Video = (0,D_deeptutor_web_node_modules_lucide_react_dist_esm_createLucideIcon/* default */.A)("video", __iconNode);


//# sourceMappingURL=video.js.map

;// D:\deeptutor\web\node_modules\lucide-react\dist\esm\icons\image.js
/**
 * @license lucide-react v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */



const D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_image_iconNode = [
  ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", ry: "2", key: "1m3agn" }],
  ["circle", { cx: "9", cy: "9", r: "2", key: "af1f0g" }],
  ["path", { d: "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21", key: "1xmnt7" }]
];
const Image = (0,D_deeptutor_web_node_modules_lucide_react_dist_esm_createLucideIcon/* default */.A)("image", D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_image_iconNode);


//# sourceMappingURL=image.js.map

;// D:\deeptutor\web\node_modules\lucide-react\dist\esm\icons\expand.js
/**
 * @license lucide-react v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */



const D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_expand_iconNode = [
  ["path", { d: "m15 15 6 6", key: "1s409w" }],
  ["path", { d: "m15 9 6-6", key: "ko1vev" }],
  ["path", { d: "M21 16v5h-5", key: "1ck2sf" }],
  ["path", { d: "M21 8V3h-5", key: "1qoq8a" }],
  ["path", { d: "M3 16v5h5", key: "1t08am" }],
  ["path", { d: "m3 21 6-6", key: "wwnumi" }],
  ["path", { d: "M3 8V3h5", key: "1ln10m" }],
  ["path", { d: "M9 9 3 3", key: "v551iv" }]
];
const Expand = (0,D_deeptutor_web_node_modules_lucide_react_dist_esm_createLucideIcon/* default */.A)("expand", D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_expand_iconNode);


//# sourceMappingURL=expand.js.map

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lucide-react\dist\esm\icons\code-xml.js
var D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_code_xml = __webpack_require__(6458);
;// D:\deeptutor\web\node_modules\lucide-react\dist\esm\icons\timer.js
/**
 * @license lucide-react v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */



const D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_timer_iconNode = [
  ["line", { x1: "10", x2: "14", y1: "2", y2: "2", key: "14vaq8" }],
  ["line", { x1: "12", x2: "15", y1: "14", y2: "11", key: "17fdiu" }],
  ["circle", { cx: "12", cy: "14", r: "8", key: "1e1u0o" }]
];
const Timer = (0,D_deeptutor_web_node_modules_lucide_react_dist_esm_createLucideIcon/* default */.A)("timer", D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_timer_iconNode);


//# sourceMappingURL=timer.js.map

// EXTERNAL MODULE: ./frontend/native/translation.ts + 2 modules
var translation = __webpack_require__(5305);
;// ./frontend/native/api.ts
function apiUrl(value) {
    if (value.startsWith('/api/deeptutor/tasks/') || value.startsWith('/static/'))
        return value;
    throw new Error('原生文件尚未获得宿主授权');
}

;// ../../vendor/DeepTutor/web/components/math-animator/MathAnimatorViewer.tsx
"use client";





function MathAnimatorViewer({ result, }) {
    const { t } = (0,translation/* useTranslation */.B)();
    const [fullscreenUrl, setFullscreenUrl] = (0,D_deeptutor_web_node_modules_react_index.useState)(null);
    const rootRef = (0,D_deeptutor_web_node_modules_react_index.useRef)(null);
    const images = (0,D_deeptutor_web_node_modules_react_index.useMemo)(() => result.artifacts.filter((item) => item.type === "image"), [result.artifacts]);
    const videos = (0,D_deeptutor_web_node_modules_react_index.useMemo)(() => result.artifacts.filter((item) => item.type === "video"), [result.artifacts]);
    const resolveAssetUrl = (url) => url.startsWith("http://") || url.startsWith("https://") ? url : apiUrl(url);
    (0,D_deeptutor_web_node_modules_react_index.useEffect)(() => {
        const el = rootRef.current;
        if (!el)
            return;
        const handler = (e) => {
            if (Math.abs(e.deltaY) < 1)
                return;
            // Don't intercept if the event target is inside a scrollable child
            // (e.g. the code <pre> block) that can still scroll in this direction.
            let node = e.target;
            while (node && node !== el) {
                if (node.scrollHeight > node.clientHeight + 2) {
                    const style = window.getComputedStyle(node);
                    if (style.overflowY === "auto" || style.overflowY === "scroll") {
                        const atBottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 2;
                        const atTop = node.scrollTop <= 2;
                        if ((e.deltaY > 0 && !atBottom) || (e.deltaY < 0 && !atTop)) {
                            return;
                        }
                    }
                }
                node = node.parentElement;
            }
            let scrollRoot = el.closest("[data-chat-scroll-root='true']");
            if (!scrollRoot) {
                let parent = el.parentElement;
                while (parent) {
                    const style = window.getComputedStyle(parent);
                    if ((style.overflowY === "auto" || style.overflowY === "scroll") &&
                        parent.scrollHeight > parent.clientHeight + 2) {
                        scrollRoot = parent;
                        break;
                    }
                    parent = parent.parentElement;
                }
            }
            if (scrollRoot) {
                e.preventDefault();
                scrollRoot.scrollBy({ top: e.deltaY, behavior: "auto" });
            }
        };
        el.addEventListener("wheel", handler, { passive: false });
        return () => el.removeEventListener("wheel", handler);
    }, []);
    return ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("div", { ref: rootRef, className: "mb-3 space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--card)]/70 p-3", children: [videos.length > 0 ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("section", { className: "space-y-2", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(Header, { icon: Video, title: t("Video Output") }), videos.map((item) => ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("div", { children: (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("video", { controls: true, playsInline: true, preload: "metadata", className: "aspect-video w-full rounded-xl border border-[var(--border)] bg-black object-contain", src: resolveAssetUrl(item.url) }) }, item.url)))] })) : null, images.length > 0 ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("section", { className: "space-y-2", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(Header, { icon: Image, title: t("Image Output") }), (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("div", { className: "grid grid-cols-1 gap-2 sm:grid-cols-2", children: images.map((item) => ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("button", { type: "button", onClick: () => setFullscreenUrl(resolveAssetUrl(item.url)), className: "group relative overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--background)]", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("img", { src: resolveAssetUrl(item.url), alt: item.label || item.filename, className: "max-h-[280px] w-full object-contain" }), (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("span", { className: "absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-black/55 px-2 py-1 text-[11px] text-white opacity-0 transition-opacity group-hover:opacity-100", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(Expand, { size: 12 }), t("Fullscreen")] })] }, item.url))) })] })) : null, result.code.content ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("details", { className: "overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--background)]", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("summary", { className: "flex cursor-pointer items-center gap-2 px-3 py-2 text-[12px] font-medium text-[var(--foreground)]", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(D_deeptutor_web_node_modules_lucide_react_dist_esm_icons_code_xml/* default */.A, { size: 14 }), t("View Manim Code")] }), (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("pre", { className: "max-h-[360px] overflow-auto border-t border-[var(--border)] px-3 py-3 font-mono text-[11px] leading-[1.6] text-[var(--foreground)]", children: result.code.content })] })) : null, result.render.visual_review &&
                result.render.visual_review.passed === false ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("div", { className: "rounded-xl border border-amber-500/35 bg-amber-500/10 px-3 py-2.5 text-[12px] leading-[1.6] text-amber-900 dark:text-amber-200", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("div", { className: "font-medium", children: [t("Visual review warning:"), " ", result.render.visual_review.summary ||
                                t("The generated result still has presentation issues.")] }), result.render.visual_review.issues &&
                        result.render.visual_review.issues.length > 0 ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("div", { className: "mt-1 opacity-90", children: result.render.visual_review.issues.join(" ") })) : null] })) : null, result.render.retry_attempts ||
                Object.keys(result.timings).length > 0 ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("div", { className: "flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]", children: [result.render.quality ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("span", { className: "rounded-full border border-[var(--border)] px-2 py-0.5", children: t("Quality: {{quality}}", { quality: result.render.quality }) })) : null, typeof result.render.retry_attempts === "number" ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("span", { className: "rounded-full border border-[var(--border)] px-2 py-0.5", children: t("Retries: {{count}}", { count: result.render.retry_attempts }) })) : null, Object.keys(result.timings).length > 0 ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("span", { className: "inline-flex items-center gap-1 rounded-full border border-[var(--border)] px-2 py-0.5", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(Timer, { size: 12 }), Object.entries(result.timings)
                                .map(([key, value]) => `${key} ${value}s`)
                                .join(" · ")] })) : null] })) : null, fullscreenUrl ? ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("div", { className: "fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-6", onClick: () => setFullscreenUrl(null), children: (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("img", { src: fullscreenUrl, alt: t("Fullscreen math animation output"), className: "max-h-full max-w-full object-contain" }) })) : null] }));
}
function Header({ icon: Icon, title }) {
    return ((0,D_deeptutor_web_node_modules_react_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2 text-[12px] font-medium text-[var(--foreground)]", children: [(0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)(Icon, { size: 14 }), (0,D_deeptutor_web_node_modules_react_jsx_runtime.jsx)("span", { children: title })] }));
}


/***/ })

}]);