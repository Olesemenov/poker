"""Mobile UI (Kivy). Run on desktop for development:  python -m app.main

Screens:
  menu     -> "Online" / "Offline"
  offline  -> local hot-seat table (2-6 players share one phone)
  host     -> starts the server on this device and shows the invite link
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.slider import Slider

from poker.game import PokerError, Table

SUITS = {"c": "♣", "d": "♦", "h": "♥", "s": "♠"}


def fmt(card: str) -> str:
    return "🂠" if card == "??" else card[0] + SUITS[card[1]]


class MenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        box = BoxLayout(orientation="vertical", padding=30, spacing=20)
        box.add_widget(Label(text="Poker", font_size="40sp"))
        box.add_widget(Button(text="Online (створити кімнату)", on_release=lambda *_: self.go("host")))
        box.add_widget(Button(text="Offline (один стіл на пристрої)", on_release=lambda *_: self.go("offline")))
        self.add_widget(box)

    def go(self, name):
        self.manager.current = name


class OfflineScreen(Screen):
    """Hot-seat table: players pass the phone around."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.table = None
        self.reveal = False
        self.raise_to = 0
        self.root_box = BoxLayout(orientation="vertical", padding=10, spacing=6)
        self.add_widget(self.root_box)

    def on_enter(self):
        self.table = Table(10, 20)
        for i in range(4):  # TODO: setup screen to choose names/count/stack/blinds
            self.table.add_player(f"p{i}", f"Гравець {i + 1}", 1000)
        self.new_hand()

    def new_hand(self):
        try:
            self.table.start_hand()
        except PokerError as e:
            self.message = str(e)
        self.reveal = False
        self.refresh()

    def act(self, action, amount=0):
        try:
            self.table.act(self.table.players[self.table.current].id, action, amount)
        except PokerError as e:
            self.message = str(e)
        self.reveal = False
        self.refresh()

    def refresh(self):
        t, box = self.table, self.root_box
        box.clear_widgets()
        s = t.public_state(None)
        box.add_widget(Label(text=f"{s['phase']} · банк {s['pot']}", size_hint_y=0.08))
        box.add_widget(Label(text="  ".join(fmt(c) for c in s["board"]) or "—", font_size="28sp", size_hint_y=0.15))
        lines = []
        for p in s["players"]:
            mark = ">" if p["is_current"] else " "
            d = "(D)" if p["is_dealer"] else ""
            st = "fold" if p["folded"] else ("all-in" if p["all_in"] else "")
            lines.append(f"{mark} {p['name']} {d}  стек {p['stack']}  ставка {p['bet']} {st}")
        box.add_widget(Label(text="\n".join(lines), size_hint_y=0.3))

        if t.phase == "waiting":
            res = t.last_result
            if res:
                names = {p.id: p.name for p in t.players}
                txt = ", ".join(f"{names[w['id']]} +{w['amount']} {w['hand'] or ''}" for w in res["winners"])
                box.add_widget(Label(text="Переможець: " + txt))
            box.add_widget(Button(text="Нова роздача", on_release=lambda *_: self.new_hand()))
        else:
            me = t.players[t.current]
            hole = "  ".join(str(c) for c in me.hole)
            if self.reveal:
                box.add_widget(Label(text=f"{me.name}: " + "  ".join(fmt(str(c)) for c in me.hole), font_size="28sp"))
            else:
                box.add_widget(Button(text=f"{me.name}: показати карти", on_release=self.show))
            la = t.legal_actions(me.id)
            row = BoxLayout(size_hint_y=0.15, spacing=6)
            row.add_widget(Button(text="Fold", on_release=lambda *_: self.act("fold")))
            if la["check"]:
                row.add_widget(Button(text="Check", on_release=lambda *_: self.act("check")))
            if la["call"]:
                row.add_widget(Button(text=f"Call {la['call']}", on_release=lambda *_: self.act("call")))
            box.add_widget(row)
            if la["raise"]:
                r = la["raise"]
                self.raise_to = r["min"]
                lbl = Label(text=f"Raise to {r['min']}", size_hint_y=0.07)
                sl = Slider(min=r["min"], max=r["max"], value=r["min"], step=max(1, t.bb // 2), size_hint_y=0.1)

                def on_val(_, v, lbl=lbl):
                    self.raise_to = int(v)
                    lbl.text = f"Raise to {int(v)}"

                sl.bind(value=on_val)
                box.add_widget(lbl)
                box.add_widget(sl)
                box.add_widget(Button(text="Raise", on_release=lambda *_: self.act("raise", self.raise_to)))
                box.add_widget(Button(text="All-in", on_release=lambda *_: self.act("allin")))
        box.add_widget(Button(text="← Меню", size_hint_y=0.08, on_release=lambda *_: setattr(self.manager, "current", "menu")))

    def show(self, *_):
        self.reveal = True
        self.refresh()

    message = ""


class HostScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.handle = None
        self.box = BoxLayout(orientation="vertical", padding=20, spacing=12)
        self.info = Label(text="Натисніть, щоб створити кімнату на цьому пристрої", halign="center")
        self.box.add_widget(self.info)
        self.box.add_widget(Button(text="Створити кімнату", on_release=self.start))
        self.box.add_widget(Button(text="← Меню", on_release=lambda *_: setattr(self.manager, "current", "menu")))
        self.add_widget(self.box)

    def start(self, *_):
        if self.handle:
            return
        from poker.server import start_in_thread  # needs aiohttp

        self.handle = start_in_thread(port=8080)
        self.info.text = (
            "Кімната створена. Надішліть гравцям посилання\n(усі в одній Wi-Fi / хотспоті):\n\n"
            f"{self.handle.guest_url}\n\nВи (host): відкрийте\n{self.handle.host_url}"
        )
        # TODO: copy/share button, QR code, embedded host UI instead of the browser link


class PokerApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(OfflineScreen(name="offline"))
        sm.add_widget(HostScreen(name="host"))
        return sm


if __name__ == "__main__":
    PokerApp().run()
