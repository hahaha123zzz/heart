"use strict";
(self["webpackChunk"] = self["webpackChunk"] || []).push([[2112],{

/***/ 2112:
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   "default": () => (__WEBPACK_DEFAULT_EXPORT__)
/* harmony export */ });
/* harmony import */ var react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(8839);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(2079);
/* harmony import */ var react_i18next__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(5305);
"use client";



const GGB_SCRIPT_SRC = "https://www.geogebra.org/apps/deployggb.js";
// Single in-flight loader shared by every Geogebra instance on the page.
// deployggb.js is ~MB and lives on geogebra.org's CDN; fetching it once and
// reusing window.GGBApplet keeps subsequent applets snappy.
let ggbLoader = null;
function loadGgbScript() {
    if (typeof window === "undefined") {
        return Promise.reject(new Error("window unavailable"));
    }
    if (window.GGBApplet)
        return Promise.resolve();
    if (ggbLoader)
        return ggbLoader;
    ggbLoader = new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[src="${GGB_SCRIPT_SRC}"]`);
        if (existing) {
            if (window.GGBApplet) {
                resolve();
                return;
            }
            existing.addEventListener("load", () => resolve());
            existing.addEventListener("error", () => {
                ggbLoader = null;
                reject(new Error("GeoGebra script failed to load"));
            });
            return;
        }
        const script = document.createElement("script");
        script.src = GGB_SCRIPT_SRC;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => {
            ggbLoader = null;
            reject(new Error("GeoGebra script failed to load"));
        };
        document.head.appendChild(script);
    });
    return ggbLoader;
}
// The agent emits one command per line and prefixes human-readable
// descriptions with `#`. evalCommand only takes one command at a time, so we
// strip comments + empty lines and feed the rest sequentially.
function parseGgbCommands(raw) {
    return raw
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0 && !line.startsWith("#"));
}
let containerCounter = 0;
const Geogebra = ({ script = "", payload, title, className = "", width = 760, height = 480, }) => {
    const { t } = (0,react_i18next__WEBPACK_IMPORTED_MODULE_2__/* .useTranslation */ .B)();
    const containerRef = (0,react__WEBPACK_IMPORTED_MODULE_1__.useRef)(null);
    const containerIdRef = (0,react__WEBPACK_IMPORTED_MODULE_1__.useRef)(`ggb-${++containerCounter}-${Date.now().toString(36)}`);
    const [error, setError] = (0,react__WEBPACK_IMPORTED_MODULE_1__.useState)(null);
    const [loading, setLoading] = (0,react__WEBPACK_IMPORTED_MODULE_1__.useState)(true);
    const [commandErrors, setCommandErrors] = (0,react__WEBPACK_IMPORTED_MODULE_1__.useState)([]);
    (0,react__WEBPACK_IMPORTED_MODULE_1__.useEffect)(() => {
        let cancelled = false;
        // Snapshot the ref now so the cleanup closure sees the same node React
        // mounted with, not whatever the ref points at after a later re-render.
        const containerAtMount = containerRef.current;
        setLoading(true);
        setError(null);
        async function mount() {
            try {
                await loadGgbScript();
                if (cancelled)
                    return;
                if (!window.GGBApplet) {
                    throw new Error("GGBApplet global missing after script load");
                }
                const commands = payload?.commands?.length
                    ? payload.commands.map(String).filter((command) => command.trim())
                    : parseGgbCommands(script);
                const container = containerRef.current;
                if (!container)
                    return;
                container.id = containerIdRef.current;
                container.innerHTML = "";
                const applet = new window.GGBApplet({
                    appName: payload?.app_name || "geometry",
                    width,
                    height,
                    showToolBar: false,
                    showAlgebraInput: false,
                    showMenuBar: false,
                    showResetIcon: true,
                    enableLabelDrags: false,
                    enableShiftDragZoom: true,
                    useBrowserForJS: false,
                    // The api passed in here lets us drive the applet
                    // imperatively without going through a global. We feed each
                    // command separately so one bad line doesn't abort the rest.
                    appletOnLoad: (api) => {
                        if (cancelled)
                            return;
                        const view = payload?.view;
                        if (view && api.setCoordSystem) {
                            api.setCoordSystem(view.x_min, view.x_max, view.y_min, view.y_max);
                        }
                        const failures = [];
                        for (const cmd of commands) {
                            try {
                                if (!api.evalCommand(cmd)) {
                                    failures.push(cmd);
                                    console.warn("[ggb] evalCommand returned false", { cmd });
                                }
                            }
                            catch (err) {
                                failures.push(cmd);
                                console.warn("[ggb] evalCommand failed", { cmd, err });
                            }
                        }
                        setLoading(false);
                        if (!cancelled && failures.length > 0) {
                            setCommandErrors(failures);
                        }
                    },
                }, true);
                applet.inject(containerIdRef.current);
            }
            catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : String(err));
                    setLoading(false);
                }
            }
        }
        void mount();
        return () => {
            cancelled = true;
            if (containerAtMount) {
                containerAtMount.innerHTML = "";
            }
        };
    }, [script, payload, width, height]);
    return ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)("div", { className: `my-4 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)] ${className}`, children: [title ? ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("div", { className: "border-b border-[var(--border)] px-3 py-2 text-sm font-medium text-[var(--foreground)]", children: title })) : null, error ? ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)("div", { className: "p-4 text-sm text-[var(--destructive,#dc2626)]", children: [t("Failed to load GeoGebra"), ": ", error] })) : ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)(react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.Fragment, { children: [commandErrors.length > 0 ? ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)("div", { role: "alert", className: "border-b border-[var(--border)] bg-[var(--destructive,#dc2626)]/5 px-3 py-2 text-[12px] leading-relaxed text-[var(--destructive,#dc2626)]", children: [(0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)("span", { className: "font-medium", children: [t("GeoGebra rejected {{count}} command(s)", {
                                        count: commandErrors.length,
                                    }), ":"] }), (0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("ul", { className: "mt-1 list-inside list-disc", children: commandErrors.map((cmd) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("li", { className: "truncate font-mono text-[11px]", children: cmd }, cmd))) })] })) : null, (0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsxs)("div", { className: "relative", style: { minHeight: height }, children: [loading ? ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("div", { className: "absolute inset-0 flex items-center justify-center text-sm text-[var(--muted-foreground)]", children: t("Loading GeoGebra...") })) : null, (0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("div", { ref: containerRef, className: "ggb-applet-container" })] })] }))] }));
};
/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (Geogebra);


/***/ })

}]);