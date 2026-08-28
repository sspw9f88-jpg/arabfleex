import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import subprocess
import os
import time
import requests
import re
import json
import threading
import queue
import shutil
import urllib3
import random
from urllib.parse import urlparse, unquote, quote
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import boto3
    from boto3.s3.transfer import TransferConfig
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

# تجاهل تحذيرات الـ SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- رقم الإصدار ---
VERSION = "14.8.2 (Smart Local Transcoding + Strict yt-dlp Format + SeriesMP4 Bypass + 360p Added)"

TOKEN = "8888154300:AAHqlPnauMLMWcYcG8-Bzrir9Xg0dWmS-bs"
ADMIN_CHAT_ID = 1013251619
CONFIG_FILE = "api_keys_config.json"

DEFAULT_KEYS = {
    "LARHU_API_KEY": "863rrqmdzm6sb4k4xwv",
    "ABSTREAM_API_KEY": "1855r1beof65n58tyjyd",
    "UQLOAD_API_KEY": "157590rbrqefwnpfz7n9qw",
    "VIDMOLY_API_KEY": "613979bpr8w0ktgk2qq9pl",
    "VIDARA_API_KEY": "cf4a3701c18ed1d4e044ee4c116ecdad3c95de9d3e2e09ec6210512851109573",
    "ONECLOUD_API_KEY": "HpZFGCVRWlaMGLybm2SqyIkjW8AilubITKtLLXrleqjZCWuxHzTcooY3IwCC8fXZ",
    "GOFILE_TOKEN": "cx4wR4PUzr9z8QhC1KySejOaq9obdoSQ",
    "VK_ACCESS_TOKEN": "vk1.a._jd7hQ2JExSqiXa87k8xEsb1EBkBUi4am0HIwMACqafuqpUZVC_KhUj-RrZRKDK4BNnFIkblwgZ0G-5jc41HzleTWTXO_dMRX6steQpiV-gPJgyhVrSEHi2Uu1OSXXjSr2jE858IJhKHJJY9tfoM5oaZ_qdjWE92zCBylXb1Tm_NqzVKsd3zK_8jWj14Mc6463-3Cs8jn8maizzzQY1jcQ",
    "DOODSTREAM_API_KEY": "561449auivdyww0hr4t161",
    "CF_R2_ACCESS_KEY": "c889ca01c50cc327d73a3726e01225a8",
    "CF_R2_SECRET_KEY": "a291f299669e419b8b5d85fa8cff421732fc3af32030b731260d844f6d5bc2a2",
    "CF_R2_ACCOUNT_ID": "a28ef4137231ef7aa6756d28c5450bcd",
    "CF_R2_BUCKET_NAME": "media-stream",
    "CF_R2_PUBLIC_URL": "https://pub-eb6d088b2e4848c1b93664d6cb1123d1.r2.dev",
    "FREEDL_API_KEY": "32642u1rlgm6q2c9b2hxc"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_KEYS, f, indent=4)
        return DEFAULT_KEYS.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            updated = False
            for k, v in DEFAULT_KEYS.items():
                if k not in data:
                    data[k] = v
                    updated = True
            if updated:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f_update:
                    json.dump(data, f_update, indent=4)
            return data
    except Exception:
        return DEFAULT_KEYS.copy()

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)

bot_config = load_config()

LARHU_DOMAIN = "larhu.website"
ABSTREAM_DOMAIN = "abstream.to"
UQLOAD_DOMAIN = "uqload.vc" 
VIDMOLY_DOMAIN = "vidmoly.me"
VIDARA_API_DOMAIN = "api.vidara.so"
DOODSTREAM_DOMAIN = "doodapi.co" 
ONECLOUD_DOMAIN = "1cloudfile.com"
FREEDL_DOMAIN = "freedl.ink"

bot = telebot.TeleBot(TOKEN)
active_tasks = {}
upload_selections = {}
failed_uploads = {}
processed_messages = set()
task_queue = queue.Queue()
merge_sessions = {}
batch_sessions = {}

COMMON_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        try:
            if task.get('type') == 'upload_only':
                upload_only_logic(task['chat_id'], task['msg_id'], task['task_id'])
            elif task.get('type') == 'merge':
                merge_process_logic(task['links'], task['chat_id'], task['msg_id'], task['servers'], task.get('custom_name'), task.get('quality', 'best'))
            elif task.get('type') == 'encode_all':
                encode_process_logic(task['url'], task['chat_id'], task['msg_id'], task['servers'], task.get('custom_name'))
            else:
                process_logic(task['url'], task['chat_id'], task['msg_id'], task['servers'], task.get('custom_name'), task.get('quality', 'best'))
        except Exception as e:
            print(f"Error in queue task: {e}")
        finally:
            task_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

def auto_cleanup():
    while True:
        try:
            now = time.time()
            for filename in os.listdir('.'):
                if filename.startswith(("video_", "out_", "err_", "merge_", "concat_")):
                    filepath = os.path.join('.', filename)
                    if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - (12 * 3600):
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass
        except Exception:
            pass
        time.sleep(3600)

threading.Thread(target=auto_cleanup, daemon=True).start()

def make_bar(percent):
    p = min(100, max(0, int(percent)))
    filled = p // 10
    empty = 10 - filled
    return "█" * filled + "░" * empty

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0

def format_time(seconds):
    mins, secs = divmod(int(seconds), 60)
    return f"{mins:02d}:{secs:02d}"

def get_cancel_keyboard(task_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ إلغاء العملية", callback_data=f"cancel_{task_id}"))
    return markup

def safe_error_text(text):
    return str(text).replace('`', '').replace('*', '').replace('_', '').replace('[', '').replace(']', '')

def get_emoji_for_server(s):
    if s == 'Abstream': return '🟢'
    if s == 'Larhu': return '🟠'
    if s == 'Uqload': return '🔵'
    if s == 'Vidmoly': return '🟣'
    if s == 'Vidara': return '🟡'
    if s == 'Doodstream': return '🟤'
    if s == 'VK': return '📘'
    if s == 'GoFile': return '🌐'
    if s == 'CloudflareR2': return '☁️'
    if s == 'FreeDL': return '🔴'
    return '⚙️'

def safe_edit(bot_instance, chat_id, message_id, text, reply_markup=None):
    try:
        bot_instance.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        pass

def get_video_height(filepath):
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height", "-of", "csv=s=x:p=0", filepath]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return int(result.stdout.strip())
    except FileNotFoundError:
        raise Exception("⚠️ أداة FFmpeg غير مثبتة على السيرفر! يرجى تشغيل: sudo apt install ffmpeg")
    except:
        return 1080 

def transcode_video(input_file, target_res, out_file, bot_instance, chat_id, message_id, task_id, custom_msg=""):
    try:
        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]
        dur_out = subprocess.check_output(dur_cmd).strip()
        total_seconds = float(dur_out)
    except:
        total_seconds = 0

    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-vf", f"scale=-2:{target_res}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "copy",
        out_file
    ]
    
    try:
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    except FileNotFoundError:
        raise Exception("⚠️ أداة FFmpeg غير مثبتة! يرجى تثبيتها لتعمل هذه الميزة.")
        
    if task_id in active_tasks:
        active_tasks[task_id]['process'] = process

    last_upd = time.time()
    for line in process.stderr:
        if task_id in active_tasks and active_tasks.get(task_id, {}).get("cancel"):
            process.terminate()
            raise Exception("🛑 تم إلغاء العملية.")
        
        if total_seconds > 0 and "time=" in line and time.time() - last_upd > 3:
            time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
            if time_match:
                h, m, s = time_match.groups()
                current_seconds = int(h)*3600 + int(m)*60 + float(s)
                perc = min(100, (current_seconds / total_seconds) * 100)
                txt = f"{custom_msg}\n\n⚙️ *تحويل الجودة لـ {target_res}p...*\n📊 التقدم: `[{make_bar(perc)}]` *{int(perc)}%*"
                safe_edit(bot_instance, chat_id, message_id, txt, reply_markup=get_cancel_keyboard(task_id))
                last_upd = time.time()
                
    process.wait()
    if process.returncode != 0:
        raise Exception(f"فشل تحويل الفيديو إلى جودة {target_res}p")

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def cancel_task(call):
    task_id = call.data.replace('cancel_', '')
    if task_id in active_tasks:
        active_tasks[task_id]['cancel'] = True
        p = active_tasks[task_id].get('process')
        if p:
            try:
                p.terminate()
            except Exception:
                pass
        bot.answer_callback_query(call.id, "🛑 جاري إيقاف العملية فوراً...")
    else:
        bot.answer_callback_query(call.id, "⚠️ العملية انتهت أو لم تبدأ بعد.")

@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    welcome_text = f"""🤖 *مرحباً بك في بوت Arab Fleex الاحترافي!*

⚡ البوت جاهز لسحب ورفع الفيديوهات (مفرد/باتش/دمج).

📋 *أهم الأوامر:*
🔹 `/batch` - رفع عدة حلقات دفعة واحدة.
🔹 `/merge` - دمج عدة أجزاء في فيديو واحد.
🔹 `/queue` - عرض الطابور والمهمات الحالية.
🔹 `/keys` - إدارة مفاتيح API الخاصة بك.
🔹 `/stats` - حالة السيرفر الداخلي.
🔹 `/check` - فحص الاتصال بسيرفرات الرفع.

📦 *الإصدار الحالي:* `{VERSION}`"""
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['keys'])
def manage_keys_cmd(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("🔑 Vidmoly", callback_data="changekey_VIDMOLY_API_KEY"),
        InlineKeyboardButton("🔑 Uqload", callback_data="changekey_UQLOAD_API_KEY"),
        InlineKeyboardButton("🔑 Abstream", callback_data="changekey_ABSTREAM_API_KEY"),
        InlineKeyboardButton("🔑 Larhu", callback_data="changekey_LARHU_API_KEY"),
        InlineKeyboardButton("🔑 Vidara", callback_data="changekey_VIDARA_API_KEY"),
        InlineKeyboardButton("🔑 GoFile", callback_data="changekey_GOFILE_TOKEN"),
        InlineKeyboardButton("🔑 VK Token", callback_data="changekey_VK_ACCESS_TOKEN"),
        InlineKeyboardButton("🔑 Doodstream", callback_data="changekey_DOODSTREAM_API_KEY"),
        InlineKeyboardButton("☁️ Cloudflare R2", callback_data="changekey_CF_R2_ACCESS_KEY"),
        InlineKeyboardButton("🔑 FreeDL", callback_data="changekey_FREEDL_API_KEY")
    ]
    markup.add(*buttons)
    bot.reply_to(message, "⚙️ *لوحة إدارة مفاتيح الـ API*\n\nاختر السيرفر الذي تريد تغيير مفتاحه. التغيير يطبق فوراً ويُحفظ دائماً:\n(بالنسبة لـ Cloudflare R2 ينصح بتعديل باقي البيانات يدوياً من السكربت لتعددها)", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('changekey_'))
def handle_change_key_callback(call):
    key_name = call.data.replace('changekey_', '')
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"📝 الرجاء إرسال المفتاح/البيان الجديد لـ `{key_name.split('_')[0]}` الآن:\n\n_(أو أرسل /cancel للإلغاء)_", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_new_key, key_name)

def process_new_key(message, key_name):
    if message.text == '/cancel':
        bot.reply_to(message, "🛑 تم إلغاء التغيير.")
        return
    new_key = message.text.strip()
    bot_config[key_name] = new_key
    save_config(bot_config)
    bot.reply_to(message, f"✅ تم حفظ البيان الجديد لـ `{key_name.split('_')[0]}` بنجاح وتفعيله فوراً!", parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    try:
        msg = bot.reply_to(message, "⏳ *جاري جمع الإحصائيات...*", parse_mode="Markdown")
        total, used, free = shutil.disk_usage(".")
        txt = f"🖥️ *حالة السيرفر:*\n\n💽 *المساحة (للمجلد الحالي):*\nمتاحة: `{format_size(free)}`\nإجمالي: `{format_size(total)}`\n"
        
        if HAS_PSUTIL:
            ram = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=1)
            txt += f"🧠 *الرام:* `{ram.percent}%` مستهلك\n⚙️ *المعالج:* `{cpu}%` مستهلك\n"
        else:
            txt += f"\n⚠️ *تنبيه:* إحصائيات الرام والمعالج غير متاحة. الرجاء تثبيت `psutil`.\n"
            
        txt += f"⏳ *مهام الطابور الحالية:* `{task_queue.qsize()}` مهمة"
        safe_edit(bot, message.chat.id, msg.message_id, txt)
    except Exception as e:
        bot.reply_to(message, f"❌ *حدث خطأ أثناء جلب الإحصائيات:*\n`{safe_error_text(e)}`", parse_mode="Markdown")

@bot.message_handler(commands=['check'])
def check_servers(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    msg = bot.reply_to(message, "🔍 *جاري فحص حالة اتصال السيرفرات والمفاتيح...*", parse_mode="Markdown")
    txt = f"📊 *تقرير حالة السيرفرات ({VERSION}):*\n\n"
    
    servers_to_check = [
        ("Abstream", ABSTREAM_DOMAIN, bot_config["ABSTREAM_API_KEY"], "🟢"),
        ("Larhu", LARHU_DOMAIN, bot_config["LARHU_API_KEY"], "🟠"),
        ("Uqload", UQLOAD_DOMAIN, bot_config["UQLOAD_API_KEY"], "🔵"),
        ("Vidmoly", VIDMOLY_DOMAIN, bot_config["VIDMOLY_API_KEY"], "🟣"),
        ("Vidara", VIDARA_API_DOMAIN, bot_config["VIDARA_API_KEY"], "🟡"),
        ("Doodstream", DOODSTREAM_DOMAIN, bot_config["DOODSTREAM_API_KEY"], "🟤"),
        ("FreeDL", FREEDL_DOMAIN, bot_config["FREEDL_API_KEY"], "🔴"),
    ]
    
    headers = {'User-Agent': COMMON_USER_AGENT}
    for name, dom, key, emj in servers_to_check:
        try:
            url_to_check = f"https://{dom}/api/upload/server?key={key}"
            if name == "Vidara": url_to_check = f"https://{dom}/"
            r = requests.get(url_to_check, headers=headers, timeout=10, verify=False)
            if r.status_code in [200, 301, 302, 403]: txt += f"{emj} *{name}:* متصل ✅\n"
            else: txt += f"{emj} *{name}:* 🔴 خطأ (كود: {r.status_code})\n"
        except requests.exceptions.Timeout: txt += f"{emj} *{name}:* 🔴 فشل (انتهى وقت الاتصال)\n"
        except Exception: txt += f"{emj} *{name}:* 🔴 فشل الاتصال\n"

    try:
        r = requests.get('https://api.gofile.io/servers', timeout=10)
        if r.status_code == 200: txt += f"🌐 *GoFile:* متصل ✅\n"
        else: txt += f"🌐 *GoFile:* 🔴 خطأ (كود: {r.status_code})\n"
    except Exception: txt += f"🌐 *GoFile:* 🔴 فشل الاتصال\n"
        
    try:
        vk_r = requests.post("https://api.vk.com/method/users.get", data={"access_token": bot_config["VK_ACCESS_TOKEN"], "v": "5.199"}, timeout=10)
        try:
            vk_json = vk_r.json()
            if "response" in vk_json: txt += f"📘 *VK:* متصل والمفتاح صحيح ✅\n"
            else: txt += f"📘 *VK:* 🔴 خطأ مفتاح\n"
        except Exception:
            if vk_r.status_code == 200: txt += f"📘 *VK:* متصل ✅ (رد غير متوقع)\n"
            else: txt += f"📘 *VK:* 🔴 خطأ (كود: {vk_r.status_code})\n"
    except Exception:
         txt += f"📘 *VK:* 🔴 فشل الاتصال\n"
         
    if HAS_BOTO3:
        try:
            s3 = boto3.client('s3', endpoint_url=f"https://{bot_config['CF_R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=bot_config['CF_R2_ACCESS_KEY'], aws_secret_access_key=bot_config['CF_R2_SECRET_KEY'], region_name='auto')
            s3.head_bucket(Bucket=bot_config['CF_R2_BUCKET_NAME'])
            txt += f"☁️ *Cloudflare R2:* متصل ✅\n"
        except Exception: txt += f"☁️ *Cloudflare R2:* 🔴 خطأ في الاتصال/البكت\n"
    else: txt += f"☁️ *Cloudflare R2:* 🔴 غير مدعوم (pip install boto3)\n"

    safe_edit(bot, message.chat.id, msg.message_id, txt)

@bot.message_handler(commands=['queue', 'clearqueue', 'clean'])
def manage_queue_and_clean(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    cmd = message.text.split()[0].lower()
    if cmd == '/queue':
        q_list = list(task_queue.queue)
        if not q_list:
            bot.reply_to(message, "الطابور فارغ حالياً. ✅")
            return
        txt = f"🚦 *مهام الطابور الحالية ({len(q_list)}):*\n\n"
        for i, task in enumerate(q_list, 1):
            if task.get('type') == 'encode_all': txt += f"{i}. `{str(task.get('custom_name') or 'مهمة')[:40]}` - (إنتاج محلي)\n"
            elif task.get('type') == 'merge': txt += f"{i}. `دمج {len(task['links'])} مقاطع` - جودة {task.get('quality', 'best')}\n"
            else: txt += f"{i}. `{str(task.get('custom_name') or 'مهمة')[:40]}` - جودة {task.get('quality', 'best')}\n"
        bot.reply_to(message, txt, parse_mode="Markdown")
    elif cmd == '/clearqueue':
        count = task_queue.qsize()
        with task_queue.mutex: task_queue.queue.clear()
        bot.reply_to(message, f"🗑️ *تم تفريغ الطابور!*\nتم حذف `{count}` مهمة بنجاح.", parse_mode="Markdown")
    elif cmd == '/clean':
        count = 0
        msg = bot.reply_to(message, "🧹 *جاري التنظيف...*", parse_mode="Markdown")
        for filename in os.listdir('.'):
            if filename.startswith(("video_", "out_", "err_", "merge_", "concat_", "master_")):
                try: os.remove(filename); count += 1
                except: pass
        safe_edit(bot, message.chat.id, msg.message_id, f"✅ *تم التنظيف!*\nتم حذف `{count}` ملف مؤقت.")

def bypass_player4me(url):
    return url, "https://arabfleex.4meplayer.com/"

def bypass_1cloudfile(url):
    headers = {'User-Agent': COMMON_USER_AGENT}
    r = requests.get(url, headers=headers, timeout=20)
    match = re.search(r'l\(\s*["\']([a-fA-F0-9]{40,})["\']\s*,', r.text)
    if match:
        hex_str = match.group(1)
        direct_link = "".join(chr(int(hex_str[i:i+2], 16) ^ 0x7A) for i in range(0, len(hex_str), 2))
        if direct_link.startswith("http"): return direct_link
    raise Exception("❌ فشل سحب الرابط المباشر من 1cloudfile.")

def bypass_uqload(url, bot_instance, chat_id, message_id, task_id):
    try:
        if task_id and message_id: safe_edit(bot_instance, chat_id, message_id, "🔍 *جاري فك حماية Uqload...*", reply_markup=get_cancel_keyboard(task_id))
        headers = {'User-Agent': COMMON_USER_AGENT, 'Referer': f'https://{UQLOAD_DOMAIN}/'}
        r = requests.get(url, headers=headers, timeout=20, verify=False)
        packed = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)\)\)", r.text, re.DOTALL)
        if not packed: raise Exception("لم يتم العثور على مشغل الفيديو.")
        p, a, c, k = packed.group(1), int(packed.group(2)), int(packed.group(3)), packed.group(4).split('|')
        def replace(m):
            word = m.group(0)
            try:
                n = int(word, a)
                return k[n] if n < len(k) and k[n] else word
            except Exception: return word
        decoded = re.sub(r'\b\w+\b', replace, p)
        urls = re.findall(r'https?://[^\\"\' ]+\.m3u8[^\\"\' ]*', decoded)
        if urls: return urls[0], f'https://{UQLOAD_DOMAIN}/'
        raise Exception("لم يتم العثور على رابط الفيديو.")
    except Exception as e: raise Exception(f"❌ Uqload: {safe_error_text(e)}")

def bypass_vidoba(url, bot_instance, chat_id, message_id, task_id):
    session = requests.Session()
    session.headers.update({'User-Agent': COMMON_USER_AGENT, 'Accept': 'text/html,*/*;q=0.8', 'Referer': 'https://vidoba.org/'})
    try:
        if task_id and message_id: safe_edit(bot_instance, chat_id, message_id, "🔍 *جاري فك حماية Vidoba...*", reply_markup=get_cancel_keyboard(task_id))
        r1 = session.get(url, timeout=15, verify=False)
        data1 = {}
        for name in ['op', 'id', 'mode', 'hash']:
            match = re.search(fr'name=["\']{name}["\']\s+value=["\']([^"\']*)["\']', r1.text)
            if match: data1[name] = match.group(1)
        if 'hash' not in data1:
            match_code = re.search(r'vidoba\.[a-z]+/(?:d/)?([a-zA-Z0-9_]+)', url)
            if match_code:
                code = match_code.group(1) + ('_n' if not match_code.group(1).endswith(('_n', '_l', '_h')) else '')
                r1 = session.get(f"https://vidoba.org/d/{code}", timeout=15, verify=False)
                for name in ['op', 'id', 'mode', 'hash']:
                    match = re.search(fr'name=["\']{name}["\']\s+value=["\']([^"\']*)["\']', r1.text)
                    if match: data1[name] = match.group(1)
        time.sleep(1)
        r2 = session.post(r1.url, data=data1, timeout=20, verify=False)
        match_link = re.search(r'href=["\'](https?://[^"\']+cdnz[^"\']+)["\']', r2.text, re.IGNORECASE) or re.search(r'href=["\'](https?://[^"\']+\.(?:mp4|mkv)[^"\']*)["\'][^>]*download-btn', r2.text, re.IGNORECASE)
        if match_link: return match_link.group(1).replace('&amp;', '&')
        raise Exception("فشلت المحاولة.")
    except Exception as e: raise Exception(f"❌ Vidoba: {safe_error_text(e)}")

def get_format_string(quality):
    # استخدام صيغ صارمة لضمان سحب أفضل جودة فعلية ممكنة
    if quality == '1080': 
        return "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    if quality == '720': 
        return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    if quality == '480': 
        return "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best"
    if quality == '360': 
        return "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best"
    
    # اختيار "best" يجبر سحب أعلى دقة متاحة صوتاً وصورة 
    return "bestvideo+bestaudio/best"

def download_manager(url, filename, bot_instance, chat_id, message_id, task_id, referer=None, origin=None, custom_msg="📥 *المرحلة 1: جاري التحميل...*", quality="best", is_fallback=False):
    if task_id and message_id: safe_edit(bot_instance, chat_id, message_id, custom_msg, reply_markup=get_cancel_keyboard(task_id))
    
    # --- تعديل خاص بتخطي حماية تطبيقات الموبايل ---
    ua = COMMON_USER_AGENT
    extra_headers_dict = {}
    if "cdn.seriesmp4.com" in url or "DramaApp" in url:
        # محاكاة كاملة لطلب قادم من تطبيق أندرويد
        ua = "Dalvik/2.1.0 (Linux; U; Android 12; SM-S908B Build/SP1A.210812.016)"
        referer = None 
        origin = None
        extra_headers_dict = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Host": urlparse(url).netloc
        }
    # ------------------------------------------------

    extra_headers = []
    if referer: extra_headers += ["--add-header", f"Referer:{referer}"]
    if origin: extra_headers += ["--add-header", f"Origin:{origin}"]
    for k, v in extra_headers_dict.items(): extra_headers += ["--add-header", f"{k}:{v}"]
    
    yt_dlp_format = get_format_string(quality)
    
    try:  
        cmd = ["python", "-m", "yt_dlp", "--no-playlist", "--geo-bypass", "-N", "8", "--newline", "--no-warnings", "--no-check-certificate", "-f", yt_dlp_format, "--remux-video", "mp4", "--hls-prefer-native", "-o", filename, "--user-agent", ua]
        if os.path.exists("cookies.txt"): cmd.extend(["--cookies", "cookies.txt"])
        cmd.extend(extra_headers)
        cmd.append(url)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if task_id in active_tasks: active_tasks[task_id]['process'] = process
            
        last_update = time.time()
        error_log = []
        
        for line in iter(process.stdout.readline, ''):
            if task_id in active_tasks and active_tasks.get(task_id, {}).get("cancel"):
                process.terminate()
                raise Exception("🛑 تم إلغاء العملية.")
                
            if "ERROR:" in line or "Sign in" in line: error_log.append(line.strip())

            if task_id and message_id and time.time() - last_update > 3 and "[download]" in line and "%" in line:
                perc_m = re.search(r'([\d\.]+)\%', line)
                speed_m = re.search(r'at\s+([\d\.\w]+)', line)
                eta_m = re.search(r'ETA\s+([\d:]+)', line)
                if perc_m:
                    txt = f"{custom_msg.split('*')[1]}\n\n📊 التقدم: `[{make_bar(float(perc_m.group(1)))}]` *{float(perc_m.group(1))}%*\n🚀 السرعة: `{speed_m.group(1) if speed_m else '؟'}`\n⏳ الوقت: `{eta_m.group(1) if eta_m else '--:--'}`"
                    safe_edit(bot_instance, chat_id, message_id, txt, reply_markup=get_cancel_keyboard(task_id))
                    last_update = time.time()
        process.wait()
        
        # التأكد الصارم من نجاح yt-dlp وحجم الملف المعقول (أكبر من 100 كيلوبايت)
        if process.returncode == 0 and os.path.exists(filename) and os.path.getsize(filename) > 100000: 
            return
        elif os.path.exists(filename): 
            os.remove(filename) # مسح الملف الوهمي أو الصغير جداً
            
        if process.returncode != 0 and any(domain in url for domain in ['youtube.com', 'youtu.be', 'vk.com', 'vkvideo.ru']):
            err_msg = "\n".join(error_log[:2]) if error_log else "الموقع يرفض التحميل (يرجى توفير ملف cookies.txt لتخطي الحماية)."
            raise Exception(f"❌ خطأ من أداة التحميل:\n{err_msg}")
    except Exception as e:
        if "تم إلغاء العملية" in str(e) or "خطأ من أداة التحميل" in str(e): raise e

    try:  
        cmd = ["aria2c", "-x", "8", "-s", "8", "-k", "1M", "--summary-interval=3", "--allow-overwrite=true", "--auto-file-renaming=false", "--check-certificate=false", "-U", ua, "-o", filename]
        if referer: cmd.extend(["--header", f"Referer: {referer}"])
        if origin: cmd.extend(["--header", f"Origin: {origin}"])
        for k, v in extra_headers_dict.items(): cmd.extend(["--header", f"{k}: {v}"])
        cmd.append(url)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if task_id in active_tasks: active_tasks[task_id]['process'] = process
        last_update = time.time()
        for line in iter(process.stdout.readline, ''):
            if task_id in active_tasks and active_tasks.get(task_id, {}).get("cancel"):
                process.terminate()
                raise Exception("🛑 تم إلغاء العملية.")
            if task_id and message_id and time.time() - last_update > 3 and "%" in line and "DL:" in line:
                perc_m = re.search(r'\((\d+)%\)', line)
                speed_m = re.search(r'DL:([^\s]+)', line)
                eta_m = re.search(r'ETA:([^\s]+)', line)
                if perc_m:
                    txt = f"{custom_msg.split('*')[1]}\n\n📊 التقدم: `[{make_bar(int(perc_m.group(1)))}]` *{int(perc_m.group(1))}%*\n🚀 السرعة: `{speed_m.group(1) if speed_m else '؟'}`\n⏳ الوقت: `{eta_m.group(1) if eta_m else '--:--'}`"
                    safe_edit(bot_instance, chat_id, message_id, txt, reply_markup=get_cancel_keyboard(task_id))
                    last_update = time.time()
        process.wait()
        
        # التأكد الصارم من aria2c
        if process.returncode == 0 and os.path.exists(filename) and os.path.getsize(filename) > 100000: 
            return
        elif os.path.exists(filename): 
            os.remove(filename)
    except Exception as e:
        if "تم إلغاء العملية" in str(e): raise e

    try:  
        headers = {'User-Agent': ua, **extra_headers_dict}
        if referer: headers['Referer'] = referer
        if origin: headers['Origin'] = origin
        with requests.get(url, stream=True, headers=headers, timeout=30, verify=False) as r:
            if r.status_code in [401, 403]: raise Exception(f"الرابط محمي ومرفوض من المصدر ({r.status_code}). الموقع يمنع التحميل المباشر خارج مشغله الخاص.")
            r.raise_for_status()
            
            if 'text/html' in r.headers.get('Content-Type', '').lower():
                try:
                    html_preview = r.raw.read(512 * 1024).decode('utf-8', errors='ignore')
                    
                    if not is_fallback:
                        # محاولة استخراج رابط مباشر من الصفحة (للمشغلات غير المدعومة)
                        possible_links = re.findall(r'(https?://[^\s\'"<>\\,]+\.(?:m3u8|mp4)[^\s\'"<>\\,]*)', html_preview)
                        if possible_links:
                            extracted = possible_links[0].replace('\\/', '/')
                            if extracted != url:
                                if task_id and message_id: safe_edit(bot_instance, chat_id, message_id, "🔍 *تم العثور على رابط مباشر في الصفحة، جاري سحبه...*", reply_markup=get_cancel_keyboard(task_id))
                                r.close()
                                return download_manager(extracted, filename, bot_instance, chat_id, message_id, task_id, referer=url, origin=origin, custom_msg=custom_msg, quality=quality, is_fallback=True)

                    title_match = re.search(r'<title>(.*?)</title>', html_preview, re.IGNORECASE)
                    page_title = title_match.group(1).strip() if title_match else "بدون عنوان"
                    if "cloudflare" in html_preview.lower() or "just a moment" in page_title.lower() or "attention required" in page_title.lower():
                        raise Exception("حماية Cloudflare تمنع البوت (الموقع يطلب تحقق بشري).")
                    raise Exception(f"الرابط غير مباشر أو محمي بـ IP. (الموقع أرسل صفحة بعنوان: [{page_title}]).\n💡 *نصيحة:* يرجى إرسال الرابط الأصلي للصفحة/المشاهدة وليس رابط التحميل المباشر.")
                except Exception as ex:
                    if "حماية Cloudflare" in str(ex) or "الرابط غير مباشر" in str(ex) or "تم إلغاء العملية" in str(ex): raise ex
                    raise Exception("الرابط غير مباشر (تم إرسال صفحة ويب HTML بدلاً من ملف فيديو).")
            
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            start_dl_time = time.time()
            last_update = time.time()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(2 * 1024 * 1024):
                    if task_id in active_tasks and active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if task_id and message_id and now - last_update > 3:
                            perc = (downloaded / total_size) * 100 if total_size else 0
                            speed = downloaded / (now - start_dl_time) if (now - start_dl_time) > 0 else 0
                            rem_time = (total_size - downloaded) / speed if speed > 0 and total_size else 0
                            txt = f"{custom_msg.split('*')[1]}\n\n📊 التقدم: `[{make_bar(perc)}]` *{int(perc)}%*\n🚀 السرعة: `{format_size(speed)}/s`\n⏳ الوقت: `{format_time(rem_time)}`"
                            safe_edit(bot_instance, chat_id, message_id, txt, reply_markup=get_cancel_keyboard(task_id))
                            last_update = now
            
            # التأكد النهائي
            if os.path.exists(filename) and os.path.getsize(filename) > 100000:
                return
            else:
                raise Exception("اكتمل التحميل ولكن الملف الناتج تالف أو فارغ (أقل من 100 كيلوبايت).")
    except Exception as e: raise Exception(f"فشل التحميل: {safe_error_text(e)}")

def upload_to_r2(file_path, safe_filename, task_id, progress_dict, result_dict):
    site_name = "CloudflareR2"
    if not HAS_BOTO3:
        progress_dict[site_name] = "❌ فشل"
        result_dict[site_name] = "ERROR:مكتبة boto3 غير مثبتة"
        return

    try:
        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
        progress_dict[site_name] = "🔍 الاتصال بـ R2..."

        account_id = bot_config.get("CF_R2_ACCOUNT_ID", "")
        access_key = bot_config.get("CF_R2_ACCESS_KEY", "")
        secret_key = bot_config.get("CF_R2_SECRET_KEY", "")
        bucket_name = bot_config.get("CF_R2_BUCKET_NAME", "")
        public_url = bot_config.get("CF_R2_PUBLIC_URL", "https://pub-eb6d088b2e4848c1b93664d6cb1123d1.r2.dev").rstrip("/")

        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        s3 = boto3.client('s3', endpoint_url=endpoint_url, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name='auto')

        class ProgressPercentage(object):
            def __init__(self, filename):
                self._size = float(os.path.getsize(filename))
                self._seen_so_far = 0
                self._lock = threading.Lock()
            def __call__(self, bytes_amount):
                with self._lock:
                    self._seen_so_far += bytes_amount
                    if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                    if self._size > 0: progress_dict[site_name] = (self._seen_so_far / self._size) * 100

        progress_dict[site_name] = "📤 جاري الرفع..."
        
        s3.upload_file(
            file_path, bucket_name, safe_filename,
            ExtraArgs={'ContentType': 'video/mp4'},
            Callback=ProgressPercentage(file_path),
            Config=TransferConfig(multipart_threshold=1024*25, max_concurrency=10, multipart_chunksize=1024*25, use_threads=True)
        )

        final_url = f"{public_url}/{quote(safe_filename)}"
        result_dict[site_name] = final_url
        progress_dict[site_name] = "✅ مكتمل"
    except Exception as e:
        progress_dict[site_name] = "❌ فشل"
        result_dict[site_name] = f"ERROR:{safe_error_text(e)}"

def upload_to_vk(file_path, safe_filename, custom_name, task_id, progress_dict, result_dict):
    site_name = "VK"
    try:
        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
        progress_dict[site_name] = "🔍 جلب السيرفر..."

        api_url = "https://api.vk.com/method/video.save"
        params = {"access_token": bot_config["VK_ACCESS_TOKEN"], "v": "5.199", "name": custom_name or safe_filename, "wallpost": 0}
        res = requests.post(api_url, data=params, timeout=15).json()
        if "error" in res: raise Exception(f"خطأ في API: {res['error'].get('error_msg')}")

        upload_url = res["response"]["upload_url"]
        video_id = res["response"]["video_id"]
        owner_id = res["response"]["owner_id"]
        access_key = res["response"].get("access_key", "")

        progress_dict[site_name] = "📤 جاري الرفع..."
        for attempt in range(3):
            try:
                with open(file_path, 'rb') as fh:
                    fields = {'video_file': (safe_filename, fh, 'video/mp4')}
                    encoder = MultipartEncoder(fields=fields)
                    def _cb(monitor):
                        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                        if monitor.len > 0: progress_dict[site_name] = (monitor.bytes_read / monitor.len) * 100
                    monitor = MultipartEncoderMonitor(encoder, _cb)
                    headers = {'Content-Type': monitor.content_type}
                    up_res = requests.post(upload_url, data=monitor, headers=headers, timeout=1800).json()
                break 
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt == 2: raise e
                progress_dict[site_name] = f"⚠️ إعادة المحاولة ({attempt+1}/3)..."
                time.sleep(5)

        if "video_hash" in up_res or "size" in up_res:
            final_url = f"https://vk.com/video_ext.php?oid={owner_id}&id={video_id}&hash={access_key}" if access_key else f"https://vk.com/video{owner_id}_{video_id}"
            result_dict[site_name] = final_url
            progress_dict[site_name] = "✅ مكتمل"
        else: raise Exception("خطأ أثناء الرفع")
    except Exception as e:
        progress_dict[site_name] = "❌ فشل"
        result_dict[site_name] = f"ERROR:{safe_error_text(e)}"

def upload_to_xfs(domain, api_key, file_path, safe_filename, site_name, task_id, progress_dict, result_dict):
    try:
        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")

        if site_name == "Vidara":
            progress_dict[site_name] = "🔍 جلب السيرفر..."
            headers = {'User-Agent': COMMON_USER_AGENT, 'Accept': 'application/json'}
            srv_req = requests.get(f"https://{VIDARA_API_DOMAIN}/v1/upload/server?api_key={api_key}", headers=headers, timeout=20, verify=False)
            upload_url = srv_req.json().get('result', {}).get('upload_server')
            if not upload_url: raise Exception("فشل في جلب سيرفر الرفع")

            for attempt in range(3):
                try:
                    with open(file_path, 'rb') as file_handle:
                        fields = {'key': api_key, 'api_key': api_key, 'file': (safe_filename, file_handle, 'video/mp4')}
                        encoder = MultipartEncoder(fields=fields)
                        def upload_callback(monitor):
                            if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                            if monitor.len > 0: progress_dict[site_name] = (monitor.bytes_read / monitor.len) * 100
                        monitor = MultipartEncoderMonitor(encoder, upload_callback)
                        up_req = requests.post(upload_url, data=monitor, headers={'Content-Type': monitor.content_type}, timeout=1800, verify=False)
                    break
                except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                    if attempt == 2: raise e
                    progress_dict[site_name] = f"⚠️ إعادة المحاولة ({attempt+1}/3)..."
                    time.sleep(5)
                    
            try:
                code = up_req.json().get('filecode')
                result_dict[site_name] = code if code else "ERROR:كود مفقود"
            except: result_dict[site_name] = "ERROR:استجابة خاطئة"
            
        else:
            progress_dict[site_name] = "🔍 جلب السيرفر..."
            # تعديل مخصص لتخطي حماية كلاودفلير 403 في FreeDL
            if site_name == 'FreeDL':
                headers = {'User-Agent': 'curl/7.81.0', 'Accept': '*/*'}
            else:
                headers = {'User-Agent': COMMON_USER_AGENT, 'Accept': 'application/json'}
                
            upload_url = None
            sess_id = api_key
            error_msg = "فشل جلب السيرفر"
            
            for attempt in range(3):
                try:
                    srv_resp = requests.get(f"https://{domain}/api/upload/server?key={api_key}", headers=headers, timeout=20, verify=False)
                    try:
                        srv_data = srv_resp.json()
                    except:
                        srv_data = {}
                        error_msg = f"الرد ليس JSON (الكود {srv_resp.status_code})"
                    
                    if isinstance(srv_data, dict):
                        if str(srv_data.get('status')) not in ["200", "OK", "success", "True"] and srv_data.get('msg'):
                            error_msg = f"رد API: {srv_data.get('msg')}"
                            
                        if srv_data.get('sess_id'):
                            sess_id = srv_data.get('sess_id')
                            
                        res_data = srv_data.get('result')
                        if isinstance(res_data, str) and (res_data.startswith('http') or res_data.startswith('//')):
                            upload_url = res_data
                        elif isinstance(res_data, dict) and res_data.get('url'):
                            upload_url = res_data.get('url')
                        elif srv_data.get('server'):
                            upload_url = srv_data.get('server')
                        elif srv_data.get('url'):
                            upload_url = srv_data.get('url')
                            
                    if not upload_url and srv_resp.text.startswith('http'):
                        upload_url = srv_resp.text.strip()
                        
                    if upload_url: break
                    time.sleep(5)
                except Exception as e: 
                    error_msg = str(e)
                    time.sleep(5)

            if not upload_url: raise Exception(error_msg)
            if upload_url.startswith('//'): upload_url = 'https:' + upload_url
            
            # المواقع العادية تحتاج key في الرابط، FreeDL قد لا يحتاج لكن سنتركه لضمان العمل
            upload_url += f"{'&' if '?' in upload_url else '?'}json=1&api_key={api_key}"

            for attempt in range(3):
                try:
                    with open(file_path, 'rb') as file_handle:
                        # ضبط الحقول لتتطابق 100% مع الوثائق
                        if site_name == 'FreeDL': 
                            fields = {
                                'sess_id': sess_id,
                                'utype': 'prem',
                                'file_0': (safe_filename, file_handle, 'video/mp4')
                            }
                        else:
                            fields = {
                                'key': api_key, 
                                'api_key': api_key, 
                                'sess_id': sess_id, 
                                'upload_type': 'file', 
                                'file': (safe_filename, file_handle, 'video/mp4')
                            }
                            
                        encoder = MultipartEncoder(fields=fields)
                        def upload_callback(monitor):
                            if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                            if monitor.len > 0: progress_dict[site_name] = (monitor.bytes_read / monitor.len) * 100
                        monitor = MultipartEncoderMonitor(encoder, upload_callback)
                        up_req = requests.post(upload_url, data=monitor, headers={'Content-Type': monitor.content_type}, timeout=1800, verify=False)
                    break 
                except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                    if attempt == 2: raise e 
                    progress_dict[site_name] = f"⚠️ إعادة المحاولة ({attempt+1}/3)..."
                    time.sleep(5)

            try:
                data = up_req.json()
                video_code = None
                
                # استخراج الكود الخاص باستجابة FreeDL
                if isinstance(data, list) and len(data) > 0 and data[0].get('file_code'):
                    video_code = data[0].get('file_code')
                elif 'files' in data and isinstance(data['files'], list) and len(data['files']) > 0: 
                    video_code = data['files'][0].get('filecode')
                elif 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0: 
                    video_code = data['result'][0].get('filecode')
                
                if not video_code:
                    match = re.search(r'"(?:file_code|filecode)"\s*:\s*"([a-zA-Z0-9]+)"', json.dumps(data), re.IGNORECASE)
                    if match: video_code = match.group(1)
                    
                result_dict[site_name] = video_code if video_code else "ERROR:الكود مفقود"
            except:
                match = re.search(r"name=['\"]fn['\"][^>]*>([a-zA-Z0-9]+)<", up_req.text, re.IGNORECASE)
                result_dict[site_name] = match.group(1).strip() if match else f"ERROR:رد غير متوقع ({up_req.status_code})"

        progress_dict[site_name] = "✅ مكتمل" if result_dict.get(site_name) and not str(result_dict.get(site_name)).startswith("ERROR:") else "❌ فشل"
    except Exception as e:
        progress_dict[site_name] = "❌ فشل"
        result_dict[site_name] = f"ERROR:{safe_error_text(e)}"

def upload_to_gofile(file_path, safe_filename, task_id, progress_dict, result_dict):
    site_name = "GoFile"
    try:
        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
        progress_dict[site_name] = "🔍 جلب السيرفر..."
        r = requests.get('https://api.gofile.io/servers', timeout=15)
        server = r.json()['data']['servers'][0]['name']

        progress_dict[site_name] = "📤 جاري الرفع..."
        for attempt in range(3):
            try:
                with open(file_path, 'rb') as fh:
                    fields = {'file': (safe_filename, fh, 'video/mp4')}
                    encoder = MultipartEncoder(fields=fields)
                    def _cb(monitor):
                        if active_tasks.get(task_id, {}).get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
                        if monitor.len > 0: progress_dict[site_name] = (monitor.bytes_read / monitor.len) * 100
                    monitor = MultipartEncoderMonitor(encoder, _cb)
                    headers = {'Content-Type': monitor.content_type, 'Authorization': f'Bearer {bot_config["GOFILE_TOKEN"]}'}
                    up = requests.post(f'https://{server}.gofile.io/contents/uploadfile', data=monitor, headers=headers, timeout=1800)
                break
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt == 2: raise e
                progress_dict[site_name] = f"⚠️ إعادة المحاولة ({attempt+1}/3)..."
                time.sleep(5)

        progress_dict[site_name] = "🔎 استخراج الرابط..."
        data = up.json()
        if data.get('status') == 'ok':
            result_dict[site_name] = data['data']['downloadPage']
            progress_dict[site_name] = "✅ مكتمل"
        else: raise Exception("خطأ في رفع GoFile")
    except Exception as e:
        progress_dict[site_name] = "❌ فشل"
        result_dict[site_name] = f"ERROR:{safe_error_text(e)}"

@bot.message_handler(func=lambda message: message.text and re.search(r'(https?://[^\s]+)', message.text))
def receive_url(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    if message.message_id in processed_messages: return
    processed_messages.add(message.message_id)

    extracted_urls = re.findall(r'(https?://[^\s]+)', message.text)
    if not extracted_urls: return

    if message.chat.id in batch_sessions:
        batch_sessions[message.chat.id].extend(extracted_urls)
        count = len(batch_sessions[message.chat.id])
        bot.reply_to(message, f"✅ تم استلام *{len(extracted_urls)}* رابط — الإجمالي: *{count}*\nأرسل المزيد أو `/done` للانتهاء.", parse_mode="Markdown")
        return

    if message.chat.id in merge_sessions:
        merge_sessions[message.chat.id].extend(extracted_urls)
        count = len(merge_sessions[message.chat.id])
        bot.reply_to(message, f"✅ تم استلام الرابط رقم `{count}`.\n\nأرسل الرابط التالي، أو أرسل `/done` إذا انتهيت من كل الأجزاء.", parse_mode="Markdown")
        return

    actual_url = extracted_urls[0]
    msg = bot.reply_to(message, f"⚙️ *تم التقاط الرابط!*\n`{actual_url}`\n\n📝 الرجاء إرسال **اسم الملف** الآن (أو أرسل `/skip` لتخطي التسمية وترك الاسم الافتراضي):", parse_mode="Markdown", disable_web_page_preview=True)
    bot.register_next_step_handler(msg, process_name_step, actual_url)

@bot.message_handler(commands=['merge'])
def start_merge_session(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    merge_sessions[message.chat.id] = []
    batch_sessions.pop(message.chat.id, None)
    bot.reply_to(message, "🧩 *وضع الدمج مفعل!*\n\nقم بإرسال الرابط **الأول** الآن.", parse_mode="Markdown")

@bot.message_handler(commands=['batch'])
def start_batch_session(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    merge_sessions.pop(message.chat.id, None)
    batch_sessions[message.chat.id] = []
    bot.reply_to(message, "📦 *وضع الباتش مفعل!*\n\nأرسل روابط الحلقات واحداً تلو الآخر.\nعند الانتهاء أرسل `/done`.", parse_mode="Markdown")

@bot.message_handler(commands=['done'])
def finish_session(message):
    if message.chat.id != ADMIN_CHAT_ID: return
    if message.chat.id in batch_sessions:
        links = batch_sessions.pop(message.chat.id)
        if not links:
            bot.reply_to(message, "⚠️ لم تُرسل أي روابط. استخدم `/batch` للبدء.", parse_mode="Markdown")
            return
        msg = bot.reply_to(message, f"✅ تم استلام *{len(links)}* رابط.\n\n📝 أرسل الاسم الأساسي للمسلسل/السلسلة\nأو أرسل `/skip` لترقيم تلقائي فقط.", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_batch_name_step, links)
        return
    if message.chat.id in merge_sessions:
        links = merge_sessions.pop(message.chat.id)
        if not links:
            bot.reply_to(message, "⚠️ لا توجد روابط مضافة للدمج. استخدم `/merge` للبدء.", parse_mode="Markdown")
            return
        msg = bot.reply_to(message, f"✅ تم استلام `{len(links)}` روابط للدمج.\n\n📝 الرجاء إرسال **الاسم الشامل** للملف المدمج (أو أرسل `/skip` للافتراضي):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_merge_name_step, links)

def process_batch_name_step(message, links):
    base_name = re.sub(r'[^\w\s\u0600-\u06FF\-]', '', message.text.strip())[:40] if message.text and message.text.strip() != '/skip' else None
    default_servers = ["Abstream", "Larhu", "Uqload", "Vidmoly", "Vidara", "GoFile", "VK", "Doodstream", "CloudflareR2", "FreeDL"]
    msg_id = bot.send_message(message.chat.id, "⏳ جاري تجهيز القائمة...").message_id
    upload_selections[msg_id] = {'type': 'batch', 'links': links, 'name': base_name, 'servers': default_servers}
    show_quality_keyboard(message.chat.id, msg_id)

def process_merge_name_step(message, links):
    custom_name = message.text.strip() if message.text and message.text.strip() != '/skip' else None
    default_servers = ["Abstream", "Larhu", "Uqload", "Vidmoly", "Vidara", "GoFile", "VK", "Doodstream", "CloudflareR2", "FreeDL"]
    msg_id = bot.send_message(message.chat.id, "⏳ جاري تجهيز القائمة للدمج...").message_id
    upload_selections[msg_id] = {'type': 'merge', 'links': links, 'name': custom_name, 'servers': default_servers}
    show_quality_keyboard(message.chat.id, msg_id)

def process_name_step(message, url):
    if message.chat.id != ADMIN_CHAT_ID: return
    custom_name = message.text.strip() if message.text and message.text.strip() != '/skip' else None
    default_servers = ["Abstream", "Larhu", "Uqload", "Vidmoly", "Vidara", "GoFile", "VK", "Doodstream", "CloudflareR2", "FreeDL"]
    msg_id = bot.send_message(message.chat.id, "⏳ جاري تجهيز القائمة...").message_id
    upload_selections[msg_id] = {'type': 'single', 'url': url, 'name': custom_name, 'servers': default_servers}
    show_quality_keyboard(message.chat.id, msg_id)

def show_quality_keyboard(chat_id, msg_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🌟 أعلى جودة", callback_data=f"qual_best_{msg_id}"),
        InlineKeyboardButton("📺 1080p", callback_data=f"qual_1080_{msg_id}"),
        InlineKeyboardButton("📺 720p", callback_data=f"qual_720_{msg_id}"),
        InlineKeyboardButton("📱 480p", callback_data=f"qual_480_{msg_id}"),
        InlineKeyboardButton("📱 360p", callback_data=f"qual_360_{msg_id}")
    )
    markup.add(InlineKeyboardButton("🎬 تحميل كل الجودات (من المصدر)", callback_data=f"qual_all_{msg_id}"))
    markup.add(InlineKeyboardButton("🎬 إنتاج الجودات محلياً (720,480,360)", callback_data=f"qual_encode_{msg_id}"))
    markup.add(InlineKeyboardButton("🛑 إلغاء", callback_data=f"sel_cancel_{msg_id}"))
    
    data = upload_selections[msg_id]
    bot.edit_message_text(f"✅ الاسم: `{data['name'] or 'الافتراضي'}`\n\n🎯 الرجاء اختيار جودة التحميل:", chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('qual_'))
def handle_quality_selection(call):
    parts = call.data.split('_')
    quality = parts[1]
    msg_id = int(parts[2])
    if msg_id not in upload_selections:
        bot.answer_callback_query(call.id, "⚠️ الجلسة انتهت.")
        return
    upload_selections[msg_id]['quality'] = quality
    
    data = upload_selections[msg_id]
    if quality == "encode": q_label = "إنتاج محلي للجودات"
    elif quality == "all": q_label = "كل الجودات (من المصدر)"
    else: q_label = "أعلى جودة" if quality == "best" else f"{quality}p"
        
    bot.edit_message_text(f"✅ الاسم: `{data['name'] or 'الافتراضي'}`\n⚙️ الجودة: `{q_label}`\n\n🎯 اختر السيرفرات:", chat_id=call.message.chat.id, message_id=msg_id, reply_markup=get_selection_keyboard(msg_id), parse_mode="Markdown")

def get_selection_keyboard(msg_id):
    markup = InlineKeyboardMarkup(row_width=2)
    if msg_id not in upload_selections: return markup
    selected = upload_selections[msg_id]['servers']
    servers_list = [("🟢 ABStream", "Abstream"), ("🟠 Larhu", "Larhu"), ("🔵 Uqload", "Uqload"), ("🟣 Vidmoly", "Vidmoly"), ("🟡 Vidara", "Vidara"), ("🌐 GoFile", "GoFile"), ("📘 VK", "VK"), ("🟤 Playmogo", "Doodstream"), ("☁️ Cloudflare R2", "CloudflareR2"), ("🔴 FreeDL", "FreeDL")]
    
    buttons = [InlineKeyboardButton(f"✅ {label}" if srv in selected else f"⬜ {label}", callback_data=f"sel_toggle_{srv}_{msg_id}") for label, srv in servers_list]
    markup.add(*buttons)
    
    markup.add(InlineKeyboardButton("✅ تحديد الكل", callback_data=f"sel_all_{msg_id}"), InlineKeyboardButton("❌ مسح التحديد", callback_data=f"sel_none_{msg_id}"))
    markup.add(InlineKeyboardButton("🚀 بـدء الـرفـع الآن", callback_data=f"sel_start_{msg_id}"))
    markup.add(InlineKeyboardButton("🛑 إلغاء", callback_data=f"sel_cancel_{msg_id}"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('sel_'))
def handle_custom_selection(call):
    parts = call.data.split('_')
    action = parts[1]
    if action == "cancel":
        msg_id = int(parts[2])
        upload_selections.pop(msg_id, None)
        safe_edit(bot, call.message.chat.id, msg_id, "🛑 *تم الإلغاء.*")
        return
    msg_id = int(parts[-1])
    if msg_id not in upload_selections:
        bot.answer_callback_query(call.id, "⚠️ الجلسة انتهت.")
        return
    if action == "toggle":
        srv = parts[2]
        if srv in upload_selections[msg_id]['servers']: upload_selections[msg_id]['servers'].remove(srv)
        else: upload_selections[msg_id]['servers'].append(srv)
        bot.edit_message_reply_markup(call.message.chat.id, msg_id, reply_markup=get_selection_keyboard(msg_id))
    elif action == "all":
        upload_selections[msg_id]['servers'] = ["Abstream", "Larhu", "Uqload", "Vidmoly", "Vidara", "GoFile", "VK", "Doodstream", "CloudflareR2", "FreeDL"]
        bot.edit_message_reply_markup(call.message.chat.id, msg_id, reply_markup=get_selection_keyboard(msg_id))
    elif action == "none":
        upload_selections[msg_id]['servers'] = []
        bot.edit_message_reply_markup(call.message.chat.id, msg_id, reply_markup=get_selection_keyboard(msg_id))
    elif action == "start":
        data = upload_selections.pop(msg_id)
        if not data['servers']:
            bot.answer_callback_query(call.id, "⚠️ اختر سيرفر واحد على الأقل!", show_alert=True)
            return
        
        quality_pref = data.get('quality', 'best')
        total_tasks_added = 0

        if quality_pref == 'encode':
            if data.get('type') == 'single':
                task_queue.put({'type': 'encode_all', 'url': data['url'], 'chat_id': call.message.chat.id, 'msg_id': msg_id, 'servers': data['servers'], 'custom_name': data['name']})
                total_tasks_added = 1
            elif data.get('type') == 'batch':
                pad = len(str(len(data['links'])))
                for i, url in enumerate(data['links'], 1):
                    ep_name = f"{data['name']} {str(i).zfill(pad)}" if data['name'] else f"EP{str(i).zfill(pad)}"
                    task_queue.put({'type': 'encode_all', 'url': url, 'chat_id': call.message.chat.id, 'msg_id': None, 'servers': data['servers'], 'custom_name': ep_name})
                    total_tasks_added += 1
            else:
                bot.answer_callback_query(call.id, "⚠️ الإنتاج غير مدعوم للدمج حالياً.", show_alert=True)
                return
        else:
            qualities_to_process = ['1080', '720', '480', '360'] if quality_pref == 'all' else [quality_pref]
            for idx, q in enumerate(qualities_to_process):
                target_msg_id = msg_id if idx == 0 and data.get('type') != 'batch' else None
                q_suffix = f" - {q}p" if q not in ['best', 'all'] else ""
                
                if data.get('type') == 'merge':
                    ep_name = f"{data['name']}{q_suffix}" if data['name'] else f"Merged{q_suffix}"
                    task_queue.put({'type': 'merge', 'links': data['links'], 'chat_id': call.message.chat.id, 'msg_id': target_msg_id, 'servers': data['servers'], 'custom_name': ep_name, 'quality': q})
                    total_tasks_added += 1
                elif data.get('type') == 'batch':
                    pad = len(str(len(data['links'])))
                    for i, url in enumerate(data['links'], 1):
                        ep_num = str(i).zfill(pad)
                        ep_name = f"{data['name']} {ep_num}{q_suffix}" if data['name'] else f"EP{ep_num}{q_suffix}"
                        task_queue.put({'type': 'full', 'url': url, 'chat_id': call.message.chat.id, 'msg_id': None, 'servers': data['servers'], 'custom_name': ep_name, 'quality': q})
                        total_tasks_added += 1
                else:
                    ep_name = f"{data['name']}{q_suffix}" if data['name'] else f"Video{q_suffix}"
                    task_queue.put({'type': 'full', 'url': data['url'], 'chat_id': call.message.chat.id, 'msg_id': target_msg_id, 'servers': data['servers'], 'custom_name': ep_name, 'quality': q})
                    total_tasks_added += 1
        
        if data.get('type') == 'batch' or quality_pref == 'all':
            bot.edit_message_text(f"✅ *تم إضافة {total_tasks_added} مهمة للطابور!*", chat_id=call.message.chat.id, message_id=msg_id, parse_mode="Markdown")
        
        pos = task_queue.qsize()
        bot.answer_callback_query(call.id, f"✅ تمت الإضافة (ترتيبك: {pos})")
        if pos == 1 and (data.get('type') != 'batch' or quality_pref == 'encode'):
            safe_edit(bot, call.message.chat.id, msg_id, "⏳ *جاري البدء...*")

@bot.callback_query_handler(func=lambda call: call.data.startswith('retryup_'))
def handle_retry_upload(call):
    task_id = call.data.replace('retryup_', '')
    if task_id not in failed_uploads or not os.path.exists(failed_uploads[task_id]['file']):
        bot.answer_callback_query(call.id, "⚠️ الملف غير موجود. يبدو أنه تم مسحه تلقائياً.", show_alert=True)
        return
    task_queue.put({'type': 'upload_only', 'chat_id': call.message.chat.id, 'msg_id': call.message.message_id, 'task_id': task_id})
    bot.answer_callback_query(call.id, f"✅ تمت الإضافة لطابور الرفع (ترتيبك: {task_queue.qsize()})")
    safe_edit(bot, call.message.chat.id, call.message.message_id, f"⏳ *تمت إضافة إعادة الرفع للطابور...*")

def encode_process_logic(url, chat_id, message_id, target_servers, custom_name):
    if not message_id: message_id = bot.send_message(chat_id, f"⏳ بدء عملية إنتاج الجودات لـ: `{custom_name}`...", parse_mode="Markdown").message_id
    task_id = f"{chat_id}_{message_id}_{int(time.time())}"
    active_tasks[task_id] = {"cancel": False, "process": None}
    
    master_file = f"master_{task_id}.mp4"
    generated_files = []
    
    try:
        ref, org = None, None
        if "4meplayer" in url or "player4me" in url: url, ref = bypass_player4me(url)
        elif "vidoba" in url: url, ref = bypass_vidoba(url, bot, chat_id, message_id, task_id)
        elif "1cloudfile" in url: url = bypass_1cloudfile(url)
        elif "up4ever" in url or "/d/" in url: ref = "https://www.up-4ever.net/"
        elif "seriesmp4.com" in url: ref, org = "https://seriesmp4.com/", "https://seriesmp4.com"
        elif "uqload" in url and (".mp4" in url or "/v/" in url or ".m3u8" in url): ref, org = f"https://{UQLOAD_DOMAIN}/", f"https://{UQLOAD_DOMAIN}"
        elif "uqload" in url: url, ref = bypass_uqload(url, bot, chat_id, message_id, task_id)

        download_manager(url, master_file, bot, chat_id, message_id, task_id, referer=ref, origin=org, custom_msg=f"📥 *تحميل النسخة الأصلية للإنتاج...*", quality="best")
        if not os.path.exists(master_file) or os.path.getsize(master_file) < 500000: raise Exception("❌ فشل تحميل الملف الأصلي.")

        original_height = get_video_height(master_file)
        
        target_resolutions = []
        if original_height >= 900: 
            target_resolutions = [720, 480, 360]
            display_original_res = "1080"
        elif original_height >= 600: 
            target_resolutions = [480, 360]
            display_original_res = "720"
        elif original_height >= 400: 
            target_resolutions = [360]
            display_original_res = "480"
        else: 
            target_resolutions = []
            display_original_res = str(original_height)
        
        encode_tasks = [{"res": "best", "file": master_file, "name_suffix": f" - {display_original_res}p"}]
        for res in target_resolutions:
            encode_tasks.append({"res": str(res), "file": f"out_{res}p_{task_id}.mp4", "name_suffix": f" - {res}p"})
            generated_files.append(f"out_{res}p_{task_id}.mp4")

        for i, item in enumerate(encode_tasks):
            res_label = item['res']
            current_file = item['file']
            file_title = f"{custom_name}{item['name_suffix']}" if custom_name else f"Video{item['name_suffix']}"
            safe_name = f"{re.sub(r'[^\w\s\u0600-\u06FF-]', '', file_title).strip()[:40] or 'Video'}.mp4"

            if res_label != "best":
                transcode_video(master_file, int(res_label), current_file, bot, chat_id, message_id, task_id, custom_msg=f"🛠️ *المرحلة {i+1}: إنتاج ورفع جودة {res_label}p*")
                
            if not os.path.exists(current_file): continue
                
            prog_dict, res_dict, threads = {s: "⏳..." for s in target_servers}, {s: None for s in target_servers}, []
            args_map = {"Abstream": (ABSTREAM_DOMAIN, bot_config["ABSTREAM_API_KEY"]), "Larhu": (LARHU_DOMAIN, bot_config["LARHU_API_KEY"]), "Uqload": (UQLOAD_DOMAIN, bot_config["UQLOAD_API_KEY"]), "Vidmoly": (VIDMOLY_DOMAIN, bot_config["VIDMOLY_API_KEY"]), "Vidara": (VIDARA_API_DOMAIN, bot_config["VIDARA_API_KEY"]), "Doodstream": (DOODSTREAM_DOMAIN, bot_config["DOODSTREAM_API_KEY"]), "FreeDL": (FREEDL_DOMAIN, bot_config["FREEDL_API_KEY"])}

            for site in target_servers:
                if site == "GoFile": t = threading.Thread(target=upload_to_gofile, args=(current_file, safe_name, task_id, prog_dict, res_dict))
                elif site == "VK": t = threading.Thread(target=upload_to_vk, args=(current_file, safe_name, file_title, task_id, prog_dict, res_dict))
                elif site == "CloudflareR2": t = threading.Thread(target=upload_to_r2, args=(current_file, safe_name, task_id, prog_dict, res_dict))
                else: t = threading.Thread(target=upload_to_xfs, args=(args_map[site][0], args_map[site][1], current_file, safe_name, site, task_id, prog_dict, res_dict))
                threads.append(t); t.start()

            last_upd = time.time()
            while any(t.is_alive() for t in threads):
                if active_tasks[task_id].get("cancel"): break
                if time.time() - last_upd > 3:
                    display_res = display_original_res if res_label == "best" else res_label
                    txt = f"🚀 *جاري رفع جودة ({display_res}p)...\n\n" + "\n".join([f"{get_emoji_for_server(s)} *{s}:* `[{make_bar(prog_dict[s])}]` *{int(prog_dict[s])}%*" if isinstance(prog_dict[s], float) else f"*{s}:* `{prog_dict[s]}`" for s in target_servers])
                    safe_edit(bot, chat_id, message_id, txt.strip(), reply_markup=get_cancel_keyboard(task_id))
                    last_upd = time.time()

            for t in threads: t.join()
            if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")

            display_res = display_original_res if res_label == "best" else res_label
            res_txt = f"📺 *جودة: {display_res}p*\n🎬 `{file_title}`\n━━━━━━━━━━━━━\n"
            
            valid_links = False
            for site in target_servers:
                code = res_dict.get(site)
                if code and not str(code).startswith("ERROR:"):
                    valid_links = True
                    if site == 'Abstream': res_txt += f"🟢 *ABStream:*\n└ 🔗 `https://abstream.to/embed-{code}.html`\n\n"
                    elif site == 'Larhu': res_txt += f"🟠 *Larhu:*\n└ 🔗 `https://larhu.website/embed-{code}.html`\n\n"
                    elif site == 'Vidmoly': res_txt += f"🟣 *Vidmoly:*\n└ 🔗 `https://vidmoly.biz/embed-{code}.html`\n\n"
                    elif site == 'Uqload': res_txt += f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/embed-{code}.html`\n\n"
                    elif site == 'Vidara': res_txt += f"🟡 *Vidara:*\n└ 🔗 `{code if str(code).startswith('http') else f'https://vidaraa.cc/e/{code}'}`\n\n"
                    elif site == 'Doodstream': res_txt += f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/e/{code}`\n\n"
                    elif site == 'GoFile': res_txt += f"🌐 *GoFile:*\n└ 🔗 `{code}`\n\n"
                    elif site == 'VK': res_txt += f"📘 *VK:*\n└ 🔗 `{code}`\n\n"
                    elif site == 'CloudflareR2': res_txt += f"☁️ *Cloudflare R2:*\n└ 🔗 `{code}`\n\n"
                    elif site == 'FreeDL': res_txt += f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`\n\n"
            
            if valid_links:
                bot.send_message(chat_id, res_txt.strip(), parse_mode="Markdown", disable_web_page_preview=True)

            if res_label != "best" and os.path.exists(current_file):
                try: os.remove(current_file)
                except: pass

        safe_edit(bot, chat_id, message_id, "✅ *اكتمل إنتاج ورفع كافة الجودات بنجاح!*")

    except Exception as e:
        safe_edit(bot, chat_id, message_id, f"❌ *توقفت مهمة الإنتاج:*\n`{safe_error_text(e)}`")
    finally:
        active_tasks.pop(task_id, None)
        if os.path.exists(master_file):
            try: os.remove(master_file)
            except: pass
        for f in generated_files:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

def upload_only_logic(chat_id, message_id, task_id):
    if task_id not in failed_uploads: return
    data = failed_uploads[task_id]
    out_file, target_servers, custom_name = data['file'], data['servers'], data['name']
    active_tasks[task_id] = {"cancel": False, "process": None}
    safe_name = f"{re.sub(r'[^\w\s\u0600-\u06FF-]', '', custom_name).strip()[:40] or 'Video'}.mp4" if custom_name else f"Vid_{random.randint(10000, 99999)}.mp4"

    try:
        prog_dict, res_dict, threads = {s: "⏳ في الانتظار..." for s in target_servers}, {s: None for s in target_servers}, []
        args_map = {"Abstream": (ABSTREAM_DOMAIN, bot_config["ABSTREAM_API_KEY"]), "Larhu": (LARHU_DOMAIN, bot_config["LARHU_API_KEY"]), "Uqload": (UQLOAD_DOMAIN, bot_config["UQLOAD_API_KEY"]), "Vidmoly": (VIDMOLY_DOMAIN, bot_config["VIDMOLY_API_KEY"]), "Vidara": (VIDARA_API_DOMAIN, bot_config["VIDARA_API_KEY"]), "Doodstream": (DOODSTREAM_DOMAIN, bot_config["DOODSTREAM_API_KEY"]), "FreeDL": (FREEDL_DOMAIN, bot_config["FREEDL_API_KEY"])}

        for site in target_servers:
            if site == "GoFile": t = threading.Thread(target=upload_to_gofile, args=(out_file, safe_name, task_id, prog_dict, res_dict))
            elif site == "VK": t = threading.Thread(target=upload_to_vk, args=(out_file, safe_name, custom_name, task_id, prog_dict, res_dict))
            elif site == "CloudflareR2": t = threading.Thread(target=upload_to_r2, args=(out_file, safe_name, task_id, prog_dict, res_dict))
            else: t = threading.Thread(target=upload_to_xfs, args=(args_map[site][0], args_map[site][1], out_file, safe_name, site, task_id, prog_dict, res_dict))
            threads.append(t); t.start(); time.sleep(3)

        last_upd = time.time()
        while any(t.is_alive() for t in threads):
            if active_tasks[task_id].get("cancel"): break
            if time.time() - last_upd > 3:
                txt = "🚀 *المرحلة 2: إعادة الرفع...*\n\n" + "\n".join([f"{get_emoji_for_server(s)} *{s}:* `[{make_bar(prog_dict[s])}]` *{int(prog_dict[s])}%*" if isinstance(prog_dict[s], float) else f"*{s}:* `{prog_dict[s]}`" for s in target_servers])
                safe_edit(bot, chat_id, message_id, txt.strip(), reply_markup=get_cancel_keyboard(task_id))
                last_upd = time.time()
            time.sleep(1)

        for t in threads: t.join()
        if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")

        watch_links, download_links, failed_sites = [], [], []
        for site in target_servers:
            code = res_dict.get(site)
            if code and not str(code).startswith("ERROR:"):
                if site == 'Abstream': watch_links.append(f"🟢 *ABStream:*\n└ 🔗 `https://abstream.to/embed-{code}.html`")
                elif site == 'Larhu': watch_links.append(f"🟠 *Larhu:*\n└ 🔗 `https://larhu.website/embed-{code}.html`")
                elif site == 'Vidmoly': watch_links.append(f"🟣 *Vidmoly:*\n└ 🔗 `https://vidmoly.biz/embed-{code}.html`")
                elif site == 'Uqload':
                    watch_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/embed-{code}.html`")
                    download_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/{code}`")
                elif site == 'Vidara': watch_links.append(f"🟡 *Vidara:*\n└ 🔗 `{code if str(code).startswith('http') else f'https://vidaraa.cc/e/{code}'}`")
                elif site == 'Doodstream': 
                    watch_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/e/{code}`")
                    download_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/d/{code}`")
                elif site == 'GoFile': download_links.append(f"🌐 *GoFile:*\n└ 🔗 `{code}`")
                elif site == 'VK': watch_links.append(f"📘 *VK:*\n└ 🔗 `{code}`")
                elif site == 'CloudflareR2': download_links.append(f"☁️ *Cloudflare R2:*\n└ 🔗 `{code}`")
                elif site == 'FreeDL': 
                    watch_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
                    download_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
            else: failed_sites.append(f"❌ *{site}:* `{str(code).replace('ERROR:', '') if code else 'فشل غير معروف'}`")

        if not watch_links and not download_links: raise Exception("لم يتم العثور على أي روابط بعد الرفع.")

        res_txt = f"🎉 *اكتملت المهمة بنجاح!*\n🎬 `{custom_name or 'فيديو جديد'}`\n💡 _(اضغط على أي رابط لنسخه مباشرة)_\n\n"
        if watch_links: res_txt += "📺 *روابط المشاهدة:*\n━━━━━━━━━━━━━\n" + "\n\n".join(watch_links) + "\n\n"
        if download_links: res_txt += "📥 *روابط التحميل المباشر:*\n━━━━━━━━━━━━━\n" + "\n\n".join(download_links) + "\n\n"
        if failed_sites: res_txt += "⚠️ *سيرفرات فشل الرفع عليها:*\n━━━━━━━━━━━━━\n" + "\n".join(failed_sites)

        safe_edit(bot, chat_id, message_id, "✅ *تم الانتهاء من إعادة الرفع! الروابط في الأسفل 👇*")
        bot.send_message(chat_id, res_txt, parse_mode="Markdown", reply_to_message_id=message_id, disable_web_page_preview=True)
        failed_uploads.pop(task_id, None)
        if os.path.exists(out_file): os.remove(out_file)
    except Exception as e:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("♻️ إعادة الرفع", callback_data=f"retryup_{task_id}"))
        safe_edit(bot, chat_id, message_id, f"❌ *توقفت إعادة الرفع:*\n`{safe_error_text(e)}`\n\n*تفاصيل الأخطاء:*\n" + "\n".join([f"{s}: {res_dict.get(s)}" for s in target_servers if str(res_dict.get(s)).startswith("ERROR:")]), reply_markup=markup)
    finally: active_tasks.pop(task_id, None)

def process_logic(url, chat_id, message_id, target_servers, custom_name, quality="best"):
    if not message_id: message_id = bot.send_message(chat_id, f"⏳ جاري بدء مهمة: `{custom_name}`...", parse_mode="Markdown").message_id
    task_id = f"{chat_id}_{message_id}_{int(time.time())}"
    active_tasks[task_id] = {"cancel": False, "process": None}
    out_file, success = f"out_{task_id}.mp4", False

    try:
        ref, org = None, None
        if "4meplayer" in url or "player4me" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري التخطي: Player4Me...*"); url, ref = bypass_player4me(url)
        elif "vidoba" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري التخطي: Vidoba...*"); url, ref = bypass_vidoba(url, bot, chat_id, message_id, task_id)
        elif "1cloudfile" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري التخطي: 1cloudfile...*"); url = bypass_1cloudfile(url)
        elif "up4ever" in url or "/d/" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري جلب الملف: Up4Ever...*"); ref = "https://www.up-4ever.net/"
        elif "seriesmp4.com" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري جلب الملف: SeriesMP4...*"); ref, org = "https://seriesmp4.com/", "https://seriesmp4.com"
        elif "uqload" in url and (".mp4" in url or "/v/" in url or ".m3u8" in url): ref, org = f"https://{UQLOAD_DOMAIN}/", f"https://{UQLOAD_DOMAIN}"
        elif "uqload" in url:
            safe_edit(bot, chat_id, message_id, "🔍 *جاري التخطي: Uqload...*"); url, ref = bypass_uqload(url, bot, chat_id, message_id, task_id)

        safe_name = f"{re.sub(r'[^\w\s\u0600-\u06FF-]', '', custom_name).strip()[:40] or 'Video'}.mp4" if custom_name else f"Vid_{random.randint(10000, 99999)}.mp4"
        download_manager(url, out_file, bot, chat_id, message_id, task_id, referer=ref, origin=org, custom_msg=f"📥 *المرحلة 1: جاري تحميل [{custom_name or 'فيديو'}]...*", quality=quality)
        
        if not os.path.exists(out_file) or os.path.getsize(out_file) < 500000: raise Exception("❌ الملف تالف أو فارغ.")

        prog_dict, res_dict, threads = {s: "⏳ في الانتظار..." for s in target_servers}, {s: None for s in target_servers}, []
        args_map = {"Abstream": (ABSTREAM_DOMAIN, bot_config["ABSTREAM_API_KEY"]), "Larhu": (LARHU_DOMAIN, bot_config["LARHU_API_KEY"]), "Uqload": (UQLOAD_DOMAIN, bot_config["UQLOAD_API_KEY"]), "Vidmoly": (VIDMOLY_DOMAIN, bot_config["VIDMOLY_API_KEY"]), "Vidara": (VIDARA_API_DOMAIN, bot_config["VIDARA_API_KEY"]), "Doodstream": (DOODSTREAM_DOMAIN, bot_config["DOODSTREAM_API_KEY"]), "FreeDL": (FREEDL_DOMAIN, bot_config["FREEDL_API_KEY"])}

        for site in target_servers:
            if site == "GoFile": t = threading.Thread(target=upload_to_gofile, args=(out_file, safe_name, task_id, prog_dict, res_dict))
            elif site == "VK": t = threading.Thread(target=upload_to_vk, args=(out_file, safe_name, custom_name, task_id, prog_dict, res_dict))
            elif site == "CloudflareR2": t = threading.Thread(target=upload_to_r2, args=(out_file, safe_name, task_id, prog_dict, res_dict))
            else: t = threading.Thread(target=upload_to_xfs, args=(args_map[site][0], args_map[site][1], out_file, safe_name, site, task_id, prog_dict, res_dict))
            threads.append(t); t.start(); time.sleep(3)

        last_upd = time.time()
        while any(t.is_alive() for t in threads):
            if active_tasks[task_id].get("cancel"): break
            if time.time() - last_upd > 3:
                txt = f"🚀 *المرحلة 2: الرفع [{custom_name or ''}]...*\n\n" + "\n".join([f"{get_emoji_for_server(s)} *{s}:* `[{make_bar(prog_dict[s])}]` *{int(prog_dict[s])}%*" if isinstance(prog_dict[s], float) else f"*{s}:* `{prog_dict[s]}`" for s in target_servers])
                safe_edit(bot, chat_id, message_id, txt.strip(), reply_markup=get_cancel_keyboard(task_id))
                last_upd = time.time()
            time.sleep(1)

        for t in threads: t.join()
        if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")

        watch_links, download_links, failed_sites = [], [], []
        for site in target_servers:
            code = res_dict.get(site)
            if code and not str(code).startswith("ERROR:"):
                if site == 'Abstream': watch_links.append(f"🟢 *ABStream:*\n└ 🔗 `https://abstream.to/embed-{code}.html`")
                elif site == 'Larhu': watch_links.append(f"🟠 *Larhu:*\n└ 🔗 `https://larhu.website/embed-{code}.html`")
                elif site == 'Vidmoly': watch_links.append(f"🟣 *Vidmoly:*\n└ 🔗 `https://vidmoly.biz/embed-{code}.html`")
                elif site == 'Uqload':
                    watch_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/embed-{code}.html`")
                    download_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/{code}`")
                elif site == 'Vidara': watch_links.append(f"🟡 *Vidara:*\n└ 🔗 `{code if str(code).startswith('http') else f'https://vidaraa.cc/e/{code}'}`")
                elif site == 'Doodstream': 
                    watch_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/e/{code}`")
                    download_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/d/{code}`")
                elif site == 'GoFile': download_links.append(f"🌐 *GoFile:*\n└ 🔗 `{code}`")
                elif site == 'VK': watch_links.append(f"📘 *VK:*\n└ 🔗 `{code}`")
                elif site == 'CloudflareR2': download_links.append(f"☁️ *Cloudflare R2:*\n└ 🔗 `{code}`")
                elif site == 'FreeDL': 
                    watch_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
                    download_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
            else: failed_sites.append(f"❌ *{site}:* `{str(code).replace('ERROR:', '') if code else 'فشل غير معروف'}`")

        if not watch_links and not download_links: raise Exception("لم يتم العثور على أي روابط بعد الرفع.")
        success = True
        
        res_txt = f"🎉 *اكتملت المهمة بنجاح!*\n🎬 `{custom_name or 'فيديو جديد'}`\n💡 _(اضغط على أي رابط لنسخه مباشرة)_\n\n"
        if watch_links: res_txt += "📺 *روابط المشاهدة:*\n━━━━━━━━━━━━━\n" + "\n\n".join(watch_links) + "\n\n"
        if download_links: res_txt += "📥 *روابط التحميل المباشر:*\n━━━━━━━━━━━━━\n" + "\n\n".join(download_links) + "\n\n"
        if failed_sites: res_txt += "⚠️ *سيرفرات فشل الرفع عليها:*\n━━━━━━━━━━━━━\n" + "\n".join(failed_sites)

        safe_edit(bot, chat_id, message_id, "✅ *تم الانتهاء من السحب والرفع! الروابط في الأسفل 👇*")
        bot.send_message(chat_id, res_txt, parse_mode="Markdown", reply_to_message_id=message_id, disable_web_page_preview=True)

    except Exception as e:
        markup = None
        if os.path.exists(out_file):
            failed_uploads[task_id] = {'file': out_file, 'name': custom_name, 'servers': target_servers}
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("♻️ إعادة رفع الفيديو", callback_data=f"retryup_{task_id}"))
        safe_edit(bot, chat_id, message_id, f"❌ *توقفت المهمة:*\n`{safe_error_text(e)}`\n\n*تفاصيل الأخطاء:*\n" + "\n".join([f"{s}: {res_dict.get(s)}" for s in target_servers if str(res_dict.get(s)).startswith("ERROR:")]), reply_markup=markup)
    finally:
        active_tasks.pop(task_id, None)
        if success and os.path.exists(out_file): os.remove(out_file)

def merge_process_logic(links_list, chat_id, message_id, target_servers, custom_name, quality="best"):
    task_id = f"merge_{chat_id}_{message_id}"
    active_tasks[task_id] = {"cancel": False, "process": None}
    merged_out_file, concat_txt_file, downloaded_parts, success = f"out_{task_id}.mp4", f"concat_{task_id}.txt", [], False

    try:
        for i, url in enumerate(links_list, 1):
            if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
            part_filename = f"part_{task_id}_{i}.mp4"
            ref, org = None, None
            if "4meplayer" in url or "player4me" in url: url, ref = bypass_player4me(url)
            elif "vidoba" in url: url, ref = bypass_vidoba(url, bot, chat_id, message_id, task_id)
            elif "1cloudfile" in url: url = bypass_1cloudfile(url)
            elif "up4ever" in url or "/d/" in url: ref = "https://www.up-4ever.net/"
            elif "seriesmp4.com" in url: ref, org = "https://seriesmp4.com/", "https://seriesmp4.com"
            elif "uqload" in url and (".mp4" in url or "/v/" in url or ".m3u8" in url): ref, org = f"https://{UQLOAD_DOMAIN}/", f"https://{UQLOAD_DOMAIN}"
            elif "uqload" in url: url, ref = bypass_uqload(url, bot, chat_id, message_id, task_id)
            
            download_manager(url, part_filename, bot, chat_id, message_id, task_id, referer=ref, origin=org, custom_msg=f"📥 *تحميل المقطع ({i}/{len(links_list)})...*", quality=quality)
            if not os.path.exists(part_filename) or os.path.getsize(part_filename) < 500000: raise Exception(f"❌ المقطع رقم {i} تالف.")
            downloaded_parts.append(part_filename)

        if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")
        safe_edit(bot, chat_id, message_id, "🧩 *المرحلة 2: جاري دمج المقاطع...*", reply_markup=get_cancel_keyboard(task_id))

        with open(concat_txt_file, 'w', encoding='utf-8') as f:
            for part in downloaded_parts: f.write(f"file '{part}'\n")

        ffmpeg_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt_file, "-c", "copy", merged_out_file]
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        active_tasks[task_id]['process'] = process
        stdout, stderr = process.communicate()

        if process.returncode != 0 or not os.path.exists(merged_out_file): raise Exception("❌ فشل عملية الدمج.")
        for part in downloaded_parts:
            try: os.remove(part)
            except: pass
        try: os.remove(concat_txt_file)
        except: pass

        safe_name = f"{re.sub(r'[^\w\s\u0600-\u06FF-]', '', custom_name).strip()[:40] or 'Merged'}.mp4" if custom_name else f"Merged_{random.randint(10000, 99999)}.mp4"
        prog_dict, res_dict, threads = {s: "⏳ في الانتظار..." for s in target_servers}, {s: None for s in target_servers}, []
        args_map = {"Abstream": (ABSTREAM_DOMAIN, bot_config["ABSTREAM_API_KEY"]), "Larhu": (LARHU_DOMAIN, bot_config["LARHU_API_KEY"]), "Uqload": (UQLOAD_DOMAIN, bot_config["UQLOAD_API_KEY"]), "Vidmoly": (VIDMOLY_DOMAIN, bot_config["VIDMOLY_API_KEY"]), "Vidara": (VIDARA_API_DOMAIN, bot_config["VIDARA_API_KEY"]), "Doodstream": (DOODSTREAM_DOMAIN, bot_config["DOODSTREAM_API_KEY"]), "FreeDL": (FREEDL_DOMAIN, bot_config["FREEDL_API_KEY"])}

        for site in target_servers:
            if site == "GoFile": t = threading.Thread(target=upload_to_gofile, args=(merged_out_file, safe_name, task_id, prog_dict, res_dict))
            elif site == "VK": t = threading.Thread(target=upload_to_vk, args=(merged_out_file, safe_name, custom_name, task_id, prog_dict, res_dict))
            elif site == "CloudflareR2": t = threading.Thread(target=upload_to_r2, args=(merged_out_file, safe_name, task_id, prog_dict, res_dict))
            else: t = threading.Thread(target=upload_to_xfs, args=(args_map[site][0], args_map[site][1], merged_out_file, safe_name, site, task_id, prog_dict, res_dict))
            threads.append(t); t.start(); time.sleep(3)

        last_upd = time.time()
        while any(t.is_alive() for t in threads):
            if active_tasks[task_id].get("cancel"): break
            if time.time() - last_upd > 3:
                txt = "🚀 *المرحلة 3: الرفع...*\n\n" + "\n".join([f"{get_emoji_for_server(s)} *{s}:* `[{make_bar(prog_dict[s])}]` *{int(prog_dict[s])}%*" if isinstance(prog_dict[s], float) else f"*{s}:* `{prog_dict[s]}`" for s in target_servers])
                safe_edit(bot, chat_id, message_id, txt.strip(), reply_markup=get_cancel_keyboard(task_id))
                last_upd = time.time()
            time.sleep(1)

        for t in threads: t.join()
        if active_tasks[task_id].get("cancel"): raise Exception("🛑 تم إلغاء العملية.")

        watch_links, download_links, failed_sites = [], [], []
        for site in target_servers:
            code = res_dict.get(site)
            if code and not str(code).startswith("ERROR:"):
                if site == 'Abstream': watch_links.append(f"🟢 *ABStream:*\n└ 🔗 `https://abstream.to/embed-{code}.html`")
                elif site == 'Larhu': watch_links.append(f"🟠 *Larhu:*\n└ 🔗 `https://larhu.website/embed-{code}.html`")
                elif site == 'Vidmoly': watch_links.append(f"🟣 *Vidmoly:*\n└ 🔗 `https://vidmoly.biz/embed-{code}.html`")
                elif site == 'Uqload':
                    watch_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/embed-{code}.html`")
                    download_links.append(f"🔵 *Uqload:*\n└ 🔗 `https://uqload.vc/{code}`")
                elif site == 'Vidara': watch_links.append(f"🟡 *Vidara:*\n└ 🔗 `{code if str(code).startswith('http') else f'https://vidaraa.cc/e/{code}'}`")
                elif site == 'Doodstream': 
                    watch_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/e/{code}`")
                    download_links.append(f"🟤 *Doodstream:*\n└ 🔗 `https://dood.to/d/{code}`")
                elif site == 'GoFile': download_links.append(f"🌐 *GoFile:*\n└ 🔗 `{code}`")
                elif site == 'VK': watch_links.append(f"📘 *VK:*\n└ 🔗 `{code}`")
                elif site == 'CloudflareR2': download_links.append(f"☁️ *Cloudflare R2:*\n└ 🔗 `{code}`")
                elif site == 'FreeDL': 
                    watch_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
                    download_links.append(f"🔴 *FreeDL:*\n└ 🔗 `https://freedl.ink/{code}`")
            else: failed_sites.append(f"❌ *{site}:* `{str(code).replace('ERROR:', '') if code else 'فشل غير معروف'}`")

        if not watch_links and not download_links: raise Exception("لم يتم العثور على أي روابط.")
        success = True
        
        res_txt = f"🎉 *اكتملت المهمة (مدمج)!*\n🎬 `{custom_name or 'فيديو جديد'}`\n💡 _(اضغط على أي رابط لنسخه مباشرة)_\n\n"
        if watch_links: res_txt += "📺 *روابط المشاهدة:*\n━━━━━━━━━━━━━\n" + "\n\n".join(watch_links) + "\n\n"
        if download_links: res_txt += "📥 *روابط التحميل المباشر:*\n━━━━━━━━━━━━━\n" + "\n\n".join(download_links) + "\n\n"
        if failed_sites: res_txt += "⚠️ *سيرفرات فشل الرفع عليها:*\n━━━━━━━━━━━━━\n" + "\n".join(failed_sites)

        safe_edit(bot, chat_id, message_id, "✅ *تم الانتهاء من الدمج والرفع! الروابط 👇*")
        bot.send_message(chat_id, res_txt, parse_mode="Markdown", reply_to_message_id=message_id, disable_web_page_preview=True)

    except Exception as e:
        markup = None
        if os.path.exists(merged_out_file):
            failed_uploads[task_id] = {'file': merged_out_file, 'name': custom_name, 'servers': target_servers}
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("♻️ إعادة الرفع", callback_data=f"retryup_{task_id}"))
        safe_edit(bot, chat_id, message_id, f"❌ *توقفت المهمة:*\n`{safe_error_text(e)}`\n\n*تفاصيل الأخطاء:*\n" + "\n".join([f"{s}: {res_dict.get(s)}" for s in target_servers if str(res_dict.get(s)).startswith("ERROR:")]), reply_markup=markup)
    finally:
        active_tasks.pop(task_id, None)
        if success and os.path.exists(merged_out_file): os.remove(merged_out_file)
        elif not os.path.exists(merged_out_file): failed_uploads.pop(task_id, None)

try:
    bot.remove_webhook()
    bot.set_my_commands([
        BotCommand("start", "بدء البوت وعرض القائمة"),
        BotCommand("batch", "رفع عدة حلقات دفعة واحدة"),
        BotCommand("merge", "دمج عدة أجزاء في فيديو واحد"),
        BotCommand("keys", "إدارة مفاتيح الـ API"),
        BotCommand("queue", "عرض قائمة الانتظار"),
        BotCommand("check", "فحص سيرفرات الرفع"),
        BotCommand("stats", "حالة السيرفر"),
        BotCommand("clearqueue", "تفريغ الطابور"),
        BotCommand("clean", "تنظيف مؤقت")
    ])
    print(f"🤖 Bot Started - {VERSION}")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
except Exception as e:
    print(f"❌ Error: {e}")
