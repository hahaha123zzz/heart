"use strict";
(self["webpackChunk"] = self["webpackChunk"] || []).push([[315],{

/***/ 315:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

// ESM COMPAT FLAG
__webpack_require__.r(__webpack_exports__);

// EXPORTS
__webpack_require__.d(__webpack_exports__, {
  "default": () => (/* reexport */ rehypeKatex)
});

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\property-information\index.js + 11 modules
var D_deeptutor_web_node_modules_property_information_index = __webpack_require__(2265);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\comma-separated-tokens\index.js
var D_deeptutor_web_node_modules_comma_separated_tokens_index = __webpack_require__(6275);
;// D:\deeptutor\web\node_modules\hast-util-parse-selector\lib\index.js
/**
 * @typedef {import('hast').Element} Element
 * @typedef {import('hast').Properties} Properties
 */

/**
 * @template {string} SimpleSelector
 *   Selector type.
 * @template {string} DefaultTagName
 *   Default tag name.
 * @typedef {(
 *   SimpleSelector extends ''
 *     ? DefaultTagName
 *     : SimpleSelector extends `${infer TagName}.${infer Rest}`
 *     ? ExtractTagName<TagName, DefaultTagName>
 *     : SimpleSelector extends `${infer TagName}#${infer Rest}`
 *     ? ExtractTagName<TagName, DefaultTagName>
 *     : SimpleSelector extends string
 *     ? SimpleSelector
 *     : DefaultTagName
 * )} ExtractTagName
 *   Extract tag name from a simple selector.
 */

const search = /[#.]/g

/**
 * Create a hast element from a simple CSS selector.
 *
 * @template {string} Selector
 *   Type of selector.
 * @template {string} [DefaultTagName='div']
 *   Type of default tag name (default: `'div'`).
 * @param {Selector | null | undefined} [selector]
 *   Simple CSS selector (optional).
 *
 *   Can contain a tag name (`foo`), classes (`.bar`), and an ID (`#baz`).
 *   Multiple classes are allowed.
 *   Uses the last ID if multiple IDs are found.
 * @param {DefaultTagName | null | undefined} [defaultTagName='div']
 *   Tag name to use if `selector` does not specify one (default: `'div'`).
 * @returns {Element & {tagName: ExtractTagName<Selector, DefaultTagName>}}
 *   Built element.
 */
function parseSelector(selector, defaultTagName) {
  const value = selector || ''
  /** @type {Properties} */
  const props = {}
  let start = 0
  /** @type {string | undefined} */
  let previous
  /** @type {string | undefined} */
  let tagName

  while (start < value.length) {
    search.lastIndex = start
    const match = search.exec(value)
    const subvalue = value.slice(start, match ? match.index : value.length)

    if (subvalue) {
      if (!previous) {
        tagName = subvalue
      } else if (previous === '#') {
        props.id = subvalue
      } else if (Array.isArray(props.className)) {
        props.className.push(subvalue)
      } else {
        props.className = [subvalue]
      }

      start += subvalue.length
    }

    if (match) {
      previous = match[0]
      start++
    }
  }

  return {
    type: 'element',
    // @ts-expect-error: tag name is parsed.
    tagName: tagName || defaultTagName || 'div',
    properties: props,
    children: []
  }
}

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\property-information\lib\find.js
var D_deeptutor_web_node_modules_property_information_lib_find = __webpack_require__(4185);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\property-information\lib\normalize.js
var D_deeptutor_web_node_modules_property_information_lib_normalize = __webpack_require__(3359);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\space-separated-tokens\index.js
var D_deeptutor_web_node_modules_space_separated_tokens_index = __webpack_require__(4960);
;// D:\deeptutor\web\node_modules\hastscript\lib\create-h.js
/**
 * @import {Element, Nodes, RootContent, Root} from 'hast'
 * @import {Info, Schema} from 'property-information'
 */

/**
 * @typedef {Array<Nodes | PrimitiveChild>} ArrayChildNested
 *   List of children (deep).
 */

/**
 * @typedef {Array<ArrayChildNested | Nodes | PrimitiveChild>} ArrayChild
 *   List of children.
 */

/**
 * @typedef {Array<number | string>} ArrayValue
 *   List of property values for space- or comma separated values (such as `className`).
 */

/**
 * @typedef {ArrayChild | Nodes | PrimitiveChild} Child
 *   Acceptable child value.
 */

/**
 * @typedef {number | string | null | undefined} PrimitiveChild
 *   Primitive children, either ignored (nullish), or turned into text nodes.
 */

/**
 * @typedef {boolean | number | string | null | undefined} PrimitiveValue
 *   Primitive property value.
 */

/**
 * @typedef {Record<string, PropertyValue | Style>} Properties
 *   Acceptable value for element properties.
 */

/**
 * @typedef {ArrayValue | PrimitiveValue} PropertyValue
 *   Primitive value or list value.
 */

/**
 * @typedef {Element | Root} Result
 *   Result from a `h` (or `s`) call.
 */

/**
 * @typedef {number | string} StyleValue
 *   Value for a CSS style field.
 */

/**
 * @typedef {Record<string, StyleValue>} Style
 *   Supported value of a `style` prop.
 */






/**
 * @param {Schema} schema
 *   Schema to use.
 * @param {string} defaultTagName
 *   Default tag name.
 * @param {ReadonlyArray<string> | undefined} [caseSensitive]
 *   Case-sensitive tag names (default: `undefined`).
 * @returns
 *   `h`.
 */
function createH(schema, defaultTagName, caseSensitive) {
  const adjust = caseSensitive ? createAdjustMap(caseSensitive) : undefined

  /**
   * Hyperscript compatible DSL for creating virtual hast trees.
   *
   * @overload
   * @param {null | undefined} [selector]
   * @param {...Child} children
   * @returns {Root}
   *
   * @overload
   * @param {string} selector
   * @param {Properties} properties
   * @param {...Child} children
   * @returns {Element}
   *
   * @overload
   * @param {string} selector
   * @param {...Child} children
   * @returns {Element}
   *
   * @param {string | null | undefined} [selector]
   *   Selector.
   * @param {Child | Properties | null | undefined} [properties]
   *   Properties (or first child) (default: `undefined`).
   * @param {...Child} children
   *   Children.
   * @returns {Result}
   *   Result.
   */
  function h(selector, properties, ...children) {
    /** @type {Result} */
    let node

    if (selector === null || selector === undefined) {
      node = {type: 'root', children: []}
      // Properties are not supported for roots.
      const child = /** @type {Child} */ (properties)
      children.unshift(child)
    } else {
      node = parseSelector(selector, defaultTagName)
      // Normalize the name.
      const lower = node.tagName.toLowerCase()
      const adjusted = adjust ? adjust.get(lower) : undefined
      node.tagName = adjusted || lower

      // Handle properties.
      if (isChild(properties)) {
        children.unshift(properties)
      } else {
        for (const [key, value] of Object.entries(properties)) {
          addProperty(schema, node.properties, key, value)
        }
      }
    }

    // Handle children.
    for (const child of children) {
      addChild(node.children, child)
    }

    if (node.type === 'element' && node.tagName === 'template') {
      node.content = {type: 'root', children: node.children}
      node.children = []
    }

    return node
  }

  return h
}

/**
 * Check if something is properties or a child.
 *
 * @param {Child | Properties} value
 *   Value to check.
 * @returns {value is Child}
 *   Whether `value` is definitely a child.
 */
function isChild(value) {
  // Never properties if not an object.
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return true
  }

  // Never node without `type`; that’s the main discriminator.
  if (typeof value.type !== 'string') return false

  // Slower check: never property value if object or array with
  // non-number/strings.
  const record = /** @type {Record<string, unknown>} */ (value)
  const keys = Object.keys(value)

  for (const key of keys) {
    const value = record[key]

    if (value && typeof value === 'object') {
      if (!Array.isArray(value)) return true

      const list = /** @type {ReadonlyArray<unknown>} */ (value)

      for (const item of list) {
        if (typeof item !== 'number' && typeof item !== 'string') {
          return true
        }
      }
    }
  }

  // Also see empty `children` as a node.
  if ('children' in value && Array.isArray(value.children)) {
    return true
  }

  // Default to properties, someone can always pass an empty object,
  // put `data: {}` in a node,
  // or wrap it in an array.
  return false
}

/**
 * @param {Schema} schema
 *   Schema.
 * @param {Properties} properties
 *   Properties object.
 * @param {string} key
 *   Property name.
 * @param {PropertyValue | Style} value
 *   Property value.
 * @returns {undefined}
 *   Nothing.
 */
function addProperty(schema, properties, key, value) {
  const info = (0,D_deeptutor_web_node_modules_property_information_lib_find/* find */.I)(schema, key)
  /** @type {PropertyValue} */
  let result

  // Ignore nullish and NaN values.
  if (value === null || value === undefined) return

  if (typeof value === 'number') {
    // Ignore NaN.
    if (Number.isNaN(value)) return

    result = value
  }
  // Booleans.
  else if (typeof value === 'boolean') {
    result = value
  }
  // Handle list values.
  else if (typeof value === 'string') {
    if (info.spaceSeparated) {
      result = (0,D_deeptutor_web_node_modules_space_separated_tokens_index/* parse */.q)(value)
    } else if (info.commaSeparated) {
      result = (0,D_deeptutor_web_node_modules_comma_separated_tokens_index/* parse */.q)(value)
    } else if (info.commaOrSpaceSeparated) {
      result = (0,D_deeptutor_web_node_modules_space_separated_tokens_index/* parse */.q)((0,D_deeptutor_web_node_modules_comma_separated_tokens_index/* parse */.q)(value).join(' '))
    } else {
      result = parsePrimitive(info, info.property, value)
    }
  } else if (Array.isArray(value)) {
    result = [...value]
  } else {
    result = info.property === 'style' ? style(value) : String(value)
  }

  if (Array.isArray(result)) {
    /** @type {Array<number | string>} */
    const finalResult = []

    for (const item of result) {
      // Assume no booleans in array.
      finalResult.push(
        /** @type {number | string} */ (
          parsePrimitive(info, info.property, item)
        )
      )
    }

    result = finalResult
  }

  // Class names (which can be added both on the `selector` and here).
  if (info.property === 'className' && Array.isArray(properties.className)) {
    // Assume no booleans in `className`.
    result = properties.className.concat(
      /** @type {Array<number | string> | number | string} */ (result)
    )
  }

  properties[info.property] = result
}

/**
 * @param {Array<RootContent>} nodes
 *   Children.
 * @param {Child} value
 *   Child.
 * @returns {undefined}
 *   Nothing.
 */
function addChild(nodes, value) {
  if (value === null || value === undefined) {
    // Empty.
  } else if (typeof value === 'number' || typeof value === 'string') {
    nodes.push({type: 'text', value: String(value)})
  } else if (Array.isArray(value)) {
    for (const child of value) {
      addChild(nodes, child)
    }
  } else if (typeof value === 'object' && 'type' in value) {
    if (value.type === 'root') {
      addChild(nodes, value.children)
    } else {
      nodes.push(value)
    }
  } else {
    throw new Error('Expected node, nodes, or string, got `' + value + '`')
  }
}

/**
 * Parse a single primitives.
 *
 * @param {Info} info
 *   Property information.
 * @param {string} name
 *   Property name.
 * @param {PrimitiveValue} value
 *   Property value.
 * @returns {PrimitiveValue}
 *   Property value.
 */
function parsePrimitive(info, name, value) {
  if (typeof value === 'string') {
    if (info.number && value && !Number.isNaN(Number(value))) {
      return Number(value)
    }

    if (
      (info.boolean || info.overloadedBoolean) &&
      (value === '' || (0,D_deeptutor_web_node_modules_property_information_lib_normalize/* normalize */.S)(value) === (0,D_deeptutor_web_node_modules_property_information_lib_normalize/* normalize */.S)(name))
    ) {
      return true
    }
  }

  return value
}

/**
 * Serialize a `style` object as a string.
 *
 * @param {Style} styles
 *   Style object.
 * @returns {string}
 *   CSS string.
 */
function style(styles) {
  /** @type {Array<string>} */
  const result = []

  for (const [key, value] of Object.entries(styles)) {
    result.push([key, value].join(': '))
  }

  return result.join('; ')
}

/**
 * Create a map to adjust casing.
 *
 * @param {ReadonlyArray<string>} values
 *   List of properly cased keys.
 * @returns {Map<string, string>}
 *   Map of lowercase keys to uppercase keys.
 */
function createAdjustMap(values) {
  /** @type {Map<string, string>} */
  const result = new Map()

  for (const value of values) {
    result.set(value.toLowerCase(), value)
  }

  return result
}

;// D:\deeptutor\web\node_modules\hastscript\lib\svg-case-sensitive-tag-names.js
/**
 * List of case-sensitive SVG tag names.
 *
 * @type {ReadonlyArray<string>}
 */
const svgCaseSensitiveTagNames = [
  'altGlyph',
  'altGlyphDef',
  'altGlyphItem',
  'animateColor',
  'animateMotion',
  'animateTransform',
  'clipPath',
  'feBlend',
  'feColorMatrix',
  'feComponentTransfer',
  'feComposite',
  'feConvolveMatrix',
  'feDiffuseLighting',
  'feDisplacementMap',
  'feDistantLight',
  'feDropShadow',
  'feFlood',
  'feFuncA',
  'feFuncB',
  'feFuncG',
  'feFuncR',
  'feGaussianBlur',
  'feImage',
  'feMerge',
  'feMergeNode',
  'feMorphology',
  'feOffset',
  'fePointLight',
  'feSpecularLighting',
  'feSpotLight',
  'feTile',
  'feTurbulence',
  'foreignObject',
  'glyphRef',
  'linearGradient',
  'radialGradient',
  'solidColor',
  'textArea',
  'textPath'
]

;// D:\deeptutor\web\node_modules\hastscript\lib\index.js
// Register the JSX namespace on `h`.
/**
 * @typedef {import('./jsx-classic.js').Element} h.JSX.Element
 * @typedef {import('./jsx-classic.js').ElementChildrenAttribute} h.JSX.ElementChildrenAttribute
 * @typedef {import('./jsx-classic.js').IntrinsicAttributes} h.JSX.IntrinsicAttributes
 * @typedef {import('./jsx-classic.js').IntrinsicElements} h.JSX.IntrinsicElements
 */

// Register the JSX namespace on `s`.
/**
 * @typedef {import('./jsx-classic.js').Element} s.JSX.Element
 * @typedef {import('./jsx-classic.js').ElementChildrenAttribute} s.JSX.ElementChildrenAttribute
 * @typedef {import('./jsx-classic.js').IntrinsicAttributes} s.JSX.IntrinsicAttributes
 * @typedef {import('./jsx-classic.js').IntrinsicElements} s.JSX.IntrinsicElements
 */





// Note: this explicit type is needed, otherwise TS creates broken types.
/** @type {ReturnType<createH>} */
const h = createH(D_deeptutor_web_node_modules_property_information_index/* html */.qy, 'div')

// Note: this explicit type is needed, otherwise TS creates broken types.
/** @type {ReturnType<createH>} */
const s = createH(D_deeptutor_web_node_modules_property_information_index/* svg */.JW, 'g', svgCaseSensitiveTagNames)

;// D:\deeptutor\web\node_modules\web-namespaces\index.js
/**
 * Map of web namespaces.
 *
 * @type {Record<string, string>}
 */
const webNamespaces = {
  html: 'http://www.w3.org/1999/xhtml',
  mathml: 'http://www.w3.org/1998/Math/MathML',
  svg: 'http://www.w3.org/2000/svg',
  xlink: 'http://www.w3.org/1999/xlink',
  xml: 'http://www.w3.org/XML/1998/namespace',
  xmlns: 'http://www.w3.org/2000/xmlns/'
}

;// D:\deeptutor\web\node_modules\hast-util-from-dom\lib\index.js
/**
 * @import {
 *   Comment as HastComment,
 *   Doctype as HastDoctype,
 *   Element as HastElement,
 *   Nodes as HastNodes,
 *   RootContent as HastRootContent,
 *   Root as HastRoot,
 *   Text as HastText,
 * } from 'hast'
 */

/**
 * @callback AfterTransform
 *   Callback called when each node is transformed.
 * @param {Node} domNode
 *   DOM node that was handled.
 * @param {HastNodes} hastNode
 *   Corresponding hast node.
 * @returns {undefined | void}
 *   Nothing.
 *
 *   Note: `void` included until TS infers `undefined` nicely.
 *
 * @typedef Options
 *   Configuration.
 * @property {AfterTransform | null | undefined} [afterTransform]
 *   Callback called when each node is transformed (optional).
 */




/**
 * Transform a DOM tree to a hast tree.
 *
 * @param {Node} tree
 *   DOM tree to transform.
 * @param {Options | null | undefined} [options]
 *   Configuration (optional).
 * @returns {HastNodes}
 *   Equivalent hast node.
 */
function fromDom(tree, options) {
  return transform(tree, options || {}) || {type: 'root', children: []}
}

/**
 * @param {Node} node
 *   DOM node to transform.
 * @param {Options} options
 *   Configuration.
 * @returns {HastNodes | undefined}
 *   Equivalent hast node.
 *
 *   Note that certain legacy DOM nodes (i.e., Attr nodes (2),  CDATA, processing instructions)
 */
function transform(node, options) {
  const transformed = one(node, options)
  if (transformed && options.afterTransform)
    options.afterTransform(node, transformed)
  return transformed
}

/**
 * @param {Node} node
 *   DOM node to transform.
 * @param {Options} options
 *   Configuration.
 * @returns {HastNodes | undefined}
 *   Equivalent hast node.
 */
function one(node, options) {
  switch (node.nodeType) {
    case 1 /* Element */: {
      const domNode = /** @type {Element} */ (node)
      return D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_element(domNode, options)
    }

    // Ignore: Attr (2).

    case 3 /* Text */: {
      const domNode = /** @type {Text} */ (node)
      return D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_text(domNode)
    }

    // Ignore: CDATA (4).
    // Removed: Entity reference (5)
    // Removed: Entity (6)
    // Ignore: Processing instruction (7).

    case 8 /* Comment */: {
      const domNode = /** @type {Comment} */ (node)
      return comment(domNode)
    }

    case 9 /* Document */: {
      const domNode = /** @type {Document} */ (node)
      return root(domNode, options)
    }

    case 10 /* Document type */: {
      return doctype()
    }

    case 11 /* Document fragment */: {
      const domNode = /** @type {DocumentFragment} */ (node)
      return root(domNode, options)
    }

    default: {
      return undefined
    }
  }
}

/**
 * Transform a document.
 *
 * @param {Document | DocumentFragment} node
 *   DOM node to transform.
 * @param {Options} options
 *   Configuration.
 * @returns {HastRoot}
 *   Equivalent hast node.
 */
function root(node, options) {
  return {type: 'root', children: D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_all(node, options)}
}

/**
 * Transform a doctype.
 *
 * @returns {HastDoctype}
 *   Equivalent hast node.
 */
function doctype() {
  return {type: 'doctype'}
}

/**
 * Transform a text.
 *
 * @param {Text} node
 *   DOM node to transform.
 * @returns {HastText}
 *   Equivalent hast node.
 */
function D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_text(node) {
  return {type: 'text', value: node.nodeValue || ''}
}

/**
 * Transform a comment.
 *
 * @param {Comment} node
 *   DOM node to transform.
 * @returns {HastComment}
 *   Equivalent hast node.
 */
function comment(node) {
  return {type: 'comment', value: node.nodeValue || ''}
}

/**
 * Transform an element.
 *
 * @param {Element} node
 *   DOM node to transform.
 * @param {Options} options
 *   Configuration.
 * @returns {HastElement}
 *   Equivalent hast node.
 */
function D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_element(node, options) {
  const space = node.namespaceURI
  const x = space === webNamespaces.svg ? s : h
  const tagName =
    space === webNamespaces.html ? node.tagName.toLowerCase() : node.tagName
  /** @type {DocumentFragment | Element} */
  const content =
    // @ts-expect-error: DOM types are wrong, content can exist.
    space === webNamespaces.html && tagName === 'template' ? node.content : node
  const attributes = node.getAttributeNames()
  /** @type {Record<string, string>} */
  const properties = {}
  let index = -1

  while (++index < attributes.length) {
    properties[attributes[index]] = node.getAttribute(attributes[index]) || ''
  }

  return x(tagName, properties, D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_all(content, options))
}

/**
 * Transform child nodes in a parent.
 *
 * @param {Document | DocumentFragment | Element} node
 *   DOM node to transform.
 * @param {Options} options
 *   Configuration.
 * @returns {Array<HastRootContent>}
 *   Equivalent hast nodes.
 */
function D_deeptutor_web_node_modules_hast_util_from_dom_lib_index_all(node, options) {
  const nodes = node.childNodes
  /** @type {Array<HastRootContent>} */
  const children = []
  let index = -1

  while (++index < nodes.length) {
    const child = transform(nodes[index], options)

    if (child !== undefined) {
      // @ts-expect-error Assume no document inside document.
      children.push(child)
    }
  }

  return children
}

;// D:\deeptutor\web\node_modules\hast-util-from-html-isomorphic\lib\browser.js
/**
 * @typedef {import('hast').Root} Root
 *
 * @typedef {typeof import('./index.js').fromHtmlIsomorphic} FromHtmlIsomorphic
 */



const parser = new DOMParser()

/** @type {FromHtmlIsomorphic} */
function fromHtmlIsomorphic(value, options) {
  const node = options?.fragment
    ? parseFragment(value)
    : parser.parseFromString(value, 'text/html')

  return /** @type {Root} */ (fromDom(node))
}

/**
 * Parse as a fragment.
 *
 * @param {string} value
 * @returns {DocumentFragment}
 */
function parseFragment(value) {
  const template = document.createElement('template')
  template.innerHTML = value
  return template.content
}

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\unist-util-is\lib\index.js
var D_deeptutor_web_node_modules_unist_util_is_lib_index = __webpack_require__(8197);
;// D:\deeptutor\web\node_modules\unist-util-find-after\lib\index.js
/**
 * @typedef {import('unist').Node} UnistNode
 * @typedef {import('unist').Parent} UnistParent
 */

/**
 * @typedef {Exclude<import('unist-util-is').Test, undefined> | undefined} Test
 *   Test from `unist-util-is`.
 *
 *   Note: we have remove and add `undefined`, because otherwise when generating
 *   automatic `.d.ts` files, TS tries to flatten paths from a local perspective,
 *   which doesn’t work when publishing on npm.
 */

/**
 * @typedef {(
 *   Fn extends (value: any) => value is infer Thing
 *   ? Thing
 *   : Fallback
 * )} Predicate
 *   Get the value of a type guard `Fn`.
 * @template Fn
 *   Value; typically function that is a type guard (such as `(x): x is Y`).
 * @template Fallback
 *   Value to yield if `Fn` is not a type guard.
 */

/**
 * @typedef {(
 *   Check extends null | undefined // No test.
 *   ? Value
 *   : Value extends {type: Check} // String (type) test.
 *   ? Value
 *   : Value extends Check // Partial test.
 *   ? Value
 *   : Check extends Function // Function test.
 *   ? Predicate<Check, Value> extends Value
 *     ? Predicate<Check, Value>
 *     : never
 *   : never // Some other test?
 * )} MatchesOne
 *   Check whether a node matches a primitive check in the type system.
 * @template Value
 *   Value; typically unist `Node`.
 * @template Check
 *   Value; typically `unist-util-is`-compatible test, but not arrays.
 */

/**
 * @typedef {(
 *   Check extends Array<any>
 *   ? MatchesOne<Value, Check[keyof Check]>
 *   : MatchesOne<Value, Check>
 * )} Matches
 *   Check whether a node matches a check in the type system.
 * @template Value
 *   Value; typically unist `Node`.
 * @template Check
 *   Value; typically `unist-util-is`-compatible test.
 */

/**
 * @typedef {(
 *   Kind extends {children: Array<infer Child>}
 *   ? Child
 *   : never
 * )} Child
 *   Collect nodes that can be parents of `Child`.
 * @template {UnistNode} Kind
 *   All node types.
 */



/**
 * Find the first node in `parent` after another `node` or after an index,
 * that passes `test`.
 *
 * @param parent
 *   Parent node.
 * @param index
 *   Child node or index.
 * @param [test=undefined]
 *   Test for child to look for (optional).
 * @returns
 *   A child (matching `test`, if given) or `undefined`.
 */
const findAfter =
  // Note: overloads like this are needed to support optional generics.
  /**
   * @type {(
   *   (<Kind extends UnistParent, Check extends Test>(parent: Kind, index: Child<Kind> | number, test: Check) => Matches<Child<Kind>, Check> | undefined) &
   *   (<Kind extends UnistParent>(parent: Kind, index: Child<Kind> | number, test?: null | undefined) => Child<Kind> | undefined)
   * )}
   */
  (
    /**
     * @param {UnistParent} parent
     * @param {UnistNode | number} index
     * @param {Test} [test]
     * @returns {UnistNode | undefined}
     */
    function (parent, index, test) {
      const is = (0,D_deeptutor_web_node_modules_unist_util_is_lib_index/* convert */.C)(test)

      if (!parent || !parent.type || !parent.children) {
        throw new Error('Expected parent node')
      }

      if (typeof index === 'number') {
        if (index < 0 || index === Number.POSITIVE_INFINITY) {
          throw new Error('Expected positive finite number as index')
        }
      } else {
        index = parent.children.indexOf(index)

        if (index < 0) {
          throw new Error('Expected child node or index')
        }
      }

      while (++index < parent.children.length) {
        if (is(parent.children[index], index, parent)) {
          return parent.children[index]
        }
      }

      return undefined
    }
  )

;// D:\deeptutor\web\node_modules\hast-util-is-element\lib\index.js
/**
 * @typedef {import('hast').Element} Element
 * @typedef {import('hast').Parents} Parents
 */

/**
 * @template Fn
 * @template Fallback
 * @typedef {Fn extends (value: any) => value is infer Thing ? Thing : Fallback} Predicate
 */

/**
 * @callback Check
 *   Check that an arbitrary value is an element.
 * @param {unknown} this
 *   Context object (`this`) to call `test` with
 * @param {unknown} [element]
 *   Anything (typically a node).
 * @param {number | null | undefined} [index]
 *   Position of `element` in its parent.
 * @param {Parents | null | undefined} [parent]
 *   Parent of `element`.
 * @returns {boolean}
 *   Whether this is an element and passes a test.
 *
 * @typedef {Array<TestFunction | string> | TestFunction | string | null | undefined} Test
 *   Check for an arbitrary element.
 *
 *   * when `string`, checks that the element has that tag name
 *   * when `function`, see `TestFunction`
 *   * when `Array`, checks if one of the subtests pass
 *
 * @callback TestFunction
 *   Check if an element passes a test.
 * @param {unknown} this
 *   The given context.
 * @param {Element} element
 *   An element.
 * @param {number | undefined} [index]
 *   Position of `element` in its parent.
 * @param {Parents | undefined} [parent]
 *   Parent of `element`.
 * @returns {boolean | undefined | void}
 *   Whether this element passes the test.
 *
 *   Note: `void` is included until TS sees no return as `undefined`.
 */

/**
 * Check if `element` is an `Element` and whether it passes the given test.
 *
 * @param element
 *   Thing to check, typically `element`.
 * @param test
 *   Check for a specific element.
 * @param index
 *   Position of `element` in its parent.
 * @param parent
 *   Parent of `element`.
 * @param context
 *   Context object (`this`) to call `test` with.
 * @returns
 *   Whether `element` is an `Element` and passes a test.
 * @throws
 *   When an incorrect `test`, `index`, or `parent` is given; there is no error
 *   thrown when `element` is not a node or not an element.
 */
const isElement =
  // Note: overloads in JSDoc can’t yet use different `@template`s.
  /**
   * @type {(
   *   (<Condition extends TestFunction>(element: unknown, test: Condition, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element & Predicate<Condition, Element>) &
   *   (<Condition extends string>(element: unknown, test: Condition, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element & {tagName: Condition}) &
   *   ((element?: null | undefined) => false) &
   *   ((element: unknown, test?: null | undefined, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element) &
   *   ((element: unknown, test?: Test, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => boolean)
   * )}
   */
  (
    /**
     * @param {unknown} [element]
     * @param {Test | undefined} [test]
     * @param {number | null | undefined} [index]
     * @param {Parents | null | undefined} [parent]
     * @param {unknown} [context]
     * @returns {boolean}
     */
    // eslint-disable-next-line max-params
    function (element, test, index, parent, context) {
      const check = convertElement(test)

      if (
        index !== null &&
        index !== undefined &&
        (typeof index !== 'number' ||
          index < 0 ||
          index === Number.POSITIVE_INFINITY)
      ) {
        throw new Error('Expected positive finite `index`')
      }

      if (
        parent !== null &&
        parent !== undefined &&
        (!parent.type || !parent.children)
      ) {
        throw new Error('Expected valid `parent`')
      }

      if (
        (index === null || index === undefined) !==
        (parent === null || parent === undefined)
      ) {
        throw new Error('Expected both `index` and `parent`')
      }

      return looksLikeAnElement(element)
        ? check.call(context, element, index, parent)
        : false
    }
  )

/**
 * Generate a check from a test.
 *
 * Useful if you’re going to test many nodes, for example when creating a
 * utility where something else passes a compatible test.
 *
 * The created function is a bit faster because it expects valid input only:
 * an `element`, `index`, and `parent`.
 *
 * @param test
 *   A test for a specific element.
 * @returns
 *   A check.
 */
const convertElement =
  // Note: overloads in JSDoc can’t yet use different `@template`s.
  /**
   * @type {(
   *   (<Condition extends TestFunction>(test: Condition) => (element: unknown, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element & Predicate<Condition, Element>) &
   *   (<Condition extends string>(test: Condition) => (element: unknown, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element & {tagName: Condition}) &
   *   ((test?: null | undefined) => (element?: unknown, index?: number | null | undefined, parent?: Parents | null | undefined, context?: unknown) => element is Element) &
   *   ((test?: Test) => Check)
   * )}
   */
  (
    /**
     * @param {Test | null | undefined} [test]
     * @returns {Check}
     */
    function (test) {
      if (test === null || test === undefined) {
        return D_deeptutor_web_node_modules_hast_util_is_element_lib_index_element
      }

      if (typeof test === 'string') {
        return tagNameFactory(test)
      }

      // Assume array.
      if (typeof test === 'object') {
        return anyFactory(test)
      }

      if (typeof test === 'function') {
        return castFactory(test)
      }

      throw new Error('Expected function, string, or array as `test`')
    }
  )

/**
 * Handle multiple tests.
 *
 * @param {Array<TestFunction | string>} tests
 * @returns {Check}
 */
function anyFactory(tests) {
  /** @type {Array<Check>} */
  const checks = []
  let index = -1

  while (++index < tests.length) {
    checks[index] = convertElement(tests[index])
  }

  return castFactory(any)

  /**
   * @this {unknown}
   * @type {TestFunction}
   */
  function any(...parameters) {
    let index = -1

    while (++index < checks.length) {
      if (checks[index].apply(this, parameters)) return true
    }

    return false
  }
}

/**
 * Turn a string into a test for an element with a certain type.
 *
 * @param {string} check
 * @returns {Check}
 */
function tagNameFactory(check) {
  return castFactory(tagName)

  /**
   * @param {Element} element
   * @returns {boolean}
   */
  function tagName(element) {
    return element.tagName === check
  }
}

/**
 * Turn a custom test into a test for an element that passes that test.
 *
 * @param {TestFunction} testFunction
 * @returns {Check}
 */
function castFactory(testFunction) {
  return check

  /**
   * @this {unknown}
   * @type {Check}
   */
  function check(value, index, parent) {
    return Boolean(
      looksLikeAnElement(value) &&
        testFunction.call(
          this,
          value,
          typeof index === 'number' ? index : undefined,
          parent || undefined
        )
    )
  }
}

/**
 * Make sure something is an element.
 *
 * @param {unknown} element
 * @returns {element is Element}
 */
function D_deeptutor_web_node_modules_hast_util_is_element_lib_index_element(element) {
  return Boolean(
    element &&
      typeof element === 'object' &&
      'type' in element &&
      element.type === 'element' &&
      'tagName' in element &&
      typeof element.tagName === 'string'
  )
}

/**
 * @param {unknown} value
 * @returns {value is Element}
 */
function looksLikeAnElement(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    'type' in value &&
    'tagName' in value
  )
}

;// D:\deeptutor\web\node_modules\hast-util-to-text\lib\index.js
/**
 * @typedef {import('hast').Comment} Comment
 * @typedef {import('hast').Element} Element
 * @typedef {import('hast').Nodes} Nodes
 * @typedef {import('hast').Parents} Parents
 * @typedef {import('hast').Text} Text
 * @typedef {import('hast-util-is-element').TestFunction} TestFunction
 */

/**
 * @typedef {'normal' | 'nowrap' | 'pre' | 'pre-wrap'} Whitespace
 *   Valid and useful whitespace values (from CSS).
 *
 * @typedef {0 | 1 | 2} BreakNumber
 *   Specific break:
 *
 *   *   `0` — space
 *   *   `1` — line ending
 *   *   `2` — blank line
 *
 * @typedef {'\n'} BreakForce
 *   Forced break.
 *
 * @typedef {boolean} BreakValue
 *   Whether there was a break.
 *
 * @typedef {BreakNumber | BreakValue | undefined} BreakBefore
 *   Any value for a break before.
 *
 * @typedef {BreakForce | BreakNumber | BreakValue | undefined} BreakAfter
 *   Any value for a break after.
 *
 * @typedef CollectionInfo
 *   Info on current collection.
 * @property {BreakAfter} breakAfter
 *   Whether there was a break after.
 * @property {BreakBefore} breakBefore
 *   Whether there was a break before.
 * @property {Whitespace} whitespace
 *   Current whitespace setting.
 *
 * @typedef Options
 *   Configuration.
 * @property {Whitespace | null | undefined} [whitespace='normal']
 *   Initial CSS whitespace setting to use (default: `'normal'`).
 */




const searchLineFeeds = /\n/g
const searchTabOrSpaces = /[\t ]+/g

const br = convertElement('br')
const cell = convertElement(isCell)
const p = convertElement('p')
const row = convertElement('tr')

// Note that we don’t need to include void elements here as they don’t have text.
// See: <https://github.com/wooorm/html-void-elements>
const notRendered = convertElement([
  // List from: <https://html.spec.whatwg.org/multipage/rendering.html#hidden-elements>
  'datalist',
  'head',
  'noembed',
  'noframes',
  'noscript', // Act as if we support scripting.
  'rp',
  'script',
  'style',
  'template',
  'title',
  // Hidden attribute.
  D_deeptutor_web_node_modules_hast_util_to_text_lib_index_hidden,
  // From: <https://html.spec.whatwg.org/multipage/rendering.html#flow-content-3>
  closedDialog
])

// See: <https://html.spec.whatwg.org/multipage/rendering.html#the-css-user-agent-style-sheet-and-presentational-hints>
const blockOrCaption = convertElement([
  'address', // Flow content
  'article', // Sections and headings
  'aside', // Sections and headings
  'blockquote', // Flow content
  'body', // Page
  'caption', // `table-caption`
  'center', // Flow content (legacy)
  'dd', // Lists
  'dialog', // Flow content
  'dir', // Lists (legacy)
  'dl', // Lists
  'dt', // Lists
  'div', // Flow content
  'figure', // Flow content
  'figcaption', // Flow content
  'footer', // Flow content
  'form,', // Flow content
  'h1', // Sections and headings
  'h2', // Sections and headings
  'h3', // Sections and headings
  'h4', // Sections and headings
  'h5', // Sections and headings
  'h6', // Sections and headings
  'header', // Flow content
  'hgroup', // Sections and headings
  'hr', // Flow content
  'html', // Page
  'legend', // Flow content
  'li', // Lists (as `display: list-item`)
  'listing', // Flow content (legacy)
  'main', // Flow content
  'menu', // Lists
  'nav', // Sections and headings
  'ol', // Lists
  'p', // Flow content
  'plaintext', // Flow content (legacy)
  'pre', // Flow content
  'section', // Sections and headings
  'ul', // Lists
  'xmp' // Flow content (legacy)
])

/**
 * Get the plain-text value of a node.
 *
 * ###### Algorithm
 *
 * *   if `tree` is a comment, returns its `value`
 * *   if `tree` is a text, applies normal whitespace collapsing to its
 *     `value`, as defined by the CSS Text spec
 * *   if `tree` is a root or element, applies an algorithm similar to the
 *     `innerText` getter as defined by HTML
 *
 * ###### Notes
 *
 * > 👉 **Note**: the algorithm acts as if `tree` is being rendered, and as if
 * > we’re a CSS-supporting user agent, with scripting enabled.
 *
 * *   if `tree` is an element that is not displayed (such as a `head`), we’ll
 *     still use the `innerText` algorithm instead of switching to `textContent`
 * *   if descendants of `tree` are elements that are not displayed, they are
 *     ignored
 * *   CSS is not considered, except for the default user agent style sheet
 * *   a line feed is collapsed instead of ignored in cases where Fullwidth, Wide,
 *     or Halfwidth East Asian Width characters are used, the same goes for a case
 *     with Chinese, Japanese, or Yi writing systems
 * *   replaced elements (such as `audio`) are treated like non-replaced elements
 *
 * @param {Nodes} tree
 *   Tree to turn into text.
 * @param {Readonly<Options> | null | undefined} [options]
 *   Configuration (optional).
 * @returns {string}
 *   Serialized `tree`.
 */
function toText(tree, options) {
  const options_ = options || {}
  const children = 'children' in tree ? tree.children : []
  const block = blockOrCaption(tree)
  const whitespace = inferWhitespace(tree, {
    whitespace: options_.whitespace || 'normal',
    breakBefore: false,
    breakAfter: false
  })

  /** @type {Array<BreakNumber | string>} */
  const results = []

  // Treat `text` and `comment` as having normal white-space.
  // This deviates from the spec as in the DOM the node’s `.data` has to be
  // returned.
  // If you want that behavior use `hast-util-to-string`.
  // All other nodes are later handled as if they are `element`s (so the
  // algorithm also works on a `root`).
  // Nodes without children are treated as a void element, so `doctype` is thus
  // ignored.
  if (tree.type === 'text' || tree.type === 'comment') {
    results.push(
      ...collectText(tree, {
        whitespace,
        breakBefore: true,
        breakAfter: true
      })
    )
  }

  // 1.  If this element is not being rendered, or if the user agent is a
  //     non-CSS user agent, then return the same value as the textContent IDL
  //     attribute on this element.
  //
  //     Note: we’re not supporting stylesheets so we’re acting as if the node
  //     is rendered.
  //
  //     If you want that behavior use `hast-util-to-string`.
  //     Important: we’ll have to account for this later though.

  // 2.  Let results be a new empty list.
  let index = -1

  // 3.  For each child node node of this element:
  while (++index < children.length) {
    // 3.1. Let current be the list resulting in running the inner text
    //      collection steps with node.
    //      Each item in results will either be a JavaScript string or a
    //      positive integer (a required line break count).
    // 3.2. For each item item in current, append item to results.
    results.push(
      ...renderedTextCollection(
        children[index],
        // @ts-expect-error: `tree` is a parent if we’re here.
        tree,
        {
          whitespace,
          breakBefore: index ? undefined : block,
          breakAfter:
            index < children.length - 1 ? br(children[index + 1]) : block
        }
      )
    )
  }

  // 4.  Remove any items from results that are the empty string.
  // 5.  Remove any runs of consecutive required line break count items at the
  //     start or end of results.
  // 6.  Replace each remaining run of consecutive required line break count
  //     items with a string consisting of as many U+000A LINE FEED (LF)
  //     characters as the maximum of the values in the required line break
  //     count items.
  /** @type {Array<string>} */
  const result = []
  /** @type {number | undefined} */
  let count

  index = -1

  while (++index < results.length) {
    const value = results[index]

    if (typeof value === 'number') {
      if (count !== undefined && value > count) count = value
    } else if (value) {
      if (count !== undefined && count > -1) {
        result.push('\n'.repeat(count) || ' ')
      }

      count = -1
      result.push(value)
    }
  }

  // 7.  Return the concatenation of the string items in results.
  return result.join('')
}

/**
 * <https://html.spec.whatwg.org/multipage/dom.html#rendered-text-collection-steps>
 *
 * @param {Nodes} node
 * @param {Parents} parent
 * @param {CollectionInfo} info
 * @returns {Array<BreakNumber | string>}
 */
function renderedTextCollection(node, parent, info) {
  if (node.type === 'element') {
    return collectElement(node, parent, info)
  }

  if (node.type === 'text') {
    return info.whitespace === 'normal'
      ? collectText(node, info)
      : collectPreText(node)
  }

  return []
}

/**
 * Collect an element.
 *
 * @param {Element} node
 *   Element node.
 * @param {Parents} parent
 * @param {CollectionInfo} info
 *   Info on current collection.
 * @returns {Array<BreakNumber | string>}
 */
function collectElement(node, parent, info) {
  // First we infer the `white-space` property.
  const whitespace = inferWhitespace(node, info)
  const children = node.children || []
  let index = -1
  /** @type {Array<BreakNumber | string>} */
  let items = []

  // We’re ignoring point 3, and exiting without any content here, because we
  // deviated from the spec in `toText` at step 3.
  if (notRendered(node)) {
    return items
  }

  /** @type {BreakNumber | undefined} */
  let prefix
  /** @type {BreakForce | BreakNumber | undefined} */
  let suffix
  // Note: we first detect if there is going to be a break before or after the
  // contents, as that changes the white-space handling.

  // 2.  If node’s computed value of `visibility` is not `visible`, then return
  //     items.
  //
  //     Note: Ignored, as everything is visible by default user agent styles.

  // 3.  If node is not being rendered, then return items. [...]
  //
  //     Note: We already did this above.

  // See `collectText` for step 4.

  // 5.  If node is a `<br>` element, then append a string containing a single
  //     U+000A LINE FEED (LF) character to items.
  if (br(node)) {
    suffix = '\n'
  }

  // 7.  If node’s computed value of `display` is `table-row`, and node’s CSS
  //     box is not the last `table-row` box of the nearest ancestor `table`
  //     box, then append a string containing a single U+000A LINE FEED (LF)
  //     character to items.
  //
  //     See: <https://html.spec.whatwg.org/multipage/rendering.html#tables-2>
  //     Note: needs further investigation as this does not account for implicit
  //     rows.
  else if (
    row(node) &&
    // @ts-expect-error: something up with types of parents.
    findAfter(parent, node, row)
  ) {
    suffix = '\n'
  }

  // 8.  If node is a `<p>` element, then append 2 (a required line break count)
  //     at the beginning and end of items.
  else if (p(node)) {
    prefix = 2
    suffix = 2
  }

  // 9.  If node’s used value of `display` is block-level or `table-caption`,
  //     then append 1 (a required line break count) at the beginning and end of
  //     items.
  else if (blockOrCaption(node)) {
    prefix = 1
    suffix = 1
  }

  // 1.  Let items be the result of running the inner text collection steps with
  //     each child node of node in tree order, and then concatenating the
  //     results to a single list.
  while (++index < children.length) {
    items = items.concat(
      renderedTextCollection(children[index], node, {
        whitespace,
        breakBefore: index ? undefined : prefix,
        breakAfter:
          index < children.length - 1 ? br(children[index + 1]) : suffix
      })
    )
  }

  // 6.  If node’s computed value of `display` is `table-cell`, and node’s CSS
  //     box is not the last `table-cell` box of its enclosing `table-row` box,
  //     then append a string containing a single U+0009 CHARACTER TABULATION
  //     (tab) character to items.
  //
  //     See: <https://html.spec.whatwg.org/multipage/rendering.html#tables-2>
  if (
    cell(node) &&
    // @ts-expect-error: something up with types of parents.
    findAfter(parent, node, cell)
  ) {
    items.push('\t')
  }

  // Add the pre- and suffix.
  if (prefix) items.unshift(prefix)
  if (suffix) items.push(suffix)

  return items
}

/**
 * 4.  If node is a Text node, then for each CSS text box produced by node,
 *     in content order, compute the text of the box after application of the
 *     CSS `white-space` processing rules and `text-transform` rules, set
 *     items to the list of the resulting strings, and return items.
 *     The CSS `white-space` processing rules are slightly modified:
 *     collapsible spaces at the end of lines are always collapsed, but they
 *     are only removed if the line is the last line of the block, or it ends
 *     with a br element.
 *     Soft hyphens should be preserved.
 *
 *     Note: See `collectText` and `collectPreText`.
 *     Note: we don’t deal with `text-transform`, no element has that by
 *     default.
 *
 * See: <https://drafts.csswg.org/css-text/#white-space-phase-1>
 *
 * @param {Comment | Text} node
 *   Text node.
 * @param {CollectionInfo} info
 *   Info on current collection.
 * @returns {Array<BreakNumber | string>}
 *   Result.
 */
function collectText(node, info) {
  const value = String(node.value)
  /** @type {Array<string>} */
  const lines = []
  /** @type {Array<BreakNumber | string>} */
  const result = []
  let start = 0

  while (start <= value.length) {
    searchLineFeeds.lastIndex = start

    const match = searchLineFeeds.exec(value)
    const end = match && 'index' in match ? match.index : value.length

    lines.push(
      // Any sequence of collapsible spaces and tabs immediately preceding or
      // following a segment break is removed.
      trimAndCollapseSpacesAndTabs(
        // […] ignoring bidi formatting characters (characters with the
        // Bidi_Control property [UAX9]: ALM, LTR, RTL, LRE-RLO, LRI-PDI) as if
        // they were not there.
        value
          .slice(start, end)
          .replace(/[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, ''),
        start === 0 ? info.breakBefore : true,
        end === value.length ? info.breakAfter : true
      )
    )

    start = end + 1
  }

  // Collapsible segment breaks are transformed for rendering according to the
  // segment break transformation rules.
  // So here we jump to 4.1.2 of [CSSTEXT]:
  // Any collapsible segment break immediately following another collapsible
  // segment break is removed
  let index = -1
  /** @type {BreakNumber | undefined} */
  let join

  while (++index < lines.length) {
    // *   If the character immediately before or immediately after the segment
    //     break is the zero-width space character (U+200B), then the break is
    //     removed, leaving behind the zero-width space.
    if (
      lines[index].charCodeAt(lines[index].length - 1) === 0x20_0b /* ZWSP */ ||
      (index < lines.length - 1 &&
        lines[index + 1].charCodeAt(0) === 0x20_0b) /* ZWSP */
    ) {
      result.push(lines[index])
      join = undefined
    }

    // *   Otherwise, if the East Asian Width property [UAX11] of both the
    //     character before and after the segment break is Fullwidth, Wide, or
    //     Halfwidth (not Ambiguous), and neither side is Hangul, then the
    //     segment break is removed.
    //
    //     Note: ignored.
    // *   Otherwise, if the writing system of the segment break is Chinese,
    //     Japanese, or Yi, and the character before or after the segment break
    //     is punctuation or a symbol (Unicode general category P* or S*) and
    //     has an East Asian Width property of Ambiguous, and the character on
    //     the other side of the segment break is Fullwidth, Wide, or Halfwidth,
    //     and not Hangul, then the segment break is removed.
    //
    //     Note: ignored.

    // *   Otherwise, the segment break is converted to a space (U+0020).
    else if (lines[index]) {
      if (typeof join === 'number') result.push(join)
      result.push(lines[index])
      join = 0
    } else if (index === 0 || index === lines.length - 1) {
      // If this line is empty, and it’s the first or last, add a space.
      // Note that this function is only called in normal whitespace, so we
      // don’t worry about `pre`.
      result.push(0)
    }
  }

  return result
}

/**
 * Collect a text node as “pre” whitespace.
 *
 * @param {Text} node
 *   Text node.
 * @returns {Array<BreakNumber | string>}
 *   Result.
 */
function collectPreText(node) {
  return [String(node.value)]
}

/**
 * 3.  Every collapsible tab is converted to a collapsible space (U+0020).
 * 4.  Any collapsible space immediately following another collapsible
 *     space—even one outside the boundary of the inline containing that
 *     space, provided both spaces are within the same inline formatting
 *     context—is collapsed to have zero advance width. (It is invisible,
 *     but retains its soft wrap opportunity, if any.)
 *
 * @param {string} value
 *   Value to collapse.
 * @param {BreakBefore} breakBefore
 *   Whether there was a break before.
 * @param {BreakAfter} breakAfter
 *   Whether there was a break after.
 * @returns {string}
 *   Result.
 */
function trimAndCollapseSpacesAndTabs(value, breakBefore, breakAfter) {
  /** @type {Array<string>} */
  const result = []
  let start = 0
  /** @type {number | undefined} */
  let end

  while (start < value.length) {
    searchTabOrSpaces.lastIndex = start
    const match = searchTabOrSpaces.exec(value)
    end = match ? match.index : value.length

    // If we’re not directly after a segment break, but there was white space,
    // add an empty value that will be turned into a space.
    if (!start && !end && match && !breakBefore) {
      result.push('')
    }

    if (start !== end) {
      result.push(value.slice(start, end))
    }

    start = match ? end + match[0].length : end
  }

  // If we reached the end, there was trailing white space, and there’s no
  // segment break after this node, add an empty value that will be turned
  // into a space.
  if (start !== end && !breakAfter) {
    result.push('')
  }

  return result.join(' ')
}

/**
 * Figure out the whitespace of a node.
 *
 * We don’t support void elements here (so `nobr wbr` -> `normal` is ignored).
 *
 * @param {Nodes} node
 *   Node (typically `Element`).
 * @param {CollectionInfo} info
 *   Info on current collection.
 * @returns {Whitespace}
 *   Applied whitespace.
 */
function inferWhitespace(node, info) {
  if (node.type === 'element') {
    const properties = node.properties || {}
    switch (node.tagName) {
      case 'listing':
      case 'plaintext':
      case 'xmp': {
        return 'pre'
      }

      case 'nobr': {
        return 'nowrap'
      }

      case 'pre': {
        return properties.wrap ? 'pre-wrap' : 'pre'
      }

      case 'td':
      case 'th': {
        return properties.noWrap ? 'nowrap' : info.whitespace
      }

      case 'textarea': {
        return 'pre-wrap'
      }

      default:
    }
  }

  return info.whitespace
}

/**
 * @type {TestFunction}
 * @param {Element} node
 * @returns {node is {properties: {hidden: true}}}
 */
function D_deeptutor_web_node_modules_hast_util_to_text_lib_index_hidden(node) {
  return Boolean((node.properties || {}).hidden)
}

/**
 * @type {TestFunction}
 * @param {Element} node
 * @returns {node is {tagName: 'td' | 'th'}}
 */
function isCell(node) {
  return node.tagName === 'td' || node.tagName === 'th'
}

/**
 * @type {TestFunction}
 */
function closedDialog(node) {
  return node.tagName === 'dialog' && !(node.properties || {}).open
}

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\katex\dist\katex.mjs
var D_deeptutor_web_node_modules_katex_dist_katex = __webpack_require__(2210);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\unist-util-visit-parents\lib\index.js + 1 modules
var D_deeptutor_web_node_modules_unist_util_visit_parents_lib_index = __webpack_require__(2786);
;// D:\deeptutor\web\node_modules\rehype-katex\lib\index.js
/**
 * @import {ElementContent, Root} from 'hast'
 * @import {KatexOptions} from 'katex'
 * @import {VFile} from 'vfile'
 */

/**
 * @typedef {Omit<KatexOptions, 'displayMode' | 'throwOnError'>} Options
 */






/** @type {Readonly<Options>} */
const emptyOptions = {}
/** @type {ReadonlyArray<unknown>} */
const emptyClasses = []

/**
 * Render elements with a `language-math` (or `math-display`, `math-inline`)
 * class with KaTeX.
 *
 * @param {Readonly<Options> | null | undefined} [options]
 *   Configuration (optional).
 * @returns
 *   Transform.
 */
function rehypeKatex(options) {
  const settings = options || emptyOptions

  /**
   * Transform.
   *
   * @param {Root} tree
   *   Tree.
   * @param {VFile} file
   *   File.
   * @returns {undefined}
   *   Nothing.
   */
  return function (tree, file) {
    ;(0,D_deeptutor_web_node_modules_unist_util_visit_parents_lib_index/* visitParents */.VG)(tree, 'element', function (element, parents) {
      const classes = Array.isArray(element.properties.className)
        ? element.properties.className
        : emptyClasses
      // This class can be generated from markdown with ` ```math `.
      const languageMath = classes.includes('language-math')
      // This class is used by `remark-math` for flow math (block, `$$\nmath\n$$`).
      const mathDisplay = classes.includes('math-display')
      // This class is used by `remark-math` for text math (inline, `$math$`).
      const mathInline = classes.includes('math-inline')
      let displayMode = mathDisplay

      // Any class is fine.
      if (!languageMath && !mathDisplay && !mathInline) {
        return
      }

      let parent = parents[parents.length - 1]
      let scope = element

      // If this was generated with ` ```math `, replace the `<pre>` and use
      // display.
      if (
        element.tagName === 'code' &&
        languageMath &&
        parent &&
        parent.type === 'element' &&
        parent.tagName === 'pre'
      ) {
        scope = parent
        parent = parents[parents.length - 2]
        displayMode = true
      }

      /* c8 ignore next -- verbose to test. */
      if (!parent) return

      const value = toText(scope, {whitespace: 'pre'})

      /** @type {Array<ElementContent> | string | undefined} */
      let result

      try {
        result = D_deeptutor_web_node_modules_katex_dist_katex["default"].renderToString(value, {
          ...settings,
          displayMode,
          throwOnError: true
        })
      } catch (error) {
        const cause = /** @type {Error} */ (error)
        const ruleId = cause.name.toLowerCase()

        file.message('Could not render math with KaTeX', {
          ancestors: [...parents, element],
          cause,
          place: element.position,
          ruleId,
          source: 'rehype-katex'
        })

        // KaTeX *should* handle `ParseError` itself, but not others.
        // it doesn’t always:
        // <https://github.com/remarkjs/react-markdown/issues/853>
        try {
          result = D_deeptutor_web_node_modules_katex_dist_katex["default"].renderToString(value, {
            ...settings,
            displayMode,
            strict: 'ignore',
            throwOnError: false
          })
        } catch {
          // Generate similar markup if this is an other error.
          // See: <https://github.com/KaTeX/KaTeX/blob/5dc7af0/docs/error.md>.
          result = [
            {
              type: 'element',
              tagName: 'span',
              properties: {
                className: ['katex-error'],
                style: 'color:' + (settings.errorColor || '#cc0000'),
                title: String(error)
              },
              children: [{type: 'text', value}]
            }
          ]
        }
      }

      if (typeof result === 'string') {
        const root = fromHtmlIsomorphic(result, {fragment: true})
        // Cast as we don’t expect `doctypes` in KaTeX result.
        result = /** @type {Array<ElementContent>} */ (root.children)
      }

      const index = parent.children.indexOf(scope)
      parent.children.splice(index, 1, ...result)
      return D_deeptutor_web_node_modules_unist_util_visit_parents_lib_index/* SKIP */._Z
    })
  }
}

;// D:\deeptutor\web\node_modules\rehype-katex\index.js
/**
 * @typedef {import('./lib/index.js').Options} Options
 */




/***/ })

}]);