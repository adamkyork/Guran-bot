import json, os, datetime as dt, requests
from zoneinfo import ZoneInfo

API = f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}"
TZ = ZoneInfo("Europe/Istanbul")
START = dt.date(2026, 11, 25)
DB = "progress.json"
INTERVALS = [1, 3, 7, 14, 30, 60, 120, 180]

PLAN = [
    (30, "Ан-Наба, Ан-Назиат"),
    (30, "Абаса, Ат-Таквир, Аль-Инфитар"),
    (30, "Аль-Мутаффифин, Аль-Иншикак, Аль-Бурудж"),
    (30, "Ат-Тарик, Аль-Аля, Аль-Гашия, Аль-Фаджр"),
    (30, "Аль-Балад — Аль-Аляк"),
    (30, "Аль-Кадр — Аль-Хумаза"),
    (30, "Аль-Филь — Ан-Нас"),
    (29, "Аль-Мульк"), (29, "Аль-Калам"), (29, "Аль-Хакка"),
    (29, "Аль-Мааридж"), (29, "Нух"), (29, "Аль-Джинн"),
    (29, "Аль-Муззаммиль"), (29, "Аль-Муддассир"), (29, "Аль-Кияма"),
    (29, "Аль-Инсан"), (29, "Аль-Мурсалят"),
]

def tg(method, **data):
    return requests.post(f"{API}/{method}", json=data, timeout=30).json()

def load():
    if os.path.exists(DB):
        return json.load(open(DB, encoding="utf-8"))
    return {"offset": 0, "chat": None, "next_new": 0, "items": {},
            "marked": None, "sent_m": None, "sent_e": None}

def save(d):
    json.dump(d, open(DB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def tasks_for(d, day, today):
    out = []
    i = d["next_new"] + (day - today).days
    if day >= START and i < len(PLAN):
        out.append(("new", i))
    for k, it in d["items"].items():
        due = dt.date.fromisoformat(it["due"])
        if due == day or (day == today and due < day):
            out.append(("rev", int(k)))
    return out

def label(kind, i):
    juz, name = PLAN[i]
    word = "Восстановить" if kind == "new" else "Повторить"
    return f"{word}: {juz}-й джуз — {name}"

def keyboard(kind, i):
    opts = [("✅ Хорошо", "good"), ("⚠️ Есть ошибки", "weak"),
            ("◐ Частично", "part"), ("❌ Не успел", "skip")]
    return {"inline_keyboard": [[{"text": t, "callback_data": f"{kind}|{i}|{c}"}] for t, c in opts]}

def send_today(d, today):
    tasks = tasks_for(d, today, today)
    if not tasks:
        tg("sendMessage", chat_id=d["chat"], text="Сегодня задач нет. Отдыхайте или читайте выученное в намазе.")
    for kind, i in tasks:
        tg("sendMessage", chat_id=d["chat"], text=label(kind, i), reply_markup=keyboard(kind, i))

def plan_text(d, today):
    lines = []
    for n, title in [(0, "Сегодня"), (1, "Завтра"), (2, "Послезавтра")]:
        tasks = tasks_for(d, today + dt.timedelta(days=n), today)
        lines.append(title + ":")
        lines += ["• " + label(k, i) for k, i in tasks] or ["• отдых"]
    return "\n".join(lines)

def progress_text(d):
    msg = []
    for juz in (30, 29):
        idx = [i for i, p in enumerate(PLAN) if p[0] == juz]
        done = sum(1 for i in idx if i < d["next_new"])
        msg.append(f"{juz}-й джуз: {done} из {len(idx)} частей")
    msg.append(f"На повторении: {len(d['items'])} частей")
    return "\n".join(msg)

def on_button(d, q, today):
    kind, i, res = q["data"].split("|"); i = int(i)
    tg("answerCallbackQuery", callback_query_id=q["id"])
    msg = q["message"]
    if res == "skip":
        tg("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
           text=label(kind, i) + "\n→ перенесено на завтра")
        return
    d["marked"] = today.isoformat()
    it = d["items"].get(str(i), {"step": -1})
    it["step"] = min(it["step"] + 1, len(INTERVALS) - 1) if res == "good" else 0
    it["due"] = (today + dt.timedelta(days=INTERVALS[it["step"]])).isoformat()
    d["items"][str(i)] = it
    if kind == "new" and res != "part" and i == d["next_new"]:
        d["next_new"] += 1
    tg("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
       text=label(kind, i) + f"\n→ отмечено. Следующее повторение: {it['due']}")

def main():
    d = load()
    now = dt.datetime.now(TZ); today = now.date()
    for u in tg("getUpdates", offset=d["offset"], timeout=0).get("result", []):
        d["offset"] = u["update_id"] + 1
        if "callback_query" in u:
            on_button(d, u["callback_query"], today)
            continue
        m = u.get("message", {}); text = m.get("text", "")
        if text.startswith("/start"):
            d["chat"] = m["chat"]["id"]
            tg("sendMessage", chat_id=d["chat"], text="Ассаляму алейкум! Бот запущен. План в 10:00, напоминание в 22:00. Команды: /today, /plan, /progress")
        elif d["chat"] and text.startswith("/today"):
            send_today(d, today)
        elif d["chat"] and text.startswith("/plan"):
            tg("sendMessage", chat_id=d["chat"], text=plan_text(d, today))
        elif d["chat"] and text.startswith("/progress"):
            tg("sendMessage", chat_id=d["chat"], text=progress_text(d))
    if d["chat"] and now.hour >= 10 and d["sent_m"] != today.isoformat():
        tg("sendMessage", chat_id=d["chat"], text="Доброе утро! План:\n\n" + plan_text(d, today))
        send_today(d, today)
        d["sent_m"] = today.isoformat()
    if d["chat"] and now.hour >= 22 and d["sent_e"] != today.isoformat():
        if d["marked"] != today.isoformat() and tasks_for(d, today, today):
            tg("sendMessage", chat_id=d["chat"], text="Сегодня ещё ничего не отмечено. Если успеете, нажмите /today. Если нет, всё перенесётся на завтра.")
        d["sent_e"] = today.isoformat()
    save(d)

main()
