import { apiFetch } from "@/shared/api/client";

export interface LearningJournal {
  version: number;
  updated_at: string;
  mission: { topic: string; why: string; level: string; updated_at: string };
  last_session: { summary: string; next_focus: string; updated_at: string };
  records: { id: string; title: string; insight: string; created_at: string }[];
  injected_context: string;
  next_offset?: number | null;
}

export async function getLearningJournal(signal?: AbortSignal, offset = 0): Promise<LearningJournal> {
  const response = await apiFetch(`/api/learning-journal?limit=20&offset=${offset}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`Learning journal request failed: ${response.status}`);
  return response.json();
}
