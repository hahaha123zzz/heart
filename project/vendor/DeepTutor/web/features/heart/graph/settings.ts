import { create } from 'zustand'
import { createSelectors } from './selectors'
// 只保留只读图谱显示配置，不导入原版后台设置和存储。
export const useSettingsStore = createSelectors(create(() => ({ enableHideUnselectedEdges: false, enableEdgeEvents: true, showEdgeLabel: false, showNodeLabel: true, minEdgeSize: 0.5, maxEdgeSize: 2 })))
