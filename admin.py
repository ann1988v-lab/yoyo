import os, mimetypes
from pathlib import Path
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from database import Database

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "sakura18.db"
MEDIA_DIR = BASE_DIR / "media"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1324")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")

db_store = Database(str(DB_PATH))
app = FastAPI(title="SAKURA 18+ Admin")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def logged_in(request): return request.session.get("admin") is True

def require_login(request):
    return None if logged_in(request) else RedirectResponse("/login", status_code=303)


def dt(value):
    return (value or "")[:19].replace("T", " ")


def user_context(uid):
    user = db_store.get_user(uid)
    if not user: return None
    return user, db_store.actions(uid), db_store.messages(uid), db_store.photos(uid)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    r = require_login(request)
    return r or RedirectResponse("/users", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return RedirectResponse("/users", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": "Неверный логин или пароль"}, status_code=401)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear(); return RedirectResponse("/login", status_code=303)


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    r = require_login(request)
    if r: return r
    users = db_store.users()
    return templates.TemplateResponse(request=request, name="users.html", context={"request": request, "users": users})


@app.get("/users/{telegram_id}", response_class=HTMLResponse)
@app.get("/user/{telegram_id}", response_class=HTMLResponse)
async def user_page(request: Request, telegram_id: int):
    r = require_login(request)
    if r: return r
    data = user_context(telegram_id)
    if not data: return HTMLResponse("Пользователь не найден", status_code=404)
    user, actions, messages, photos = data
    return templates.TemplateResponse(request=request, name="user.html", context={"request": request, "user": user, "actions": actions, "messages": messages, "photos": photos})


@app.get("/photo/{photo_id}")
async def view_photo(request: Request, photo_id: int):
    r = require_login(request)
    if r: return r
    p = db_store.get_photo(photo_id)
    if not p: return HTMLResponse("Фото не найдено", status_code=404)
    path = Path(p["local_path"])
    if not path.is_file(): return HTMLResponse("Файл фото отсутствует на диске", status_code=404)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "image/jpeg")


@app.get("/photo/{photo_id}/download")
async def download_photo(request: Request, photo_id: int):
    r = require_login(request)
    if r: return r
    p = db_store.get_photo(photo_id)
    if not p: return HTMLResponse("Фото не найдено", status_code=404)
    path = Path(p["local_path"])
    if not path.is_file(): return HTMLResponse("Файл фото отсутствует на диске", status_code=404)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "image/jpeg", filename=f"sakura_photo_{photo_id}{path.suffix or '.jpg'}")


@app.post("/user/{telegram_id}/tickets")
async def update_tickets(request: Request, telegram_id: int, delta: int = Form(0)):
    r = require_login(request)
    if r: return r
    old = db_store.get_user(telegram_id)
    if not old: return HTMLResponse("Пользователь не найден", status_code=404)
    new = db_store.change_tickets(telegram_id, delta)
    db_store.add_action(telegram_id, "admin_ticket_change", f"Администратор изменил баланс: {old['tickets']} → {new} ({delta:+d})")
    return RedirectResponse(f"/users/{telegram_id}", status_code=303)


@app.post("/user/{telegram_id}/tickets/set")
async def set_tickets(request: Request, telegram_id: int, amount: int = Form(...)):
    r = require_login(request)
    if r: return r
    old = db_store.get_user(telegram_id)
    if not old: return HTMLResponse("Пользователь не найден", status_code=404)
    db_store.set_tickets(telegram_id, amount)
    db_store.add_action(telegram_id, "admin_ticket_set", f"Администратор установил баланс: {old['tickets']} → {max(0, amount)}")
    return RedirectResponse(f"/users/{telegram_id}", status_code=303)


@app.post("/user/{telegram_id}/message")
async def message_user(request: Request, telegram_id: int, text: str = Form(""), photo: UploadFile | None = File(None)):
    r = require_login(request)
    if r: return r
    if not db_store.get_user(telegram_id): return HTMLResponse("Пользователь не найден", status_code=404)
    try:
        from bot import bot
        from aiogram.types import FSInputFile
    except Exception:
        return HTMLResponse("Не удалось загрузить Telegram-бота", status_code=500)
    saved = None
    try:
        if photo and photo.filename:
            MEDIA_DIR.mkdir(exist_ok=True)
            safe = Path(photo.filename).name
            saved = MEDIA_DIR / f"admin_{telegram_id}_{safe}"
            saved.write_bytes(await photo.read())
            sent = await bot.send_photo(telegram_id, FSInputFile(str(saved)), caption=text or None)
            db_store.add_message(telegram_id, sent.message_id, "outgoing", "photo", text)
            pid = db_store.add_photo(telegram_id, "", "", str(saved), text, sent.message_id, "outgoing")
            db_store.add_action(telegram_id, "admin_message", f"Отправлено фото #{pid} и сообщение администратора")
        elif text.strip():
            sent = await bot.send_message(telegram_id, text)
            db_store.add_message(telegram_id, sent.message_id, "outgoing", "text", text)
            db_store.add_action(telegram_id, "admin_message", "Отправлено сообщение администратора")
    except Exception as exc:
        return HTMLResponse(f"Ошибка отправки: {exc}", status_code=500)
    return RedirectResponse(f"/users/{telegram_id}", status_code=303)


@app.post("/broadcast")
async def broadcast(request: Request, text: str = Form(""), photo: UploadFile | None = File(None)):
    r = require_login(request)
    if r: return r
    if not text.strip() and not (photo and photo.filename): return RedirectResponse("/users", status_code=303)
    try:
        from bot import bot
        from aiogram.types import FSInputFile
    except Exception:
        return HTMLResponse("Не удалось загрузить Telegram-бота", status_code=500)
    saved = None
    if photo and photo.filename:
        MEDIA_DIR.mkdir(exist_ok=True)
        saved = MEDIA_DIR / f"broadcast_{Path(photo.filename).name}"
        saved.write_bytes(await photo.read())
    for row in db_store.users():
        uid = int(row["telegram_id"])
        try:
            if saved:
                sent = await bot.send_photo(uid, FSInputFile(str(saved)), caption=text or None)
                db_store.add_message(uid, sent.message_id, "outgoing", "photo", text)
            else:
                sent = await bot.send_message(uid, text)
                db_store.add_message(uid, sent.message_id, "outgoing", "text", text)
            db_store.add_action(uid, "broadcast_sent", "Массовая рассылка")
        except Exception as exc:
            db_store.add_action(uid, "broadcast_error", str(exc)[:500])
    return RedirectResponse("/users", status_code=303)
