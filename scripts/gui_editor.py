#!/usr/bin/env python3
"""SenderGirl UserData.saveIt セーブエディタ (簡易GUI, Tk / Mac・Windows対応)。

使い方:
    python3 gui_editor.py

外部パッケージ不要。Python 3.8+ の標準ライブラリ (Tkinter含む) のみで動作。
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import saveit_format  # noqa: E402
import save_payload  # noqa: E402
from save_payload import Decimal96  # noqa: E402

# バックアップの保存先。編集元ファイルと同じフォルダに書こうとすると、
# それがiOSアプリのサンドボックスコンテナ内 (~/Library/Containers/<UUID>/...)
# だった場合、選択したファイル自体への書き込みは許可されていても
# 同じフォルダに新規ファイルを作ることは許可されておらず
# ([Errno 1] Operation not permitted) バックアップが作れないことがある
# (実機で確認済み)。ホームディレクトリ直下の専用フォルダに退避することで
# この問題を避ける。
BACKUP_DIR = Path.home() / ".SGSE_bak"


# (キー, ラベル, 種別)  種別: "bool" / "int" / "float" / "decimal" / "str"
SIMPLE_FIELDS = [
    ("boyfriendName", "彼氏の名前", "str"),
    ("BGMOn", "BGM ON", "bool"),
    ("SEOn", "SE ON", "bool"),
    ("VIBEOn", "バイブ ON", "bool"),
    ("BGMVolume", "BGM音量 (0.0-1.0)", "float"),
    ("SEVolume", "SE音量 (0.0-1.0)", "float"),
    ("currentCookieCount", "♡の数", "decimal"),
    ("totalCookieCount", "♡総生産数", "decimal"),
    ("maxCookie", "最高♡所持数", "decimal"),
    # currentCrystal (課金アイテムのクリスタル) は編集すると起動直後に
    # フリーズすることが実機で確認されたため、簡単編集タブからは意図的に
    # 除外している。課金アイテムのため整合性チェックが厳しいと見られる。
    # 触りたい場合は自己責任で「詳細 (JSON)」タブから編集すること。
    ("clickMakeCount", "タップ増加量", "int"),
    ("autoMakeSpeed", "自動生成速度", "float"),
    ("round", "ラウンド", "int"),
    ("eventCompleteLevel", "イベント達成レベル", "int"),
    ("tutoProgress", "チュートリアル進行度", "int"),
    ("totalClickMakeCount", "部屋タップの生産数", "int"),
    # totalClickCount (部屋タップ回数) は編集するとフリーズすることが
    # 実機で確認された。【関西弁版】ではタップ強化アイテムの一部の解放
    # 条件 (300/750/1250回タップ) にこの値が使われているらしく、他の
    # 値との整合性が取れなくなるのが原因と見られるが、何を合わせれば
    # よいかは未検証。タップ回数はいじらず、アイテムの状態を直接
    # 解放する方が安全。currentCrystal 同様、簡単編集タブから除外。
    ("comeEnemyCount", "友達が来た回数", "int"),
    ("repelEnemyCount", "おもてなし回数", "int"),
    ("useRepelItemCount", "撃退アイテム使用回数", "int"),
    ("lostCookieCount", "邪魔された♡の数", "int"),
    ("maxTeaSet", "最大ティーセット数", "int"),
    ("teaset", "ティーセットの所持数", "int"),
    ("boostAvailavleTime", "ブースト使用可能時間", "int"),
    ("boostOnTime", "ブースト発動時間", "int"),
    ("shopBadgeFlg", "ショップバッジ表示", "bool"),
    ("appReview", "アプリレビュー済み", "bool"),
    ("appReviewCrystal", "レビュー報酬クリスタル受取済み", "bool"),
]

FACILITIES_COUNT = 11
TEA_ITEM_COUNT = 4

# 実機での動作確認により判明した状態 (ユーザー提供の解析結果、2026-08-24)。
# powerupItemLevel / tapItemLevel: 0=未解放, 1=解放済み(未確認),
#   2=確認済み(詳細を開いた), 3=購入済み
# teaItemLevel: 0=未解放, 1=解放済み(未購入), 2=購入済み。
#   購入済み(=2)の個数 n に対して maxTeaSet = 2n (0個→0, 1個→2, 2個→4,
#   3個→6, 4個→8)。
POWERUP_STATES = [(0, "未解放"), (1, "未確認"), (2, "確認済"), (3, "購入済")]
TEA_STATES = [(0, "未解放"), (1, "未購入"), (2, "購入済")]
POWERUP_LABELS = [f"{i}: {desc}" for i, desc in POWERUP_STATES]
TEA_LABELS = [f"{i}: {desc}" for i, desc in TEA_STATES]

# openClothesIds (【関西弁版】限定の衣装開放状態、実機検証済み、
# 2026-08-25): 0=未解放, 1=解放済み(未着用), 2=解放済み(着用歴あり)。
# 衣装そのものに固有の名前は無い (説明文はあるがシンプルな名前は無い)
# とのことなので、"衣装N" という通し番号のみで表示する。
CLOTHES_STATES = [(0, "未解放"), (1, "解放済み(未着用)"), (2, "解放済み(着用歴あり)")]
CLOTHES_LABELS = [f"{i}: {desc}" for i, desc in CLOTHES_STATES]

# 生産アイテム (facilitiesLevel/powerupItemLevel の11種) は、レベルアップ
# する度に見た目・名前が変わる。各アイテムのレベル0〜3の名前
# (ユーザーが実機で確認・提供)。
FACILITY_NAMES = [
    ["電柱", "ダンボール", "透明マント", "着ぐるみ"],
    ["監視カメラ", "全方位型監視カメラ", "暗視カメラ", "ロボット型監視カメラ"],
    ["探偵さん", "サイバー探偵さん", "霊能探偵さん", "名探偵さん"],
    ["監視衛星", "探査衛星", "キラー衛星", "宇宙ステーション"],
    ["殺し屋さん", "スナイパーさん", "ボマーさん", "仕事人さん"],
    ["警察官さん", "刑事さん", "FBIさん", "警視総監さん"],
    ["総理大臣さん", "連合国首相さん", "法王さん", "大統領さん"],
    ["調査兵団さん", "巨人兵団さん", "大型巨人兵団さん", "兵長兵団さん"],
    ["寄生さん", "完全寄生さん", "寄生失敗さん", "最強生物さん"],
    ["願いを叶える龍", "願いを叶えるネコ", "願いを叶えるノート", "願いを叶えるロボ"],
    ["彼の部屋の鍵", "彼の机の鍵", "彼の実家の鍵", "彼の心の鍵"],
]

# タップ強化アイテム (tapItemLevel) の名前。無印は4種類、【関西弁版】
# (SenderGirlK) は7種類 (衣装) あることを実機で確認済み (ユーザー提供、
# 2026-08-25)。
TAP_ITEM_NAMES_VANILLA = ["お掃除", "メイク", "トレーニング", "ヨガ"]
TAP_ITEM_NAMES_K = [
    "猛虎おろしな服",
    "インテリ女子な服",
    "おりぼんモンスターな服",
    "タコヤキはっぴーな服",
    "フライングアイドルな服",
    "ミナミの女王な服",
    "新世界タワーな服",
]

# 【関西弁版】ではタップ強化アイテムの一部 (2/4/6番目、0-indexedで1/3/5)
# に「部屋タップ回数」による解放条件があるらしい (ユーザー提供の実機
# 検証結果)。ただし totalClickCount (部屋タップ回数) を直接編集すると
# フリーズすることが確認されているため、あくまで参考情報として表示する
# だけにとどめ、GUIからタップ回数自体を書き換える機能は設けない。
K_TAP_UNLOCK_TAPS = {1: 300, 3: 750, 5: 1250}


def _tap_item_name(i: int, is_k: bool) -> str:
    names = TAP_ITEM_NAMES_K if is_k else TAP_ITEM_NAMES_VANILLA
    label = names[i] if i < len(names) else f"タップアイテム{i + 1} (未確認)"
    taps = K_TAP_UNLOCK_TAPS.get(i)
    if is_k and taps is not None:
        label += f" (部屋タップ{taps}回で解放)"
    return label


def _powerup_labels_for(name: str | None):
    """0〜3の状態ラベルを返す。name を渡すと、3(購入済み)にそのレベルで
    入手できるアイテム名を添える。"""
    labels = []
    for i, desc in POWERUP_STATES:
        if i == 3 and name is not None:
            labels.append(f"{i}: {desc}({name})")
        else:
            labels.append(f"{i}: {desc}")
    return labels


def _label_for_state(value, labels):
    for lbl in labels:
        if lbl.startswith(f"{value}:"):
            return lbl
    return labels[0]


def _state_from_label(label):
    return int(label.split(":", 1)[0])


def _decimal_to_json(obj):
    if isinstance(obj, Decimal96):
        return str(obj.value)
    if isinstance(obj, dict):
        return {k: _decimal_to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_json(v) for v in obj]
    return obj


def _reapply_types(old, new):
    """new (JSONをパースしたプレーンなPython値) に、old が持っていた
    Decimal96 などの特殊な型を再適用する。"""
    if isinstance(old, Decimal96):
        try:
            return Decimal96(Decimal(str(new)))
        except InvalidOperation:
            return old
    if isinstance(old, dict) and isinstance(new, dict):
        return {k: (_reapply_types(old[k], v) if k in old else v) for k, v in new.items()}
    if isinstance(old, list) and isinstance(new, list):
        return [
            _reapply_types(old[i], v) if i < len(old) else v
            for i, v in enumerate(new)
        ]
    return new


class SaveEditorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SenderGirl セーブエディタ")
        self.root.geometry("1080x760")
        self.root.minsize(900, 480)

        self.data: dict | None = None
        self.raw_main: bytes | None = None
        self.loaded_path: Path | None = None
        self.widgets: dict[str, tuple[str, tk.Variable | tk.Text]] = {}
        self.facilities_vars: list[tk.StringVar] = []
        self.powerup_vars: list[list[tk.StringVar]] = []
        self.tap_vars: list[tk.StringVar] = []
        self.tea_vars: list[tk.StringVar] = []
        self.k_select_clothes_var: tk.StringVar | None = None
        self.k_next_tap_var: tk.StringVar | None = None
        self.k_clothes_vars: list[tk.StringVar] = []
        self.is_k = False

        self._build_menu()
        self._build_body()
        self._set_status("UserData.saveIt を開いてください (ファイル > 開く)")

    # ---- UI 構築 ----------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        accel_mod = "Command" if sys.platform == "darwin" else "Ctrl"
        filemenu.add_command(label="開く...", command=self.open_file, accelerator=f"{accel_mod}+O")
        filemenu.add_command(label="保存 (上書き)", command=self.save_file, accelerator=f"{accel_mod}+S")
        filemenu.add_command(label="名前を付けて保存...", command=self.save_file_as)
        menubar.add_cascade(label="ファイル", menu=filemenu)
        self.root.config(menu=menubar)
        self.root.bind_all("<Command-o>", lambda e: self.open_file())
        self.root.bind_all("<Control-o>", lambda e: self.open_file())
        self.root.bind_all("<Command-s>", lambda e: self.save_file())
        self.root.bind_all("<Control-s>", lambda e: self.save_file())

    def _build_body(self):
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill="x", padx=8, pady=(8, 0))
        self.variant_badge = tk.Label(
            top_bar, text="", font=("", 10, "bold"), padx=8, pady=2, relief="flat"
        )
        self.variant_badge.pack(side="right")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.simple_tab = ttk.Frame(self.notebook)
        self.items_tab = ttk.Frame(self.notebook)
        self.k_tab = ttk.Frame(self.notebook)
        self.advanced_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.simple_tab, text="簡単編集")
        self.notebook.add(self.items_tab, text="アイテム")
        self.notebook.add(self.k_tab, text="関西弁版限定")
        self.notebook.add(self.advanced_tab, text="詳細 (JSON)")
        self.notebook.tab(self.k_tab, state="disabled")

        self._build_simple_tab()
        self._build_items_tab()
        self._build_k_tab()
        self._build_advanced_tab()

        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom", padx=8, pady=(0, 8))
        self.status_var = tk.StringVar()
        ttk.Label(status_bar, textvariable=self.status_var, foreground="#555").pack(anchor="w")

    def _build_simple_tab(self):
        canvas = tk.Canvas(self.simple_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.simple_tab, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for row, (key, label, kind) in enumerate(SIMPLE_FIELDS):
            ttk.Label(inner, text=label, width=28, anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=4)
            if kind == "bool":
                var = tk.BooleanVar()
                widget = ttk.Checkbutton(inner, variable=var)
                widget.grid(row=row, column=1, sticky="w", padx=6, pady=4)
            else:
                var = tk.StringVar()
                widget = ttk.Entry(inner, textvariable=var, width=30)
                widget.grid(row=row, column=1, sticky="w", padx=6, pady=4)
            self.widgets[key] = (kind, var)
        self.simple_canvas = canvas
        self._bind_wheel_recursive(self.simple_tab, canvas)

    def _build_items_tab(self):
        canvas = tk.Canvas(self.items_tab, highlightthickness=0)
        vscroll = ttk.Scrollbar(self.items_tab, orient="vertical", command=canvas.yview)
        hscroll = ttk.Scrollbar(self.items_tab, orient="horizontal", command=canvas.xview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        vscroll.pack(side="right", fill="y")
        hscroll.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)

        row = 0
        ttk.Label(
            inner,
            text="生産アイテム (11種) の所持数",
            font=("", 11, "bold"),
        ).grid(row=row, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 2))
        row += 1
        for i in range(FACILITIES_COUNT):
            ttk.Label(
                inner, text=f"{i + 1}: {FACILITY_NAMES[i][0]}系 所持数", width=26, anchor="w"
            ).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            var = tk.StringVar()
            ttk.Entry(inner, textvariable=var, width=12).grid(row=row, column=1, sticky="w", padx=6, pady=2)
            self.facilities_vars.append(var)
            row += 1

        row += 1
        ttk.Label(
            inner,
            text="生産アイテムのレベルアップ (各アイテム4段階、Lv1〜4の順に左から)\n"
            "0=未解放 / 1=未確認 / 2=確認済 / 3=購入済み (購入済みで入手できる名前を表示)",
            font=("", 11, "bold"),
            justify="left",
        ).grid(row=row, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 2))
        row += 1
        for i in range(FACILITIES_COUNT):
            ttk.Label(
                inner, text=f"{i + 1}: {FACILITY_NAMES[i][0]}系", width=14, anchor="w"
            ).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            level_vars = []
            for lv in range(4):
                labels = _powerup_labels_for(FACILITY_NAMES[i][lv])
                var = tk.StringVar()
                cb = ttk.Combobox(inner, textvariable=var, values=labels, state="readonly", width=13)
                cb.grid(row=row, column=1 + lv, sticky="w", padx=3, pady=2)
                level_vars.append(var)
            self.powerup_vars.append(level_vars)
            row += 1

        row += 1
        ttk.Label(
            inner,
            text="タップ強化アイテムの状態 (無印は4種、【関西弁版】は7種)\n"
            "0=未解放 / 1=未確認 / 2=確認済 / 3=購入済み",
            font=("", 11, "bold"),
            justify="left",
        ).grid(row=row, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 2))
        row += 1
        self.tap_frame = ttk.Frame(inner)
        self.tap_frame.grid(row=row, column=0, columnspan=5, sticky="w")
        row += 1

        row += 1
        ttk.Label(
            inner,
            text="妨害ブロックアイテム (4種) の状態\n"
            "0=未解放 / 1=未購入 / 2=購入済み\n"
            "(購入済みの個数 n に対して maxTeaSet = 2n。例: 2個購入済みなら maxTeaSet=4)",
            font=("", 11, "bold"),
            justify="left",
        ).grid(row=row, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 2))
        row += 1
        ttk.Label(inner, text="状態", width=12, anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=2)
        for i in range(TEA_ITEM_COUNT):
            var = tk.StringVar()
            cb = ttk.Combobox(inner, textvariable=var, values=TEA_LABELS, state="readonly", width=9)
            cb.grid(row=row, column=1 + i, sticky="w", padx=3, pady=2)
            self.tea_vars.append(var)
        row += 1

        self.items_canvas = canvas
        self._bind_wheel_recursive(self.items_tab, canvas)

    def _rebuild_tap_rows(self, count: int):
        """tapItemLevel の要素数は無印(4)と【関西弁版】(7)で異なるため、
        読み込んだデータの実際の長さに合わせて行を作り直す。"""
        for child in self.tap_frame.winfo_children():
            child.destroy()
        self.tap_vars = []
        for i in range(count):
            ttk.Label(
                self.tap_frame, text=_tap_item_name(i, self.is_k), width=30, anchor="w"
            ).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            var = tk.StringVar()
            cb = ttk.Combobox(
                self.tap_frame, textvariable=var, values=POWERUP_LABELS, state="readonly", width=14
            )
            cb.grid(row=i, column=1, sticky="w", padx=3, pady=2)
            self.tap_vars.append(var)
        self._bind_wheel_recursive(self.tap_frame, self.items_canvas)

    def _build_k_tab(self):
        canvas = tk.Canvas(self.k_tab, highlightthickness=0)
        vscroll = ttk.Scrollbar(self.k_tab, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        ttk.Label(
            inner,
            text="【関西弁版】(ゆるヤミ彼女と100万件のメッセージ / com.Happygamer.SenderGirlK)\n"
            "にしか存在しないフィールド。無印には無いため、無印のセーブを開いている間は\n"
            "このタブは操作できません。\n"
            "衣装 (着せ替え) 関連の要素と判明済み (実機検証、2026-08-25)。個々の衣装に\n"
            "固有の名前は無いようなので通し番号で表示しています。",
            justify="left",
            foreground="#a05a2c",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 10))

        ttk.Label(inner, text="selectClothes (選択中の衣装ID。-1=未選択)", width=40, anchor="w").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )
        self.k_select_clothes_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.k_select_clothes_var, width=12).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(
            inner, text="nextTapItemAvailStatus (意味未確認。無関係な値の可能性あり)", width=48, anchor="w"
        ).grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.k_next_tap_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.k_next_tap_var, width=12).grid(
            row=2, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(
            inner,
            text="openClothesIds (各衣装の開放状態)",
            font=("", 11, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(12, 2))
        self.k_clothes_frame = ttk.Frame(inner)
        self.k_clothes_frame.grid(row=4, column=0, columnspan=2, sticky="w")

        self.k_canvas = canvas
        self._bind_wheel_recursive(self.k_tab, canvas)

    def _rebuild_k_clothes_rows(self, count: int):
        for child in self.k_clothes_frame.winfo_children():
            child.destroy()
        self.k_clothes_vars = []
        for i in range(count):
            ttk.Label(self.k_clothes_frame, text=f"衣装{i + 1}", width=12, anchor="w").grid(
                row=i, column=0, sticky="w", padx=6, pady=2
            )
            var = tk.StringVar()
            cb = ttk.Combobox(
                self.k_clothes_frame, textvariable=var, values=CLOTHES_LABELS, state="readonly", width=20
            )
            cb.grid(row=i, column=1, sticky="w", padx=6, pady=2)
            self.k_clothes_vars.append(var)
        self._bind_wheel_recursive(self.k_clothes_frame, self.k_canvas)

    def _build_advanced_tab(self):
        info = ttk.Label(
            self.advanced_tab,
            text="全フィールドの生データ (JSON)。編集後は必ず [JSONを適用] を押してください。"
            "\n巨大な数値フィールド (♡の数など) は文字列として表示されます。",
            justify="left",
        )
        info.pack(anchor="w", padx=8, pady=(8, 4))

        self.json_text = tk.Text(self.advanced_tab, wrap="none", font=("Menlo", 11))
        self.json_text.pack(fill="both", expand=True, padx=8, pady=4)

        btns = ttk.Frame(self.advanced_tab)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="JSONを適用 (簡単編集タブに反映)", command=self.apply_json).pack(side="left")
        ttk.Button(btns, text="現在値でJSONを再生成", command=self.refresh_json_from_data).pack(side="left", padx=8)

    def _bind_wheel_recursive(self, widget, canvas):
        """widget とその子孫すべてに直接ホイール/トラックパッドの
        バインドを張り、canvas をスクロールする。

        (背景) canvas 自体や bind_all だけに頼ると、上に乗っている
        ttk.Entry/ttk.Combobox などの子ウィジェットがホイールイベントを
        内部で処理してしまい、canvas まで伝播しないことがある
        (スクロールバー上でだけスクロールできて、それ以外の場所では
        効かない、という不具合として現れる)。ウィジェット単位で直接
        bind すれば、そのウィジェット自身の (デフォルトの) ハンドラより
        先に必ず実行されるため、確実にスクロールできる。"""

        def _on_wheel(event):
            # event.delta の絶対値は Mac/Windows/トラックパッドの種類で
            # まちまち (小さすぎて int() で 0 になったり、逆に大きすぎて
            # 一気に最後まで飛んだりする) なので、符号だけを見て1単位ずつ
            # 動かす。これが最も環境に依存しない安全な方法。
            if event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.delta < 0:
                canvas.yview_scroll(1, "units")

        def _on_up(_event):
            canvas.yview_scroll(-1, "units")

        def _on_down(_event):
            canvas.yview_scroll(1, "units")

        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_up)
        widget.bind("<Button-5>", _on_down)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child, canvas)

    # ---- データ <-> ウィジェット -------------------------------------
    def _refresh_simple_tab(self):
        if self.data is None:
            return
        for key, (kind, var) in self.widgets.items():
            value = self.data.get(key)
            if kind == "bool":
                var.set(bool(value))
            elif kind == "decimal":
                v = value.value if isinstance(value, Decimal96) else value
                var.set(str(v))
            else:
                var.set("" if value is None else str(value))

    def _collect_simple_tab_into_data(self):
        if self.data is None:
            return
        for key, (kind, var) in self.widgets.items():
            if key not in self.data:
                continue
            raw = var.get()
            try:
                if kind == "bool":
                    self.data[key] = bool(var.get())
                elif kind == "int":
                    self.data[key] = int(raw)
                elif kind == "float":
                    self.data[key] = float(raw)
                elif kind == "decimal":
                    self.data[key] = Decimal96(Decimal(raw))
                else:
                    self.data[key] = raw
            except (ValueError, InvalidOperation):
                raise ValueError(f"「{key}」の値が不正です: {raw!r}")

    def _refresh_items_tab(self):
        if self.data is None:
            return
        self.is_k = save_payload.is_k_variant(self.data)
        self.notebook.tab(self.k_tab, state="normal" if self.is_k else "disabled")
        if self.is_k:
            self.variant_badge.config(text="関西弁版", bg="#ffe0b2", fg="#5d4037")
        else:
            self.variant_badge.config(text="ゆるヤミ彼女(無印)", bg="#f8bbd0", fg="#4a148c")

        facilities = self.data.get("facilitiesLevel") or []
        for i, var in enumerate(self.facilities_vars):
            var.set(str(facilities[i]) if i < len(facilities) else "")

        powerup = self.data.get("powerupItemLevel") or []
        for i, level_vars in enumerate(self.powerup_vars):
            levels = powerup[i] if i < len(powerup) else []
            for lv, var in enumerate(level_vars):
                value = levels[lv] if lv < len(levels) else 0
                labels = _powerup_labels_for(FACILITY_NAMES[i][lv])
                var.set(_label_for_state(value, labels))

        tap = self.data.get("tapItemLevel") or []
        self._rebuild_tap_rows(len(tap))
        for i, var in enumerate(self.tap_vars):
            var.set(_label_for_state(tap[i], POWERUP_LABELS))

        tea = self.data.get("teaItemLevel") or []
        for i, var in enumerate(self.tea_vars):
            value = tea[i] if i < len(tea) else 0
            var.set(_label_for_state(value, TEA_LABELS))

        if self.is_k:
            self.k_select_clothes_var.set(str(self.data.get("selectClothes", "")))
            self.k_next_tap_var.set(str(self.data.get("nextTapItemAvailStatus", "")))
            clothes = self.data.get("openClothesIds") or []
            self._rebuild_k_clothes_rows(len(clothes))
            for i, var in enumerate(self.k_clothes_vars):
                var.set(_label_for_state(clothes[i], CLOTHES_LABELS))
        else:
            self._rebuild_k_clothes_rows(0)

    def _collect_items_tab_into_data(self):
        if self.data is None:
            return
        if "facilitiesLevel" in self.data:
            try:
                self.data["facilitiesLevel"] = [int(var.get()) for var in self.facilities_vars]
            except ValueError:
                raise ValueError("生産アイテムの所持数には整数を入力してください。")

        if "powerupItemLevel" in self.data:
            self.data["powerupItemLevel"] = [
                [_state_from_label(var.get()) for var in level_vars] for level_vars in self.powerup_vars
            ]

        if "tapItemLevel" in self.data:
            self.data["tapItemLevel"] = [_state_from_label(var.get()) for var in self.tap_vars]

        if "teaItemLevel" in self.data:
            self.data["teaItemLevel"] = [_state_from_label(var.get()) for var in self.tea_vars]

        if self.is_k:
            try:
                if "selectClothes" in self.data:
                    self.data["selectClothes"] = int(self.k_select_clothes_var.get())
                if "nextTapItemAvailStatus" in self.data:
                    self.data["nextTapItemAvailStatus"] = int(self.k_next_tap_var.get())
                if "openClothesIds" in self.data:
                    self.data["openClothesIds"] = [
                        _state_from_label(var.get()) for var in self.k_clothes_vars
                    ]
            except ValueError:
                raise ValueError("「関西弁版限定」タブの selectClothes / nextTapItemAvailStatus には整数を入力してください。")

    def refresh_json_from_data(self):
        if self.data is None:
            return
        pretty = json.dumps(_decimal_to_json(self.data), indent=2, ensure_ascii=False)
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", pretty)

    def apply_json(self):
        if self.data is None:
            return
        text = self.json_text.get("1.0", "end")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSONエラー", f"JSONの構文が不正です:\n{e}")
            return
        try:
            self.data = _reapply_types(self.data, parsed)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("エラー", f"JSONの適用に失敗しました:\n{e}")
            return
        self._refresh_simple_tab()
        self._refresh_items_tab()
        self._set_status("JSONの内容を反映しました。")

    # ---- ファイル操作 -------------------------------------------------
    def open_file(self):
        path = filedialog.askopenfilename(
            title="UserData.saveIt を開く",
            filetypes=[("SaveIt files", "*.saveIt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            main = saveit_format.decrypt_main_entry(raw)
            self.data = save_payload.decode_main(main)
            self.raw_main = main
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("読み込みエラー", f"ファイルの読み込みに失敗しました:\n{e}")
            return
        self.loaded_path = Path(path)
        self._refresh_simple_tab()
        self._refresh_items_tab()
        self.refresh_json_from_data()
        self._set_status(f"読み込み完了: {path}")

    def save_file(self):
        if self.loaded_path is None:
            self.save_file_as()
            return
        self._write_to(self.loaded_path)

    def save_file_as(self):
        if self.data is None:
            messagebox.showwarning("未読み込み", "先に UserData.saveIt を開いてください。")
            return
        path = filedialog.asksaveasfilename(
            title="名前を付けて保存",
            defaultextension=".saveIt",
            initialfile="UserData.saveIt",
            filetypes=[("SaveIt files", "*.saveIt"), ("All files", "*.*")],
        )
        if not path:
            return
        self._write_to(Path(path))

    def _write_to(self, path: Path):
        try:
            self._collect_simple_tab_into_data()
            self._collect_items_tab_into_data()
        except ValueError as e:
            messagebox.showerror("入力エラー", str(e))
            return
        try:
            main = save_payload.encode_main(self.raw_main, self.data)
            new_saveit = saveit_format.build_saveit_file(main)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("書き込みエラー", f"セーブデータの生成に失敗しました:\n{e}")
            return

        backup = None
        backup_error = None
        if path.exists():
            try:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%y%m%d-%H%M")
                variant_tag = "K-" if self.is_k else ""
                backup = BACKUP_DIR / f"{timestamp}-{variant_tag}{path.name}"
                backup.write_bytes(path.read_bytes())
            except Exception as e:  # noqa: BLE001
                backup_error = str(e)
                backup = None

        path.write_bytes(new_saveit)
        self.loaded_path = path
        self.refresh_json_from_data()
        msg = f"保存しました: {path}"
        if backup:
            msg += f"\n(元ファイルは {backup} にバックアップ済み)"
        elif backup_error:
            msg += f"\n⚠ バックアップの作成に失敗しました: {backup_error}"
        self._set_status(msg)
        messagebox.showinfo("保存完了", msg)

    def _set_status(self, text: str):
        self.status_var.set(text)


def main():
    root = tk.Tk()
    SaveEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
