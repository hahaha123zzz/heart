export const labelColorDarkTheme = '#FFFFFF'
export const LabelColorHighlightedDarkTheme = '#000000'
export const labelColorLightTheme = '#000'
export const nodeColorDisabled = '#E2E2E2'
export const nodeBorderColor = '#EEEEEE'
export const nodeBorderColorSelected = '#F57F17'
export const edgeColorDarkTheme = '#888888'
export const edgeColorSelected = '#F57F17'
export const edgeColorHighlightedDarkTheme = '#F57F17'
export const edgeColorHighlightedLightTheme = '#F57F17'
export const minNodeSize = 4
export const maxNodeSize = 20
export const LABEL_RENDER_LIMIT = 2000
export const EDGE_PERF_LIMIT = 5000
export const workerBudgetMs = (order: number): number => Math.min(1500 + order / 10, 10000)
