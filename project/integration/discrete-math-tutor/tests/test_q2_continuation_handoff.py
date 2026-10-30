"""集成窗口接续候选补丁的检查；不属于目标质量提交。"""
import unittest


class ContinuationHandoffTests(unittest.TestCase):
    def test_continuation_budget_uses_action_and_keeps_rephrase_short(self):
        from agents.reply_budget import reply_budget
        from agents.task_execution import TaskExecution
        execution = TaskExecution(learning_intents=['explain'], targets=[{
            'kind': 'course_navigation', 'mode': 'repeat', 'continuation_action': 'continue_current'}])
        self.assertEqual(reply_budget('继续这个例子', execution=execution).maximum, 360)
        execution.targets[0]['continuation_action'] = 'rephrase_current'
        self.assertEqual(reply_budget('没听懂', execution=execution).maximum, 260)

