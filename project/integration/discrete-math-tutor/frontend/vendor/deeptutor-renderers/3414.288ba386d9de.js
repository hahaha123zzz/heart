"use strict";
(self["webpackChunk"] = self["webpackChunk"] || []).push([[3414],{

/***/ 751:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {


// EXPORTS
__webpack_require__.d(__webpack_exports__, {
  A: () => (/* binding */ D_deeptutor_web_node_modules_lodash_es_values)
});

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_arrayMap.js
var D_deeptutor_web_node_modules_lodash_es_arrayMap = __webpack_require__(9377);
;// D:\deeptutor\web\node_modules\lodash-es\_baseValues.js


/**
 * The base implementation of `_.values` and `_.valuesIn` which creates an
 * array of `object` property values corresponding to the property names
 * of `props`.
 *
 * @private
 * @param {Object} object The object to query.
 * @param {Array} props The property names to get values for.
 * @returns {Object} Returns the array of property values.
 */
function baseValues(object, props) {
  return (0,D_deeptutor_web_node_modules_lodash_es_arrayMap/* default */.A)(props, function(key) {
    return object[key];
  });
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseValues = (baseValues);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\keys.js
var D_deeptutor_web_node_modules_lodash_es_keys = __webpack_require__(6205);
;// D:\deeptutor\web\node_modules\lodash-es\values.js



/**
 * Creates an array of the own enumerable string keyed property values of `object`.
 *
 * **Note:** Non-object values are coerced to objects.
 *
 * @static
 * @since 0.1.0
 * @memberOf _
 * @category Object
 * @param {Object} object The object to query.
 * @returns {Array} Returns the array of property values.
 * @example
 *
 * function Foo() {
 *   this.a = 1;
 *   this.b = 2;
 * }
 *
 * Foo.prototype.c = 3;
 *
 * _.values(new Foo);
 * // => [1, 2] (iteration order is not guaranteed)
 *
 * _.values('hi');
 * // => ['h', 'i']
 */
function values(object) {
  return object == null ? [] : D_deeptutor_web_node_modules_lodash_es_baseValues(object, (0,D_deeptutor_web_node_modules_lodash_es_keys/* default */.A)(object));
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_values = (values);


/***/ }),

/***/ 2851:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {


// EXPORTS
__webpack_require__.d(__webpack_exports__, {
  A: () => (/* binding */ D_deeptutor_web_node_modules_lodash_es_baseClone)
});

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_Stack.js + 5 modules
var D_deeptutor_web_node_modules_lodash_es_Stack = __webpack_require__(8929);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_arrayEach.js
var D_deeptutor_web_node_modules_lodash_es_arrayEach = __webpack_require__(6714);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_assignValue.js
var D_deeptutor_web_node_modules_lodash_es_assignValue = __webpack_require__(7616);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_copyObject.js
var D_deeptutor_web_node_modules_lodash_es_copyObject = __webpack_require__(9578);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\keys.js
var D_deeptutor_web_node_modules_lodash_es_keys = __webpack_require__(6205);
;// D:\deeptutor\web\node_modules\lodash-es\_baseAssign.js



/**
 * The base implementation of `_.assign` without support for multiple sources
 * or `customizer` functions.
 *
 * @private
 * @param {Object} object The destination object.
 * @param {Object} source The source object.
 * @returns {Object} Returns `object`.
 */
function baseAssign(object, source) {
  return object && (0,D_deeptutor_web_node_modules_lodash_es_copyObject/* default */.A)(source, (0,D_deeptutor_web_node_modules_lodash_es_keys/* default */.A)(source), object);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseAssign = (baseAssign);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\keysIn.js + 2 modules
var D_deeptutor_web_node_modules_lodash_es_keysIn = __webpack_require__(2646);
;// D:\deeptutor\web\node_modules\lodash-es\_baseAssignIn.js



/**
 * The base implementation of `_.assignIn` without support for multiple sources
 * or `customizer` functions.
 *
 * @private
 * @param {Object} object The destination object.
 * @param {Object} source The source object.
 * @returns {Object} Returns `object`.
 */
function baseAssignIn(object, source) {
  return object && (0,D_deeptutor_web_node_modules_lodash_es_copyObject/* default */.A)(source, (0,D_deeptutor_web_node_modules_lodash_es_keysIn/* default */.A)(source), object);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseAssignIn = (baseAssignIn);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_cloneBuffer.js
var D_deeptutor_web_node_modules_lodash_es_cloneBuffer = __webpack_require__(5533);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_copyArray.js
var D_deeptutor_web_node_modules_lodash_es_copyArray = __webpack_require__(6688);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_getSymbols.js
var D_deeptutor_web_node_modules_lodash_es_getSymbols = __webpack_require__(2313);
;// D:\deeptutor\web\node_modules\lodash-es\_copySymbols.js



/**
 * Copies own symbols of `source` to `object`.
 *
 * @private
 * @param {Object} source The object to copy symbols from.
 * @param {Object} [object={}] The object to copy symbols to.
 * @returns {Object} Returns `object`.
 */
function copySymbols(source, object) {
  return (0,D_deeptutor_web_node_modules_lodash_es_copyObject/* default */.A)(source, (0,D_deeptutor_web_node_modules_lodash_es_getSymbols/* default */.A)(source), object);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_copySymbols = (copySymbols);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_arrayPush.js
var D_deeptutor_web_node_modules_lodash_es_arrayPush = __webpack_require__(4835);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_getPrototype.js
var D_deeptutor_web_node_modules_lodash_es_getPrototype = __webpack_require__(7242);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\stubArray.js
var D_deeptutor_web_node_modules_lodash_es_stubArray = __webpack_require__(5680);
;// D:\deeptutor\web\node_modules\lodash-es\_getSymbolsIn.js





/* Built-in method references for those with the same name as other `lodash` methods. */
var nativeGetSymbols = Object.getOwnPropertySymbols;

/**
 * Creates an array of the own and inherited enumerable symbols of `object`.
 *
 * @private
 * @param {Object} object The object to query.
 * @returns {Array} Returns the array of symbols.
 */
var getSymbolsIn = !nativeGetSymbols ? D_deeptutor_web_node_modules_lodash_es_stubArray/* default */.A : function(object) {
  var result = [];
  while (object) {
    (0,D_deeptutor_web_node_modules_lodash_es_arrayPush/* default */.A)(result, (0,D_deeptutor_web_node_modules_lodash_es_getSymbols/* default */.A)(object));
    object = (0,D_deeptutor_web_node_modules_lodash_es_getPrototype/* default */.A)(object);
  }
  return result;
};

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_getSymbolsIn = (getSymbolsIn);

;// D:\deeptutor\web\node_modules\lodash-es\_copySymbolsIn.js



/**
 * Copies own and inherited symbols of `source` to `object`.
 *
 * @private
 * @param {Object} source The object to copy symbols from.
 * @param {Object} [object={}] The object to copy symbols to.
 * @returns {Object} Returns `object`.
 */
function copySymbolsIn(source, object) {
  return (0,D_deeptutor_web_node_modules_lodash_es_copyObject/* default */.A)(source, D_deeptutor_web_node_modules_lodash_es_getSymbolsIn(source), object);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_copySymbolsIn = (copySymbolsIn);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_getAllKeys.js
var D_deeptutor_web_node_modules_lodash_es_getAllKeys = __webpack_require__(5559);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_baseGetAllKeys.js
var D_deeptutor_web_node_modules_lodash_es_baseGetAllKeys = __webpack_require__(1234);
;// D:\deeptutor\web\node_modules\lodash-es\_getAllKeysIn.js




/**
 * Creates an array of own and inherited enumerable property names and
 * symbols of `object`.
 *
 * @private
 * @param {Object} object The object to query.
 * @returns {Array} Returns the array of property names and symbols.
 */
function getAllKeysIn(object) {
  return (0,D_deeptutor_web_node_modules_lodash_es_baseGetAllKeys/* default */.A)(object, D_deeptutor_web_node_modules_lodash_es_keysIn/* default */.A, D_deeptutor_web_node_modules_lodash_es_getSymbolsIn);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_getAllKeysIn = (getAllKeysIn);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_getTag.js + 3 modules
var D_deeptutor_web_node_modules_lodash_es_getTag = __webpack_require__(9730);
;// D:\deeptutor\web\node_modules\lodash-es\_initCloneArray.js
/** Used for built-in method references. */
var objectProto = Object.prototype;

/** Used to check objects for own properties. */
var D_deeptutor_web_node_modules_lodash_es_initCloneArray_hasOwnProperty = objectProto.hasOwnProperty;

/**
 * Initializes an array clone.
 *
 * @private
 * @param {Array} array The array to clone.
 * @returns {Array} Returns the initialized clone.
 */
function initCloneArray(array) {
  var length = array.length,
      result = new array.constructor(length);

  // Add properties assigned by `RegExp#exec`.
  if (length && typeof array[0] == 'string' && D_deeptutor_web_node_modules_lodash_es_initCloneArray_hasOwnProperty.call(array, 'index')) {
    result.index = array.index;
    result.input = array.input;
  }
  return result;
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_initCloneArray = (initCloneArray);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_cloneArrayBuffer.js
var D_deeptutor_web_node_modules_lodash_es_cloneArrayBuffer = __webpack_require__(6400);
;// D:\deeptutor\web\node_modules\lodash-es\_cloneDataView.js


/**
 * Creates a clone of `dataView`.
 *
 * @private
 * @param {Object} dataView The data view to clone.
 * @param {boolean} [isDeep] Specify a deep clone.
 * @returns {Object} Returns the cloned data view.
 */
function cloneDataView(dataView, isDeep) {
  var buffer = isDeep ? (0,D_deeptutor_web_node_modules_lodash_es_cloneArrayBuffer/* default */.A)(dataView.buffer) : dataView.buffer;
  return new dataView.constructor(buffer, dataView.byteOffset, dataView.byteLength);
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_cloneDataView = (cloneDataView);

;// D:\deeptutor\web\node_modules\lodash-es\_cloneRegExp.js
/** Used to match `RegExp` flags from their coerced string values. */
var reFlags = /\w*$/;

/**
 * Creates a clone of `regexp`.
 *
 * @private
 * @param {Object} regexp The regexp to clone.
 * @returns {Object} Returns the cloned regexp.
 */
function cloneRegExp(regexp) {
  var result = new regexp.constructor(regexp.source, reFlags.exec(regexp));
  result.lastIndex = regexp.lastIndex;
  return result;
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_cloneRegExp = (cloneRegExp);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_Symbol.js
var D_deeptutor_web_node_modules_lodash_es_Symbol = __webpack_require__(5440);
;// D:\deeptutor\web\node_modules\lodash-es\_cloneSymbol.js


/** Used to convert symbols to primitives and strings. */
var symbolProto = D_deeptutor_web_node_modules_lodash_es_Symbol/* default */.A ? D_deeptutor_web_node_modules_lodash_es_Symbol/* default */.A.prototype : undefined,
    symbolValueOf = symbolProto ? symbolProto.valueOf : undefined;

/**
 * Creates a clone of the `symbol` object.
 *
 * @private
 * @param {Object} symbol The symbol object to clone.
 * @returns {Object} Returns the cloned symbol object.
 */
function cloneSymbol(symbol) {
  return symbolValueOf ? Object(symbolValueOf.call(symbol)) : {};
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_cloneSymbol = (cloneSymbol);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_cloneTypedArray.js
var D_deeptutor_web_node_modules_lodash_es_cloneTypedArray = __webpack_require__(5658);
;// D:\deeptutor\web\node_modules\lodash-es\_initCloneByTag.js






/** `Object#toString` result references. */
var boolTag = '[object Boolean]',
    dateTag = '[object Date]',
    mapTag = '[object Map]',
    numberTag = '[object Number]',
    regexpTag = '[object RegExp]',
    setTag = '[object Set]',
    stringTag = '[object String]',
    symbolTag = '[object Symbol]';

var arrayBufferTag = '[object ArrayBuffer]',
    dataViewTag = '[object DataView]',
    float32Tag = '[object Float32Array]',
    float64Tag = '[object Float64Array]',
    int8Tag = '[object Int8Array]',
    int16Tag = '[object Int16Array]',
    int32Tag = '[object Int32Array]',
    uint8Tag = '[object Uint8Array]',
    uint8ClampedTag = '[object Uint8ClampedArray]',
    uint16Tag = '[object Uint16Array]',
    uint32Tag = '[object Uint32Array]';

/**
 * Initializes an object clone based on its `toStringTag`.
 *
 * **Note:** This function only supports cloning values with tags of
 * `Boolean`, `Date`, `Error`, `Map`, `Number`, `RegExp`, `Set`, or `String`.
 *
 * @private
 * @param {Object} object The object to clone.
 * @param {string} tag The `toStringTag` of the object to clone.
 * @param {boolean} [isDeep] Specify a deep clone.
 * @returns {Object} Returns the initialized clone.
 */
function initCloneByTag(object, tag, isDeep) {
  var Ctor = object.constructor;
  switch (tag) {
    case arrayBufferTag:
      return (0,D_deeptutor_web_node_modules_lodash_es_cloneArrayBuffer/* default */.A)(object);

    case boolTag:
    case dateTag:
      return new Ctor(+object);

    case dataViewTag:
      return D_deeptutor_web_node_modules_lodash_es_cloneDataView(object, isDeep);

    case float32Tag: case float64Tag:
    case int8Tag: case int16Tag: case int32Tag:
    case uint8Tag: case uint8ClampedTag: case uint16Tag: case uint32Tag:
      return (0,D_deeptutor_web_node_modules_lodash_es_cloneTypedArray/* default */.A)(object, isDeep);

    case mapTag:
      return new Ctor;

    case numberTag:
    case stringTag:
      return new Ctor(object);

    case regexpTag:
      return D_deeptutor_web_node_modules_lodash_es_cloneRegExp(object);

    case setTag:
      return new Ctor;

    case symbolTag:
      return D_deeptutor_web_node_modules_lodash_es_cloneSymbol(object);
  }
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_initCloneByTag = (initCloneByTag);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_initCloneObject.js + 1 modules
var D_deeptutor_web_node_modules_lodash_es_initCloneObject = __webpack_require__(9294);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isArray.js
var D_deeptutor_web_node_modules_lodash_es_isArray = __webpack_require__(2832);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isBuffer.js + 1 modules
var D_deeptutor_web_node_modules_lodash_es_isBuffer = __webpack_require__(5681);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isObjectLike.js
var D_deeptutor_web_node_modules_lodash_es_isObjectLike = __webpack_require__(8661);
;// D:\deeptutor\web\node_modules\lodash-es\_baseIsMap.js



/** `Object#toString` result references. */
var D_deeptutor_web_node_modules_lodash_es_baseIsMap_mapTag = '[object Map]';

/**
 * The base implementation of `_.isMap` without Node.js optimizations.
 *
 * @private
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is a map, else `false`.
 */
function baseIsMap(value) {
  return (0,D_deeptutor_web_node_modules_lodash_es_isObjectLike/* default */.A)(value) && (0,D_deeptutor_web_node_modules_lodash_es_getTag/* default */.A)(value) == D_deeptutor_web_node_modules_lodash_es_baseIsMap_mapTag;
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseIsMap = (baseIsMap);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_baseUnary.js
var D_deeptutor_web_node_modules_lodash_es_baseUnary = __webpack_require__(5306);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_nodeUtil.js
var D_deeptutor_web_node_modules_lodash_es_nodeUtil = __webpack_require__(60);
;// D:\deeptutor\web\node_modules\lodash-es\isMap.js




/* Node.js helper references. */
var nodeIsMap = D_deeptutor_web_node_modules_lodash_es_nodeUtil/* default */.A && D_deeptutor_web_node_modules_lodash_es_nodeUtil/* default */.A.isMap;

/**
 * Checks if `value` is classified as a `Map` object.
 *
 * @static
 * @memberOf _
 * @since 4.3.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is a map, else `false`.
 * @example
 *
 * _.isMap(new Map);
 * // => true
 *
 * _.isMap(new WeakMap);
 * // => false
 */
var isMap = nodeIsMap ? (0,D_deeptutor_web_node_modules_lodash_es_baseUnary/* default */.A)(nodeIsMap) : D_deeptutor_web_node_modules_lodash_es_baseIsMap;

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_isMap = (isMap);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isObject.js
var D_deeptutor_web_node_modules_lodash_es_isObject = __webpack_require__(6186);
;// D:\deeptutor\web\node_modules\lodash-es\_baseIsSet.js



/** `Object#toString` result references. */
var D_deeptutor_web_node_modules_lodash_es_baseIsSet_setTag = '[object Set]';

/**
 * The base implementation of `_.isSet` without Node.js optimizations.
 *
 * @private
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is a set, else `false`.
 */
function baseIsSet(value) {
  return (0,D_deeptutor_web_node_modules_lodash_es_isObjectLike/* default */.A)(value) && (0,D_deeptutor_web_node_modules_lodash_es_getTag/* default */.A)(value) == D_deeptutor_web_node_modules_lodash_es_baseIsSet_setTag;
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseIsSet = (baseIsSet);

;// D:\deeptutor\web\node_modules\lodash-es\isSet.js




/* Node.js helper references. */
var nodeIsSet = D_deeptutor_web_node_modules_lodash_es_nodeUtil/* default */.A && D_deeptutor_web_node_modules_lodash_es_nodeUtil/* default */.A.isSet;

/**
 * Checks if `value` is classified as a `Set` object.
 *
 * @static
 * @memberOf _
 * @since 4.3.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is a set, else `false`.
 * @example
 *
 * _.isSet(new Set);
 * // => true
 *
 * _.isSet(new WeakSet);
 * // => false
 */
var isSet = nodeIsSet ? (0,D_deeptutor_web_node_modules_lodash_es_baseUnary/* default */.A)(nodeIsSet) : D_deeptutor_web_node_modules_lodash_es_baseIsSet;

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_isSet = (isSet);

;// D:\deeptutor\web\node_modules\lodash-es\_baseClone.js























/** Used to compose bitmasks for cloning. */
var CLONE_DEEP_FLAG = 1,
    CLONE_FLAT_FLAG = 2,
    CLONE_SYMBOLS_FLAG = 4;

/** `Object#toString` result references. */
var argsTag = '[object Arguments]',
    arrayTag = '[object Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_boolTag = '[object Boolean]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_dateTag = '[object Date]',
    errorTag = '[object Error]',
    funcTag = '[object Function]',
    genTag = '[object GeneratorFunction]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_mapTag = '[object Map]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_numberTag = '[object Number]',
    objectTag = '[object Object]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_regexpTag = '[object RegExp]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_setTag = '[object Set]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_stringTag = '[object String]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_symbolTag = '[object Symbol]',
    weakMapTag = '[object WeakMap]';

var D_deeptutor_web_node_modules_lodash_es_baseClone_arrayBufferTag = '[object ArrayBuffer]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_dataViewTag = '[object DataView]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_float32Tag = '[object Float32Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_float64Tag = '[object Float64Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_int8Tag = '[object Int8Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_int16Tag = '[object Int16Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_int32Tag = '[object Int32Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_uint8Tag = '[object Uint8Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_uint8ClampedTag = '[object Uint8ClampedArray]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_uint16Tag = '[object Uint16Array]',
    D_deeptutor_web_node_modules_lodash_es_baseClone_uint32Tag = '[object Uint32Array]';

/** Used to identify `toStringTag` values supported by `_.clone`. */
var cloneableTags = {};
cloneableTags[argsTag] = cloneableTags[arrayTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_arrayBufferTag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_dataViewTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_boolTag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_dateTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_float32Tag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_float64Tag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_int8Tag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_int16Tag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_int32Tag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_mapTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_numberTag] = cloneableTags[objectTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_regexpTag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_setTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_stringTag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_symbolTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_uint8Tag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_uint8ClampedTag] =
cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_uint16Tag] = cloneableTags[D_deeptutor_web_node_modules_lodash_es_baseClone_uint32Tag] = true;
cloneableTags[errorTag] = cloneableTags[funcTag] =
cloneableTags[weakMapTag] = false;

/**
 * The base implementation of `_.clone` and `_.cloneDeep` which tracks
 * traversed objects.
 *
 * @private
 * @param {*} value The value to clone.
 * @param {boolean} bitmask The bitmask flags.
 *  1 - Deep clone
 *  2 - Flatten inherited properties
 *  4 - Clone symbols
 * @param {Function} [customizer] The function to customize cloning.
 * @param {string} [key] The key of `value`.
 * @param {Object} [object] The parent object of `value`.
 * @param {Object} [stack] Tracks traversed objects and their clone counterparts.
 * @returns {*} Returns the cloned value.
 */
function baseClone(value, bitmask, customizer, key, object, stack) {
  var result,
      isDeep = bitmask & CLONE_DEEP_FLAG,
      isFlat = bitmask & CLONE_FLAT_FLAG,
      isFull = bitmask & CLONE_SYMBOLS_FLAG;

  if (customizer) {
    result = object ? customizer(value, key, object, stack) : customizer(value);
  }
  if (result !== undefined) {
    return result;
  }
  if (!(0,D_deeptutor_web_node_modules_lodash_es_isObject/* default */.A)(value)) {
    return value;
  }
  var isArr = (0,D_deeptutor_web_node_modules_lodash_es_isArray/* default */.A)(value);
  if (isArr) {
    result = D_deeptutor_web_node_modules_lodash_es_initCloneArray(value);
    if (!isDeep) {
      return (0,D_deeptutor_web_node_modules_lodash_es_copyArray/* default */.A)(value, result);
    }
  } else {
    var tag = (0,D_deeptutor_web_node_modules_lodash_es_getTag/* default */.A)(value),
        isFunc = tag == funcTag || tag == genTag;

    if ((0,D_deeptutor_web_node_modules_lodash_es_isBuffer/* default */.A)(value)) {
      return (0,D_deeptutor_web_node_modules_lodash_es_cloneBuffer/* default */.A)(value, isDeep);
    }
    if (tag == objectTag || tag == argsTag || (isFunc && !object)) {
      result = (isFlat || isFunc) ? {} : (0,D_deeptutor_web_node_modules_lodash_es_initCloneObject/* default */.A)(value);
      if (!isDeep) {
        return isFlat
          ? D_deeptutor_web_node_modules_lodash_es_copySymbolsIn(value, D_deeptutor_web_node_modules_lodash_es_baseAssignIn(result, value))
          : D_deeptutor_web_node_modules_lodash_es_copySymbols(value, D_deeptutor_web_node_modules_lodash_es_baseAssign(result, value));
      }
    } else {
      if (!cloneableTags[tag]) {
        return object ? value : {};
      }
      result = D_deeptutor_web_node_modules_lodash_es_initCloneByTag(value, tag, isDeep);
    }
  }
  // Check for circular references and return its corresponding clone.
  stack || (stack = new D_deeptutor_web_node_modules_lodash_es_Stack/* default */.A);
  var stacked = stack.get(value);
  if (stacked) {
    return stacked;
  }
  stack.set(value, result);

  if (D_deeptutor_web_node_modules_lodash_es_isSet(value)) {
    value.forEach(function(subValue) {
      result.add(baseClone(subValue, bitmask, customizer, subValue, value, stack));
    });
  } else if (D_deeptutor_web_node_modules_lodash_es_isMap(value)) {
    value.forEach(function(subValue, key) {
      result.set(key, baseClone(subValue, bitmask, customizer, key, value, stack));
    });
  }

  var keysFunc = isFull
    ? (isFlat ? D_deeptutor_web_node_modules_lodash_es_getAllKeysIn : D_deeptutor_web_node_modules_lodash_es_getAllKeys/* default */.A)
    : (isFlat ? D_deeptutor_web_node_modules_lodash_es_keysIn/* default */.A : D_deeptutor_web_node_modules_lodash_es_keys/* default */.A);

  var props = isArr ? undefined : keysFunc(value);
  (0,D_deeptutor_web_node_modules_lodash_es_arrayEach/* default */.A)(props || value, function(subValue, key) {
    if (props) {
      key = subValue;
      subValue = value[key];
    }
    // Recursively populate clone (susceptible to call stack limits).
    (0,D_deeptutor_web_node_modules_lodash_es_assignValue/* default */.A)(result, key, baseClone(subValue, bitmask, customizer, key, value, stack));
  });
  return result;
}

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_baseClone = (baseClone);


/***/ }),

/***/ 5145:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   A: () => (__WEBPACK_DEFAULT_EXPORT__)
/* harmony export */ });
/**
 * Checks if `value` is `undefined`.
 *
 * @static
 * @since 0.1.0
 * @memberOf _
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is `undefined`, else `false`.
 * @example
 *
 * _.isUndefined(void 0);
 * // => true
 *
 * _.isUndefined(null);
 * // => false
 */
function isUndefined(value) {
  return value === undefined;
}

/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (isUndefined);


/***/ }),

/***/ 5988:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   T: () => (/* reexport safe */ _graph_js__WEBPACK_IMPORTED_MODULE_0__.T)
/* harmony export */ });
/* unused harmony export version */
/* harmony import */ var _graph_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(7536);
// Includes only the "core" of graphlib



const version = '2.1.9-pre';




/***/ }),

/***/ 7536:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {


// EXPORTS
__webpack_require__.d(__webpack_exports__, {
  T: () => (/* binding */ Graph)
});

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\constant.js
var D_deeptutor_web_node_modules_lodash_es_constant = __webpack_require__(5769);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isFunction.js
var D_deeptutor_web_node_modules_lodash_es_isFunction = __webpack_require__(7457);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\keys.js
var D_deeptutor_web_node_modules_lodash_es_keys = __webpack_require__(6205);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\filter.js + 1 modules
var D_deeptutor_web_node_modules_lodash_es_filter = __webpack_require__(4727);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isEmpty.js
var D_deeptutor_web_node_modules_lodash_es_isEmpty = __webpack_require__(7876);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\forEach.js
var D_deeptutor_web_node_modules_lodash_es_forEach = __webpack_require__(5655);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isUndefined.js
var D_deeptutor_web_node_modules_lodash_es_isUndefined = __webpack_require__(5145);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_baseFlatten.js + 1 modules
var D_deeptutor_web_node_modules_lodash_es_baseFlatten = __webpack_require__(9614);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_baseRest.js
var D_deeptutor_web_node_modules_lodash_es_baseRest = __webpack_require__(5179);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\_baseUniq.js + 7 modules
var D_deeptutor_web_node_modules_lodash_es_baseUniq = __webpack_require__(3840);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\isArrayLikeObject.js
var D_deeptutor_web_node_modules_lodash_es_isArrayLikeObject = __webpack_require__(2196);
;// D:\deeptutor\web\node_modules\lodash-es\union.js





/**
 * Creates an array of unique values, in order, from all given arrays using
 * [`SameValueZero`](http://ecma-international.org/ecma-262/7.0/#sec-samevaluezero)
 * for equality comparisons.
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Array
 * @param {...Array} [arrays] The arrays to inspect.
 * @returns {Array} Returns the new array of combined values.
 * @example
 *
 * _.union([2], [1, 2]);
 * // => [2, 1]
 */
var union = (0,D_deeptutor_web_node_modules_lodash_es_baseRest/* default */.A)(function(arrays) {
  return (0,D_deeptutor_web_node_modules_lodash_es_baseUniq/* default */.A)((0,D_deeptutor_web_node_modules_lodash_es_baseFlatten/* default */.A)(arrays, 1, D_deeptutor_web_node_modules_lodash_es_isArrayLikeObject/* default */.A, true));
});

/* harmony default export */ const D_deeptutor_web_node_modules_lodash_es_union = (union);

// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\values.js + 1 modules
var D_deeptutor_web_node_modules_lodash_es_values = __webpack_require__(751);
// EXTERNAL MODULE: D:\deeptutor\web\node_modules\lodash-es\reduce.js + 2 modules
var D_deeptutor_web_node_modules_lodash_es_reduce = __webpack_require__(2235);
;// D:\deeptutor\web\node_modules\dagre-d3-es\src\graphlib\graph.js


var DEFAULT_EDGE_NAME = '\x00';
var GRAPH_NODE = '\x00';
var EDGE_KEY_DELIM = '\x01';

/**
 * @typedef {string} NodeID ID of a node.
 */

/**
 * @typedef {`${string}${typeof EDGE_KEY_DELIM}${string}${typeof EDGE_KEY_DELIM}${string}`} EdgeID ID of an edge.
 * @internal - All public APIs use {@link EdgeObj} instead to refer to edges.
 */

/**
 * @typedef {object} EdgeObj
 * @property {NodeID} v the id of the source or tail node of an edge
 * @property {NodeID} w the id of the target or head node of an edge
 * @property {string | number} [name] Name of the edge. Needed to uniquely identify
 * multiple edges between the same pair of nodes in a multigraph.
 */

/**
 * @template {unknown} T
 * @typedef {T[] | Record<any, T>} Collection
 * Lodash object that can be iterated over with `_.each`.
 *
 * Beware, objects with `.length` are treated as arrays, see
 * https://lodash.com/docs/4.17.15#forEach
 */

// Implementation notes:
//
//  * Node id query functions should return string ids for the nodes
//  * Edge id query functions should return an "edgeObj", edge object, that is
//    composed of enough information to uniquely identify an edge: {v, w, name}.
//  * Internally we use an "edgeId", a stringified form of the edgeObj, to
//    reference edges. This is because we need a performant way to look these
//    edges up and, object properties, which have string keys, are the closest
//    we're going to get to a performant hashtable in JavaScript.

// Implementation notes:
//
//  * Node id query functions should return string ids for the nodes
//  * Edge id query functions should return an "edgeObj", edge object, that is
//    composed of enough information to uniquely identify an edge: {v, w, name}.
//  * Internally we use an "edgeId", a stringified form of the edgeObj, to
//    reference edges. This is because we need a performant way to look these
//    edges up and, object properties, which have string keys, are the closest
//    we're going to get to a performant hashtable in JavaScript.

/**
 * @typedef {object} GraphOptions
 * @property {boolean | undefined} [directed] - set to `true` to get a
 * directed graph and `false` to get an undirected graph.
 * An undirected graph does not treat the order of nodes in an edge as
 * significant.
 * In other words, `g.edge("a", "b") === g.edge("b", "a")` for
 * an undirected graph.
 * Default: `true`
 * @property {boolean | undefined} [multigraph] - set to `true` to allow a
 * graph to have multiple edges between the same pair of nodes.
 * Default: `false`.
 * @property {boolean | undefined} [compound] - set to `true` to allow a
 * graph to have compound nodes - nodes which can be the parent of other
 * nodes.
 * Default: `false`.
 */

/**
 * Graphlib has a single graph type: {@link Graph}. To create a new instance:
 *
 * ```js
 * var g = new Graph();
 * ```
 *
 * By default this will create a directed graph that does not allow multi-edges
 * or compound nodes.
 * The following options can be used when constructing a new graph:
 *
 * * {@link GraphOptions#directed}: set to `true` to get a directed graph and `false` to get an
 *   undirected graph.
 *   An undirected graph does not treat the order of nodes in an edge as
 *   significant. In other words,
 *   `g.edge("a", "b") === g.edge("b", "a")` for an undirected graph.
 *   Default: `true`.
 * * {@link GraphOptions#multigraph}: set to `true` to allow a graph to have multiple edges
 *   between the same pair of nodes. Default: `false`.
 * * {@link GraphOptions#compound}: set to `true` to allow a graph to have compound nodes -
 *   nodes which can be the parent of other nodes. Default: `false`.
 *
 * To set the options, pass in an options object to the `Graph` constructor.
 * For example, to create a directed compound multigraph:
 *
 * ```js
 * var g = new Graph({ directed: true, compound: true, multigraph: true });
 * ```
 *
 * ### Node and Edge Representation
 *
 * In graphlib, a node is represented by a user-supplied String id.
 * All node related functions use this String id as a way to uniquely identify
 * the node. Here is an example of interacting with nodes:
 *
 * ```js
 * var g = new Graph();
 * g.setNode("my-id", "my-label");
 * g.node("my-id"); // returns "my-label"
 * ```
 *
 * Edges in graphlib are identified by the nodes they connect. For example:
 *
 * ```js
 * var g = new Graph();
 * g.setEdge("source", "target", "my-label");
 * g.edge("source", "target"); // returns "my-label"
 * ```
 *
 * However, we need a way to uniquely identify an edge in a single object for
 * various edge queries (e.g. {@link Graph#outEdges}).
 * We use {@link EdgeObj}s for this purpose.
 * They consist of the following properties:
 *
 * * {@link EdgeObj#v}: the id of the source or tail node of an edge
 * * {@link EdgeObj#w}: the id of the target or head node of an edge
 * * {@link EdgeObj#name} (optional): the name that uniquely identifies a multiedge.
 *
 * Any edge function that takes an edge id will also work with an {@link EdgeObj}. For example:
 *
 * ```js
 * var g = new Graph();
 * g.setEdge("source", "target", "my-label");
 * g.edge({ v: "source", w: "target" }); // returns "my-label"
 * ```
 *
 * ### Multigraphs
 *
 * A [multigraph](https://en.wikipedia.org/wiki/Multigraph) is a graph that can
 * have more than one edge between the same pair of nodes.
 * By default graphlib graphs are not multigraphs, but a multigraph can be
 * constructed by setting the {@link GraphOptions#multigraph} property to true:
 *
 * ```js
 * var g = new Graph({ multigraph: true });
 * ```
 *
 * With multiple edges between two nodes we need some way to uniquely identify
 * each edge. We call this the {@link EdgeObj#name} property.
 * Here's an example of creating a couple of edges between the same nodes:
 *
 * ```js
 * var g = new Graph({ multigraph: true });
 * g.setEdge("a", "b", "edge1-label", "edge1");
 * g.setEdge("a", "b", "edge2-label", "edge2");
 * g.edge("a", "b", "edge1"); // returns "edge1-label"
 * g.edge("a", "b", "edge2"); // returns "edge2-label"
 * g.edges(); // returns [{ v: "a", w: "b", name: "edge1" },
 *            //          { v: "a", w: "b", name: "edge2" }]
 * ```
 *
 * A multigraph still allows an edge with no name to be created:
 *
 * ```js
 * var g = new Graph({ multigraph: true });
 * g.setEdge("a", "b", "my-label");
 * g.edge({ v: "a", w: "b" }); // returns "my-label"
 * ```
 *
 * ### Compound Graphs
 *
 * A compound graph is one where a node can be the parent of other nodes.
 * The child nodes form a "subgraph".
 * Here's an example of constructing and interacting with a compound graph:
 *
 * ```js
 * var g = new Graph({ compound: true });
 * g.setParent("a", "parent");
 * g.setParent("b", "parent");
 * g.parent("a");      // returns "parent"
 * g.parent("b");      // returns "parent"
 * g.parent("parent"); // returns undefined
 * ```
 *
 * ### Default Labels
 *
 * When a node or edge is created without a label, a default label can be assigned.
 * See {@link setDefaultNodeLabel} and {@link setDefaultEdgeLabel}.
 *
 * @template [GraphLabel=any] - Label of the graph.
 * @template [NodeLabel=any] - Label of a node.
 * Even though this is a "label", this could be any type that the user requires
 * (and may need to be an object for some layout/ranking algorithms in dagre).
 * @template [EdgeLabel=any] - Label of an edge.
 * Even though this is a "label", this could be any type that the user requires,
 * (and may need to be a object for ranking in dagre).
 */
class Graph {
  /**
   * @param {GraphOptions} [opts] - Graph options.
   */
  constructor(opts = {}) {
    /**
     * @type {boolean}
     * @private
     */
    this._isDirected = Object.prototype.hasOwnProperty.call(opts, 'directed')
      ? opts.directed
      : true;
    /**
     * @type {boolean}
     * @private
     */
    this._isMultigraph = Object.prototype.hasOwnProperty.call(opts, 'multigraph')
      ? opts.multigraph
      : false;
    /**
     * @type {boolean}
     * @private
     */
    this._isCompound = Object.prototype.hasOwnProperty.call(opts, 'compound')
      ? opts.compound
      : false;

    /**
     * @type {GraphLabel | undefined}
     * Label for the graph itself
     */
    this._label = undefined;

    /**
     * Default label to be set when creating a new node.
     *
     * @private
     * @type {(v: NodeID | number) => NodeLabel}
     */
    this._defaultNodeLabelFn = D_deeptutor_web_node_modules_lodash_es_constant/* default */.A(undefined);

    /**
     * Default label to be set when creating a new edge
     *
     * @private
     * @type {(v: NodeID, w: NodeID, name: string | undefined) => EdgeLabel}
     */
    this._defaultEdgeLabelFn = D_deeptutor_web_node_modules_lodash_es_constant/* default */.A(undefined);

    /**
     * @type {Record<NodeID, NodeLabel>}
     * @private
     *
     * v -> label
     */
    this._nodes = {};

    if (this._isCompound) {
      /**
       * @type {Record<NodeID, NodeID>}
       * @private
       * v -> parent
       */
      this._parent = {};

      /**
       * @type {Record<NodeID, Record<NodeID, true>>}
       * @private
       * v -> children
       */
      this._children = {};
      this._children[GRAPH_NODE] = {};
    }

    /**
     * @type {Record<NodeID, Record<EdgeID, EdgeObj>>}
     * @private
     * v -> edgeObj
     */
    this._in = {};

    /**
     * @type {Record<NodeID, Record<NodeID, number>>}
     * @private
     * u -> v -> Number
     */
    this._preds = {};

    /**
     * @type {Record<NodeID, Record<EdgeID, EdgeObj>>}
     * @private
     * v -> edgeObj
     */
    this._out = {};

    /**
     * @type {Record<NodeID, Record<NodeID, number>>}
     * @private
     * v -> w -> Number
     */
    this._sucs = {};

    /**
     * @type {Record<EdgeID, EdgeObj>}
     * @private
     * e -> edgeObj
     */
    this._edgeObjs = {};

    /**
     * @type {Record<EdgeID, EdgeLabel>}
     * @private
     * e -> label
     */
    this._edgeLabels = {};
  }

  /* === Graph functions ========= */

  /**
   *
   * @returns {boolean} `true` if the graph is [directed](https://en.wikipedia.org/wiki/Directed_graph).
   * A directed graph treats the order of nodes in an edge as significant whereas an
   * [undirected](https://en.wikipedia.org/wiki/Graph_(mathematics)#Undirected_graph)
   * graph does not.
   * This example demonstrates the difference:
   *
   * @example
   *
   * ```js
   * var directed = new Graph({ directed: true });
   * directed.setEdge("a", "b", "my-label");
   * directed.edge("a", "b"); // returns "my-label"
   * directed.edge("b", "a"); // returns undefined
   *
   * var undirected = new Graph({ directed: false });
   * undirected.setEdge("a", "b", "my-label");
   * undirected.edge("a", "b"); // returns "my-label"
   * undirected.edge("b", "a"); // returns "my-label"
   * ```
   */
  isDirected() {
    return this._isDirected;
  }
  /**
   * @returns {boolean} `true` if the graph is a multigraph.
   */
  isMultigraph() {
    return this._isMultigraph;
  }
  /**
   * @returns {boolean} `true` if the graph is compound.
   */
  isCompound() {
    return this._isCompound;
  }

  /**
   * Sets the label for the graph to `label`.
   *
   * @param {GraphLabel} label - Label for the graph.
   * @returns {this}
   */
  setGraph(label) {
    this._label = label;
    return this;
  }

  /**
   * @returns {GraphLabel | undefined} the currently assigned label for the graph.
   * If no label has been assigned, returns `undefined`.
   *
   * @example
   *
   * ```js
   * var g = new Graph();
   * g.graph(); // returns undefined
   * g.setGraph("graph-label");
   *  g.graph(); // returns "graph-label"
   * ```
   */
  graph() {
    return this._label;
  }
  /* === Node functions ========== */

  /**
   * Sets a new default value that is assigned to nodes that are created without
   * a label.
   *
   * @param {typeof this._defaultNodeLabelFn | NodeLabel} newDefault - If a function,
   * it is called with the id of the node being created.
   * Otherwise, it is assigned as the label directly.
   * @returns {this}
   */
  setDefaultNodeLabel(newDefault) {
    if (!D_deeptutor_web_node_modules_lodash_es_isFunction/* default */.A(newDefault)) {
      newDefault = D_deeptutor_web_node_modules_lodash_es_constant/* default */.A(newDefault);
    }
    this._defaultNodeLabelFn = newDefault;
    return this;
  }

  /**
   * @returns {number} the number of nodes in the graph.
   */
  nodeCount() {
    return this._nodeCount;
  }

  /**
   * @returns {NodeID[]} the ids of the nodes in the graph.
   *
   * @remarks
   * Use {@link node()} to get the label for each node.
   * Takes `O(|V|)` time.
   */
  nodes() {
    return D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(this._nodes);
  }
  /**
   * @returns {NodeID[]} those nodes in the graph that have no in-edges.
   * @remarks Takes `O(|V|)` time.
   */
  sources() {
    var self = this;
    return D_deeptutor_web_node_modules_lodash_es_filter/* default */.A(this.nodes(), function (v) {
      return D_deeptutor_web_node_modules_lodash_es_isEmpty/* default */.A(self._in[v]);
    });
  }
  /**
   * @returns {NodeID[]} those nodes in the graph that have no out-edges.
   * @remarks Takes `O(|V|)` time.
   */
  sinks() {
    var self = this;
    return D_deeptutor_web_node_modules_lodash_es_filter/* default */.A(this.nodes(), function (v) {
      return D_deeptutor_web_node_modules_lodash_es_isEmpty/* default */.A(self._out[v]);
    });
  }

  /**
   * Invokes setNode method for each node in `vs` list.
   *
   * @param {Collection<NodeID | number>} vs - List of node IDs to create/set.
   * @param {NodeLabel} [value] - If set, update all nodes with this value.
   * @returns {this}
   * @remarks Complexity: O(|names|).
   */
  setNodes(vs, value) {
    var args = arguments;
    var self = this;
    D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(vs, function (v) {
      if (args.length > 1) {
        self.setNode(v, value);
      } else {
        self.setNode(v);
      }
    });
    return this;
  }

  /**
   * Creates or updates the value for the node `v` in the graph.
   *
   * @param {NodeID | number} v - ID of the node to create/set.
   * @param {NodeLabel} [value] - If supplied, it is set as the value for the node.
   * If not supplied and the node was created by this call then
   * {@link setDefaultNodeLabel} will be used to set the node's value.
   * @returns {this} the graph, allowing this to be chained with other functions.
   * @remarks Takes `O(1)` time.
   */
  setNode(v, value) {
    if (Object.prototype.hasOwnProperty.call(this._nodes, v)) {
      if (arguments.length > 1) {
        this._nodes[v] = value;
      }
      return this;
    }

    this._nodes[v] = arguments.length > 1 ? value : this._defaultNodeLabelFn(v);
    if (this._isCompound) {
      this._parent[v] = GRAPH_NODE;
      this._children[v] = {};
      this._children[GRAPH_NODE][v] = true;
    }
    this._in[v] = {};
    this._preds[v] = {};
    this._out[v] = {};
    this._sucs[v] = {};
    ++this._nodeCount;
    return this;
  }

  /**
   * Gets the label of node with specified name.
   *
   * @param {NodeID | number} v - Node ID.
   * @returns {NodeLabel | undefined} the label assigned to the node with the id `v`
   * if it is in the graph.
   * Otherwise returns `undefined`.
   * @remarks Takes `O(1)` time.
   */
  node(v) {
    return this._nodes[v];
  }

  /**
   * Detects whether graph has a node with specified name or not.
   *
   * @param {NodeID | number} v - Node ID.
   * @returns {boolean} Returns `true` the graph has a node with the id.
   * @remarks Takes `O(1)` time.
   */
  hasNode(v) {
    return Object.prototype.hasOwnProperty.call(this._nodes, v);
  }

  /**
   * Remove the node with the id `v` in the graph or do nothing if the node is
   * not in the graph.
   *
   * If the node was removed this function also removes any incident edges.
   *
   * @param {NodeID | number} v - Node ID to remove.
   * @returns {this} the graph, allowing this to be chained with other functions.
   * @remarks Takes `O(|E|)` time.
   */
  removeNode(v) {
    if (Object.prototype.hasOwnProperty.call(this._nodes, v)) {
      var removeEdge = (e) => this.removeEdge(this._edgeObjs[e]);
      delete this._nodes[v];
      if (this._isCompound) {
        this._removeFromParentsChildList(v);
        delete this._parent[v];
        D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(this.children(v), (child) => {
          this.setParent(child);
        });
        delete this._children[v];
      }
      D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(this._in[v]), removeEdge);
      delete this._in[v];
      delete this._preds[v];
      D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(this._out[v]), removeEdge);
      delete this._out[v];
      delete this._sucs[v];
      --this._nodeCount;
    }
    return this;
  }

  /**
   * Sets the parent for `v` to `parent` if it is defined or removes the parent
   * for `v` if `parent` is undefined.
   *
   * @param {NodeID | number} v - Node ID to set the parent for.
   * @param {NodeID | number} [parent] - Parent node ID. If not defined, removes the parent.
   * @returns {this} the graph, allowing this to be chained with other functions.
   * @throws if the graph is not compound.
   * @throws if setting the parent would create a cycle.
   * @remarks Takes `O(1)` time.
   */
  setParent(v, parent) {
    if (!this._isCompound) {
      throw new Error('Cannot set parent in a non-compound graph');
    }

    if (D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(parent)) {
      parent = GRAPH_NODE;
    } else {
      // Coerce parent to string
      parent += '';
      for (var ancestor = parent; !D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(ancestor); ancestor = this.parent(ancestor)) {
        if (ancestor === v) {
          throw new Error('Setting ' + parent + ' as parent of ' + v + ' would create a cycle');
        }
      }

      this.setNode(parent);
    }

    this.setNode(v);
    this._removeFromParentsChildList(v);
    // @ts-expect-error -- We coerced parent to a string above
    this._parent[v] = parent;
    this._children[parent][v] = true;
    return this;
  }

  /**
   * @private
   * @param {NodeID | number} v - Node ID.
   */
  _removeFromParentsChildList(v) {
    delete this._children[this._parent[v]][v];
  }

  /**
   * Get parent node for node `v`.
   *
   * @param {NodeID | number} v - Node ID.
   * @returns {NodeID | undefined} the node that is a parent of node `v`
   * or `undefined` if node `v` does not have a parent or is not a member of
   * the graph.
   * Always returns `undefined` for graphs that are not compound.
   * @remarks Takes `O(1)` time.
   */
  parent(v) {
    if (this._isCompound) {
      var parent = this._parent[v];
      if (parent !== GRAPH_NODE) {
        return parent;
      }
    }
  }

  /**
   * Gets list of direct children of node v.
   *
   * @param {NodeID | number} [v] - Node ID. If not specified, gets nodes
   * with no parent (top-level nodes).
   * @returns {NodeID[] | undefined} all nodes that are children of node `v` or
   * `undefined` if node `v` is not in the graph.
   * Always returns `[]` for graphs that are not compound.
   * @remarks Takes `O(|V|)` time.
   */
  children(v) {
    if (D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(v)) {
      v = GRAPH_NODE;
    }

    if (this._isCompound) {
      var children = this._children[v];
      if (children) {
        return D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(children);
      }
    } else if (v === GRAPH_NODE) {
      return this.nodes();
    } else if (this.hasNode(v)) {
      return [];
    }
  }

  /**
   * @param {NodeID | number} v - Node ID.
   * @returns {NodeID[] | undefined} all nodes that are predecessors of the
   * specified node or `undefined` if node `v` is not in the graph.
   * @remarks
   * Behavior is undefined for undirected graphs - use {@link neighbors} instead.
   * Takes `O(|V|)` time.
   */
  predecessors(v) {
    var predsV = this._preds[v];
    if (predsV) {
      return D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(predsV);
    }
  }

  /**
   * @param {NodeID | number} v - Node ID.
   * @returns {NodeID[] | undefined} all nodes that are successors of the
   * specified node or `undefined` if node `v` is not in the graph.
   * @remarks
   * Behavior is undefined for undirected graphs - use {@link neighbors} instead.
   * Takes `O(|V|)` time.
   */
  successors(v) {
    var sucsV = this._sucs[v];
    if (sucsV) {
      return D_deeptutor_web_node_modules_lodash_es_keys/* default */.A(sucsV);
    }
  }

  /**
   * @param {NodeID | number} v - Node ID.
   * @returns {NodeID[] | undefined} all nodes that are predecessors or
   * successors of the specified node
   * or `undefined` if node `v` is not in the graph.
   * @remarks Takes `O(|V|)` time.
   */
  neighbors(v) {
    var preds = this.predecessors(v);
    if (preds) {
      return D_deeptutor_web_node_modules_lodash_es_union(preds, this.successors(v));
    }
  }

  /**
   * @param {NodeID | number} v - Node ID.
   * @returns {boolean} True if the node is a leaf (has no successors), false otherwise.
   */
  isLeaf(v) {
    var neighbors;
    if (this.isDirected()) {
      neighbors = this.successors(v);
    } else {
      neighbors = this.neighbors(v);
    }
    return neighbors.length === 0;
  }

  /**
   * Creates new graph with nodes filtered via `filter`.
   * Edges incident to rejected node
   * are also removed.
   * 
   * In case of compound graph, if parent is rejected by `filter`,
   * than all its children are rejected too.

   * @param {(v: NodeID) => boolean} filter - Function that returns `true` for nodes to keep.
   * @returns {Graph<GraphLabel, NodeLabel, EdgeLabel>} A new graph containing only the nodes for which `filter` returns `true`.
   * @remarks Average-case complexity: O(|E|+|V|).
   */
  filterNodes(filter) {
    /**
     * @type {Graph<GraphLabel, NodeLabel, EdgeLabel>}
     */
    // @ts-expect-error
    var copy = new this.constructor({
      directed: this._isDirected,
      multigraph: this._isMultigraph,
      compound: this._isCompound,
    });

    copy.setGraph(this.graph());

    var self = this;
    D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(this._nodes, function (value, v) {
      if (filter(v)) {
        copy.setNode(v, value);
      }
    });

    D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(this._edgeObjs, function (e) {
      if (copy.hasNode(e.v) && copy.hasNode(e.w)) {
        copy.setEdge(e, self.edge(e));
      }
    });

    var parents = {};
    function findParent(v) {
      var parent = self.parent(v);
      if (parent === undefined || copy.hasNode(parent)) {
        parents[v] = parent;
        return parent;
      } else if (parent in parents) {
        return parents[parent];
      } else {
        return findParent(parent);
      }
    }

    if (this._isCompound) {
      D_deeptutor_web_node_modules_lodash_es_forEach/* default */.A(copy.nodes(), function (v) {
        copy.setParent(v, findParent(v));
      });
    }

    return copy;
  }

  /* === Edge functions ========== */

  /**
   * Sets a new default value that is assigned to edges that are created without
   * a label.
   *
   * @param {typeof this._defaultEdgeLabelFn | EdgeLabel} newDefault - If a function,
   * it is called with the parameters `(v, w, name)`.
   * Otherwise, it is assigned as the label directly.
   * @returns {this}
   */
  setDefaultEdgeLabel(newDefault) {
    if (!D_deeptutor_web_node_modules_lodash_es_isFunction/* default */.A(newDefault)) {
      newDefault = D_deeptutor_web_node_modules_lodash_es_constant/* default */.A(newDefault);
    }
    this._defaultEdgeLabelFn = newDefault;
    return this;
  }

  /**
   * @returns {number} the number of edges in the graph.
   * @remarks Complexity: O(1).
   */
  edgeCount() {
    return this._edgeCount;
  }

  /**
   * Gets edges of the graph.
   *
   * @returns {EdgeObj[]} the {@link EdgeObj} for each edge in the graph.
   *
   * @remarks
   * In case of compound graph subgraphs are not considered.
   * Use {@link edge()} to get the label for each edge.
   * Takes `O(|E|)` time.
   */
  edges() {
    return D_deeptutor_web_node_modules_lodash_es_values/* default */.A(this._edgeObjs);
  }

  /**
   * Establish an edges path over the nodes in nodes list.
   *
   * If some edge is already exists, it will update its label, otherwise it will
   * create an edge between pair of nodes with label provided or default label
   * if no label provided.
   *
   * @param {Collection<NodeID>} vs - List of node IDs to create edges between.
   * @param {EdgeLabel} [value] - If set, update all edges with this value.
   * @returns {this}
   * @remarks Complexity: O(|nodes|).
   */
  setPath(vs, value) {
    var self = this;
    var args = arguments;
    D_deeptutor_web_node_modules_lodash_es_reduce/* default */.A(vs, function (v, w) {
      if (args.length > 1) {
        self.setEdge(v, w, value);
      } else {
        self.setEdge(v, w);
      }
      return w;
    });
    return this;
  }

  /**
   * Creates or updates the label for the edge (`v`, `w`) with the optionally
   * supplied `name`.
   *
   * @overload
   * @param {EdgeObj} arg0 - Edge object.
   * @param {EdgeLabel} [value] - If supplied, it is set as the label for the edge.
   * If not supplied and the edge was created by this call then
   * {@link setDefaultEdgeLabel} will be used to assign the edge's label.
   * @returns {this} the graph, allowing this to be chained with other functions.
   * @remarks Takes `O(1)` time.
   */
  /**
   * Creates or updates the label for the edge (`v`, `w`) with the optionally
   * supplied `name`.
   *
   * @overload
   * @param {NodeID | number} v - Source node ID. Number values will be coerced to strings.
   * @param {NodeID | number} w - Target node ID. Number values will be coerced to strings.
   * @param {EdgeLabel} [value] - If supplied, it is set as the label for the edge.
   * If not supplied and the edge was created by this call then
   * {@link setDefaultEdgeLabel} will be used to assign the edge's label.
   * @param {string | number} [name] - Edge name. Only useful with multigraphs.
   * @returns {this} the graph, allowing this to be chained with other functions.
   * @remarks Takes `O(1)` time.
   */
  setEdge() {
    var v, w, name, value;
    var valueSpecified = false;
    var arg0 = arguments[0];

    if (typeof arg0 === 'object' && arg0 !== null && 'v' in arg0) {
      v = arg0.v;
      w = arg0.w;
      name = arg0.name;
      if (arguments.length === 2) {
        value = arguments[1];
        valueSpecified = true;
      }
    } else {
      v = arg0;
      w = arguments[1];
      name = arguments[3];
      if (arguments.length > 2) {
        value = arguments[2];
        valueSpecified = true;
      }
    }

    v = '' + v;
    w = '' + w;
    if (!D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(name)) {
      name = '' + name;
    }

    var e = edgeArgsToId(this._isDirected, v, w, name);
    if (Object.prototype.hasOwnProperty.call(this._edgeLabels, e)) {
      if (valueSpecified) {
        this._edgeLabels[e] = value;
      }
      return this;
    }

    if (!D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(name) && !this._isMultigraph) {
      throw new Error('Cannot set a named edge when isMultigraph = false');
    }

    // It didn't exist, so we need to create it.
    // First ensure the nodes exist.
    this.setNode(v);
    this.setNode(w);

    this._edgeLabels[e] = valueSpecified ? value : this._defaultEdgeLabelFn(v, w, name);

    var edgeObj = edgeArgsToObj(this._isDirected, v, w, name);
    // Ensure we add undirected edges in a consistent way.
    v = edgeObj.v;
    w = edgeObj.w;

    Object.freeze(edgeObj);
    this._edgeObjs[e] = edgeObj;
    incrementOrInitEntry(this._preds[w], v);
    incrementOrInitEntry(this._sucs[v], w);
    this._in[w][e] = edgeObj;
    this._out[v][e] = edgeObj;
    this._edgeCount++;
    return this;
  }

  /**
   * Gets the label for the specified edge.
   *
   * @overload
   * @param {EdgeObj} v - Edge object.
   * @returns {EdgeLabel | undefined} the label for the edge (`v`, `w`) if the
   * graph has an edge between `v` and `w` with the optional `name`.
   * Returned `undefined` if there is no such edge in the graph.
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * Takes `O(1)` time.
   */
  /**
   * Gets the label for the specified edge.
   *
   * @overload
   * @param {NodeID | number} v - Source node ID.
   * @param {NodeID | number} w - Target node ID.
   * @param {string | number} [name] - Edge name. Only useful with multigraphs.
   * @returns {EdgeLabel | undefined} the label for the edge (`v`, `w`) if the
   * graph has an edge between `v` and `w` with the optional `name`.
   * Returned `undefined` if there is no such edge in the graph.
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * Takes `O(1)` time.
   */
  edge(v, w, name) {
    var e =
      arguments.length === 1
        ? edgeObjToId(this._isDirected, arguments[0])
        : edgeArgsToId(this._isDirected, v, w, name);
    return this._edgeLabels[e];
  }

  /**
   * Detects whether the graph contains specified edge or not.
   *
   * @overload
   * @param {EdgeObj} v - Edge object.
   * @returns {boolean} `true` if the graph has an edge between `v` and `w`
   * with the optional `name`.
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * No subgraphs are considered.
   * Takes `O(1)` time.
   */
  /**
   * Detects whether the graph contains specified edge or not.
   *
   * @overload
   * @param {NodeID | number} v - Source node ID.
   * @param {NodeID | number} w - Target node ID.
   * @param {string | number} [name] - Edge name. Only useful with multigraphs.
   * @returns {boolean} `true` if the graph has an edge between `v` and `w`
   * with the optional `name`.
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * No subgraphs are considered.
   * Takes `O(1)` time.
   */
  hasEdge(v, w, name) {
    var e =
      arguments.length === 1
        ? edgeObjToId(this._isDirected, arguments[0])
        : edgeArgsToId(this._isDirected, v, w, name);
    return Object.prototype.hasOwnProperty.call(this._edgeLabels, e);
  }

  /**
   * Removes the edge (`v`, `w`) if the graph has an edge between `v` and `w`
   * with the optional `name`. If not this function does nothing.
   *
   * @overload
   * @param {EdgeObj} v - Edge object.
   * @returns {this}
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * No subgraphs are considered.
   * Takes `O(1)` time.
   */
  /**
   * Removes the edge (`v`, `w`) if the graph has an edge between `v` and `w`
   * with the optional `name`. If not this function does nothing.
   *
   * @overload
   * @param {NodeID | number} v - Source node ID.
   * @param {NodeID | number} w - Target node ID.
   * @param {string | number} [name] - Edge name. Only useful with multigraphs.
   * @returns {this}
   * @remarks
   * `v` and `w` can be interchanged for undirected graphs.
   * Takes `O(1)` time.
   */
  removeEdge(v, w, name) {
    var e =
      arguments.length === 1
        ? edgeObjToId(this._isDirected, arguments[0])
        : edgeArgsToId(this._isDirected, v, w, name);
    var edge = this._edgeObjs[e];
    if (edge) {
      v = edge.v;
      w = edge.w;
      delete this._edgeLabels[e];
      delete this._edgeObjs[e];
      decrementOrRemoveEntry(this._preds[w], v);
      decrementOrRemoveEntry(this._sucs[v], w);
      delete this._in[w][e];
      delete this._out[v][e];
      this._edgeCount--;
    }
    return this;
  }

  /**
   * @param {NodeID | number} v - Target node ID.
   * @param {NodeID | number} [u] - Optionally filters edges down to just those
   * coming from node `u`.
   * @returns {EdgeObj[] | undefined} all edges that point to the node `v`.
   * Returns `undefined` if node `v` is not in the graph.
   * @remarks
   * Behavior is undefined for undirected graphs - use {@link nodeEdges} instead.
   * Takes `O(|E|)` time.
   */
  inEdges(v, u) {
    var inV = this._in[v];
    if (inV) {
      var edges = D_deeptutor_web_node_modules_lodash_es_values/* default */.A(inV);
      if (!u) {
        return edges;
      }
      return D_deeptutor_web_node_modules_lodash_es_filter/* default */.A(edges, function (edge) {
        return edge.v === u;
      });
    }
  }

  /**
   * @param {NodeID | number} v - Target node ID.
   * @param {NodeID | number} [w] - Optionally filters edges down to just those
   * that point to `w`.
   * @returns {EdgeObj[] | undefined} all edges that point to the node `v`.
   * Returns `undefined` if node `v` is not in the graph.
   * @remarks
   * Behavior is undefined for undirected graphs - use {@link nodeEdges} instead.
   * Takes `O(|E|)` time.
   */
  outEdges(v, w) {
    var outV = this._out[v];
    if (outV) {
      var edges = D_deeptutor_web_node_modules_lodash_es_values/* default */.A(outV);
      if (!w) {
        return edges;
      }
      return D_deeptutor_web_node_modules_lodash_es_filter/* default */.A(edges, function (edge) {
        return edge.w === w;
      });
    }
  }

  /**
   * @param {NodeID | number} v - Target Node ID.
   * @param {NodeID | number} [w] - If set, filters those edges down to just
   * those between nodes `v` and `w` regardless of direction
   * @returns {EdgeObj[] | undefined} all edges to or from node `v` regardless
   * of direction. Returns `undefined` if node `v` is not in the graph.
   * @remarks Takes `O(|E|)` time.
   */
  nodeEdges(v, w) {
    var inEdges = this.inEdges(v, w);
    if (inEdges) {
      return inEdges.concat(this.outEdges(v, w));
    }
  }
}

/* Number of nodes in the graph. Should only be changed by the implementation. */
Graph.prototype._nodeCount = 0;

/* Number of edges in the graph. Should only be changed by the implementation. */
Graph.prototype._edgeCount = 0;

/**
 * @param {Record<NodeID, number>} map - Object mapping node IDs to counts.
 * @param {NodeID | number} k - Node ID.
 */
function incrementOrInitEntry(map, k) {
  if (map[k]) {
    map[k]++;
  } else {
    map[k] = 1;
  }
}

/**
 * @param {Record<NodeID, number>} map - Object mapping node IDs to counts.
 * @param {NodeID | number} k - Node ID.
 */
function decrementOrRemoveEntry(map, k) {
  if (!--map[k]) {
    delete map[k];
  }
}

/**
 * @param {boolean} isDirected - If `false`, sorts v and w to ensure a consistent ID.
 * @param {EdgeObj['v'] | number} v_ - Source node ID.
 * @param {EdgeObj['w'] | number} w_ - Target node ID.
 * @param {EdgeObj['name']} [name] - Edge name (for multiple edges between the same nodes).
 * @returns {EdgeID} Unique ID for the edge.
 */
function edgeArgsToId(isDirected, v_, w_, name) {
  var v = '' + v_;
  var w = '' + w_;
  if (!isDirected && v > w) {
    var tmp = v;
    v = w;
    w = tmp;
  }
  return v + EDGE_KEY_DELIM + w + EDGE_KEY_DELIM + (D_deeptutor_web_node_modules_lodash_es_isUndefined/* default */.A(name) ? DEFAULT_EDGE_NAME : name);
}

/**
 * @param {boolean} isDirected - If `false`, sorts v and w to ensure a consistent ID.
 * @param {EdgeObj['v'] | number} v_ - Source node ID.
 * @param {EdgeObj['w'] | number} w_ - Target node ID.
 * @param {EdgeObj['name']} [name] - Edge name (for multiple edges between the same nodes).
 * @returns {EdgeObj}
 */
function edgeArgsToObj(isDirected, v_, w_, name) {
  var v = '' + v_;
  var w = '' + w_;
  if (!isDirected && v > w) {
    var tmp = v;
    v = w;
    w = tmp;
  }
  var edgeObj = { v: v, w: w };
  if (name) {
    edgeObj.name = name;
  }
  return edgeObj;
}

/**
 * @param {boolean} isDirected - If `false`, sorts v and w to ensure a consistent ID.
 * @param {EdgeObj} edgeObj - Edge object.
 * @returns {EdgeID} Unique ID for the edge.
 */
function edgeObjToId(isDirected, edgeObj) {
  return edgeArgsToId(isDirected, edgeObj.v, edgeObj.w, edgeObj.name);
}


/***/ })

}]);