"use strict";
(self["webpackChunk"] = self["webpackChunk"] || []).push([[3842],{

/***/ 3842:
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   "default": () => (/* binding */ RichInlineMarkdown)
/* harmony export */ });
/* harmony import */ var react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(8839);
/* harmony import */ var katex_dist_katex_min_css__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(2728);
/* harmony import */ var katex_dist_katex_min_css__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(katex_dist_katex_min_css__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(2079);
/* harmony import */ var react_markdown__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(6771);
/* harmony import */ var remark_gfm__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(3510);
/* harmony import */ var _lib_latex__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(5800);
"use client";






/**
 * Phrasing-only components.
 *
 * The host is frequently a `<button>` or a `<span>`, whose content model is
 * phrasing content — a `<p>` there is invalid markup and drags the block
 * spacing of the surrounding renderer in with it. Paragraphs and headings
 * therefore collapse to their children, and the block constructs a one-line
 * question cannot contain are simply not overridden: react-markdown will not
 * produce them from the inline grammar these strings use.
 */
const COMPONENTS = {
    p: ({ children }) => (0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)(react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.Fragment, { children: children }),
    h1: ({ children }) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("strong", { children: children })),
    h2: ({ children }) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("strong", { children: children })),
    h3: ({ children }) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("strong", { children: children })),
    code: ({ children }) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("code", { className: "rounded bg-[color-mix(in_srgb,var(--foreground)_8%,transparent)] px-1 py-px font-mono text-[0.92em]", children: children })),
    a: ({ children }) => ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("span", { className: "underline underline-offset-2", children: children })),
    // A question stem is one line; a hard break inside it should not open a
    // block box the card then has to lay out around.
    br: () => (0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)("span", { children: " " }),
};
function RichInlineMarkdown({ content }) {
    const [plugins, setPlugins] = (0,react__WEBPACK_IMPORTED_MODULE_2__.useState)({});
    (0,react__WEBPACK_IMPORTED_MODULE_2__.useEffect)(() => {
        let cancelled = false;
        void (async () => {
            const [remarkMath, rehypeKatex] = await Promise.all([
                __webpack_require__.e(/* import() */ 1455).then(__webpack_require__.bind(__webpack_require__, 1455)),
                Promise.all(/* import() */[__webpack_require__.e(2210), __webpack_require__.e(315)]).then(__webpack_require__.bind(__webpack_require__, 315)),
            ]);
            if (!cancelled) {
                setPlugins({
                    remarkMath: remarkMath.default,
                    rehypeKatex: rehypeKatex.default,
                });
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);
    const remarkPlugins = [remark_gfm__WEBPACK_IMPORTED_MODULE_4__/* ["default"] */ .A];
    if (plugins.remarkMath)
        remarkPlugins.push(plugins.remarkMath);
    const rehypePlugins = plugins.rehypeKatex ? [plugins.rehypeKatex] : [];
    return ((0,react_jsx_runtime__WEBPACK_IMPORTED_MODULE_0__.jsx)(react_markdown__WEBPACK_IMPORTED_MODULE_5__/* .Markdown */ .oz, { remarkPlugins: remarkPlugins, rehypePlugins: rehypePlugins, components: COMPONENTS, children: (0,_lib_latex__WEBPACK_IMPORTED_MODULE_3__/* .processLatexContent */ .HS)(content) }));
}


/***/ })

}]);