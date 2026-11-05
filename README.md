# Poker (Texas Hold'em) — mobile, Python

Мобільний покер для друзів: **Online** (хост створює кімнату на своєму пристрої,
до 6 гравців заходять за посиланням) та **Offline** (один стіл на одному пристрої).

Стек: Python 3.11+, Kivy (UI), aiohttp (сервер/WebSocket).

- План і етапи: [docs/PLAN.md](docs/PLAN.md)
- Інструкція для macOS: [docs/MAC_SETUP.md](docs/MAC_SETUP.md)
- Тести: `python -m unittest discover -s tests -t .`
- Dev-сервер: `python -m poker.server`
- UI на ПК: `python -m app.main`

Статус: ядро гри протестоване; сервер і Kivy-UI — перший чернетковий каркас.
