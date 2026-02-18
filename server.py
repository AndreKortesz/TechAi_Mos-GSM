"""
TechBase — AI-ассистент по СКУД и СВН
Backend: FastAPI + Claude API + Web Search

Деплой: GitHub → Railway
Переменные окружения в Railway: ANTHROPIC_API_KEY
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import anthropic

# ── Config ──
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-5-20250929"  # Лучшее соотношение цена/качество
MAX_TOKENS = 4096

# ── System Prompt — сердце бота ──
SYSTEM_PROMPT = """Ты — TechBase AI, экспертный технический ассистент компании по системам безопасности.
Твоя специализация: СКУД (системы контроля и управления доступом) и СВН (системы видеонаблюдения).

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
4. **Используй веб-поиск** когда нужна актуальная или точная информация. Не отвечай по памяти если не уверен на 100%.
5. **Указывай конкретные модели и версии** — не "камера Hikvision", а "DS-2CD2143G2-I"
6. **Схемы подключения** — клеммы, провода, настройки + поясняй зачем каждый провод нужен.
7. **Если не уверен — скажи честно** и предложи обратиться к инженеру. Лучше сказать "не знаю, нужно уточнить", чем дать неверную информацию.
8. **Отвечай на русском языке**
9. **Если вопрос неоднозначный** — уточни модель, версию прошивки, контекст
10. **Формат**: заголовки + пункты. Таблицы — только когда реально помогают сравнить данные.

## КРИТИЧЕСКИ ВАЖНО — Точность информации:

### Расчёты и формулы:
- Перед любым расчётом (архив, пропускная способность, питание, длина кабеля) — **сначала поищи в интернете** актуальную формулу или калькулятор от вендора. Не считай по памяти если не уверен на 100%.
- **Показывай каждый шаг** расчёта, чтобы менеджер мог проверить.
- **Перепроверь себя**: после расчёта проверь результат на здравый смысл. Например: одна 2Мп камера за 30 дней — это сотни ГБ, не единицы. Если результат выглядит неправдоподобно маленьким или большим — пересчитай.
- В конце расчёта **всегда добавляй оговорку**: "Это приблизительный расчёт. Для точных данных используйте калькулятор от производителя" и дай ссылку если нашёл.
- Не забывай переводить единицы: секунды↔часы (×3600), байты↔биты (×8), ГБ↔ТБ (÷1024).

### Технические данные:
- Если не уверен в характеристиках конкретной модели — **поищи в интернете**, не придумывай.
- Параметры по умолчанию, IP-адреса, пароли, версии прошивок — всё меняется, **ищи актуальные данные**.
- Если вопрос про совместимость оборудования — **ищи на сайте вендора**, не угадывай.

### Общий принцип:
Лучше найти и дать точную информацию из источника, чем отвечать по памяти и ошибиться. Менеджеры принимают решения о закупках на основе твоих ответов — цена ошибки высокая.

## При использовании веб-поиска:
- Ищи на официальных сайтах производителей: bolid.ru, hikvision.com, dahua.com, sigur.com, perco.ru
- Ищи на профессиональных форумах и порталах
- Всегда указывай источник информации
"""

# ── In-memory chat storage (в проде заменить на PostgreSQL/Redis) ──
chat_sessions: dict = {}

# ── FastAPI App ──
app = FastAPI(title="TechBase AI", version="1.0")

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[dict] = []

def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, list]:
    if session_id and session_id in chat_sessions:
        return session_id, chat_sessions[session_id]["messages"]
    new_id = str(uuid.uuid4())[:8]
    chat_sessions[new_id] = {
        "messages": [],
        "created_at": datetime.now().isoformat()
    }
    return new_id, chat_sessions[new_id]["messages"]

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Основной эндпоинт чата — отправляет сообщение Claude с веб-поиском"""
    
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен. Установите переменную окружения.")
    
    session_id, messages = get_or_create_session(req.session_id)
    
    # Добавляем сообщение пользователя
    messages.append({"role": "user", "content": req.message})
    
    # Ограничиваем историю последними 20 сообщениями (экономия токенов)
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
                    "max_uses": 5  # До 5 поисков за один ответ
                }
            ]
        )
    except anthropic.APIError as e:
        raise HTTPException(500, f"Ошибка Claude API: {str(e)}")
    
    # Извлекаем текст ответа и источники
    reply_text = ""
    sources = []
    
    for block in response.content:
        if block.type == "text":
            reply_text += block.text
        elif block.type == "web_search_tool_result":
            # Собираем источники из результатов поиска
            if hasattr(block, 'content'):
                for result in block.content:
                    if hasattr(result, 'url') and hasattr(result, 'title'):
                        sources.append({
                            "url": result.url,
                            "title": result.title
                        })
    
    # Сохраняем ответ в историю
    messages.append({"role": "assistant", "content": reply_text})
    
    return ChatResponse(
        reply=reply_text,
        session_id=session_id,
        sources=sources
    )

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Стриминг ответа — текст появляется по мере генерации (как в claude.ai)"""
    
    if not API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY не настроен")
    
    session_id, messages = get_or_create_session(req.session_id)
    messages.append({"role": "user", "content": req.message})
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
                        "max_uses": 5
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
                                    pass  # начало текстового блока, ждём дельты
            
            # Сохраняем в историю
            messages.append({"role": "assistant", "content": full_reply})
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/sessions")
async def list_sessions():
    """Список всех сессий чата"""
    return {
        sid: {
            "created_at": data["created_at"],
            "message_count": len(data["messages"]),
            "last_message": data["messages"][-1]["content"][:80] if data["messages"] else ""
        }
        for sid, data in chat_sessions.items()
    }

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Удалить сессию"""
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
