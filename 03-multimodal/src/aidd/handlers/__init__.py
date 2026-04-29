from aiogram import Router

from . import balance, check_telegram, non_text, plain_text, receipt_photo, start


def get_main_router() -> Router:
    r = Router()
    r.include_router(start.router)
    r.include_router(check_telegram.router)
    r.include_router(balance.router)
    r.include_router(receipt_photo.router)
    r.include_router(non_text.router)
    r.include_router(plain_text.router)
    return r
