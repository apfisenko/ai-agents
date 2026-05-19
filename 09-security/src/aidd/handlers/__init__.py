from aiogram import Router

from . import (
    check_telegram,
    evaluate_cmd,
    hitl_callback,
    indexing_cmds,
    mcp_status_cmd,
    non_text,
    plain_text,
    start,
)


def get_main_router() -> Router:
    r = Router()
    r.include_router(start.router)
    r.include_router(check_telegram.router)
    r.include_router(mcp_status_cmd.router)
    r.include_router(indexing_cmds.router)
    r.include_router(evaluate_cmd.router)
    r.include_router(non_text.router)
    r.include_router(hitl_callback.router)
    r.include_router(plain_text.router)
    return r
