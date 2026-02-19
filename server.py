"""
TechBase — AI-ассистент по СКУД и СВН
Backend: FastAPI + Claude API + Web Search + PostgreSQL + Bitrix24 OAuth

Деплой: GitHub → Railway
Переменные: ANTHROPIC_API_KEY, DATABASE_URL, BITRIX_CLIENT_ID, BITRIX_CLIENT_SECRET, BITRIX_REDIRECT_URI
"""

import os
import json
import uuid
import secrets
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse, HTMLResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
import anthropic
import asyncpg
import httpx

# ── Config ──
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 4096

# ── Bitrix24 OAuth ──
BITRIX_CLIENT_ID = os.environ.get("BITRIX_CLIENT_ID", "")
BITRIX_CLIENT_SECRET = os.environ.get("BITRIX_CLIENT_SECRET", "")
BITRIX_REDIRECT_URI = os.environ.get("BITRIX_REDIRECT_URI", "")
BITRIX_DOMAIN = os.environ.get("BITRIX_DOMAIN", "svyaz.bitrix24.ru")
SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))

# ── System Prompt ──
SYSTEM_PROMPT = """Ты — TechBase AI, экспертный технический ассистент компании Mos-GSM.
Твоя специализация: СКУД (системы контроля и управления доступом) и СВН (системы видеонаблюдения).

## КТО ТОБОЙ ПОЛЬЗУЕТСЯ:

Тобой пользуются МЕНЕДЖЕРЫ компании Mos-GSM — это компания, которая сама продаёт, проектирует и устанавливает слаботочные системы. Менеджеры — это сотрудники Mos-GSM, а не конечные заказчики.

Поэтому:
- НИКОГДА не советуй "обратиться к интегратору" или "вызвать специалиста" — менеджер и есть сотрудник интегратора.
- НИКОГДА не пиши "вызовите монтажников на замер" — монтажники работают в той же компании.
- Если нужно что-то уточнить — пиши "уточните у инженера" или "согласуйте с проектным отделом".
- При расчётах стоимости — показывай цены на оборудование отдельно, монтаж отдельно. Менеджеру нужно составить смету для клиента.
- Помни: менеджер использует твои ответы чтобы консультировать СВОИХ клиентов и составлять коммерческие предложения.

## ТВОИ ТЕХНИЧЕСКИЕ ОГРАНИЧЕНИЯ:

- Ты работаешь ТОЛЬКО с текстом. Ты НЕ можешь принимать или просматривать фото, файлы, PDF, видео.
- НИКОГДА не проси прислать фото или загрузить файл — ты не сможешь их увидеть.
- Если менеджер говорит про фото от клиента — попроси ОПИСАТЬ словами что на фото: сколько дверей, какие помещения, тип дверей и т.д.
- Если нужна информация из документа — попроси скопировать текст из него.

## Твои знания охватывают:

### СКУД — производители и оборудование:
- **Болид** (ИСО «Орион»): контроллеры С2000-2, С2000-4, пульт С2000М, считыватели Proxy, программирование через UProg, интерфейс RS-485
- **Sigur**: контроллеры, серверное ПО, интеграция с 1С, шаблоны пропусков, настройка точек доступа
- **PERCo**: турникеты, контроллеры CT/L серии, PERCo-Web, электромеханические замки, считыватели
- **RusGuard**: контроллеры ACS, биометрические считыватели, облачный СКУД
- **Parsec**: контроллеры NC серии, ParsecNET
- **HID Global**: считыватели iCLASS, контроллеры VertX/Edge
- **ZKTeco**: биометрия, терминалы, контроллеры InBio
- **Hikvision СКУД**: контроллеры DS-K2600, терминалы распознавания лиц

### СВН — производители и оборудование:
- **Hikvision**: IP-камеры (DS-2CD серия), NVR (DS-7600/7700/9600), iVMS-4200, HiLook, SADP Tool, ONVIF, сброс паролей
- **Dahua**: IP-камеры (IPC-HDW/HFW), NVR (DHI-NVR), SmartPSS, DSS Pro, ConfigTool, ONVIF
- **Axis**: IP-камеры, AXIS Companion, ACAP аналитика, VAPIX API
- **Trassir**: VMS, модуль СКУД, аналитика (AutoTRASSIR, нейроаналитика), ActiveDome
- **Macroscop**: VMS, распознавание лиц, интеграция со СКУД
- **IDIS**: DirectIP, NVR, камеры
- **Uniview**: IP-камеры, NVR, EZStation

### Общие темы:
- Протоколы: ONVIF, RTSP, RS-485, Wiegand (26/34/37), OSDP, Dallas Touch Memory
- Сетевые настройки: IP-адресация, DHCP, Port Forwarding, DDNS, P2P облако
- Расчёты: архив видеонаблюдения, пропускная способность сети, выбор жёстких дисков
- Совместимость оборудования разных вендоров
- Монтаж: прокладка кабелей, питание (PoE, 12V, 24V), грозозащита

## Правила ответа:

Ты — лучший в мире специалист по слаботочным системам, который умеет объяснять сложные вещи простым языком. Представь, что объясняешь ребёнку — чтобы даже человек без технического образования понял. При этом информация должна быть точной и профессиональной.

1. **Объясняй понятно** — используй простые слова, аналогии из жизни. Если говоришь "RS-485", тут же поясни что это и зачем. Менеджер не инженер.
2. **Не дублируй информацию** — каждая мысль только в одном месте.
3. **Не лей воду** — никаких "Отличный вопрос!", "Давайте разберём подробно". Сразу к делу.
4. **НЕ используй веб-поиск по умолчанию!** Подробности ниже.
5. **Указывай конкретные модели и версии** — не "камера Hikvision", а "DS-2CD2143G2-I"
6. **Схемы подключения** — клеммы, провода, настройки + поясняй зачем каждый провод нужен.
7. **Если не уверен — скажи честно** и предложи уточнить у инженера.
8. **Отвечай на русском языке**
9. **Если вопрос неоднозначный** — уточни модель, версию прошивки, контекст
10. **Формат**: заголовки + пункты. Таблицы — только когда реально помогают сравнить данные.

## КРИТИЧЕСКИ ВАЖНО — Экономия веб-поиска:

Каждый веб-поиск стоит денег компании. Используй его ТОЛЬКО когда без него НЕВОЗМОЖНО ответить.

### НЕ НУЖЕН поиск (отвечай из своих знаний):
- Как настроить / подключить / сбросить оборудование
- Схемы подключения (SADP, ONVIF, Wiegand, RS-485, PoE и т.д.)
- Объяснение принципов работы
- Типовые ошибки и диагностика
- Расчёты (архив, пропускная способность, сечение кабеля)
- Сравнение технологий и подходов
- IP-адреса по умолчанию, стандартные пароли

### НУЖЕН поиск (только эти случаи):
- Актуальные ЦЕНЫ на оборудование
- Пользователь ПРЯМО просит: "найди", "поищи", "актуальная ссылка"
- Конкретные характеристики редкой модели, в которых ты совсем не уверен

### Если сомневаешься — НЕ ищи. Ответь из знаний и добавь: "Если нужны актуальные данные с сайта производителя — скажите, поищу."

## Точность расчётов:
- Показывай каждый шаг расчёта
- Перепроверь результат на здравый смысл
- Не забывай переводить единицы: секунды↔часы (×3600), байты↔биты (×8), ГБ↔ТБ (÷1024)
- В конце добавь: "Приблизительный расчёт. Для точных данных используйте калькулятор производителя."
"""

# ── Database ──
DATABASE_URL = os.environ.get("DATABASE_URL", "")
db_pool = None
chat_sessions: dict = {}

async def init_db():
    global db_pool
    if not DATABASE_URL:
        print("⚠️  DATABASE_URL не задан — используется in-memory хранение")
        return
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT '',
                    user_name TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
            ''')
            # Migration: add columns if missing
            try:
                await conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT ''")
                await conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT ''")
            except:
                pass
        print("✅ PostgreSQL подключена, таблицы готовы")
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")

async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    await close_db()

# ── FastAPI App ──
app = FastAPI(title="TechBase AI", version="1.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# ── Auth helpers ──
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user

# ── Auth routes ──
@app.get("/auth/login")
async def auth_login():
    if not BITRIX_CLIENT_ID:
        return HTMLResponse("<h1>Ошибка: BITRIX_CLIENT_ID не настроен</h1>", status_code=500)
    auth_url = (
        f"https://{BITRIX_DOMAIN}/oauth/authorize/"
        f"?client_id={BITRIX_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={BITRIX_REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    domain = params.get("domain", BITRIX_DOMAIN)
    server_domain = params.get("server_domain", "oauth.bitrix.info")

    if not code:
        return HTMLResponse("<h1>Ошибка авторизации: нет кода</h1>", status_code=400)

    token_url = f"https://{server_domain}/oauth/token/"

    async with httpx.AsyncClient() as client:
        try:
            # Exchange code for token
            resp = await client.post(token_url, data={
                "grant_type": "authorization_code",
                "client_id": BITRIX_CLIENT_ID,
                "client_secret": BITRIX_CLIENT_SECRET,
                "redirect_uri": BITRIX_REDIRECT_URI,
                "code": code
            })

            if resp.status_code != 200:
                print(f"❌ Token exchange failed: {resp.status_code} - {resp.text}")
                return HTMLResponse(f"<h1>Ошибка получения токена</h1>", status_code=400)

            token_data = resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return HTMLResponse("<h1>Ошибка: нет access_token</h1>", status_code=400)

            # Get user info
            user_domain = domain or BITRIX_DOMAIN
            user_resp = await client.post(
                f"https://{user_domain}/rest/user.current",
                data={"auth": access_token}
            )

            if user_resp.status_code != 200:
                print(f"❌ User info failed: {user_resp.status_code}")
                return HTMLResponse("<h1>Ошибка получения данных пользователя</h1>", status_code=400)

            user_data = user_resp.json().get("result", {})
            user = {
                "id": user_data.get("ID", ""),
                "name": f"{user_data.get('NAME', '')} {user_data.get('LAST_NAME', '')}".strip(),
                "email": user_data.get("EMAIL", ""),
                "position": user_data.get("WORK_POSITION", ""),
                "photo": user_data.get("PERSONAL_PHOTO", ""),
            }

            request.session["user"] = user
            print(f"✅ User logged in: {user['name']} (ID: {user['id']})")
            return RedirectResponse("/")

        except Exception as e:
            print(f"❌ Auth error: {e}")
            return HTMLResponse(f"<h1>Ошибка авторизации</h1><p>{str(e)}</p>", status_code=500)

@app.get("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/auth/me")
async def auth_me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Не авторизован")
    return user

# ── Login page ──
@app.get("/login")
async def login_page():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Вход — Mos-GSM AI</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Roboto',sans-serif;background:#F5F3EF;display:flex;align-items:center;justify-content:center;min-height:100vh;color:#1A1A1A}
.login-card{background:#fff;border-radius:16px;padding:48px 40px;text-align:center;max-width:400px;width:90%;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.logo-mark{width:72px;height:72px;border-radius:20px;background:#D4A53A;display:inline-flex;align-items:flex-end;justify-content:center;gap:3px;padding-bottom:12px;margin-bottom:20px}
.logo-mark i{display:block;width:8px;border-radius:3px;background:#1A1A1A}
.logo-mark i:nth-child(1){height:8px}
.logo-mark i:nth-child(2){height:16px}
.logo-mark i:nth-child(3){height:26px}
.logo-mark i:nth-child(4){height:36px}
h1{font-family:'Bebas Neue',sans-serif;font-size:28px;letter-spacing:2px;margin-bottom:8px}
.subtitle{color:#6B6560;font-size:14px;margin-bottom:32px;line-height:1.5}
.login-btn{display:inline-flex;align-items:center;gap:10px;padding:14px 32px;background:#1A1A1A;color:#F3C04D;border:none;border-radius:10px;font-size:15px;font-weight:600;font-family:inherit;cursor:pointer;transition:.2s;text-decoration:none}
.login-btn:hover{background:#333;transform:translateY(-1px)}
.login-btn svg{width:20px;height:20px}
.footer{margin-top:32px;font-size:12px;color:#9A9590}
.footer a{color:#C9982E;text-decoration:none}
</style>
</head>
<body>
<div class="login-card">
  <div class="logo-mark"><i></i><i></i><i></i><i></i></div>
  <h1>MOS-GSM AI</h1>
  <p class="subtitle">AI-ассистент по СКУД и СВН<br>Для сотрудников компании Mos-GSM</p>
  <a href="/auth/login" class="login-btn">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
    Войти через Битрикс24
  </a>
  <div class="footer">
    <a href="https://mos-gsm.ru" target="_blank">mos-gsm.ru</a> · Комплексные слаботочные системы
  </div>
</div>
</body>
</html>""")

# ── Models ──
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[dict] = []

# ── Session helpers ──
async def get_or_create_session(session_id: Optional[str] = None, user_id: str = "", user_name: str = "") -> tuple[str, list]:
    if db_pool:
        async with db_pool.acquire() as conn:
            if session_id:
                row = await conn.fetchrow('SELECT id FROM chat_sessions WHERE id=$1', session_id)
                if row:
                    rows = await conn.fetch(
                        'SELECT role, content FROM chat_messages WHERE session_id=$1 ORDER BY id', session_id
                    )
                    return session_id, [{"role": r['role'], "content": r['content']} for r in rows]
            new_id = str(uuid.uuid4())[:8]
            await conn.execute(
                'INSERT INTO chat_sessions (id, user_id, user_name, created_at, updated_at) VALUES ($1,$2,$3,NOW(),NOW())',
                new_id, user_id, user_name
            )
            return new_id, []
    else:
        if session_id and session_id in chat_sessions:
            return session_id, chat_sessions[session_id]["messages"]
        new_id = str(uuid.uuid4())[:8]
        chat_sessions[new_id] = {"messages": [], "created_at": datetime.now().isoformat()}
        return new_id, chat_sessions[new_id]["messages"]

async def save_message(session_id: str, role: str, content: str, title: str = None):
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO chat_messages (session_id, role, content) VALUES ($1,$2,$3)',
                session_id, role, content
            )
            if title:
                await conn.execute('UPDATE chat_sessions SET updated_at=NOW(), title=$2 WHERE id=$1', session_id, title[:80])
            else:
                await conn.execute('UPDATE chat_sessions SET updated_at=NOW() WHERE id=$1', session_id)

# ── Protected API endpoints ──
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    user = require_auth(request)
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен")

    session_id, messages = await get_or_create_session(req.session_id, user["id"], user["name"])
    messages.append({"role": "user", "content": req.message})
    await save_message(session_id, "user", req.message, title=req.message)

    recent_messages = messages[-20:]
    client = anthropic.Anthropic(api_key=API_KEY)

    try:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
            messages=recent_messages,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}]
        )
    except anthropic.APIError as e:
        raise HTTPException(500, f"Ошибка Claude API: {str(e)}")

    reply_text = ""
    sources = []
    for block in response.content:
        if block.type == "text":
            reply_text += block.text
        elif block.type == "web_search_tool_result":
            if hasattr(block, 'content'):
                for result in block.content:
                    if hasattr(result, 'url') and hasattr(result, 'title'):
                        sources.append({"url": result.url, "title": result.title})

    messages.append({"role": "assistant", "content": reply_text})
    await save_message(session_id, "assistant", reply_text)
    return ChatResponse(reply=reply_text, session_id=session_id, sources=sources)

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    user = require_auth(request)
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен")

    session_id, messages = await get_or_create_session(req.session_id, user["id"], user["name"])
    messages.append({"role": "user", "content": req.message})
    await save_message(session_id, "user", req.message, title=req.message)

    recent_messages = messages[-20:]
    client = anthropic.Anthropic(api_key=API_KEY)

    async def generate():
        full_reply = ""
        try:
            with client.messages.stream(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                messages=recent_messages,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}]
            ) as stream:
                for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == 'content_block_delta':
                            if hasattr(event.delta, 'text') and event.delta.text is not None:
                                full_reply += event.delta.text
                                yield f"data: {json.dumps({'type': 'text', 'content': event.delta.text})}\n\n"
                        elif event.type == 'content_block_start':
                            if hasattr(event.content_block, 'type'):
                                if event.content_block.type == 'server_tool_use':
                                    yield f"data: {json.dumps({'type': 'searching', 'content': 'Ищу информацию...'})}\n\n"
                                elif event.content_block.type == 'web_search_tool_result':
                                    yield f"data: {json.dumps({'type': 'search_done', 'content': 'Найдено!'})}\n\n"
                                elif event.content_block.type == 'text':
                                    pass

            await save_message(session_id, "assistant", full_reply)
            messages.append({"role": "assistant", "content": full_reply})
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/sessions")
async def list_sessions(request: Request):
    user = require_auth(request)
    if db_pool:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM chat_messages WHERE session_id=s.id) as msg_count
                   FROM chat_sessions s WHERE s.user_id=$1 ORDER BY s.updated_at DESC LIMIT 50''',
                user["id"]
            )
            return [
                {"id": r['id'], "title": r['title'] or "Новый чат",
                 "created_at": r['created_at'].isoformat(), "updated_at": r['updated_at'].isoformat(),
                 "message_count": r['msg_count']}
                for r in rows
            ]
    return []

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    require_auth(request)
    if db_pool:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT role, content, created_at FROM chat_messages WHERE session_id=$1 ORDER BY id', session_id
            )
            if not rows:
                raise HTTPException(404, "Сессия не найдена")
            return [{"role": r['role'], "content": r['content'], "time": r['created_at'].strftime('%H:%M')} for r in rows]
    raise HTTPException(404, "Сессия не найдена")

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    user = require_auth(request)
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute('DELETE FROM chat_sessions WHERE id=$1 AND user_id=$2', session_id, user["id"])
            return {"status": "deleted"}
    raise HTTPException(404, "Сессия не найдена")

# ── Frontend ──
@app.get("/")
async def serve_frontend(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return FileResponse("static/index.html")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
