"""原图身份、临时模型消息、配对顺序与跨轮限额。"""
import json
import unittest
from unittest.mock import Mock, patch
from agents.transient_messages import with_transient_model_messages, extend_transient_model_messages
from knowledge.answer_media import current_media, model_message
from knowledge.figures import get_figure, retrieve_figures, load_figures


class AnswerMediaTests(unittest.TestCase):
    def test_loop_consumes_tool_images_and_state_never_contains_base64(self):
        from agents.agent_loop import LocalAgentLoop
        from agents.tool_protocol import BaseTool, ToolDefinition, ToolResult, ToolRegistry
        from tests.test_q3_agent_loop import ScriptedLLM, request, tool_round, final_round
        class ImageTool(BaseTool):
            definition = ToolDefinition('picture', '原图')
            def run(self, arguments, context):
                return ToolResult(content='真实图', sources=[{'source_id':'s', 'image_refs':[{'id':'img'}]}],
                    model_message={'role':'user', '_media_ids':['img'], 'content':[
                        {'type':'image_url', 'image_url':{'url':'data:image/png;base64,eA=='}}]})
        registry = ToolRegistry(); registry.register(ImageTool())
        llm = ScriptedLLM([tool_round(('picture', {})), final_round('图示说明')])
        result = LocalAgentLoop(llm).run(request(llm, registry))
        self.assertTrue(result.completed)
        self.assertEqual([m['role'] for m in llm.calls[1]['messages']], ['system','user','assistant','tool','user'])
        self.assertTrue(result.sources[0]['image_refs'][0]['model_saw_pixels'])
        self.assertNotIn('base64', json.dumps(result.state()))

    def test_images_follow_complete_tool_batch_and_do_not_enter_history(self):
        history = [{'role': 'assistant', 'tool_calls': [{'id': 'a'}, {'id': 'b'}]},
                   {'role': 'tool', 'tool_call_id': 'a', 'content': '原文1'},
                   {'role': 'tool', 'tool_call_id': 'b', 'content': '原文2'}]
        image = {'_after_tool_call_id': 'a', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,eA=='}}]}
        wire = with_transient_model_messages(history, [image])
        self.assertEqual([m['role'] for m in wire], ['assistant', 'tool', 'tool', 'user'])
        self.assertNotIn('base64', json.dumps(history))
        transient = []
        for i in range(5):
            extend_transient_model_messages(transient, [{**image, '_media_ids': [str(i)]}])
        self.assertEqual(len(transient), 2)
        self.assertEqual(transient[-1]['_media_ids'], ['4'])

    def test_plain_comparison_does_not_attach_section_images(self):
        self.assertEqual(retrieve_figures('用对照表比较被试内与被试间设计', []), [])

    def test_qr_is_not_an_experimental_figure(self):
        self.assertIsNone(get_figure('image-05-0002'))

    def test_pixels_are_current_and_can_be_disabled_without_claiming_seen(self):
        figures = [f for f in load_figures() if f.is_valid()]
        if not figures:
            self.skipTest('工作区没有教材原图')
        figure = figures[0]
        ref = figure.public()
        self.assertEqual(current_media([ref])[0][1].sha256, figure.sha256)
        message = model_message([ref])
        self.assertTrue(message['content'][1]['image_url']['url'].startswith('data:image/'))
        self.assertNotIn('model_saw_pixels', ref)
        with patch.dict('os.environ', LLM_VISION_ENABLED='0'):
            self.assertIsNone(model_message([ref]))
        self.assertEqual(current_media([{**ref, 'sha256': '0' * 64}]), [])
        self.assertEqual(current_media([{**ref, 'document_id': 'another-course'}]), [])
        self.assertEqual(current_media([{**ref, 'document_id': 'another-course'}]), [])


if __name__ == '__main__':
    unittest.main()
