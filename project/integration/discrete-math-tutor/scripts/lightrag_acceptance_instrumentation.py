"""仅隔离验收使用的native计时/缓存/截止故障包装，不修改来源或检索结果。"""
import asyncio
import time


def wrap_native_query(original_native_query, *, state, event):
    # 闭包绑定原函数，启动器后续的全局变量赋值不会改变调用目标。
    async def measured_query(rag, *args, **kwargs):
        rag.llm_response_cache.global_config['enable_llm_cache'] = False
        event('query_start')
        status = 'success'
        try:
            if state['mode'] != 'timeout':
                return await original_native_query(rag, *args, **kwargs)
            previous = sum(e['event'] == 'sdk_start' for e in state['events'])
            task = asyncio.create_task(original_native_query(rag, *args, **kwargs))
            try:
                deadline = time.monotonic() + 90
                while sum(e['event'] == 'sdk_start' for e in state['events']) == previous:
                    if task.done():
                        return await task
                    if time.monotonic() > deadline:
                        raise TimeoutError('隔离故障注入：native未在90秒内进入SDK')
                    await asyncio.sleep(.01)
                # 明确的故障注入：本次实际SDK开始后施加50ms截止时间。
                return await asyncio.wait_for(task, timeout=.05)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        except BaseException as exc:
            status = type(exc).__name__
            raise
        finally:
            event('query_end', status=status)
    return measured_query
