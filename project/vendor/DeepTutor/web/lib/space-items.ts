"use client";

import {
  Bot,
  ClipboardList,
  History,
  NotebookPen,
  UserRound,
  Wand2,
  type LucideIcon,
} from "lucide-react";

export type SpaceItemKey =
  | "chat_history"
  | "agents"
  | "notebooks"
  | "question_bank"
  | "personas"
  | "skills";

export type SpaceMemoryFile = "summary" | "profile";

export interface SpaceItem {
  key: SpaceItemKey;
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const SPACE_ITEMS: SpaceItem[] = [
  {
    key: "chat_history",
    href: "/chat",
    label: "Chat History",
    description: "Review and reopen previous conversations.",
    icon: History,
  },
  {
    key: "notebooks",
    href: "/notebooks",
    label: "Notebooks",
    description:
      "Organize saved outputs from chat, research, Co-Writer, and more.",
    icon: NotebookPen,
  },
  {
    key: "question_bank",
    href: "/learning/practice",
    label: "Question Bank",
    description: "Review and organize quiz questions across sessions.",
    icon: ClipboardList,
  },
];
