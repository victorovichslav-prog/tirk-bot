import os
import re
import time
import datetime
import telebot
import requests
from threading import Thread
from flask import Flask

# ============ МИКРО-ВЕБ-СЕРВЕР ДЛЯ RENDER ============
app = Flask('')

@app.route('/')
def home():
    return "Tirk Systems v4.1 is running 24/7!"

def run_web_server():
    # Рендер сам выдает порт в переменные окружения, обычно это 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ============ НАСТРОЙКИ БОТА ============
CACHE = {}
CACHE_TTL = 600  # 10 минут

FANDOM_API = {
    'genshin': 'https://genshin-impact.fandom.com/api.php?action=parse&page=Promotional_Code&prop=wikitext&format=json',
    'roblox': 'https://blox-fruits.fandom.com/api.php?action=parse&page=Codes&prop=wikitext&format=json'
}

REDDIT_SOURCES = {
    'genshin': [
        'https://www.reddit.com/r/Genshin_Impact/new.json?limit=30',
        'https://www.reddit.com/r/GenshinImpactCodes/new.json?limit=20',
    ],
    'roblox': [
        'https://www.reddit.com/r/bloxfruits/new.json?limit=20',
    ]
}
MAX_AGE_REDDIT = 30 * 86400

BACKUP_CODES = {
    'genshin': (
        "🤖 <b>Genshin Impact</b>\n"
        "<i>⚠️ Ни один источник не ответил. Вот резервная база:</i>\n\n"
        "• <b>GENSHINGIFT</b> — 50 примогемов\n"
        "• <b>9A9239SLUX7A</b> — 60 примогемов"
    ),
    'roblox': (
        "🤖 <b>Blox Fruits</b>\n"
        "<i>⚠️ Ни один источник не ответил. Вот резервная база:</i>\n\n"
        "• <b>REWARD_FUN</b> — 2x опыт\n"
        "• <b>ADMIN_STRENGTH</b> — 2x опыт"
    )
}

# Брем токен из скрытых настроек сервера (Environment Variables)
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    print("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в настройках сервера!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============ УТИЛИТЫ ============
def time_ago(ts):
    diff = time.time() - ts
    if diff < 60: return "только что"
    elif diff < 3600: return f"{int(diff//60)} мин назад"
    elif diff < 86400: return f"{int(diff//3600)} ч назад"
    else: return f"{int(diff//86400)} д назад"

def extract_codes(text):
    pattern = r'\b([A-Z][A-Z0-9_]{3,19})\b'
    found = re.findall(pattern, text)
    blacklist = {'HTTP', 'HTTPS', 'HTML', 'URL', 'API', 'JSON', 'CSS', 'CS2', 'DOTA2', 'DOTA',
                 'MT', 'WWW', 'IMG', 'PNG', 'JPG', 'GIF', 'PDF', 'ZIP', 'EXE', 'DLL', 'FAQ',
                 'TOS', 'GDPR', 'USA', 'UK', 'EU', 'CN', 'JP', 'KR', 'RU', 'UTC', 'SERVER',
                 'ASIA', 'AMERICA', 'EUROPE', 'CHINA', 'TW', 'HK', 'MACAO', 'PRIMOGEM',
                 'MORA', 'HERO', 'WIT', 'EXP', 'ORE', 'RECIPE', 'MAIL', 'CODE', 'CODES',
                 'REDEEM', 'VALID', 'INFINITE', 'INDEFINITE', 'DISCOVERED', 'EXPIRED',
                 'NOTES', 'FROM', 'UNTIL', 'MAX', 'USAGE', 'LIMIT', 'REVOKED', 'ALREADY',
                 'CLAIMED', 'CONFIRM', 'INVALID', 'INPUT', 'SPACE', 'CHARACTER', 'BEGINNING',
                 'END', 'CAUSE', 'BECOME', 'PLAYER', 'ADVENTURE', 'RANK', 'EXCEPTION',
                 'PRIME', 'GAMING', 'OFFER', 'EARLIEST', 'ABLE', 'CLAIM', 'REWARD',
                 'MAILBOX', 'DELIVERY', 'STANDARD', 'FOLLOWING', 'UNIQUE', 'SURPRISE',
                 'NICOLE', 'LITTLE', 'HOYOLAB', 'ARTICLE', 'ADDITIONALLY', 'PLEASE',
                 'AWARE', 'CONDITIONS', 'CELEBRATORY', 'MILESTONE', 'SIMILAR', 'ACTIVITY',
                 'OCCASIONALLY', 'RELEASED', 'HOYOVERSE', 'SOCIAL', 'MEDIA', 'EVENT',
                 'LIVE', 'STREAM', 'SETTING', 'MENU', 'ACCOUNT', 'ONLINE', 'OFFICIAL',
                 'PAGE', 'GLOBAL', 'ONLY', 'CURRENT', 'REDEEMABLE', 'EARLY', 'SENT',
                 'TELLING', 'STILL', 'INPUTTING', 'CHARACTERS', 'WILL', 'ALSO', 'NOTE',
                 'DOES', 'NOT', 'MEAN', 'CAN', 'HITS', 'DECIDES', 'REVOKE', 'ALL',
                 'TIMES', 'LISTED', 'BELOW', 'ARE', 'ACCORDING', 'SIGN', 'EDIT',
                 'REFERENCES', 'NOTACODE', 'YES', 'NO', 'SECOND', 'SEA', 'FIRST',
                 'TITLE', 'GIVEN', 'WHEN', 'ENTERS', 'BUT', 'ITSELF', 'REDEEMED'}
    results = []
    for code in found:
        if code in blacklist: continue
        if not re.search(r'\d', code):
            if code not in ('GENSHINGIFT',): continue
        results.append(code)
    return list(dict.fromkeys(results))

# ============ FANDOM WIKI API ПАРСЕР ============
def parse_fandom_api(game_key):
    try:
        url = FANDOM_API.get(game_key)
        if not url: return None
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return None
        
        data = r.json()
        wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')
        if not wikitext: return None
        
        wikitext_clean = re.sub(r'<!--.*?-->', '', wikitext, flags=re.DOTALL)
        
        if game_key == 'genshin':
            active_match = re.search(r'==\s*Active Codes\s*==(.*?)(?===\s*Expired Codes\s*==|===|$)', wikitext_clean, re.DOTALL)
            if not active_match: return None
            
            active_section = active_match.group(1)
            code_blocks = re.findall(r'\{\{Code Row\s*\|(.*?)(?:\}\}|\|notacode=yes)', active_section, re.DOTALL)
            
            collected = []
            seen_codes = set()
            
            for block in code_blocks:
                parts = [p.strip() for p in block.split('|')]
                if len(parts) < 5: continue
                
                code = parts[0].upper()
                server = parts[1]
                rewards = parts[2]
                expiry = parts[4]
                
                is_expired = False
                if expiry and expiry.lower() not in ('unknown', 'indefinite', 'n/a', ''):
                    try:
                        expiry_date = datetime.datetime.strptime(expiry, '%Y-%m-%d')
                        if expiry_date < datetime.datetime.now(): is_expired = True
                    except: pass
                
                if len(code) < 4 or len(code) > 20 or not re.match(r'^[A-Z0-9_]+$', code) or code in seen_codes: continue
                seen_codes.add(code)
                
                desc_parts = []
                if rewards:
                    clean_rewards = re.sub(r'\{\{[^}]+\}\}', '', rewards.replace('*', ' ').replace(';', ', '))
                    clean_rewards = re.sub(r'\s+', ' ', clean_rewards).strip()
                    if clean_rewards: desc_parts.append(clean_rewards)
                
                if server:
                    server_map = {'G': 'Global', 'A': 'All', 'NA': 'America', 'EU': 'Europe', 'SEA': 'Asia'}
                    desc_parts.append(f"[{server_map.get(server, server)}]")
                
                if expiry and expiry.lower() not in ('unknown', 'indefinite', 'n/a', ''): desc_parts.append(f"(до {expiry})")
                
                desc = " ".join(desc_parts) if desc_parts else "из Fandom Wiki"
                if not is_expired:
                    collected.append({'code': code, 'desc': desc, 'age': 'актуально'})
            
            if collected:
                return {'codes': collected, 'source': 'Fandom Wiki', 'freshness': f"🟢 Fandom Wiki, {len(collected)} активных кодов"}
        
        elif game_key == 'roblox':
            working_start = wikitext_clean.find('Working Codes')
            expired_start = wikitext_clean.find('Expired Codes')
            if working_start == -1: return None
            if expired_start == -1: expired_start = len(wikitext_clean)
            
            working_section = wikitext_clean[working_start:expired_start]
            lines = working_section.split('\n')
            
            collected = []
            seen_codes = set()
            
            for i, line in enumerate(lines):
                code_match = re.search(r'\|\s*<code>([^<]+)</code>', line)
                if code_match:
                    code = code_match.group(1).strip().upper()
                    if len(code) < 4 or len(code) > 25 or not re.match(r'^[A-Z0-9_]+$', code) or code in seen_codes: continue
                    seen_codes.add(code)
                    
                    reward = ""
                    for j in range(i+1, min(i+5, len(lines))):
                        next_line = lines[j].strip()
                        if next_line.startswith('|-') or next_line.startswith('!') or next_line.startswith('|}') or '<code>' in next_line: break
                        if next_line.startswith('|'):
                            reward = re.sub(r'\{\{[^}]+\}\}', '', next_line[1:].strip())
                            reward = re.sub(r'\[\[[^\]]+\|([^\]]+)\]\]', r'\1', reward)
                            break
                    
                    desc = reward if reward else "из Fandom Wiki"
                    collected.append({'code': code, 'desc': desc, 'age': 'актуально'})
            
            if collected:
                return {'codes': collected, 'source': 'Fandom Wiki', 'freshness': f"🟢 Fandom Wiki, {len(collected)} рабочих кодов"}
        return None
    except: return None

# ============ REDDIT ПАРСЕР ============
def parse_reddit(urls, game_key, max_age_sec):
    all_codes = []
    seen_codes = set()
    for url in urls:
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200: continue
            posts = r.json().get('data', {}).get('children', [])
            now = time.time()
            
            for post in posts:
                p = post.get('data', {})
                created = p.get('created_utc', 0)
                if now - created > max_age_sec: continue
                
                all_text = p.get('title', '') + '\n' + p.get('selftext', '')
                codes = extract_codes(all_text)
                
                for code in codes:
                    code = code.upper().strip()
                    if code in seen_codes: continue
                    seen_codes.add(code)
                    
                    desc = p.get('title', '')
                    all_codes.append({'code': code, 'desc': desc[:110], 'age': time_ago(created)})
            if all_codes: break
        except: continue
    if all_codes: return {'codes': all_codes, 'source': 'Reddit', 'freshness': f"🟢 Live с Reddit, {len(all_codes)} кодов"}
    return None

def get_codes(game_key):
    now = time.time()
    cache_key = f"{game_key}_final"
    if cache_key in CACHE:
        ts, data, src = CACHE[cache_key]
        if now - ts < CACHE_TTL: return data, src
    
    result = parse_fandom_api(game_key)
    source = 'fandom' if result else None
    
    if not result and game_key in REDDIT_SOURCES:
        result = parse_reddit(REDDIT_SOURCES[game_key], game_key, MAX_AGE_REDDIT)
        if result: source = 'reddit'
        
    if result:
        if len(result['codes']) > 15: result['codes'] = result['codes'][:15]
        CACHE[cache_key] = (now, result, source)
        return result, source
    return None, None

# ============ КОМАНДЫ БОТА ============
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 <b>Tirk Systems v4.1 — Render Cloud</b>\n\n/genshin — промокоды\n/roblox — Blox Fruits\n/status — статус", parse_mode='HTML')

@bot.message_handler(commands=['genshin', 'roblox'])
def handle_codes(message):
    is_genshin = message.text == '/genshin'
    game_key = 'genshin' if is_genshin else 'roblox'
    game_title = '🎮 Genshin Impact' if is_genshin else '🍎 Blox Fruits'
    bot.send_chat_action(message.chat.id, 'typing')
    data, source = get_codes(game_key)
    
    if data and data.get('codes'):
        lines = [f"🤖 <b>{game_title}</b>", f"<i>{data['freshness']}</i>", ""]
        for item in data['codes']:
            age_badge = f" ({item['age']})" if item['age'] != 'актуально' else ""
            lines.append(f"• <b>{item['code']}</b>{age_badge} — {item['desc']}")
        final_text = "\n".join(lines)
    else: final_text = BACKUP_CODES[game_key]
    bot.send_message(message.chat.id, final_text, parse_mode='HTML', disable_web_page_preview=True)

@bot.message_handler(commands=['status'])
def status(message):
    lines = []
    for game in ['genshin', 'roblox']:
        cache_key = f"{game}_final"
        if cache_key in CACHE:
            ts, data, src = CACHE[cache_key]
            lines.append(f"• <b>{game}</b>: {time_ago(ts)} | {src}")
        else: lines.append(f"• <b>{game}</b>: нет данных")
    bot.send_message(message.chat.id, "📊 <b>Статус:</b>\n" + "\n".join(lines), parse_mode='HTML')

if __name__ == '__main__':
    print("🌍 Запуск веб-сервера для Render...")
    # Запускаем Flask-сервер в отдельном потоке, чтобы он слушал порт 10000
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()
    
    print("🚀 Бот Tirk Systems запущен!")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)