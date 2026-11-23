"""跨页选区必须通过请求边界，并完整进入运行时。"""
import pytest
from pydantic import ValidationError
from deeptutor.core.turn_request import TurnRequest
from deeptutor.services.session._turn_runtime_shared import _reading_viewport

def test_cross_page_regions_survive_request_and_runtime_normalization():
    pages=[{'locator':1,'quote':'第一页','rects':[[.1,.2,.5,.3]]},{'locator':2,'quote':'第二页','rects':[[.2,.1,.6,.2]]}]
    request=TurnRequest.model_validate({'content':'解释选区','reading_viewport':{'locator':1,'selection':'第一页 第二页','selection_pages':pages}})
    viewport=request.to_payload()['reading_viewport']
    assert _reading_viewport(viewport)['selection_pages']==pages

@pytest.mark.parametrize('rect', [[-.1,0,.5,.2],[0,0,float('nan'),.2],[.7,.2,.1,.3],[0,.9,.5,.2]])
def test_invalid_region_is_rejected_before_starting_a_turn(rect):
    with pytest.raises(ValidationError):
        TurnRequest.model_validate({'content':'test','reading_viewport':{'selection_pages':[{'locator':1,'quote':'中文','rects':[rect]}]}})

def test_selection_page_count_is_bounded():
    with pytest.raises(ValidationError):
        TurnRequest.model_validate({'content':'test','reading_viewport':{'selection_pages':[{'locator':1,'quote':'中文','rects':[]}] * 41}})
