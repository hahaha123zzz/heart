"""让显式声明且已确认的规范知识点保留身份，不靠名称猜测映射。"""
from functools import wraps
from integrations.deeptutor.assessment_intake import confirmed_catalog

def install_catalog_binding():
    from deeptutor.learning import topic_generation as native
    original=native.materialize_modules
    if getattr(original,'_heart_catalog_binding',False):
        return
    @wraps(original)
    def materialize(path_id,raw_modules,**options):
        if not options.get("strict"):
            return original(path_id,raw_modules,**options)
        catalog,_=confirmed_catalog()
        claimed=set()
        for module in raw_modules:
            if not isinstance(module,dict):continue
            for point in module.get('knowledge_points',[]):
                if not isinstance(point,dict):continue
                point_id=str(point.get('id') or '').strip()
                if not point_id.startswith('kc-'):continue
                canonical=catalog.get(point_id)
                if not canonical or point.get('name','').strip()!=canonical['name']:
                    raise native.TopicGenerationError('规范知识点 ID 与已确认目录名称不匹配')
                if point_id in claimed:
                    raise native.TopicGenerationError('同一路径不能重复声明同一规范知识点')
                claimed.add(point_id)
        if claimed and options.get('existing_objective_ids') is None:
            options['existing_objective_ids']=claimed
        return original(path_id,raw_modules,**options)
    materialize._heart_catalog_binding=True
    native.materialize_modules=materialize
