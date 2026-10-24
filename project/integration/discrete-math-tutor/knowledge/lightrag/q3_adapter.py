"""现有LearningNavigator边界适配；调用方负责选择后端及正式发布。"""
import asyncio,re,time
from agents.q3_navigation import SourceRef
from .course_input import COURSE

class LightRagNavigator:
    def __init__(self, base_navigator, backend, *, course_id=COURSE, cancellation=None):
        self.base=base_navigator;self.backend=backend;self.course_id=course_id
        self.cancellation=cancellation;self.calls=[];self.last_result=None
    def resolve(self, **kwargs):return self.base.resolve(**kwargs)
    def search(self, *, target, query, limit, preferred_types=()):
        self.last_result=None
        started=time.monotonic()
        record={"query":query,"target_id":target.target_id,"requested_backend":"lightrag","fallback":False}
        self.calls.append(record)
        try:
            if self.cancellation is not None:self.cancellation.check()
            if target.source_scope.get("block_start") is not None or re.fullmatch(r"ch\d+:s\d+:b\d+",target.target_id):
                record.update(actual_backend="q2_exact",navigation_only=True,status="success")
                sources=self.base.search(target=target,query=query,limit=limit,preferred_types=preferred_types)
                record["sources"]=len(sources)
                return sources
            record.update(actual_backend="lightrag",navigation_only=False)
            self.last_result=asyncio.run(self.backend.search(query,course_id=self.course_id,limit=limit,
                chapter_id=target.chapter_id,section_id=target.section_id,cancellation=self.cancellation))
            from knowledge.course_release import binding
            release=binding();sources=[]
            for row in self.last_result["sources"]:
                fields={k:row[k] for k in ("source_id","document_id","version","chapter_id","section_id","text","quote","page","image_refs","location")}
                images=[]
                for visual in self.last_result.get("visuals",[]):
                    if (visual["chapter_id"],visual["section_id"])!=(row["chapter_id"],row["section_id"]):continue
                    from knowledge.source_visuals import get_visual
                    asset=get_visual(visual["id"])
                    if asset is None or not asset.is_valid() or asset.sha256!=visual["sha256"]:
                        raise ValueError("LightRAG原图候选无法映射到有效Q2资源")
                    images.append({**asset.public(),"document_id":row["document_id"],"version":row["version"],
                        "sha256":asset.sha256,"textbook_release":release["release_id"],"model_saw_pixels":False})
                fields["image_refs"]=images
                fields["location"]={**fields["location"],"retrieval_backend":"lightrag","fallback":False,
                    "course_id":self.course_id,"retrieval_score":row.get("score"),"textbook_release":release["release_id"],
                    "release_status":release["status"],"release_ready":release["ready"],
                    "relationship_semantics":"association_only; no prerequisite or mastery inference"}
                sources.append(SourceRef(**fields))
            record.update(status=self.last_result["status"],sources=len(sources),usage=self.last_result["usage"],trace=self.last_result.get("trace",[]))
            record['source_binding']=self.last_result.get('source_binding')
            return sources
        except asyncio.CancelledError as exc:
            from agents.tool_protocol import CancelledError
            record.update(getattr(exc,"lightrag_audit",{}));record.update(status="cancelled")
            raise CancelledError("LightRAG检索已取消") from None
        except Exception as exc:
            record.update(getattr(exc,"lightrag_audit",{}));record.update(status="failed",error_type=type(exc).__name__,error=str(exc))
            raise
        finally:record["seconds"]=time.monotonic()-started

    def tool_context(self,sources):
        from .relationships import relationship_context
        return relationship_context((self.last_result or {}).get('graph_context',[]),sources)


from agents.q3_tools import RetrieveCourseTool
class ContextualRetrieveCourseTool(RetrieveCourseTool):
    """保留原工具授权/编号/去重；仅附加独立关联与缺口区块。"""
    def run(self,arguments,context):
        from .relationships import append_tool_context
        from .trace import stage
        result=super().run(arguments,context)
        context.check_cancelled()
        stage(getattr(context.navigation,'trace',None),'tool_output',result.sources,result.sources,'')
        if hasattr(context.navigation,'tool_context'):
            return append_tool_context(result,context.navigation.tool_context(result.sources))
        return result
