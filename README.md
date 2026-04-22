# ⚽ Formachi.uz — Telegram Bot + Admin Panel

## Loyiha haqida
Formachi.uz uchun to'liq e-commerce bot.

## 🚀 Railway Deploy — Bosqichlar

### 1. GitHub ga push qiling
```bash
git init && git add . && git commit -m "init"
git remote add origin https://github.com/SIZNING/REPO
git push -u origin main
```

### 2. Railway.app
1. New Project → GitHub repo ulang
2. + New → Database → PostgreSQL qo'shing

### 3. Bot servisi — Environment Variables
```
BOT_TOKEN=8694138415:AAG...
ADMIN_IDS=8156792282
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_PANEL_SECRET=o'z_parolingiz
```
Start Command: `python bot/main.py`

### 4. Web servisi — yangi servis qo'shing
```
BOT_TOKEN=same
ADMIN_IDS=same
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_PANEL_SECRET=same
```
Start Command: `python run_web.py`

### Admin Panel
`https://your-web.railway.app/admin`
Parol: ADMIN_PANEL_SECRET qiymati
