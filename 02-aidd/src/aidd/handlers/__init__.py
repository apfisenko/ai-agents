from aiogram import Router

from . import non_text, start


def get_main_router() -> Router:
    r = Router()
    r.include_router(start.router)
    r.include_router(non_text.router)
    return r
