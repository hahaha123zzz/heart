import type { StoreApi, UseBoundStore } from 'zustand'
export function createSelectors<T extends object>(store: UseBoundStore<StoreApi<T>>) {
  const result = store as typeof store & { use: { [K in keyof T]: () => T[K] } }
  result.use = {} as typeof result.use
  for (const key of Object.keys(store.getState()) as (keyof T)[]) result.use[key] = () => store(state => state[key])
  return result
}
