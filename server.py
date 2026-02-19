"""
TechBase — AI-ассистент по СКУД и СВН
Backend: FastAPI + Claude API + Web Search + PostgreSQL

Деплой: GitHub → Railway
Переменные окружения в Railway: ANTHROPIC_API_KEY, DATABASE_URL
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import anthropic
import asyncpg

# ── Config ──
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-5-20250929"  # Лучшее соотношение цена/качество
MAX_TOKENS = 4096

# ── System Prompt — сердце бота ──
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
2. **Не дублируй информацию** — каждая мысль только в одном месте. Если написал про длину кабеля UTP — не повторяй это в другой секции.
3. **Не лей воду** — никаких "Отличный вопрос!", "Давайте разберём подробно", "Это важный момент". Сразу к делу.
4. **НЕ используй веб-поиск по умолчанию!** Подробности ниже.
5. **Указывай конкретные модели и версии** — не "камера Hikvision", а "DS-2CD2143G2-I"
6. **Схемы подключения** — клеммы, провода, настройки + поясняй зачем каждый провод нужен.
7. **Если не уверен — скажи честно** и предложи обратиться к инженеру. Лучше сказать "не знаю, нужно уточнить", чем дать неверную информацию.
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

# ── In-memory fallback + PostgreSQL ──
DATABASE_URL = os.environ.get("DATABASE_URL", "")
db_pool = None
chat_sessions: dict = {}  # Fallback if no DB

async def init_db():
    """Create tables if they don't exist"""
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
            ''')
        print("✅ PostgreSQL подключена, таблицы готовы")
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print("⚠️  Используется in-memory хранение")

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

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[dict] = []

async def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, list]:
    """Get existing session or create new one. Returns (session_id, messages_list)"""
    
    if db_pool:
        async with db_pool.acquire() as conn:
            if session_id:
                # Check if exists
                row = await conn.fetchrow('SELECT id FROM chat_sessions WHERE id=$1', session_id)
                if row:
                    # Load messages
                    rows = await conn.fetch(
                        'SELECT role, content FROM chat_messages WHERE session_id=$1 ORDER BY id',
                        session_id
                    )
                    messages = [{"role": r['role'], "content": r['content']} for r in rows]
                    return session_id, messages
            
            # Create new session
            new_id = str(uuid.uuid4())[:8]
            await conn.execute(
                'INSERT INTO chat_sessions (id, created_at, updated_at) VALUES ($1, NOW(), NOW())',
                new_id
            )
            return new_id, []
    else:
        # In-memory fallback
        if session_id and session_id in chat_sessions:
            return session_id, chat_sessions[session_id]["messages"]
        new_id = str(uuid.uuid4())[:8]
        chat_sessions[new_id] = {"messages": [], "created_at": datetime.now().isoformat()}
        return new_id, chat_sessions[new_id]["messages"]

async def save_message(session_id: str, role: str, content: str, title: str = None):
    """Save a message to DB"""
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3)',
                session_id, role, content
            )
            # Update session timestamp and title
            if title:
                await conn.execute(
                    'UPDATE chat_sessions SET updated_at=NOW(), title=$2 WHERE id=$1',
                    session_id, title[:80]
                )
            else:
                await conn.execute(
                    'UPDATE chat_sessions SET updated_at=NOW() WHERE id=$1',
                    session_id
                )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Основной эндпоинт чата — отправляет сообщение Claude с веб-поиском"""
    
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен. Установите переменную окружения.")
    
    session_id, messages = await get_or_create_session(req.session_id)
    
    # Добавляем сообщение пользователя
    messages.append({"role": "user", "content": req.message})
    await save_message(session_id, "user", req.message, title=req.message)
    
    # Ограничиваем историю последними 20 сообщениями
    recent_messages = messages[-20:]
    
    client = anthropic.Anthropic(api_key=API_KEY)
    
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=recent_messages,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 2
                }
            ]
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
    
    # Сохраняем ответ
    messages.append({"role": "assistant", "content": reply_text})
    await save_message(session_id, "assistant", reply_text)
    
    return ChatResponse(reply=reply_text, session_id=session_id, sources=sources)

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Стриминг ответа — текст появляется по мере генерации"""
    
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен")
    
    session_id, messages = await get_or_create_session(req.session_id)
    messages.append({"role": "user", "content": req.message})
    
    # Save user message to DB
    await save_message(session_id, "user", req.message, title=req.message)
    
    recent_messages = messages[-20:]
    
    client = anthropic.Anthropic(api_key=API_KEY)
    
    async def generate():
        full_reply = ""
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=recent_messages,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2
                    }
                ]
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
            
            # Save assistant reply to DB
            await save_message(session_id, "assistant", full_reply)
            messages.append({"role": "assistant", "content": full_reply})
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/sessions")
async def list_sessions():
    """Список всех сессий чата"""
    if db_pool:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM chat_messages WHERE session_id=s.id) as msg_count
                   FROM chat_sessions s ORDER BY s.updated_at DESC LIMIT 50'''
            )
            return [
                {
                    "id": r['id'],
                    "title": r['title'] or "Новый чат",
                    "created_at": r['created_at'].isoformat(),
                    "updated_at": r['updated_at'].isoformat(),
                    "message_count": r['msg_count']
                }
                for r in rows
            ]
    else:
        return [
            {"id": sid, "title": data["messages"][0]["content"][:80] if data["messages"] else "Новый чат",
             "created_at": data["created_at"], "message_count": len(data["messages"])}
            for sid, data in chat_sessions.items()
        ]

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Получить все сообщения сессии"""
    if db_pool:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT role, content, created_at FROM chat_messages WHERE session_id=$1 ORDER BY id',
                session_id
            )
            if not rows:
                raise HTTPException(404, "Сессия не найдена")
            return [
                {"role": r['role'], "content": r['content'], "time": r['created_at'].strftime('%H:%M')}
                for r in rows
            ]
    else:
        if session_id in chat_sessions:
            return [{"role": m['role'], "content": m['content'], "time": ""} for m in chat_sessions[session_id]["messages"]]
        raise HTTPException(404, "Сессия не найдена")

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Удалить сессию"""
    if db_pool:
        async with db_pool.acquire() as conn:
            result = await conn.execute('DELETE FROM chat_sessions WHERE id=$1', session_id)
            if result == 'DELETE 0':
                raise HTTPException(404, "Сессия не найдена")
            return {"status": "deleted"}
    else:
        if session_id in chat_sessions:
            del chat_sessions[session_id]
            return {"status": "deleted"}
        raise HTTPException(404, "Сессия не найдена")

# Раздаём фронтенд
@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

# Статика
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
