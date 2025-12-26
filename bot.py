import logging
import io
import math
import os
import re
import json
import time
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import Forbidden

# --- IMPORT KEEP_ALIVE FOR RENDER ---
from keep_alive import keep_alive

# --- CONFIGURATION ---
# We now load the token from the Environment Variable "BOT_TOKEN"
TOKEN = os.environ.get("BOT_TOKEN")
ROOT_FOLDER_ID = "13OMd9S3N7ONRXiYFbbWPkavuwg3ZKqeD"
ITEMS_PER_PAGE = 10
KEY_FILE_NAME = "service_key.json" 

# Check if Token exists
if not TOKEN:
    print("❌ Error: BOT_TOKEN environment variable is not set!")

# --- TRANSLATION DICTIONARY ---
STRINGS = {
    'en': {
        'welcome': "🌟 **Welcome to Perfection In Physics** 🌟",
        'error_drive': "❌ Error: Could not connect to Google Drive.",
        'search_usage': "ℹ️ **Search Usage:**\nType `/search` followed by the file name.\nExample: `/search Chapter 1`",
        'searching': "🔍 Searching for: `'{q}'`...",
        'no_results': "❌ No results found.",
        'search_header': "🔍 **Search Results**\n`Query: {context}`\n\nFound: {count} files",
        'browser_header': "📂 **{name}**\n`{path}`\n\nPage {page} of {total}",
        'empty_folder': "\n\n❌ _This folder is empty._",
        'back': "🔙 Back",
        'home': "🏠 Home",
        'prev': "⬅️ Prev",
        'next': "Next ➡️",
        'page_fmt': "📄 {page}/{total}",
        'starting': "⬇️ Starting Request...",
        'fetching': "⏳ **Fetching Info...**",
        'error_fetch': "❌ Error fetching info: {msg}",
        'file_too_large': "⚠️ **File too large (>100MB).**\n\n🔗 [Click to Open in Drive]({link})",
        'dl_drive': "📥 **Downloading from Drive...**\n`{name}`\n{bar} {percent}%",
        'error_init': "❌ Init Error: {msg}",
        'ul_telegram': "📤 **Uploading to Telegram...**\n`{name}`\n{bar} {percent}%",
        'caption': "📄 **{name}**\n💾 Size: {size}\n📅 Date: {date}\n🤖 _Perfection In Physics Bot_",
        'ul_failed': "⚠️ **Upload Failed.**\n\n🔗 [Click to Open in Drive]({link})"
    },
    'ar': {
        'welcome': "🌟 **مرحبًا بك في Perfection In Physics** 🌟",
        'error_drive': "❌ خطأ: تعذر الاتصال بجوجل درايف.",
        'search_usage': "ℹ️ **طريقة البحث:**\nاكتب `/search` متبوعة باسم الملف.\nمثال: `/search الفصل الأول`",
        'searching': "🔍 جاري البحث عن: `'{q}'`...",
        'no_results': "❌ لم يتم العثور على نتائج.",
        'search_header': "🔍 **نتائج البحث**\n`الاستعلام: {context}`\n\nتم العثور على: {count} ملفات",
        'browser_header': "📂 **{name}**\n`{path}`\n\nصفحة {page} من {total}",
        'empty_folder': "\n\n❌ _هذا المجلد فارغ._",
        'back': "🔙 رجوع",
        'home': "🏠 الرئيسية",
        'prev': "⬅️ السابق",
        'next': "التالي ➡️",
        'page_fmt': "📄 {page}/{total}",
        'starting': "⬇️ جاري بدء الطلب...",
        'fetching': "⏳ **جاري جلب المعلومات...**",
        'error_fetch': "❌ خطأ في جلب المعلومات: {msg}",
        'file_too_large': "⚠️ **الملف كبير جدًا (>100MB).**\n\n🔗 [اضغط هنا للفتح في درايف]({link})",
        'dl_drive': "📥 **جاري التنزيل من درايف...**\n`{name}`\n{bar} {percent}%",
        'error_init': "❌ خطأ في البدء: {msg}",
        'ul_telegram': "📤 **جاري الرفع إلى تيليجرام...**\n`{name}`\n{bar} {percent}%",
        'caption': "📄 **{name}**\n💾 الحجم: {size}\n📅 التاريخ: {date}\n🤖 _Perfection In Physics Bot_",
        'ul_failed': "⚠️ **فشل الرفع.**\n\n🔗 [اضغط هنا للفتح في درايف]({link})"
    }
}

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- GOOGLE DRIVE SETUP ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

try:
    # Check if running on Render (Environment Variable)
    if os.environ.get("GOOGLE_CREDENTIALS"):
        logging.info("🔄 Loading credentials from Environment Variable...")
        key_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
        creds = service_account.Credentials.from_service_account_info(key_dict, scopes=SCOPES)
    
    # Check if running Locally (File)
    elif os.path.exists(KEY_FILE_NAME):
        logging.info("📂 Loading credentials from Local File...")
        creds = service_account.Credentials.from_service_account_file(KEY_FILE_NAME, scopes=SCOPES)
    
    else:
        raise FileNotFoundError("No credentials found! Set GOOGLE_CREDENTIALS env var or add service_key.json")
        
    logging.info("✅ Credentials Loaded Successfully")

except Exception as e:
    logging.error(f"❌ Key Error: {e}")
    # Don't exit immediately, let the bot try to start so we can see logs on Render
    creds = None

# --- MEMORY & CACHE & USERS ---
folder_names = {ROOT_FOLDER_ID: "Root"}
parent_map = {}
search_cache = {}
background_tasks = set()

# Load File ID Cache
CACHE_FILE = "file_ids.json"
try:
    with open(CACHE_FILE, "r") as f:
        file_id_cache = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    file_id_cache = {}

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(file_id_cache, f)
    except: pass

# Load User List
USERS_FILE = "users.json"
try:
    with open(USERS_FILE, "r") as f:
        subscribed_users = set(json.load(f))
except (FileNotFoundError, json.JSONDecodeError):
    subscribed_users = set()

def save_users():
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(list(subscribed_users), f)
    except: pass

def register_user(user_id):
    if user_id not in subscribed_users:
        subscribed_users.add(user_id)
        save_users()

def get_text(key, lang_code, **kwargs):
    """Helper to get translated string"""
    lang = lang_code if lang_code in STRINGS else 'en'
    text = STRINGS[lang].get(key, STRINGS['en'][key])
    return text.format(**kwargs)

# --- PROGRESS HELPER ---
class ProgressReader:
    def __init__(self, file_obj, size, update_callback):
        self.file = file_obj
        self.size = size
        self.callback = update_callback
        self.bytes_read = 0
        self.last_update = time.time()

    def read(self, size=-1):
        data = self.file.read(size)
        if data:
            self.bytes_read += len(data)
            now = time.time()
            if now - self.last_update > 4:
                self.last_update = now
                percent = int((self.bytes_read / self.size) * 100)
                asyncio.run_coroutine_threadsafe(
                    self.callback(percent),
                    asyncio.get_running_loop()
                )
        return data

    def seek(self, *args): return self.file.seek(*args)
    def tell(self): return self.file.tell()

def make_bar(percent):
    filled = int(percent / 10)
    empty = 10 - filled
    return f"{'⬛' * filled}{'⬜' * empty}"

# --- HELPERS ---
def format_size(size_bytes):
    if not size_bytes: return ""
    try:
        s = int(size_bytes)
        if s == 0: return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(s, 1024)))
        p = math.pow(1024, i)
        return f"{round(s / p, 1)} {size_name[i]}"
    except: return ""

def format_date(iso_str):
    if not iso_str: return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d")
    except: return iso_str

def get_icon(mime, name):
    name_l = name.lower()
    if mime == 'application/vnd.google-apps.folder': return "📁"
    if 'pdf' in mime: return "📕"
    if 'image' in mime: return "🖼️"
    if 'video' in mime: return "🎬"
    if 'audio' in mime: return "🎵"
    if 'presentation' in mime or 'ppt' in name_l: return "🟧"
    if 'sheet' in mime or 'xls' in name_l: return "📊"
    if 'document' in mime or 'word' in name_l: return "📝"
    if 'zip' in mime or 'rar' in name_l: return "📦"
    return "📄"

def build_path_string(service_instance, folder_id):
    if folder_id == ROOT_FOLDER_ID: return "Root"
    current_id = folder_id
    path_names = []
    loop_limit = 0
    while current_id and loop_limit < 10:
        if current_id in folder_names:
            name = folder_names[current_id]
        else:
            try:
                meta = service_instance.files().get(fileId=current_id, fields='name, parents').execute()
                name = meta.get('name', 'Unknown')
                folder_names[current_id] = name
                if 'parents' in meta: parent_map[current_id] = meta['parents'][0]
            except: name = "Unknown"
        path_names.insert(0, name)
        if current_id == ROOT_FOLDER_ID: break
        current_id = parent_map.get(current_id)
        loop_limit += 1
    return " » ".join(path_names)

def natural_keys(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

# --- DRIVE ACTIONS ---
def get_files(folder_id):
    if not creds: return None
    try:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType, size, parents)"
        ).execute()

        all_files = results.get('files', [])
        folders = []
        files = []
        for f in all_files:
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                folders.append(f)
            else:
                files.append(f)

        folders.sort(key=lambda x: natural_keys(x['name']))
        files.sort(key=lambda x: natural_keys(x['name']))

        return folders + files
    except Exception as e:
        logging.error(f"API Error: {e}")
        return None

def search_drive(query):
    if not creds: return []
    try:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        query = query.replace("'", "\\'")
        results = service.files().list(
            q=f"name contains '{query}' and trashed = false",
            pageSize=50, fields="nextPageToken, files(id, name, mimeType, size, parents)",
            orderBy="name").execute()
        return results.get('files', [])
    except Exception as e: return []

# --- MENU GENERATOR ---
async def send_menu(update: Update, files, context_id, page=0, is_search=False, msg=None):
    # Detect Language
    lang = update.effective_user.language_code.split('-')[0] if update.effective_user.language_code else 'en'

    keyboard = []
    total_pages = math.ceil(len(files) / ITEMS_PER_PAGE)

    if is_search:
        title = get_text('search_header', lang, context=context_id, count=len(files))
    else:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        path = build_path_string(service, context_id)

        if context_id == ROOT_FOLDER_ID:
            current_name = get_text('home', lang).replace("🏠 ", "")
        else:
            current_name = folder_names.get(context_id, "Folder")

        title = get_text('browser_header', lang, name=current_name, path=path, page=page+1, total=total_pages)

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_files = files[start:end]

    if not current_files:
        title += get_text('empty_folder', lang)

    for f in current_files:
        icon = get_icon(f['mimeType'], f['name'])
        folder_names[f['id']] = f['name']

        if f['mimeType'] == 'application/vnd.google-apps.folder':
            parent_map[f['id']] = context_id
            keyboard.append([InlineKeyboardButton(f"{icon} {f['name']}", callback_data=f"OPEN|{f['id']}")])
        else:
            size = format_size(f.get('size'))
            name = f['name']
            if len(name) > 35: name = name[:32] + "..."
            btn_txt = f"{icon} {name} ({size})"
            keyboard.append([InlineKeyboardButton(btn_txt, callback_data=f"DL|{f['id']}")])

    nav = []
    if not is_search:
        pid = parent_map.get(context_id)
        if context_id != ROOT_FOLDER_ID:
            if pid:
                nav.append(InlineKeyboardButton(get_text('back', lang), callback_data=f"OPEN|{pid}"))
            nav.append(InlineKeyboardButton(get_text('home', lang), callback_data=f"OPEN|{ROOT_FOLDER_ID}"))

    if total_pages > 1:
        prefix = "SPAGE" if is_search else "PAGE"
        if page > 0: nav.append(InlineKeyboardButton(get_text('prev', lang), callback_data=f"{prefix}|{context_id}|{page-1}"))
        nav.append(InlineKeyboardButton(get_text('page_fmt', lang, page=page+1, total=total_pages), callback_data="IGNORE"))
        if page < total_pages - 1: nav.append(InlineKeyboardButton(get_text('next', lang), callback_data=f"{prefix}|{context_id}|{page+1}"))
    if nav: keyboard.append(nav)

    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if msg: await msg.edit_text(title, reply_markup=reply_markup, parse_mode='Markdown')
        else: await update.message.reply_text(title, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception: pass

# --- WORKER FUNCTIONS ---
def get_meta_worker(file_id):
    if not creds: return {"status": "error", "msg": "No Credentials"}
    try:
        thread_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        meta = thread_service.files().get(
            fileId=file_id,
            fields='name, size, mimeType, webViewLink, modifiedTime'
        ).execute()
        return {"status": "ok", "meta": meta}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

def init_download_worker(file_id, meta):
    try:
        thread_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        mime = meta.get('mimeType', '')

        request = None
        if "application/vnd.google-apps" in mime and "folder" not in mime:
            request = thread_service.files().export_media(fileId=file_id, mimeType='application/pdf')
        else:
            request = thread_service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request, chunksize=5 * 1024 * 1024)
        return {"status": "ok", "downloader": downloader, "fh": fh}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

async def handle_download(update, file_id):
    try:
        query = update.callback_query
        register_user(query.from_user.id)
        # Detect Language
        lang = query.from_user.language_code.split('-')[0] if query.from_user.language_code else 'en'

        await query.answer(get_text('starting', lang), show_alert=False)

        # 1. FETCH METADATA
        status = await query.message.reply_text(get_text('fetching', lang))
        loop = asyncio.get_running_loop()

        with ThreadPoolExecutor() as pool:
            meta_res = await loop.run_in_executor(pool, get_meta_worker, file_id)

        if meta_res['status'] != 'ok':
            await status.edit_text(get_text('error_fetch', lang, msg=meta_res['msg']))
            return

        meta = meta_res['meta']
        name = meta.get('name', 'File')
        size_bytes = int(meta.get('size', 0))
        size_str = format_size(size_bytes)
        mod_time = format_date(meta.get('modifiedTime'))
        link = meta.get('webViewLink', '')

        if "application/vnd.google-apps" in meta.get('mimeType', '') and "folder" not in meta.get('mimeType', ''):
            name += ".pdf"

        caption = get_text('caption', lang, name=name, size=size_str, date=mod_time)

        # 2. CACHE CHECK
        if file_id in file_id_cache:
            tg_file_id = file_id_cache[file_id]
            try:
                await query.message.reply_document(
                    document=tg_file_id,
                    caption=caption,
                    parse_mode='Markdown'
                )
                await status.delete()
                return
            except Exception as e:
                logging.warning(f"Cached ID failed: {e}")

        # Size Check
        if size_bytes > 99 * 1024 * 1024:
            await status.edit_text(get_text('file_too_large', lang, link=link), parse_mode='Markdown')
            return

        # 3. DOWNLOAD
        await status.edit_text(get_text('dl_drive', lang, name=name, bar=make_bar(0), percent=0), parse_mode='Markdown')

        with ThreadPoolExecutor() as pool:
            init_res = await loop.run_in_executor(pool, init_download_worker, file_id, meta)

            if init_res['status'] != 'ok':
                await status.edit_text(get_text('error_init', lang, msg=init_res['msg']))
                return

            downloader = init_res['downloader']
            fh = init_res['fh']
            done = False
            last_update_time = time.time()

            while not done:
                status_obj, done = await loop.run_in_executor(pool, downloader.next_chunk)

                now = time.time()
                if now - last_update_time > 4:
                    last_update_time = now
                    if status_obj:
                        progress = int(status_obj.progress() * 100)
                        try:
                            await status.edit_text(get_text('dl_drive', lang, name=name, bar=make_bar(progress), percent=progress), parse_mode='Markdown')
                        except: pass

            fh.seek(0)

        # 4. UPLOAD
        await status.edit_text(get_text('ul_telegram', lang, name=name, bar=make_bar(0), percent=0), parse_mode='Markdown')

        async def upload_progress_callback(percent):
            try:
                await status.edit_text(get_text('ul_telegram', lang, name=name, bar=make_bar(percent), percent=percent), parse_mode='Markdown')
            except: pass

        progress_file = ProgressReader(fh, len(fh.getvalue()), upload_progress_callback)

        try:
            sent_msg = await query.message.reply_document(
                document=progress_file,
                filename=name,
                caption=caption,
                parse_mode='Markdown',
                read_timeout=300,
                write_timeout=300,
                connect_timeout=300
            )

            if sent_msg.document:
                file_id_cache[file_id] = sent_msg.document.file_id
                save_cache()

            await status.delete()
        except Exception as e:
            try:
                await status.edit_text(get_text('ul_failed', lang, link=link), parse_mode='Markdown')
            except: pass

    except asyncio.CancelledError:
        return

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_chat.id)
    lang = update.effective_user.language_code.split('-')[0] if update.effective_user.language_code else 'en'

    welcome_text = get_text('welcome', lang)

    files = get_files(ROOT_FOLDER_ID)
    if files is None:
        await update.message.reply_text(get_text('error_drive', lang))
    else:
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        await send_menu(update, files, ROOT_FOLDER_ID, 0, False, None)

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_chat.id)
    lang = update.effective_user.language_code.split('-')[0] if update.effective_user.language_code else 'en'

    if not context.args:
        await update.message.reply_text(get_text('search_usage', lang), parse_mode='Markdown')
        return
    q = " ".join(context.args)
    msg = await update.message.reply_text(get_text('searching', lang, q=q), parse_mode='Markdown')
    res = search_drive(q)
    if not res: await msg.edit_text(get_text('no_results', lang))
    else:
        search_cache[q] = res
        await send_menu(update, res, q, 0, True, msg)

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    register_user(q.from_user.id)

    if "DL|" not in q.data:
        try: await q.answer()
        except: pass

    data = q.data
    if data == "IGNORE": return

    if "DL|" in data:
        task = asyncio.create_task(handle_download(update, data.split("|")[1]))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    elif "PAGE|" in data:
        is_search = "SPAGE" in data
        parts = data.split("|")
        ctx_id, pg = parts[1], int(parts[2])
        files = search_cache.get(ctx_id) if is_search else get_files(ctx_id)
        if files: await send_menu(update, files, ctx_id, pg, is_search, q.message)

    elif "OPEN|" in data:
        tid = data.split("|")[1]
        files = get_files(tid)
        if files: await send_menu(update, files, tid, 0, False, q.message)

async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "🏠 Home"),
        BotCommand("search", "🔍 Search Files")
    ])

    if subscribed_users:
        print(f"📢 Broadcasting to {len(subscribed_users)} users...")
        for user_id in subscribed_users:
            try:
                await app.bot.send_message(chat_id=user_id, text="Perfection In Physics Bot Back ❤")
                await asyncio.sleep(0.05)
            except Exception: pass
        print(f"✅ Broadcast complete.")

if __name__ == '__main__':
    # START KEEP ALIVE SERVER BEFORE THE BOT
    keep_alive()

    if not TOKEN:
        print("❌ CRITICAL ERROR: Token not found. Bot cannot start.")
    else:
        request = HTTPXRequest(
            connection_pool_size=20,
            read_timeout=300,
            write_timeout=300,
            connect_timeout=60
        )

        app = ApplicationBuilder().token(TOKEN).request(request).post_init(post_init).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("search", search))
        app.add_handler(CallbackQueryHandler(btn))
        print("✅ Bot is online!")

        try:
            app.run_polling(drop_pending_updates=True)
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user.")
        except Exception as e:
            print(f"\n❌ Error: {e}")