import os
import re
import time
import datetime
import threading
import telebot
import requests
from flask import Flask

# =============================================================
# TIRK SYSTEMS v5.1 -- Полный бак (FIXED)
# =============================================================

# ============ 1. КОНФИГУРАЦИЯ И ОКРУЖЕНИЕ ============
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    print("[FATAL] Переменная окружения BOT_TOKEN не найдена!")
    print("[FATAL] Установи BOT_TOKEN в настройках Render и перезапусти.")
    exit(1)

PORT = int(os.environ.get("PORT", 10000))
CACHE = {}
CACHE_TTL = 600  # 10 минут

# =============================================================
# 2. ИСТОЧНИКИ ДАННЫХ
# =============================================================

# Fandom Wiki API
FANDOM_API = {
    'genshin': 'https://genshin-impact.fandom.com/api.php?action=parse&page=Promotional_Code&prop=wikitext&format=json',
    'bloxfruits': 'https://blox-fruits.fandom.com/api.php?action=parse&page=Codes&prop=wikitext&format=json',
    'kinglegacy': 'https://king-legacy.fandom.com/api.php?action=parse&page=Codes&prop=wikitext&format=json',
    'astd': 'https://allstartd.fandom.com/api.php?action=parse&page=Codes&prop=wikitext&format=json',
}

# Reddit fallback
REDDIT_SOURCES = {
    'genshin': [
        'https://www.reddit.com/r/Genshin_Impact/new.json?limit=30',
        'https://www.reddit.com/r/GenshinImpactCodes/new.json?limit=20',
    ],
    'bloxfruits': ['https://www.reddit.com/r/bloxfruits/new.json?limit=20'],
    'kinglegacy': ['https://www.reddit.com/r/KingLegacy/new.json?limit=20'],
    'astd': ['https://www.reddit.com/r/AllStarTowerDefense/new.json?limit=20'],
}
MAX_AGE_REDDIT = 30 * 86400

# Steam deals (CheapShark API)
STEAM_API = 'https://www.cheapshark.com/api/1.0/deals?storeID=1&onSale=1&pageSize=15'

# =============================================================
# 3. РЕЗЕРВНЫЕ БАЗЫ
# =============================================================

BACKUP_CODES = {
    'genshin': [
        {'code': 'GENSHINGIFT', 'desc': '50 примогемов, 3 опыта героя'},
        {'code': '9A9239SLUX7A', 'desc': '60 примогемов'},
    ],
    'bloxfruits': [
        {'code': 'REWARD_FUN', 'desc': '2x опыт'},
        {'code': 'ADMIN_STRENGTH', 'desc': '2x опыт'},
    ],
    'kinglegacy': [
        {'code': 'DinoxLive', 'desc': '+100,000 $'},
        {'code': 'Peodiz', 'desc': '+100,000 $'},
        {'code': '<3LEEPUNGG', 'desc': 'Free 2x EXP for 30 minutes'},
        {'code': 'WELCOMETOKINGLEGACY', 'desc': 'Free 2x EXP for 30 minutes'},
        {'code': 'SKGames', 'desc': 'Free 2x EXP for 30 minutes (Sea King Games group)'},
        {'code': 'FREESTATSRESET', 'desc': 'Free Refund Stats'},
        {'code': '2MFAV', 'desc': 'Free Refund Stats'},
    ],
    'astd': [
        {'code': 'tboicats', 'desc': 'Stardust 170, Gems 3000'},
        {'code': 'sorryfordelayandmonkeyking', 'desc': 'Stardust 280, Gems 4000'},
        {'code': 'yickadee', 'desc': 'Stardust 230, Gems 2000'},
    ],
}

STEAM_BACKUP = [
    {'title': 'Counter-Strike 2', 'price': 'Free', 'discount': '100%', 'store': 'Steam'},
    {'title': 'Dota 2', 'price': 'Free', 'discount': '100%', 'store': 'Steam'},
    {'title': 'Apex Legends', 'price': 'Free', 'discount': '100%', 'store': 'Steam'},
]

# =============================================================
# 4. ИНИЦИАЛИЗАЦИЯ БОТА
# =============================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Регистрация команд в меню Telegram
bot.set_my_commands([
    telebot.types.BotCommand('start', 'Запустить бота'),
    telebot.types.BotCommand('genshin', 'Коды Genshin Impact'),
    telebot.types.BotCommand('roblox', 'Коды Blox Fruits'),
    telebot.types.BotCommand('kinglegacy', 'Коды King Legacy'),
    telebot.types.BotCommand('astd', 'Коды All Star Tower Defense'),
    telebot.types.BotCommand('steam', 'Скидки Steam'),
    telebot.types.BotCommand('status', 'Статус бота'),
])

# =============================================================
# 5. УТИЛИТЫ И СТИЛИЗАЦИЯ
# =============================================================

def time_ago(ts):
    diff = time.time() - ts
    if diff < 60:
        return "только что"
    elif diff < 3600:
        return f"{int(diff//60)} мин назад"
    elif diff < 86400:
        return f"{int(diff//3600)} ч назад"
    else:
        return f"{int(diff//86400)} д назад"

def make_header(emoji, title, subtitle=""):
    lines = [f"<b>{emoji} {title}</b>"]
    if subtitle:
        lines.append(f"<i>{subtitle}</i>")
    lines.append("")
    return "
".join(lines)

def make_footer(source_name, is_live=True):
    if is_live:
        return (
            "
<i>💡 Данные актуальны на момент запроса.
"
            "Просроченные коды отфильтрованы автоматически.</i>"
        )
    else:
        return (
            "
<i>⚠️ Показана резервная база — коды могут быть просрочены.
"
            "Проверьте актуальность в игре.</i>"
        )

def extract_codes(text):
    pattern = r'([A-Z][A-Z0-9_]{3,19})'
    found = re.findall(pattern, text)
    blacklist = {
        'HTTP', 'HTTPS', 'HTML', 'URL', 'API', 'JSON', 'CSS', 'CS2', 'DOTA2', 'DOTA',
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
        'TITLE', 'GIVEN', 'WHEN', 'ENTERS', 'BUT', 'ITSELF', 'REDEEMED',
        'UPDATE', 'VISITS', 'GEMS', 'GOLD', 'RESET', 'STAT', 'FREE',
        'MINUTES', 'HOURS', 'DAYS', 'MONTHS', 'YEARS', 'NEW', 'OLD',
        'BIG', 'SMALL', 'FAST', 'SLOW', 'EASY', 'HARD', 'GOOD', 'BAD',
        'ON', 'OFF', 'UP', 'DOWN', 'LEFT', 'RIGHT',
        'TOP', 'BOTTOM', 'FRONT', 'BACK', 'NEXT', 'PREV', 'LAST',
        'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX',
        'SEVEN', 'EIGHT', 'NINE', 'TEN', 'HUNDRED', 'THOUSAND',
    }
    results = []
    for code in found:
        if code in blacklist:
            continue
        if not re.search(r'\d', code):
            if code not in ('GENSHINGIFT',):
                continue
        results.append(code)
    return list(dict.fromkeys(results))

# =============================================================
# 6. ПАРСЕРЫ ИСТОЧНИКОВ
# =============================================================

def parse_fandom_genshin(wikitext_clean):
    """Парсит Genshin Impact из Fandom Wiki."""
    active_match = re.search(
        r'==\s*Active Codes\s*==(.*?)(?===\s*Expired Codes\s*==|===|$)',
        wikitext_clean, re.DOTALL
    )
    if not active_match:
        return None

    active_section = active_match.group(1)
    code_blocks = re.findall(
        r'\{\{Code Row\s*\|(.*?)(?:\}\}|\|notacode=yes)', active_section, re.DOTALL
    )

    collected = []
    seen_codes = set()

    for block in code_blocks:
        parts = [p.strip() for p in block.split('|')]
        if len(parts) < 5:
            continue

        code = parts[0].upper()
        server = parts[1]
        rewards = parts[2]
        discovery = parts[3]
        expiry = parts[4]

        is_expired = False
        if expiry and expiry.lower() not in ('unknown', 'indefinite', 'n/a', ''):
            try:
                expiry_date = datetime.datetime.strptime(expiry, '%Y-%m-%d')
                if expiry_date < datetime.datetime.now():
                    is_expired = True
            except:
                pass

        if len(code) < 4 or len(code) > 20:
            continue
        if not re.match(r'^[A-Z0-9_]+$', code):
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)

        desc_parts = []
        if rewards:
            clean_rewards = rewards.replace('*', ' ').replace(';', ', ')
            clean_rewards = re.sub(r'\{\{[^}]+\}\}', '', clean_rewards)
            clean_rewards = re.sub(r'\s+', ' ', clean_rewards).strip()
            if clean_rewards:
                desc_parts.append(clean_rewards)

        if server:
            server_map = {
                'G': '🌍 Global', 'A': '🌍 All', 'NA': '🇺🇸 America',
                'EU': '🇪🇺 Europe', 'SEA': '🇨🇳 Asia', 'CN': '🇨🇳 China',
                'SAR': '🇭🇰 TW/HK/Macao'
            }
            srv = server_map.get(server, server)
            desc_parts.append(srv)

        if expiry and expiry.lower() not in ('unknown', 'indefinite', 'n/a', ''):
            desc_parts.append(f"📆 до {expiry}")
        elif expiry.lower() == 'unknown':
            desc_parts.append("❓ срок неизвестен")

        desc = " | ".join(desc_parts) if desc_parts else "из Fandom Wiki"
        if len(desc) > 150:
            desc = desc[:147] + '...'

        if not is_expired:
            collected.append({'code': code, 'desc': desc})

    return collected if collected else None

def parse_fandom_bloxfruits(wikitext_clean):
    """Парсит Blox Fruits из Fandom Wiki."""
    working_start = wikitext_clean.find('Working Codes')
    expired_start = wikitext_clean.find('Expired Codes')

    if working_start == -1:
        return None
    if expired_start == -1:
        expired_start = len(wikitext_clean)

    working_section = wikitext_clean[working_start:expired_start]
    lines = working_section.split('
')

    collected = []
    seen_codes = set()

    for i, line in enumerate(lines):
        code_match = re.search(r'\|\s*<code>([^<]+)</code>', line)
        if code_match:
            code = code_match.group(1).strip().upper()

            reward = ""
            for j in range(i+1, min(i+5, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith('|-') or next_line.startswith('!') or next_line.startswith('|}'):
                    break
                if '<code>' in next_line:
                    break
                if next_line.startswith('|'):
                    reward = next_line[1:].strip()
                    reward = re.sub(r'\{\{[^}]+\}\}', '', reward)
                    reward = re.sub(r'\[\[[^\]]+\|([^\]]+)\]\]', r'', reward)
                    reward = re.sub(r'\s+', ' ', reward).strip()
                    break

            if len(code) < 4 or len(code) > 25:
                continue
            if not re.match(r'^[A-Z0-9_]+$', code):
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)

            desc = reward if reward else "из Fandom Wiki"
            if len(desc) > 150:
                desc = desc[:147] + '...'

            collected.append({'code': code, 'desc': desc})

    return collected if collected else None

def parse_fandom_kinglegacy(wikitext_clean):
    """Парсит King Legacy из Fandom Wiki (plain text формат)."""
    # Ищем секцию Active Codes
    active_match = re.search(
        r'Active Codes:\s*
+(.*?)(?=

|
[A-Z]|\[\[Category|$)',
        wikitext_clean, re.DOTALL
    )
    if not active_match:
        # Пробуем без двоеточия
        active_match = re.search(
            r'Active Codes\s*
+(.*?)(?=

|
[A-Z]|\[\[Category|$)',
            wikitext_clean, re.DOTALL
        )

    if not active_match:
        return None

    section = active_match.group(1)
    lines = section.strip().split('
')

    collected = []
    seen_codes = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Формат: Code - description или Code — description
        match = re.match(r'^([A-Za-z0-9_<]{3,25})\s*[-—]\s*(.+)$', line)
        if match:
            code = match.group(1).strip()
            desc = match.group(2).strip()

            # Очищаем от wiki-разметки
            code = re.sub(r'<[^>]+>', '', code)
            desc = re.sub(r'<[^>]+>', '', desc)
            desc = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'', desc)
            desc = re.sub(r'\[\[([^\]]+)\]\]', r'', desc)
            desc = re.sub(r'\{\{[^}]+\}\}', '', desc)
            desc = re.sub(r'\s+', ' ', desc).strip()

            if len(code) < 3 or len(code) > 25:
                continue
            if not re.match(r'^[A-Za-z0-9_]+$', code):
                continue
            if code.upper() in seen_codes:
                continue
            seen_codes.add(code.upper())

            if len(desc) > 150:
                desc = desc[:147] + '...'

            collected.append({'code': code, 'desc': desc})

    return collected if collected else None

def parse_fandom_astd(wikitext_clean):
    """Парсит ASTD из Fandom Wiki (tabber + article-table формат)."""
    # Ищем Working Codes внутри <tabber>
    working_match = re.search(
        r'Working Codes:?\s*=\s*
*\{\|.*?
(.*?)
\|-\|
',
        wikitext_clean, re.DOTALL
    )
    if not working_match:
        # Пробуем другой паттерн
        working_match = re.search(
            r'Working Codes:?\s*=\s*
*\{\|class="article-table".*?(.*?)
\|-\|
',
            wikitext_clean, re.DOTALL
        )

    if not working_match:
        # Ищем любую таблицу с ! Code !! Reward !! Date
        working_match = re.search(
            r'!\s*Code\s*!!\s*Reward\s*!!\s*Date\s*
\|-
(.*?)
\|-\|
',
            wikitext_clean, re.DOTALL
        )

    if not working_match:
        return None

    section = working_match.group(1)
    lines = section.split('
|-')

    collected = []
    seen_codes = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Ищем строки таблицы: |<p style="color:Tomato;">code||{{Stardust|170}}, {{Gems|3000}}||23.06.2026
        # или просто | code || reward || date
        cells = re.findall(r'\|\s*([^|]*(?:\{\{[^}]+\}\}[^|]*)*)', line)
        if len(cells) >= 3:
            code = cells[0].strip()
            reward = cells[1].strip()
            date = cells[2].strip()
        elif len(cells) >= 2:
            code = cells[0].strip()
            reward = cells[1].strip()
            date = ""
        else:
            continue

        # Очищаем код
        code = re.sub(r'<[^>]+>', '', code)
        code = re.sub(r'\s+', '', code)

        if len(code) < 3 or len(code) > 30:
            continue
        if not re.match(r'^[A-Za-z0-9_]+$', code):
            continue
        if code.upper() in seen_codes:
            continue
        seen_codes.add(code.upper())

        # Очищаем reward
        reward = re.sub(r'\{\{([^|]+)\|([^}]+)\}\}', r' ', reward)
        reward = re.sub(r'\[\[[^\]]+\|([^\]]+)\]\]', r'', reward)
        reward = re.sub(r'\s+', ' ', reward).strip()

        desc = reward if reward else "из Fandom Wiki"
        if date:
            desc += f" | 📆 {date}"
        if len(desc) > 150:
            desc = desc[:147] + '...'

        collected.append({'code': code, 'desc': desc})

    return collected if collected else None

def parse_fandom_api(game_key):
    """Главный парсер Fandom Wiki."""
    try:
        url = FANDOM_API.get(game_key)
        if not url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[FANDOM] {game_key} -> HTTP {r.status_code}")
            return None

        data = r.json()
        wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')
        if not wikitext:
            print(f"[FANDOM] {game_key} -> пустой wikitext")
            return None

        wikitext_clean = re.sub(r'<!--.*?-->', '', wikitext, flags=re.DOTALL)

        if game_key == 'genshin':
            codes = parse_fandom_genshin(wikitext_clean)
        elif game_key == 'bloxfruits':
            codes = parse_fandom_bloxfruits(wikitext_clean)
        elif game_key == 'kinglegacy':
            codes = parse_fandom_kinglegacy(wikitext_clean)
        elif game_key == 'astd':
            codes = parse_fandom_astd(wikitext_clean)
        else:
            codes = None

        if codes:
            return {
                'codes': codes,
                'source': 'Fandom Wiki',
                'freshness': f"🟢 Fandom Wiki — {len(codes)} активных кодов"
            }
        return None

    except Exception as e:
        print(f"[FANDOM ERROR] {game_key}: {e}")
        return None

def parse_reddit(urls, game_key, max_age_sec):
    """Парсит Reddit как fallback."""
    all_codes = []
    seen_codes = set()

    for url in urls:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue

            data = r.json()
            posts = data.get('data', {}).get('children', [])
            now = time.time()

            for post in posts:
                p = post.get('data', {})
                title = p.get('title', '')
                body = p.get('selftext', '')
                created = p.get('created_utc', 0)

                if now - created > max_age_sec:
                    continue

                all_text = title + '
' + body
                codes = extract_codes(all_text)

                for code in codes:
                    code = code.upper().strip()
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)

                    desc = ""
                    lines = all_text.replace('', '
').split('
')
                    for line in lines:
                        if code in line.upper():
                            clean = re.sub(r'[*#`\[\]()]', '', line).strip()
                            if len(clean) > len(code) + 3:
                                desc = clean
                                break

                    if not desc:
                        desc = title
                    if len(desc) > 120:
                        desc = desc[:117] + '...'

                    all_codes.append({
                        'code': code,
                        'desc': desc,
                        'age': time_ago(created)
                    })

            if all_codes:
                break

        except Exception as e:
            print(f"[REDDIT ERROR] {url}: {e}")
            continue

    if all_codes:
        return {
            'codes': all_codes,
            'source': 'Reddit',
            'freshness': f"🟠 Reddit — {len(all_codes)} кодов"
        }
    return None

def parse_steam_deals():
    """Парсит скидки Steam через CheapShark API."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        r = requests.get(STEAM_API, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[STEAM] HTTP {r.status_code}")
            return None

        deals = r.json()
        if not deals or not isinstance(deals, list):
            print("[STEAM] Пустой ответ")
            return None

        collected = []
        for deal in deals[:15]:
            title = deal.get('title', 'Unknown')
            sale_price = deal.get('salePrice', '0')
            normal_price = deal.get('normalPrice', '0')
            savings = float(deal.get('savings', 0))
            deal_id = deal.get('dealID', '')

            discount = round(savings)
            price_str = f"${sale_price}" if sale_price != '0.00' else 'Free'
            old_price = f"~~${normal_price}~~" if normal_price != sale_price else ''

            store_url = f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else ''

            collected.append({
                'title': title,
                'price': price_str,
                'old_price': old_price,
                'discount': f"-{discount}%",
                'url': store_url,
            })

        if collected:
            return {
                'deals': collected,
                'source': 'CheapShark',
                'freshness': f"🔥 CheapShark — {len(collected)} горячих скидок"
            }
        return None

    except Exception as e:
        print(f"[STEAM ERROR] {e}")
        return None

# =============================================================
# 7. SMART GETTER
# =============================================================

def get_game_codes(game_key):
    """Получает коды для игры: Fandom -> Reddit -> Backup."""
    now = time.time()
    cache_key = f"{game_key}_final"

    if cache_key in CACHE:
        ts, data, src = CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return data, src, True

    result = None
    source = None

    # 1. Fandom Wiki
    print(f"[GET] {game_key}: Fandom Wiki...")
    result = parse_fandom_api(game_key)
    if result and len(result['codes']) <= 100:
        source = 'fandom'
        print(f"[GET] {game_key}: Fandom OK, {len(result['codes'])} кодов")
    elif result and len(result['codes']) > 100:
        print(f"[GET] {game_key}: Подозрительно много кодов ({len(result['codes'])}), скипаем")
        result = None

    # 2. Reddit fallback
    if not result and game_key in REDDIT_SOURCES:
        print(f"[GET] {game_key}: Reddit fallback...")
        result = parse_reddit(REDDIT_SOURCES[game_key], game_key, MAX_AGE_REDDIT)
        if result:
            source = 'reddit'
            print(f"[GET] {game_key}: Reddit OK, {len(result['codes'])} кодов")

    # 3. Backup fallback
    if not result:
        print(f"[GET] {game_key}: Backup fallback")
        backup = BACKUP_CODES.get(game_key, [])
        if backup:
            result = {
                'codes': backup,
                'source': 'Backup',
                'freshness': "⚠️ Резервная база"
            }
            source = 'backup'

    if result:
        if len(result['codes']) > 15:
            result['codes'] = result['codes'][:15]
        CACHE[cache_key] = (now, result, source)
        return result, source, source != 'backup'

    return None, None, False

def get_steam_deals():
    """Получает скидки Steam: API -> Backup."""
    now = time.time()
    cache_key = "steam_final"

    if cache_key in CACHE:
        ts, data, src = CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return data, src, True

    print("[GET] steam: CheapShark API...")
    result = parse_steam_deals()
    if result:
        source = 'cheapshark'
        print(f"[GET] steam: OK, {len(result['deals'])} сделок")
        CACHE[cache_key] = (now, result, source)
        return result, source, True

    print("[GET] steam: Backup fallback")
    result = {
        'deals': STEAM_BACKUP,
        'source': 'Backup',
        'freshness': "⚠️ Резервная база"
    }
    CACHE[cache_key] = (now, result, 'backup')
    return result, 'backup', False

# =============================================================
# 8. ОБРАБОТЧИКИ КОМАНД
# =============================================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    text = (
        "<b>🤖 Tirk Systems v5.1 — Полный бак</b>
"
        "━━━━━━━━━━━━━━━━━━━━━━

"
        "<b>🎮 Игровые промокоды:</b>
"
        "  /genshin — Genshin Impact
"
        "  /roblox — Blox Fruits
"
        "  /kinglegacy — King Legacy
"
        "  /astd — All Star Tower Defense

"
        "<b>🛒 Игровые скидки:</b>
"
        "  /steam — Горячие скидки Steam

"
        "<b>📊 Система:</b>
"
        "  /status — Статус и источники

"
        "<i>💡 Все данные берутся из Fandom Wiki и проверяются на актуальность.
"
        "Просроченные коды отфильтрованы автоматически.</i>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['genshin'])
def cmd_genshin(message):
    bot.send_chat_action(message.chat.id, 'typing')
    data, source, is_live = get_game_codes('genshin')

    if not data:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить данные.")
        return

    text = make_header("🎮", "Genshin Impact", data['freshness'])
    for item in data['codes']:
        text += f"• <code>{item['code']}</code> — {item['desc']}
"
    text += make_footer(source, is_live)

    bot.send_message(message.chat.id, text, disable_web_page_preview=True)

@bot.message_handler(commands=['roblox'])
def cmd_roblox(message):
    bot.send_chat_action(message.chat.id, 'typing')
    data, source, is_live = get_game_codes('bloxfruits')

    if not data:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить данные.")
        return

    text = make_header("🍎", "Blox Fruits", data['freshness'])
    for item in data['codes']:
        text += f"• <code>{item['code']}</code> — {item['desc']}
"
    text += make_footer(source, is_live)

    bot.send_message(message.chat.id, text, disable_web_page_preview=True)

@bot.message_handler(commands=['kinglegacy'])
def cmd_kinglegacy(message):
    bot.send_chat_action(message.chat.id, 'typing')
    data, source, is_live = get_game_codes('kinglegacy')

    if not data:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить данные.")
        return

    text = make_header("👑", "King Legacy", data['freshness'])
    for item in data['codes']:
        text += f"• <code>{item['code']}</code> — {item['desc']}
"
    text += make_footer(source, is_live)

    bot.send_message(message.chat.id, text, disable_web_page_preview=True)

@bot.message_handler(commands=['astd'])
def cmd_astd(message):
    bot.send_chat_action(message.chat.id, 'typing')
    data, source, is_live = get_game_codes('astd')

    if not data:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить данные.")
        return

    text = make_header("⭐", "All Star Tower Defense", data['freshness'])
    for item in data['codes']:
        text += f"• <code>{item['code']}</code> — {item['desc']}
"
    text += make_footer(source, is_live)

    bot.send_message(message.chat.id, text, disable_web_page_preview=True)

@bot.message_handler(commands=['steam'])
def cmd_steam(message):
    bot.send_chat_action(message.chat.id, 'typing')
    data, source, is_live = get_steam_deals()

    if not data:
        bot.send_message(message.chat.id, "❌ Не удалось загрузить данные.")
        return

    text = make_header("🛒", "Steam Deals", data['freshness'])

    for deal in data['deals'][:10]:
        old = f" {deal['old_price']}" if deal.get('old_price') else ''
        text += f"🎮 <b>{deal['title']}</b>
"
        text += f"   💰 {deal['price']}{old} 🔥 <b>{deal['discount']}</b>
"
        if deal.get('url'):
            text += f"   🔗 <a href='{deal['url']}'>Купить</a>
"
        text += "
"

    if not is_live:
        text += "
<i>⚠️ Показана резервная база — проверьте актуальность цен.</i>"
    else:
        text += "
<i>💡 Данные с CheapShark API в реальном времени.</i>"

    bot.send_message(message.chat.id, text, disable_web_page_preview=True)

@bot.message_handler(commands=['status'])
def cmd_status(message):
    lines = ["<b>📊 Tirk Systems v5.1 — Статус</b>", "━━━━━━━━━━━━━━━━━━━━━━", ""]

    games = [
        ('genshin', '🎮 Genshin Impact'),
        ('bloxfruits', '🍎 Blox Fruits'),
        ('kinglegacy', '👑 King Legacy'),
        ('astd', '⭐ ASTD'),
    ]

    for key, name in games:
        cache_key = f"{key}_final"
        if cache_key in CACHE:
            ts, data, src = CACHE[cache_key]
            ago = time_ago(ts)
            src_emoji = "🟢" if src == 'fandom' else "🟠" if src == 'reddit' else "⚠️"
            lines.append(f"{src_emoji} <b>{name}</b>: {ago} | {data['freshness']}")
        else:
            lines.append(f"⬜ <b>{name}</b>: ещё не запрашивалось")

    lines.append("")

    if 'steam_final' in CACHE:
        ts, data, src = CACHE['steam_final']
        ago = time_ago(ts)
        src_emoji = "🟢" if src == 'cheapshark' else "⚠️"
        lines.append(f"{src_emoji} <b>🛒 Steam</b>: {ago} | {data['freshness']}")
    else:
        lines.append(f"⬜ <b>🛒 Steam</b>: ещё не запрашивалось")

    lines.append("")
    lines.append(f"<i>⏱️ Кэш обновляется каждые {CACHE_TTL//60} минут</i>")

    bot.send_message(message.chat.id, "
".join(lines))

# =============================================================
# 9. FLASK WEB-SERVER (для Render)
# =============================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Tirk Systems v5.1 is online!"

@app.route('/health')
def health():
    return {"status": "ok", "version": "5.1", "timestamp": time.time()}

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# =============================================================
# 10. ЗАПУСК
# =============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Tirk Systems v5.1 — Полный бак")
    print("=" * 60)
    print(f"📡 Flask-сервер: http://0.0.0.0:{PORT}")
    print(f"🤖 Telegram-бот: инициализация...")
    print(f"💾 Кэш: {CACHE_TTL} секунд")
    print("=" * 60)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"✅ Flask запущен в потоке (port={PORT})")

    print("✅ Бот запущен, ждём команды...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"[FATAL] Бот упал: {e}")
