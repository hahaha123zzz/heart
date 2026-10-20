"""独立 PDF 的真实字符、旋转、多页裁图及不可信引用协议回归。"""
import hashlib,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import fitz
from knowledge.citation_index import CitationIndex,build_index,pdf_characters,_rectangles
from knowledge.grounded_citations import EvidenceBundle,CitationGroundingError,choose_evidence,claims_for,selection_evidence
from knowledge.grounding_text import normalized,normalized_with_map,selection_ranges
from knowledge.source_mapping import source_spans
from knowledge.textbook import TextbookChunk


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);directory=self.root/'chapters/chapter_01';directory.mkdir(parents=True)
        self.pdf=directory/'chapter_01.generated.pdf'
        self.quote='The first condition is necessary. A value of -10 is not 10.'
        with fitz.open() as pdf:
            page=pdf.new_page();page.insert_text((70,90),self.quote)
            page.insert_text((70,120),'Repeated phrase.');page.insert_text((70,150),'Unique boundary before the second page.')
            page=pdf.new_page();page.insert_text((70,90),'Repeated phrase.')
            page.insert_text((70,120),'The final condition must also hold.')
            page.set_cropbox(fitz.Rect(30,50,570,750));page.set_rotation(90)
            pdf.save(self.pdf)
        self.record={'document_id':'experimental-psychology-3:chapter-01','version':hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
            'chapter_id':1,'source':'fixture.docx','page_count':2,'sections':[{'id':1,'title':'条件','page':1,'y':0,'verified':True}]}
        blocks=[{'block_index':i,'kind':'paragraph','text':t,'section_id':1} for i,t in enumerate([
            self.quote,'Repeated phrase.','Unique boundary before the second page.','Repeated phrase.','The final condition must also hold.'])]
        (directory/'document.json').write_text(json.dumps({'blocks':blocks}),encoding='utf-8')
        (self.root/'pdf_manifest.json').write_text(json.dumps([self.record]),encoding='utf-8')
        self.path=self.root/'positions.sqlite3';self.report=build_index(self.path,self.root)
        self.index=CitationIndex(self.path);self.addCleanup(self.index.close)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name,value in [('knowledge.pdf_reader.documents',lambda:[self.record]),('knowledge.grounded_citations.documents',lambda:[self.record]),
            ('knowledge.pdf_reader.pdf_path',lambda r:self.pdf),('knowledge.grounded_citations.pdf_path',lambda r:self.pdf),
            ('knowledge.pdf_reader.CROPS',self.root/'crops'),('knowledge.pdf_reader.get_section',lambda *a:{'content':self.quote})]:
            self.stack.enter_context(patch(name,value))

    def locate(self,quote,block=None):
        return self.index.locate(self.record['document_id'],self.record['version'],quote,block_id=block)

    def bundle(self,quote=None,block=0):
        quote=quote or self.quote;located=self.locate(quote,block)
        item={'evidence_id':'stable','document_id':self.record['document_id'],'document_version':self.record['version'],
            'source_block_id':block,'section_id':1,'quote':quote,'location_status':'exact','rects':located['rects']}
        source=TextbookChunk('fixture.docx','条件',quote,frozenset(),chapter_id=1,section_id=1,block_start=0,block_end=4)
        return EvidenceBundle([source],[item],[source])

    def test_normalization_keeps_semantic_symbols_and_reverse_offsets(self):
        text='Ａ \n-１０ ≠ 10'
        folded,mapping=normalized_with_map(text)
        self.assertEqual(folded,'A-10≠10')
        self.assertEqual(text[mapping[1]],'-')
        self.assertEqual(selection_ranges('ab ab','ab'),[(0,2),(3,5)])
        self.assertNotEqual(normalized('-10'),normalized('10'))
        self.assertNotEqual(normalized('x²'),normalized('x2'))
        self.assertNotEqual(normalized('H₂O'),normalized('H2O'))

    def test_repeated_global_quote_requires_block_disambiguation(self):
        self.assertEqual(self.locate('Repeated phrase.')['status'],'ambiguous')
        self.assertEqual(self.locate('Repeated phrase.',1)['rects'][0]['page'],1)
        self.assertEqual(self.locate('Repeated phrase.',3)['rects'][0]['page'],2)
        with self.assertRaises(ValueError):self.index.locate(self.record['document_id'],'0'*64,self.quote)
        self.assertEqual(self.locate(self.quote.replace('-10','10'),0)['status'],'unlocated')

    def test_real_rotated_glyphs_crop_and_same_saved_location(self):
        quote='The final condition must also hold.'
        ref=self.bundle(quote,4).references('最后条件必须成立。[1]')[0]
        selected=ref['evidence']['selections'][0]
        self.assertEqual(ref['selection_ref']['rects'],selected['rects'])
        self.assertEqual(selected['rects'][0]['page'],2)
        self.assertIn(normalized(quote),normalized(selected['text']))
        self.assertTrue(list((self.root/'crops').glob('*.png')))

    def test_image_only_selection_is_page_source_not_fabricated_exact_text(self):
        from knowledge.pdf_reader import PDFSelection,resolve_selection
        with fitz.open() as pdf:
            page=pdf.new_page();page.draw_circle((120,120),30);pdf.save(self.pdf)
        self.record['version']=hashlib.sha256(self.pdf.read_bytes()).hexdigest();self.record['page_count']=1
        selected=resolve_selection(PDFSelection(document_id=self.record['document_id'],version=self.record['version'],kind='area',
            rects=[dict(page=1,x1=.1,y1=.08,x2=.35,y2=.25)]))
        llm=SimpleNamespace(chat_json=Mock())
        bundle=selection_evidence(llm,'解释原图',selected,self.path)
        ref=bundle.references('圈选内容是圆形。[1]')[0]
        llm.chat_json.assert_not_called()
        self.assertEqual(ref['evidence']['location_status'],'page')
        self.assertEqual(ref['selection_ref']['page'],1)
        self.assertEqual(ref['selection_ref']['rects'],[])

    def test_missing_crop_quote_downgrades_without_fake_highlight(self):
        bundle=self.bundle()
        with patch('knowledge.grounded_citations.evidence_text',return_value='裁图不含完整引句'):
            ref=bundle.references('结论。[1]')[0]
        self.assertEqual(ref['evidence']['location_status'],'section')
        self.assertEqual(ref['selection_ref']['rects'],[])
        self.assertEqual(ref['evidence']['selections'],[])

    def test_attachment_rejects_no_marker_foreign_marker_and_stale_pdf(self):
        for text in ('没有编号','结论[2]','[1]'):
            with self.subTest(text=text),self.assertRaises(CitationGroundingError):self.bundle().references(text)
        bundle=self.bundle();self.pdf.write_bytes(self.pdf.read_bytes()+b' changed')
        with self.assertRaises(CitationGroundingError):bundle.references('结论[1]')

    def test_checked_question_can_have_no_marker_but_foreign_marker_still_fails(self):
        self.assertEqual(self.bundle().references('哪一个条件没有满足？',allow_uncited_question=True),[])
        with self.assertRaises(CitationGroundingError):self.bundle().references('请看[99]',allow_uncited_question=True)

    def test_multiple_evidence_ids_bind_same_claim(self):
        claims=claims_for('第一项。[1][2]\n第二项。[2]')
        self.assertEqual(claims[0]['markers'],[1,2])
        self.assertEqual(claims[1]['text'],'第二项。')

    def test_selection_only_allows_server_ids_not_model_geometry(self):
        def choose(messages,**kw):
            payload=json.loads(messages[1]['content'])
            return {'evidence_ids':[payload['candidates'][0]['evidence_id']]}
        llm=SimpleNamespace(chat_json=Mock(side_effect=choose))
        sources=self.bundle().sources
        bundle=choose_evidence(llm,'解释条件',sources,self.path)
        self.assertEqual(bundle.evidence[0]['quote'],self.quote)
        llm.chat_json=Mock(return_value={'evidence_ids':['forged']})
        with self.assertRaises(CitationGroundingError):choose_evidence(llm,'解释条件',sources,self.path)
        llm.chat_json=Mock(return_value={'evidence_ids':['forged'],'rects':[]})
        with self.assertRaises(ValueError):choose_evidence(llm,'解释条件',sources,self.path)

    def test_quote_lookup_does_not_let_model_choose_ambiguous_or_invented_origin(self):
        llm=SimpleNamespace(chat_json=Mock())
        for quote in ('Repeated phrase.','An invented quotation.'):
            with self.subTest(quote=quote),self.assertRaises(CitationGroundingError):
                choose_evidence(llm,f'请核对“{quote}”的教材出处。',self.bundle().sources,self.path)
        llm.chat_json.assert_not_called()

    def test_selector_receives_referent_history_without_old_numbers(self):
        def choose(messages,**kw):
            payload=json.loads(messages[1]['content'])
            self.assertEqual(payload['conversation_context'][0]['content'],'必要条件（历史引用）')
            return {'evidence_ids':[payload['candidates'][0]['evidence_id']]}
        history=[{'role':'assistant','content':'必要条件[9]'}]
        choose_evidence(SimpleNamespace(chat_json=choose),'我还是不懂',self.bundle().sources,self.path,history=history)
        self.assertEqual(history[0]['content'],'必要条件[9]')

    def test_generator_does_not_reuse_previous_turn_citation_numbers(self):
        from agents.response_generator import ResponseGenerator
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState
        llm=SimpleNamespace(mock=False,chat=Mock(return_value='解释。[1]'))
        history=[{'role':'assistant','content':'上一轮定义。[9]'}]
        ResponseGenerator(llm).generate(StudentState(),TeachingPlan(goal='条件',strategy='worked_example',action='explain',difficulty='easy'),
            '继续解释',history,None,'',textbook_excerpts='[1] fixture｜条件｜证据ID:stable\n'+self.quote)
        messages=llm.chat.call_args.args[0]
        self.assertIn('历史中的编号全部失效',messages[0]['content'])
        self.assertNotIn('[9]',messages[1]['content'])
        self.assertEqual(history[0]['content'],'上一轮定义。[9]')

    def test_grounded_check_question_preserves_options_without_answer_metadata(self):
        from agents.response_generator import ResponseGenerator
        from agents.question_designer import QuestionSpec,QuestionOption
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState
        llm=SimpleNamespace(mock=False,chat=Mock())
        spec=QuestionSpec(stem='哪一个条件缺失？',options=[QuestionOption(text=t,correct=i==1,maps_to='内部误解') for i,t in enumerate(('条件一','条件二','条件三'))],acceptable_free_answer='内部标准答案')
        reply=ResponseGenerator(llm).generate(StudentState(),TeachingPlan(goal='条件',strategy='retrieval_practice',action='ask_question',difficulty='easy'),
            '我明白了',[],spec,'',textbook_excerpts='[1] fixture｜条件｜证据ID:stable\n'+self.quote,answer_feedback={'mode':'check_self_report'})
        self.assertIn('A. 条件一',reply);self.assertIn('C. 条件三',reply)
        self.assertNotIn('内部',reply);self.assertNotIn('correct',reply)
        llm.chat.assert_not_called()

    def test_partial_multi_block_source_mapping_and_table_offsets(self):
        first='第一段开头。'+'甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥'
        second='天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往。第二段末尾。'
        text=first[6:]+'\n'+second[:-7]
        blocks=[{'block_index':1,'kind':'paragraph','text':first},{'block_index':2,'kind':'paragraph','text':second}]
        spans=source_spans(blocks,text)
        self.assertEqual({s['block_id'] for s in spans},{1,2})
        for span in spans:
            original=blocks[span['block_id']-1]['text'][span['block_start']:span['block_end']]
            self.assertEqual(normalized(text[span['text_start']:span['text_end']]),normalized(original))
        table='aa | bb\ncc | dd'
        span=source_spans([{'block_index':3,'kind':'table','rows':[['aa','bb'],['cc','dd']]}],table)[0]
        self.assertEqual(span['text_end'],len(table))

    def test_long_three_page_evidence_splits_without_losing_last_line(self):
        with fitz.open() as pdf:
            for number in range(3):
                page=pdf.new_page()
                for line in range(90):
                    text=f'Page {number+1} line {line:03}: The prerequisite is mandatory; preserve all conditions and the final line.'
                    page.insert_text((50,40+line*8),text,fontsize=6)
            pdf.save(self.pdf)
        self.record['version']=hashlib.sha256(self.pdf.read_bytes()).hexdigest();self.record['page_count']=3
        text,glyphs,_=pdf_characters(self.pdf)
        source=TextbookChunk('fixture.docx','条件',text,frozenset(),chapter_id=1,section_id=1)
        item={'evidence_id':'large','document_id':self.record['document_id'],'document_version':self.record['version'],
            'source_block_id':0,'section_id':1,'quote':text,'location_status':'exact','rects':_rectangles([g for g in glyphs if g])}
        ref=EvidenceBundle([source],[item],[source]).references('所有条件都必须保留。[1]')[0]
        selections=ref['evidence']['selections']
        self.assertEqual(ref['evidence']['location_status'],'exact')
        self.assertEqual({r['page'] for s in selections for r in s['rects']},{1,2,3})
        self.assertTrue(all(len(s['rects'])<=80 and len(s['text'])<=4000 for s in selections))
        self.assertIn(normalized(text),normalized(''.join(s['text'] for s in selections)))

    def test_incomplete_release_cannot_activate_index(self):
        from scripts.switch_citation_index import approved
        report={'schema':'citation-grounding-v1','index_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(ValueError,'门槛'):approved(report,self.path)

    def test_atomic_activation_disable_and_rollback_in_isolated_directory(self):
        from scripts import switch_citation_index as switcher
        report={'schema':'citation-grounding-v1','index_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),
            'gates':dict.fromkeys(switcher.GATES,'passed'),'metrics':{'semantic_support':.95,'exact_precision':.98,'exact_coverage':.95},
            'real_model_runs':160,'reviewed_holdout_cases':30}
        acceptance=self.root/'synthetic-acceptance.json';acceptance.write_text(json.dumps(report),encoding='utf-8')
        pointer=self.root/'live/citation_index.json'
        with patch.object(switcher,'POINTER',pointer),patch.object(switcher,'documents',lambda:[self.record]),patch.object(switcher,'pdf_path',lambda r:self.pdf):
            for args,enabled in ((['--enable',str(self.path),'--acceptance',str(acceptance)],True),(['--disable'],False),(['--rollback'],True)):
                with patch('sys.argv',['switch_citation_index',*args]),patch('builtins.print'):switcher.main()
                self.assertEqual(json.loads(pointer.read_text(encoding='utf-8'))['enabled'],enabled)
            active=json.loads(pointer.read_text(encoding='utf-8'))
            copied=pointer.parent/active['path'];self.assertEqual(copied.read_bytes(),self.path.read_bytes())
            self.pdf.write_bytes(self.pdf.read_bytes()+b' changed')
            with self.assertRaisesRegex(ValueError,'版本'):switcher.verified_pointer(active)


if __name__=='__main__':unittest.main()
