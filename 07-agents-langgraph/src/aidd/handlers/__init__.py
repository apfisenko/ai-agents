from aiogram import Router

from . import check_telegram, evaluate_cmd, indexing_cmds, non_text, plain_text, start


def get_main_router() -> Router:
    r = Router()
    r.include_router(start.router)
    r.include_router(check_telegram.router)
    r.include_router(indexing_cmds.router)
    r.include_router(evaluate_cmd.router)
    r.include_router(non_text.router)
    r.include_router(plain_text.router)
    return r
