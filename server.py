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
import base64
import subprocess
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse, HTMLResponse, Response
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

# ── Юридические лица ──
LEGAL_ENTITIES = {
    "ip_kontorin": {
        "id": "ip_kontorin",
        "name": "ИП Конторин А.В.",
        "full_name": "Индивидуальный предприниматель Конторин Андрей Валентинович",
        "inn": "502498623314",
        "address": "143423, Московская область, Красногорский район, п. Истра, д. 18, кв. 31",
        "phone": "+7 (499) 393-34-42",
        "bank": "АО \"ТБанк\"",
        "bik": "044525974",
        "corr_account": "30101810145250000974",
        "account": "40802810100000405964",
        "vat": None,  # Без НДС
        "signer": "Конторин А.В.",
        "signer_title": "Предприниматель",
        "logo": "logo_mosgsm.png",
        "stamp": "stamp_ip_kontorin.png",
        "sign": "sign_ip_kontorin.png"
    },
    "ooo_infinity": {
        "id": "ooo_infinity",
        "name": "ООО \"Инфинити Буст\"",
        "full_name": "Общество с ограниченной ответственностью \"Инфинити Буст\"",
        "inn": "5024206433",
        "kpp": "502401001",
        "address": "143402, Московская область, г.о. Красногорск, г Красногорск, пер Железнодорожный, дом 7, помещение 32",
        "phone": "+7 (499) 393-34-42",
        "bank": "ООО \"Банк Точка\"",
        "bik": "044525104",
        "corr_account": "30101810745374525104",
        "account": "40702810020000044948",
        "vat": 22,  # НДС 22%
        "signer": "Конторин А. В.",
        "signer_title": "Предприниматель",
        "logo": "logo_infinity.png",
        "stamp": "stamp_ooo_infinity.png",
        "sign": "sign_ooo_infinity.png"
    },
    "ip_timofeev": {
        "id": "ip_timofeev",
        "name": "ИП Тимофеев Д.Д.",
        "full_name": "Индивидуальный предприниматель Тимофеев Денис Дмитриевич",
        "inn": "502482648754",
        "address": "143406, Московская область, г.о. Красногорск, г Красногорск, ул Циолковского, д. 4, кв. 88",
        "phone": "+7 (495) 414-11-53",
        "bank": "",
        "bik": "",
        "corr_account": "",
        "account": "",
        "vat": None,  # Без НДС
        "signer": "Тимофеев Д.Д.",
        "signer_title": "Предприниматель",
        "logo": "logo_mosgsm.png",
        "stamp": "stamp_ip_timofeev.png",
        "sign": "sign_ip_timofeev.png"
    }
}

# ── Tool для генерации КП ──
KP_TOOL = {
    "name": "generate_kp",
    "description": """Генерирует коммерческое предложение (КП) в формате PDF.
    
Используй этот инструмент когда менеджер просит:
- составить КП / коммерческое предложение
- сделать смету / расчёт для клиента
- подготовить предложение на оборудование и работы

ВАЖНО: Перед вызовом уточни у менеджера:
1. От какого юрлица выставлять (ИП Конторин, ООО Инфинити Буст, ИП Тимофеев)
2. Название клиента (покупателя)
3. Список оборудования с ценами
4. Список работ с ценами""",
    "input_schema": {
        "type": "object",
        "properties": {
            "legal_entity_id": {
                "type": "string",
                "enum": ["ip_kontorin", "ooo_infinity", "ip_timofeev"],
                "description": "ID юрлица поставщика"
            },
            "client_name": {
                "type": "string",
                "description": "Название клиента (покупателя)"
            },
            "client_contact": {
                "type": "string",
                "description": "Контакт клиента (телефон, email) - опционально"
            },
            "object_address": {
                "type": "string",
                "description": "Адрес объекта - опционально"
            },
            "materials": {
                "type": "array",
                "description": "Список материалов/оборудования",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Наименование"},
                        "quantity": {"type": "number", "description": "Количество"},
                        "unit": {"type": "string", "description": "Единица измерения (шт, м, компл)"},
                        "price": {"type": "number", "description": "Цена за единицу"}
                    },
                    "required": ["name", "quantity", "unit", "price"]
                }
            },
            "works": {
                "type": "array",
                "description": "Список работ",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Наименование работы"},
                        "quantity": {"type": "number", "description": "Количество"},
                        "unit": {"type": "string", "description": "Единица измерения"},
                        "price": {"type": "number", "description": "Цена за единицу"}
                    },
                    "required": ["name", "quantity", "unit", "price"]
                }
            },
            "validity_days": {
                "type": "integer",
                "description": "Срок актуальности КП в рабочих днях (по умолчанию 14)"
            }
        },
        "required": ["legal_entity_id", "client_name", "materials", "works"]
    }
}

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
            # Create tables
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
                
                CREATE TABLE IF NOT EXISTS kp_documents (
                    id SERIAL PRIMARY KEY,
                    kp_number TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT,
                    legal_entity_id TEXT NOT NULL,
                    client_name TEXT NOT NULL,
                    data JSONB NOT NULL,
                    total_materials NUMERIC,
                    total_works NUMERIC,
                    total NUMERIC,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_kp_user ON kp_documents(user_id);
            ''')
            # Migration: add new columns
            for col in [
                "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT ''",
                "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_name TEXT DEFAULT ''",
            ]:
                try:
                    await conn.execute(col)
                except:
                    pass
            # Index on user_id (after column exists)
            try:
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id)")
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

# ── KP Generation ──
def num_to_words(num: float) -> str:
    """Конвертирует число в слова (рубли)"""
    units = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
    teens = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 
             'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
    tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 
            'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
    hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 
                'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
    
    def three_digits(n, feminine=False):
        result = []
        if n >= 100:
            result.append(hundreds[n // 100])
            n %= 100
        if 10 <= n < 20:
            result.append(teens[n - 10])
            return ' '.join(result)
        if n >= 10:
            result.append(tens[n // 10])
            n %= 10
        if n > 0:
            if feminine and n in [1, 2]:
                result.append(['', 'одна', 'две'][n])
            else:
                result.append(units[n])
        return ' '.join(result)
    
    num = int(num)
    if num == 0:
        return "ноль рублей 00 копеек"
    
    result = []
    
    # Миллионы
    if num >= 1000000:
        millions = num // 1000000
        word = three_digits(millions)
        if millions % 10 == 1 and millions % 100 != 11:
            result.append(f"{word} миллион")
        elif 2 <= millions % 10 <= 4 and not (12 <= millions % 100 <= 14):
            result.append(f"{word} миллиона")
        else:
            result.append(f"{word} миллионов")
        num %= 1000000
    
    # Тысячи
    if num >= 1000:
        thousands = num // 1000
        word = three_digits(thousands, feminine=True)
        if thousands % 10 == 1 and thousands % 100 != 11:
            result.append(f"{word} тысяча")
        elif 2 <= thousands % 10 <= 4 and not (12 <= thousands % 100 <= 14):
            result.append(f"{word} тысячи")
        else:
            result.append(f"{word} тысяч")
        num %= 1000
    
    # Рубли
    if num > 0 or not result:
        word = three_digits(num)
        result.append(word)
    
    text = ' '.join(result).strip()
    text = text[0].upper() + text[1:] if text else ""
    
    # Окончание "рублей"
    last_digit = int(str(num)[-1]) if num > 0 else 0
    last_two = num % 100
    if last_digit == 1 and last_two != 11:
        text += " рубль"
    elif 2 <= last_digit <= 4 and not (12 <= last_two <= 14):
        text += " рубля"
    else:
        text += " рублей"
    
    text += " 00 копеек"
    return text

def format_price(num: float) -> str:
    """Форматирует цену с пробелами"""
    return f"{num:,.0f}".replace(",", " ")

async def get_next_kp_number() -> str:
    """Получает следующий номер КП"""
    if db_pool:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT MAX(id) as max_id FROM kp_documents")
            next_id = (row['max_id'] or 0) + 1
            return str(next_id)
    return str(uuid.uuid4())[:6]

def generate_kp_html(kp_data: dict, legal_entity: dict, kp_number: str) -> str:
    """Генерирует HTML коммерческого предложения"""
    
    # Расчёт сумм
    materials = kp_data.get("materials", [])
    works = kp_data.get("works", [])
    
    total_materials = sum(m["quantity"] * m["price"] for m in materials)
    total_works = sum(w["quantity"] * w["price"] for w in works)
    total = total_materials + total_works
    
    vat_rate = legal_entity.get("vat")
    vat_amount = 0
    if vat_rate:
        vat_amount = total * vat_rate / (100 + vat_rate)
    
    # Дата
    today = datetime.now().strftime("%d.%m.%y")
    validity_days = kp_data.get("validity_days", 14)
    
    # Клиент
    client_name = kp_data.get("client_name", "")
    client_contact = kp_data.get("client_contact", "")
    object_address = kp_data.get("object_address", "")
    
    # Путь к картинкам
    stamps_dir = Path(__file__).parent / "static" / "stamps"
    
    def img_to_base64(filename: str) -> str:
        path = stamps_dir / filename
        if path.exists():
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        return ""
    
    logo_b64 = img_to_base64(legal_entity.get("logo", ""))
    stamp_b64 = img_to_base64(legal_entity.get("stamp", ""))
    sign_b64 = img_to_base64(legal_entity.get("sign", ""))
    
    # Таблицы
    materials_rows = ""
    for i, m in enumerate(materials, 1):
        summa = m["quantity"] * m["price"]
        materials_rows += f"""
        <tr>
            <td class="center">{i}</td>
            <td>{m["name"]}</td>
            <td class="center">{m["quantity"]}</td>
            <td class="center">{m["unit"]}</td>
            <td class="right">{format_price(m["price"])}</td>
            <td class="right">{format_price(summa)}</td>
        </tr>"""
    
    works_rows = ""
    for i, w in enumerate(works, len(materials) + 1):
        summa = w["quantity"] * w["price"]
        works_rows += f"""
        <tr>
            <td class="center">{i}</td>
            <td>{w["name"]}</td>
            <td class="center">{w["quantity"]}</td>
            <td class="center">{w["unit"]}</td>
            <td class="right">{format_price(w["price"])}</td>
            <td class="right">{format_price(summa)}</td>
        </tr>"""
    
    # НДС строка
    vat_line = "НДС (Без НДС):" if not vat_rate else f"НДС ({vat_rate}%): {format_price(vat_amount)} руб"
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 15mm 15mm 20mm 15mm;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'DejaVu Sans', Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
            color: #1a1a1a;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #D4A53A;
        }}
        .logo {{
            height: 50px;
        }}
        .title {{
            font-size: 18pt;
            font-weight: bold;
            margin-bottom: 20px;
        }}
        .info-block {{
            margin-bottom: 15px;
        }}
        .info-row {{
            display: flex;
            margin-bottom: 5px;
        }}
        .info-label {{
            width: 120px;
            color: #666;
        }}
        .info-value {{
            flex: 1;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 10px;
        }}
        th, td {{
            border: 1px solid #ccc;
            padding: 6px 8px;
            text-align: left;
            font-size: 9pt;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
        }}
        .center {{ text-align: center; }}
        .right {{ text-align: right; }}
        .section-title {{
            font-weight: bold;
            margin: 15px 0 8px 0;
            font-size: 11pt;
        }}
        .totals {{
            margin-top: 15px;
            text-align: right;
        }}
        .totals-row {{
            margin-bottom: 3px;
        }}
        .totals-final {{
            font-size: 12pt;
            font-weight: bold;
        }}
        .amount-words {{
            margin: 15px 0;
            font-style: italic;
        }}
        .validity {{
            margin: 15px 0;
            color: #666;
        }}
        .signature-block {{
            margin-top: 40px;
            display: flex;
            align-items: flex-end;
            gap: 20px;
        }}
        .signature-line {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .stamp {{
            width: 150px;
            height: auto;
        }}
        .sign {{
            width: 120px;
            height: auto;
        }}
        .signer-name {{
            border-top: 1px solid #000;
            padding-top: 5px;
            min-width: 150px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="header">
        {'<img class="logo" src="data:image/png;base64,' + logo_b64 + '">' if logo_b64 else ''}
        <div></div>
    </div>
    
    <div class="title">Коммерческое предложение № {kp_number} от {today}</div>
    
    <div class="info-block">
        <div class="info-row">
            <span class="info-label">Поставщик:</span>
            <span class="info-value">{legal_entity["name"]}, ИНН {legal_entity["inn"]}, {legal_entity["address"]}, тел.: {legal_entity["phone"]}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Покупатель:</span>
            <span class="info-value">{client_name}{', тел.: ' + client_contact if client_contact else ''}</span>
        </div>
        {f'<div class="info-row"><span class="info-label">Объект:</span><span class="info-value">{object_address}</span></div>' if object_address else ''}
    </div>
    
    <div class="section-title">Материалы</div>
    <table>
        <tr>
            <th class="center" style="width:30px">№</th>
            <th>Наименование</th>
            <th class="center" style="width:50px">Кол-во</th>
            <th class="center" style="width:40px">Ед.</th>
            <th class="right" style="width:80px">Цена</th>
            <th class="right" style="width:90px">Сумма</th>
        </tr>
        {materials_rows}
    </table>
    <div class="totals-row right"><strong>Итого материалы: {format_price(total_materials)} руб</strong></div>
    
    <div class="section-title">Работы</div>
    <table>
        <tr>
            <th class="center" style="width:30px">№</th>
            <th>Наименование</th>
            <th class="center" style="width:50px">Кол-во</th>
            <th class="center" style="width:40px">Ед.</th>
            <th class="right" style="width:80px">Цена</th>
            <th class="right" style="width:90px">Сумма</th>
        </tr>
        {works_rows}
    </table>
    <div class="totals-row right"><strong>Итого работы: {format_price(total_works)} руб</strong></div>
    
    <div class="validity">Срок актуальности предложения {validity_days} рабочих дней</div>
    
    <div class="totals">
        <div class="totals-row">Итого: {format_price(total)} руб</div>
        <div class="totals-row">{vat_line}</div>
        <div class="totals-row totals-final">Всего к оплате: {format_price(total)} руб</div>
    </div>
    
    <div class="amount-words">{num_to_words(total)}</div>
    
    <div class="signature-block">
        <span>{legal_entity["signer_title"]}</span>
        <div class="signature-line">
            {'<img class="stamp" src="data:image/png;base64,' + stamp_b64 + '">' if stamp_b64 else ''}
            {'<img class="sign" src="data:image/png;base64,' + sign_b64 + '">' if sign_b64 else ''}
        </div>
        <div class="signer-name">{legal_entity["signer"]}</div>
    </div>
</body>
</html>"""
    return html, total_materials, total_works, total

async def generate_kp_pdf(kp_data: dict, user: dict) -> dict:
    """Генерирует PDF коммерческого предложения"""
    legal_entity_id = kp_data.get("legal_entity_id")
    legal_entity = LEGAL_ENTITIES.get(legal_entity_id)
    
    if not legal_entity:
        return {"error": f"Юрлицо {legal_entity_id} не найдено"}
    
    kp_number = await get_next_kp_number()
    html_content, total_materials, total_works, total = generate_kp_html(kp_data, legal_entity, kp_number)
    
    # Сохраняем HTML временно
    kp_dir = Path("/tmp/kp")
    kp_dir.mkdir(exist_ok=True)
    
    html_path = kp_dir / f"kp_{kp_number}.html"
    pdf_path = kp_dir / f"kp_{kp_number}.pdf"
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Конвертируем в PDF через weasyprint
    try:
        result = subprocess.run(
            ["weasyprint", str(html_path), str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            print(f"WeasyPrint error: {result.stderr}")
            return {"error": f"Ошибка генерации PDF: {result.stderr}"}
    except FileNotFoundError:
        return {"error": "WeasyPrint не установлен на сервере"}
    except Exception as e:
        return {"error": f"Ошибка: {str(e)}"}
    
    # Сохраняем в базу
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO kp_documents (kp_number, user_id, user_name, legal_entity_id, client_name, data, total_materials, total_works, total)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ''', kp_number, user["id"], user["name"], legal_entity_id, 
                kp_data.get("client_name", ""), json.dumps(kp_data),
                total_materials, total_works, total)
    
    return {
        "success": True,
        "kp_number": kp_number,
        "download_url": f"/api/kp/{kp_number}/download",
        "total_materials": total_materials,
        "total_works": total_works,
        "total": total
    }

async def handle_tool_use(tool_name: str, tool_input: dict, user: dict) -> str:
    """Обрабатывает вызов инструмента"""
    if tool_name == "generate_kp":
        result = await generate_kp_pdf(tool_input, user)
        if result.get("error"):
            return f"Ошибка генерации КП: {result['error']}"
        return f"""✅ КП № {result['kp_number']} успешно сформировано!

📊 **Итого:**
- Материалы: {format_price(result['total_materials'])} руб
- Работы: {format_price(result['total_works'])} руб  
- **Всего: {format_price(result['total'])} руб**

📥 [Скачать PDF]({result['download_url']})"""
    return "Неизвестный инструмент"

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
    
    # Список инструментов
    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
        KP_TOOL
    ]

    async def generate():
        full_reply = ""
        tool_use_block = None
        
        try:
            with client.messages.stream(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                messages=recent_messages,
                tools=tools
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
                                elif event.content_block.type == 'tool_use':
                                    tool_use_block = {
                                        "id": event.content_block.id,
                                        "name": event.content_block.name,
                                        "input": {}
                                    }
                                    yield f"data: {json.dumps({'type': 'tool_start', 'content': f'Генерирую КП...'})}\n\n"
                        elif event.type == 'content_block_stop':
                            pass
                
                # Получаем финальное сообщение для проверки tool_use
                final_message = stream.get_final_message()
                
                # Проверяем на tool_use
                for block in final_message.content:
                    if block.type == "tool_use" and block.name == "generate_kp":
                        yield f"data: {json.dumps({'type': 'generating_kp', 'content': 'Формирую КП...'})}\n\n"
                        
                        # Выполняем генерацию КП
                        tool_result = await handle_tool_use(block.name, block.input, user)
                        
                        # Отправляем результат обратно Claude для формирования ответа
                        tool_messages = recent_messages + [
                            {"role": "assistant", "content": final_message.content},
                            {
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": tool_result
                                }]
                            }
                        ]
                        
                        # Получаем финальный ответ
                        final_response = client.messages.create(
                            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                            messages=tool_messages,
                            tools=tools
                        )
                        
                        for final_block in final_response.content:
                            if final_block.type == "text":
                                full_reply += final_block.text
                                yield f"data: {json.dumps({'type': 'text', 'content': final_block.text})}\n\n"

            await save_message(session_id, "assistant", full_reply)
            messages.append({"role": "assistant", "content": full_reply})
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
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

# ── KP Download ──
@app.get("/api/kp/{kp_number}/download")
async def download_kp(kp_number: str, request: Request):
    """Скачать PDF коммерческого предложения"""
    user = require_auth(request)
    
    pdf_path = Path(f"/tmp/kp/kp_{kp_number}.pdf")
    if not pdf_path.exists():
        raise HTTPException(404, "КП не найдено")
    
    # Проверяем права доступа
    if db_pool:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT user_id, client_name FROM kp_documents WHERE kp_number=$1',
                kp_number
            )
            if not row:
                raise HTTPException(404, "КП не найдено в базе")
            # Можно добавить проверку user_id если нужно ограничить доступ
    
    # Получаем имя клиента для имени файла
    client_name = row['client_name'] if row else "client"
    filename = f"KP_{kp_number}_{client_name.replace(' ', '_')}.pdf"
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename
    )

@app.get("/api/kp")
async def list_kp(request: Request):
    """Список КП пользователя"""
    user = require_auth(request)
    if db_pool:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT kp_number, legal_entity_id, client_name, total, created_at
                   FROM kp_documents WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50''',
                user["id"]
            )
            return [
                {
                    "kp_number": r['kp_number'],
                    "legal_entity": LEGAL_ENTITIES.get(r['legal_entity_id'], {}).get("name", r['legal_entity_id']),
                    "client_name": r['client_name'],
                    "total": float(r['total']) if r['total'] else 0,
                    "created_at": r['created_at'].isoformat(),
                    "download_url": f"/api/kp/{r['kp_number']}/download"
                }
                for r in rows
            ]
    return []

# ── Frontend ──
@app.get("/")
async def serve_frontend(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return FileResponse("static/index.html")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
