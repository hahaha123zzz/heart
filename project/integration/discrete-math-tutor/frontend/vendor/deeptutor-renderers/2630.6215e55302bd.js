(self["webpackChunk"] = self["webpackChunk"] || []).push([[2630],{

/***/ 2630:
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   render: () => (/* binding */ render2)
/* harmony export */ });
/* harmony import */ var _chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(9491);
/* harmony import */ var cytoscape__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(6313);
/* harmony import */ var cytoscape_cose_bilkent__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(5964);
/* harmony import */ var d3__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(3520);


// src/rendering-util/layout-algorithms/cose-bilkent/cytoscape-setup.ts



cytoscape__WEBPACK_IMPORTED_MODULE_1__/* ["default"] */ .A.use(cytoscape_cose_bilkent__WEBPACK_IMPORTED_MODULE_2__);
function addNodes(nodes, cy) {
  nodes.forEach((node) => {
    const nodeData = {
      id: node.id,
      labelText: node.label,
      height: node.height,
      width: node.width,
      padding: node.padding ?? 0
    };
    Object.keys(node).forEach((key) => {
      if (!["id", "label", "height", "width", "padding", "x", "y"].includes(key)) {
        nodeData[key] = node[key];
      }
    });
    cy.add({
      group: "nodes",
      data: nodeData,
      position: {
        x: node.x ?? 0,
        y: node.y ?? 0
      }
    });
  });
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(addNodes, "addNodes");
function addEdges(edges, cy) {
  edges.forEach((edge) => {
    const edgeData = {
      id: edge.id,
      source: edge.start,
      target: edge.end
    };
    Object.keys(edge).forEach((key) => {
      if (!["id", "start", "end"].includes(key)) {
        edgeData[key] = edge[key];
      }
    });
    cy.add({
      group: "edges",
      data: edgeData
    });
  });
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(addEdges, "addEdges");
function createCytoscapeInstance(data) {
  return new Promise((resolve) => {
    const renderEl = (0,d3__WEBPACK_IMPORTED_MODULE_3__/* .select */ .Ltv)("body").append("div").attr("id", "cy").attr("style", "display:none");
    const cy = (0,cytoscape__WEBPACK_IMPORTED_MODULE_1__/* ["default"] */ .A)({
      container: document.getElementById("cy"),
      // container to render in
      style: [
        {
          selector: "edge",
          style: {
            "curve-style": "bezier"
          }
        }
      ]
    });
    renderEl.remove();
    addNodes(data.nodes, cy);
    addEdges(data.edges, cy);
    cy.nodes().forEach(function(n) {
      n.layoutDimensions = () => {
        const nodeData = n.data();
        return { w: nodeData.width, h: nodeData.height };
      };
    });
    const layoutConfig = {
      name: "cose-bilkent",
      // @ts-ignore Types for cose-bilkent are not correct?
      quality: "proof",
      styleEnabled: false,
      animate: false
    };
    cy.layout(layoutConfig).run();
    cy.ready((e) => {
      _chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .log */ .Rm.info("Cytoscape ready", e);
      resolve(cy);
    });
  });
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(createCytoscapeInstance, "createCytoscapeInstance");
function extractPositionedNodes(cy) {
  return cy.nodes().map((node) => {
    const data = node.data();
    const position = node.position();
    const positionedNode = {
      id: data.id,
      x: position.x,
      y: position.y
    };
    Object.keys(data).forEach((key) => {
      if (key !== "id") {
        positionedNode[key] = data[key];
      }
    });
    return positionedNode;
  });
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(extractPositionedNodes, "extractPositionedNodes");
function extractPositionedEdges(cy) {
  return cy.edges().map((edge) => {
    const data = edge.data();
    const rscratch = edge._private.rscratch;
    const positionedEdge = {
      id: data.id,
      source: data.source,
      target: data.target,
      startX: rscratch.startX,
      startY: rscratch.startY,
      midX: rscratch.midX,
      midY: rscratch.midY,
      endX: rscratch.endX,
      endY: rscratch.endY
    };
    Object.keys(data).forEach((key) => {
      if (!["id", "source", "target"].includes(key)) {
        positionedEdge[key] = data[key];
      }
    });
    return positionedEdge;
  });
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(extractPositionedEdges, "extractPositionedEdges");

// src/rendering-util/layout-algorithms/cose-bilkent/layout.ts
async function executeCoseBilkentLayout(data, _config) {
  _chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .log */ .Rm.debug("Starting cose-bilkent layout algorithm");
  try {
    validateLayoutData(data);
    const cy = await createCytoscapeInstance(data);
    const positionedNodes = extractPositionedNodes(cy);
    const positionedEdges = extractPositionedEdges(cy);
    _chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .log */ .Rm.debug(`Layout completed: ${positionedNodes.length} nodes, ${positionedEdges.length} edges`);
    return {
      nodes: positionedNodes,
      edges: positionedEdges
    };
  } catch (error) {
    _chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .log */ .Rm.error("Error in cose-bilkent layout algorithm:", error);
    throw error;
  }
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(executeCoseBilkentLayout, "executeCoseBilkentLayout");
function validateLayoutData(data) {
  if (!data) {
    throw new Error("Layout data is required");
  }
  if (!data.config) {
    throw new Error("Configuration is required in layout data");
  }
  if (!data.rootNode) {
    throw new Error("Root node is required");
  }
  if (!data.nodes || !Array.isArray(data.nodes)) {
    throw new Error("No nodes found in layout data");
  }
  if (!Array.isArray(data.edges)) {
    throw new Error("Edges array is required in layout data");
  }
  return true;
}
(0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(validateLayoutData, "validateLayoutData");

// src/rendering-util/layout-algorithms/cose-bilkent/render.ts
var render = /* @__PURE__ */ (0,_chunk_AGHRB4JF_mjs__WEBPACK_IMPORTED_MODULE_0__/* .__name */ .K2)(async (data4Layout, svg, {
  insertCluster,
  insertEdge,
  insertEdgeLabel,
  insertMarkers,
  insertNode,
  log: log2,
  positionEdgeLabel
}, { algorithm: _algorithm }) => {
  const nodeDb = {};
  const clusterDb = {};
  const element = svg.select("g");
  insertMarkers(element, data4Layout.markers, data4Layout.type, data4Layout.diagramId);
  const subGraphsEl = element.insert("g").attr("class", "subgraphs");
  const edgePaths = element.insert("g").attr("class", "edgePaths");
  const edgeLabels = element.insert("g").attr("class", "edgeLabels");
  const nodes = element.insert("g").attr("class", "nodes");
  log2.debug("Inserting nodes into DOM for dimension calculation");
  await Promise.all(
    data4Layout.nodes.map(async (node) => {
      if (node.isGroup) {
        const clusterNode = { ...node };
        clusterDb[node.id] = clusterNode;
        nodeDb[node.id] = clusterNode;
        await insertCluster(subGraphsEl, node);
      } else {
        const nodeWithPosition = { ...node };
        nodeDb[node.id] = nodeWithPosition;
        const nodeEl = await insertNode(nodes, node, {
          config: data4Layout.config,
          dir: data4Layout.direction || "TB"
        });
        const boundingBox = nodeEl.node().getBBox();
        nodeWithPosition.width = boundingBox.width;
        nodeWithPosition.height = boundingBox.height;
        nodeWithPosition.domId = nodeEl;
        log2.debug(`Node ${node.id} dimensions: ${boundingBox.width}x${boundingBox.height}`);
      }
    })
  );
  log2.debug("Running cose-bilkent layout algorithm");
  const updatedLayoutData = {
    ...data4Layout,
    nodes: data4Layout.nodes.map((node) => {
      const nodeWithDimensions = nodeDb[node.id];
      return {
        ...node,
        width: nodeWithDimensions.width,
        height: nodeWithDimensions.height
      };
    })
  };
  const layoutResult = await executeCoseBilkentLayout(updatedLayoutData, data4Layout.config);
  log2.debug("Positioning nodes based on layout results");
  layoutResult.nodes.forEach((positionedNode) => {
    const node = nodeDb[positionedNode.id];
    if (node?.domId) {
      node.domId.attr(
        "transform",
        `translate(${positionedNode.x}, ${positionedNode.y})`
      );
      node.x = positionedNode.x;
      node.y = positionedNode.y;
      log2.debug(`Positioned node ${node.id} at center (${positionedNode.x}, ${positionedNode.y})`);
    }
  });
  layoutResult.edges.forEach((positionedEdge) => {
    const edge = data4Layout.edges.find((e) => e.id === positionedEdge.id);
    if (edge) {
      edge.points = [
        { x: positionedEdge.startX, y: positionedEdge.startY },
        { x: positionedEdge.midX, y: positionedEdge.midY },
        { x: positionedEdge.endX, y: positionedEdge.endY }
      ];
    }
  });
  log2.debug("Inserting and positioning edges");
  await Promise.all(
    data4Layout.edges.map(async (edge) => {
      const _edgeLabel = await insertEdgeLabel(edgeLabels, edge);
      const startNode = nodeDb[edge.start ?? ""];
      const endNode = nodeDb[edge.end ?? ""];
      if (startNode && endNode) {
        const positionedEdge = layoutResult.edges.find((e) => e.id === edge.id);
        if (positionedEdge) {
          log2.debug("APA01 positionedEdge", positionedEdge);
          const edgeWithPath = { ...edge };
          const paths = insertEdge(
            edgePaths,
            edgeWithPath,
            clusterDb,
            data4Layout.type,
            startNode,
            endNode,
            data4Layout.diagramId
          );
          positionEdgeLabel(edgeWithPath, paths);
        } else {
          const edgeWithPath = {
            ...edge,
            points: [
              { x: startNode.x || 0, y: startNode.y || 0 },
              { x: endNode.x || 0, y: endNode.y || 0 }
            ]
          };
          const paths = insertEdge(
            edgePaths,
            edgeWithPath,
            clusterDb,
            data4Layout.type,
            startNode,
            endNode,
            data4Layout.diagramId
          );
          positionEdgeLabel(edgeWithPath, paths);
        }
      }
    })
  );
  log2.debug("Cose-bilkent rendering completed");
}, "render");

// src/rendering-util/layout-algorithms/cose-bilkent/index.ts
var render2 = render;



/***/ }),

/***/ 5964:
/***/ (function(module, __unused_webpack_exports, __webpack_require__) {

(function webpackUniversalModuleDefinition(root, factory) {
	if(true)
		module.exports = factory(__webpack_require__(540));
	else {}
})(this, function(__WEBPACK_EXTERNAL_MODULE_0__) {
return /******/ (function(modules) { // webpackBootstrap
/******/ 	// The module cache
/******/ 	var installedModules = {};
/******/
/******/ 	// The require function
/******/ 	function __nested_webpack_require_659__(moduleId) {
/******/
/******/ 		// Check if module is in cache
/******/ 		if(installedModules[moduleId]) {
/******/ 			return installedModules[moduleId].exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = installedModules[moduleId] = {
/******/ 			i: moduleId,
/******/ 			l: false,
/******/ 			exports: {}
/******/ 		};
/******/
/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, __nested_webpack_require_659__);
/******/
/******/ 		// Flag the module as loaded
/******/ 		module.l = true;
/******/
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/
/******/
/******/ 	// expose the modules object (__webpack_modules__)
/******/ 	__nested_webpack_require_659__.m = modules;
/******/
/******/ 	// expose the module cache
/******/ 	__nested_webpack_require_659__.c = installedModules;
/******/
/******/ 	// identity function for calling harmony imports with the correct context
/******/ 	__nested_webpack_require_659__.i = function(value) { return value; };
/******/
/******/ 	// define getter function for harmony exports
/******/ 	__nested_webpack_require_659__.d = function(exports, name, getter) {
/******/ 		if(!__nested_webpack_require_659__.o(exports, name)) {
/******/ 			Object.defineProperty(exports, name, {
/******/ 				configurable: false,
/******/ 				enumerable: true,
/******/ 				get: getter
/******/ 			});
/******/ 		}
/******/ 	};
/******/
/******/ 	// getDefaultExport function for compatibility with non-harmony modules
/******/ 	__nested_webpack_require_659__.n = function(module) {
/******/ 		var getter = module && module.__esModule ?
/******/ 			function getDefault() { return module['default']; } :
/******/ 			function getModuleExports() { return module; };
/******/ 		__nested_webpack_require_659__.d(getter, 'a', getter);
/******/ 		return getter;
/******/ 	};
/******/
/******/ 	// Object.prototype.hasOwnProperty.call
/******/ 	__nested_webpack_require_659__.o = function(object, property) { return Object.prototype.hasOwnProperty.call(object, property); };
/******/
/******/ 	// __webpack_public_path__
/******/ 	__nested_webpack_require_659__.p = "";
/******/
/******/ 	// Load entry module and return exports
/******/ 	return __nested_webpack_require_659__(__nested_webpack_require_659__.s = 1);
/******/ })
/************************************************************************/
/******/ ([
/* 0 */
/***/ (function(module, exports) {

module.exports = __WEBPACK_EXTERNAL_MODULE_0__;

/***/ }),
/* 1 */
/***/ (function(module, exports, __nested_webpack_require_3201__) {

"use strict";


var LayoutConstants = __nested_webpack_require_3201__(0).layoutBase.LayoutConstants;
var FDLayoutConstants = __nested_webpack_require_3201__(0).layoutBase.FDLayoutConstants;
var CoSEConstants = __nested_webpack_require_3201__(0).CoSEConstants;
var CoSELayout = __nested_webpack_require_3201__(0).CoSELayout;
var CoSENode = __nested_webpack_require_3201__(0).CoSENode;
var PointD = __nested_webpack_require_3201__(0).layoutBase.PointD;
var DimensionD = __nested_webpack_require_3201__(0).layoutBase.DimensionD;

var defaults = {
  // Called on `layoutready`
  ready: function ready() {},
  // Called on `layoutstop`
  stop: function stop() {},
  // 'draft', 'default' or 'proof" 
  // - 'draft' fast cooling rate 
  // - 'default' moderate cooling rate 
  // - "proof" slow cooling rate
  quality: 'default',
  // include labels in node dimensions
  nodeDimensionsIncludeLabels: false,
  // number of ticks per frame; higher is faster but more jerky
  refresh: 30,
  // Whether to fit the network view after when done
  fit: true,
  // Padding on fit
  padding: 10,
  // Whether to enable incremental mode
  randomize: true,
  // Node repulsion (non overlapping) multiplier
  nodeRepulsion: 4500,
  // Ideal edge (non nested) length
  idealEdgeLength: 50,
  // Divisor to compute edge forces
  edgeElasticity: 0.45,
  // Nesting factor (multiplier) to compute ideal edge length for nested edges
  nestingFactor: 0.1,
  // Gravity force (constant)
  gravity: 0.25,
  // Maximum number of iterations to perform
  numIter: 2500,
  // For enabling tiling
  tile: true,
  // Type of layout animation. The option set is {'during', 'end', false}
  animate: 'end',
  // Duration for animate:end
  animationDuration: 500,
  // Represents the amount of the vertical space to put between the zero degree members during the tiling operation(can also be a function)
  tilingPaddingVertical: 10,
  // Represents the amount of the horizontal space to put between the zero degree members during the tiling operation(can also be a function)
  tilingPaddingHorizontal: 10,
  // Gravity range (constant) for compounds
  gravityRangeCompound: 1.5,
  // Gravity force (constant) for compounds
  gravityCompound: 1.0,
  // Gravity range (constant)
  gravityRange: 3.8,
  // Initial cooling factor for incremental layout
  initialEnergyOnIncremental: 0.5
};

function extend(defaults, options) {
  var obj = {};

  for (var i in defaults) {
    obj[i] = defaults[i];
  }

  for (var i in options) {
    obj[i] = options[i];
  }

  return obj;
};

function _CoSELayout(_options) {
  this.options = extend(defaults, _options);
  getUserOptions(this.options);
}

var getUserOptions = function getUserOptions(options) {
  if (options.nodeRepulsion != null) CoSEConstants.DEFAULT_REPULSION_STRENGTH = FDLayoutConstants.DEFAULT_REPULSION_STRENGTH = options.nodeRepulsion;
  if (options.idealEdgeLength != null) CoSEConstants.DEFAULT_EDGE_LENGTH = FDLayoutConstants.DEFAULT_EDGE_LENGTH = options.idealEdgeLength;
  if (options.edgeElasticity != null) CoSEConstants.DEFAULT_SPRING_STRENGTH = FDLayoutConstants.DEFAULT_SPRING_STRENGTH = options.edgeElasticity;
  if (options.nestingFactor != null) CoSEConstants.PER_LEVEL_IDEAL_EDGE_LENGTH_FACTOR = FDLayoutConstants.PER_LEVEL_IDEAL_EDGE_LENGTH_FACTOR = options.nestingFactor;
  if (options.gravity != null) CoSEConstants.DEFAULT_GRAVITY_STRENGTH = FDLayoutConstants.DEFAULT_GRAVITY_STRENGTH = options.gravity;
  if (options.numIter != null) CoSEConstants.MAX_ITERATIONS = FDLayoutConstants.MAX_ITERATIONS = options.numIter;
  if (options.gravityRange != null) CoSEConstants.DEFAULT_GRAVITY_RANGE_FACTOR = FDLayoutConstants.DEFAULT_GRAVITY_RANGE_FACTOR = options.gravityRange;
  if (options.gravityCompound != null) CoSEConstants.DEFAULT_COMPOUND_GRAVITY_STRENGTH = FDLayoutConstants.DEFAULT_COMPOUND_GRAVITY_STRENGTH = options.gravityCompound;
  if (options.gravityRangeCompound != null) CoSEConstants.DEFAULT_COMPOUND_GRAVITY_RANGE_FACTOR = FDLayoutConstants.DEFAULT_COMPOUND_GRAVITY_RANGE_FACTOR = options.gravityRangeCompound;
  if (options.initialEnergyOnIncremental != null) CoSEConstants.DEFAULT_COOLING_FACTOR_INCREMENTAL = FDLayoutConstants.DEFAULT_COOLING_FACTOR_INCREMENTAL = options.initialEnergyOnIncremental;

  if (options.quality == 'draft') LayoutConstants.QUALITY = 0;else if (options.quality == 'proof') LayoutConstants.QUALITY = 2;else LayoutConstants.QUALITY = 1;

  CoSEConstants.NODE_DIMENSIONS_INCLUDE_LABELS = FDLayoutConstants.NODE_DIMENSIONS_INCLUDE_LABELS = LayoutConstants.NODE_DIMENSIONS_INCLUDE_LABELS = options.nodeDimensionsIncludeLabels;
  CoSEConstants.DEFAULT_INCREMENTAL = FDLayoutConstants.DEFAULT_INCREMENTAL = LayoutConstants.DEFAULT_INCREMENTAL = !options.randomize;
  CoSEConstants.ANIMATE = FDLayoutConstants.ANIMATE = LayoutConstants.ANIMATE = options.animate;
  CoSEConstants.TILE = options.tile;
  CoSEConstants.TILING_PADDING_VERTICAL = typeof options.tilingPaddingVertical === 'function' ? options.tilingPaddingVertical.call() : options.tilingPaddingVertical;
  CoSEConstants.TILING_PADDING_HORIZONTAL = typeof options.tilingPaddingHorizontal === 'function' ? options.tilingPaddingHorizontal.call() : options.tilingPaddingHorizontal;
};

_CoSELayout.prototype.run = function () {
  var ready;
  var frameId;
  var options = this.options;
  var idToLNode = this.idToLNode = {};
  var layout = this.layout = new CoSELayout();
  var self = this;

  self.stopped = false;

  this.cy = this.options.cy;

  this.cy.trigger({ type: 'layoutstart', layout: this });

  var gm = layout.newGraphManager();
  this.gm = gm;

  var nodes = this.options.eles.nodes();
  var edges = this.options.eles.edges();

  this.root = gm.addRoot();
  this.processChildrenList(this.root, this.getTopMostNodes(nodes), layout);

  for (var i = 0; i < edges.length; i++) {
    var edge = edges[i];
    var sourceNode = this.idToLNode[edge.data("source")];
    var targetNode = this.idToLNode[edge.data("target")];
    if (sourceNode !== targetNode && sourceNode.getEdgesBetween(targetNode).length == 0) {
      var e1 = gm.add(layout.newEdge(), sourceNode, targetNode);
      e1.id = edge.id();
    }
  }

  var getPositions = function getPositions(ele, i) {
    if (typeof ele === "number") {
      ele = i;
    }
    var theId = ele.data('id');
    var lNode = self.idToLNode[theId];

    return {
      x: lNode.getRect().getCenterX(),
      y: lNode.getRect().getCenterY()
    };
  };

  /*
   * Reposition nodes in iterations animatedly
   */
  var iterateAnimated = function iterateAnimated() {
    // Thigs to perform after nodes are repositioned on screen
    var afterReposition = function afterReposition() {
      if (options.fit) {
        options.cy.fit(options.eles, options.padding);
      }

      if (!ready) {
        ready = true;
        self.cy.one('layoutready', options.ready);
        self.cy.trigger({ type: 'layoutready', layout: self });
      }
    };

    var ticksPerFrame = self.options.refresh;
    var isDone;

    for (var i = 0; i < ticksPerFrame && !isDone; i++) {
      isDone = self.stopped || self.layout.tick();
    }

    // If layout is done
    if (isDone) {
      // If the layout is not a sublayout and it is successful perform post layout.
      if (layout.checkLayoutSuccess() && !layout.isSubLayout) {
        layout.doPostLayout();
      }

      // If layout has a tilingPostLayout function property call it.
      if (layout.tilingPostLayout) {
        layout.tilingPostLayout();
      }

      layout.isLayoutFinished = true;

      self.options.eles.nodes().positions(getPositions);

      afterReposition();

      // trigger layoutstop when the layout stops (e.g. finishes)
      self.cy.one('layoutstop', self.options.stop);
      self.cy.trigger({ type: 'layoutstop', layout: self });

      if (frameId) {
        cancelAnimationFrame(frameId);
      }

      ready = false;
      return;
    }

    var animationData = self.layout.getPositionsData(); // Get positions of layout nodes note that all nodes may not be layout nodes because of tiling

    // Position nodes, for the nodes whose id does not included in data (because they are removed from their parents and included in dummy compounds)
    // use position of their ancestors or dummy ancestors
    options.eles.nodes().positions(function (ele, i) {
      if (typeof ele === "number") {
        ele = i;
      }
      // If ele is a compound node, then its position will be defined by its children
      if (!ele.isParent()) {
        var theId = ele.id();
        var pNode = animationData[theId];
        var temp = ele;
        // If pNode is undefined search until finding position data of its first ancestor (It may be dummy as well)
        while (pNode == null) {
          pNode = animationData[temp.data('parent')] || animationData['DummyCompound_' + temp.data('parent')];
          animationData[theId] = pNode;
          temp = temp.parent()[0];
          if (temp == undefined) {
            break;
          }
        }
        if (pNode != null) {
          return {
            x: pNode.x,
            y: pNode.y
          };
        } else {
          return {
            x: ele.position('x'),
            y: ele.position('y')
          };
        }
      }
    });

    afterReposition();

    frameId = requestAnimationFrame(iterateAnimated);
  };

  /*
  * Listen 'layoutstarted' event and start animated iteration if animate option is 'during'
  */
  layout.addListener('layoutstarted', function () {
    if (self.options.animate === 'during') {
      frameId = requestAnimationFrame(iterateAnimated);
    }
  });

  layout.runLayout(); // Run cose layout

  /*
   * If animate option is not 'during' ('end' or false) perform these here (If it is 'during' similar things are already performed)
   */
  if (this.options.animate !== "during") {
    self.options.eles.nodes().not(":parent").layoutPositions(self, self.options, getPositions); // Use layout positions to reposition the nodes it considers the options parameter
    ready = false;
  }

  return this; // chaining
};

//Get the top most ones of a list of nodes
_CoSELayout.prototype.getTopMostNodes = function (nodes) {
  var nodesMap = {};
  for (var i = 0; i < nodes.length; i++) {
    nodesMap[nodes[i].id()] = true;
  }
  var roots = nodes.filter(function (ele, i) {
    if (typeof ele === "number") {
      ele = i;
    }
    var parent = ele.parent()[0];
    while (parent != null) {
      if (nodesMap[parent.id()]) {
        return false;
      }
      parent = parent.parent()[0];
    }
    return true;
  });

  return roots;
};

_CoSELayout.prototype.processChildrenList = function (parent, children, layout) {
  var size = children.length;
  for (var i = 0; i < size; i++) {
    var theChild = children[i];
    var children_of_children = theChild.children();
    var theNode;

    var dimensions = theChild.layoutDimensions({
      nodeDimensionsIncludeLabels: this.options.nodeDimensionsIncludeLabels
    });

    if (theChild.outerWidth() != null && theChild.outerHeight() != null) {
      theNode = parent.add(new CoSENode(layout.graphManager, new PointD(theChild.position('x') - dimensions.w / 2, theChild.position('y') - dimensions.h / 2), new DimensionD(parseFloat(dimensions.w), parseFloat(dimensions.h))));
    } else {
      theNode = parent.add(new CoSENode(this.graphManager));
    }
    // Attach id to the layout node
    theNode.id = theChild.data("id");
    // Attach the paddings of cy node to layout node
    theNode.paddingLeft = parseInt(theChild.css('padding'));
    theNode.paddingTop = parseInt(theChild.css('padding'));
    theNode.paddingRight = parseInt(theChild.css('padding'));
    theNode.paddingBottom = parseInt(theChild.css('padding'));

    //Attach the label properties to compound if labels will be included in node dimensions  
    if (this.options.nodeDimensionsIncludeLabels) {
      if (theChild.isParent()) {
        var labelWidth = theChild.boundingBox({ includeLabels: true, includeNodes: false }).w;
        var labelHeight = theChild.boundingBox({ includeLabels: true, includeNodes: false }).h;
        var labelPos = theChild.css("text-halign");
        theNode.labelWidth = labelWidth;
        theNode.labelHeight = labelHeight;
        theNode.labelPos = labelPos;
      }
    }

    // Map the layout node
    this.idToLNode[theChild.data("id")] = theNode;

    if (isNaN(theNode.rect.x)) {
      theNode.rect.x = 0;
    }

    if (isNaN(theNode.rect.y)) {
      theNode.rect.y = 0;
    }

    if (children_of_children != null && children_of_children.length > 0) {
      var theNewGraph;
      theNewGraph = layout.getGraphManager().add(layout.newGraph(), theNode);
      this.processChildrenList(theNewGraph, children_of_children, layout);
    }
  }
};

/**
 * @brief : called on continuous layouts to stop them before they finish
 */
_CoSELayout.prototype.stop = function () {
  this.stopped = true;

  return this; // chaining
};

var register = function register(cytoscape) {
  //  var Layout = getLayout( cytoscape );

  cytoscape('layout', 'cose-bilkent', _CoSELayout);
};

// auto reg for globals
if (typeof cytoscape !== 'undefined') {
  register(cytoscape);
}

module.exports = register;

/***/ })
/******/ ]);
});

/***/ })

}]);