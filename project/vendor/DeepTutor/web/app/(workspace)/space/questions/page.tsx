import { redirect } from "next/navigation";

export default function QuestionBankPage() {
  // 题库管理并入练习页，保留旧链接不产生 404。
  redirect("/learning/practice");
}
