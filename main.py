import base64
import hashlib
import hmac
import json
import random
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


MAX_LINES = 3
MAX_BET = 300
MAX_DEPOSIT = 3000
MIN_BET = 1
ROWS = 3
COLS = 3
SESSION_COOKIE = "slot_session"
SESSION_TTL_DAYS = 7
UPLOAD_SIZE_LIMIT = 2 * 1024 * 1024

SYMBOL_COUNT = {
    "A": 2,
    "B": 4,
    "C": 6,
    "D": 8,
}

SYMBOL_VALUE = {
    "A": 35,
    "B": 25,
    "C": 15,
    "D": 5,
}

DEFAULT_GRID = [["A"] * ROWS for _ in range(COLS)]
WEB_DIR = Path(__file__).parent / "web"
UPLOADS_DIR = WEB_DIR / "uploads"
DB_PATH = Path(__file__).parent / "slots.db"

BASE_SKINS = [
    {"id": "skyline", "name": "Skyline Glass", "elite": False},
    {"id": "mint_mesh", "name": "Mint Mesh", "elite": False},
    {"id": "sunrise", "name": "Sunrise Pop", "elite": False},
]
ELITE_SKINS = [
    {"id": "top10_prism", "name": "Top 10 Prism", "elite": True},
    {"id": "royal_circuit", "name": "Royal Circuit", "elite": True},
]

BASE_BANNERS = [
    {"id": "aurora", "name": "Aurora Flow", "elite": False},
    {"id": "mint_wave", "name": "Mint Wave", "elite": False},
    {"id": "peach_glow", "name": "Peach Glow", "elite": False},
]
ELITE_BANNERS = [
    {"id": "legend_ribbon", "name": "Legend Ribbon", "elite": True},
    {"id": "crown_beam", "name": "Crown Beam", "elite": True},
]

BASE_AVATARS = [
    {"id": "orbit", "name": "Orbit", "elite": False},
    {"id": "spark", "name": "Spark", "elite": False},
    {"id": "pulse", "name": "Pulse", "elite": False},
]
ELITE_AVATARS = [
    {"id": "trophy", "name": "Trophy Crest", "elite": True},
    {"id": "nova", "name": "Nova Sigil", "elite": True},
]

IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def utcnow():
    return datetime.now(timezone.utc)


def isoformat(dt):
    return dt.isoformat()


def parse_datetime(value):
    return datetime.fromisoformat(value)


def check_winnings(columns, lines, bet, values):
    winnings = 0
    winning_lines = []
    for line in range(lines):
        symbol = columns[0][line]
        for column in columns:
            if symbol != column[line]:
                break
        else:
            winnings += values[symbol] * bet
            winning_lines.append(line + 1)
    return winnings, winning_lines


def get_slot_machine_spin(rows, cols, symbols):
    all_symbols = []
    for symbol, count in symbols.items():
        for _ in range(count):
            all_symbols.append(symbol)

    columns = []
    for _ in range(cols):
        column = []
        current_symbols = all_symbols[:]
        for _ in range(rows):
            value = random.choice(current_symbols)
            current_symbols.remove(value)
            column.append(value)
        columns.append(column)
    return columns


def deposit_tier_for_amount(amount):
    if amount < 200:
        return "A"
    if amount <= 5000:
        return "B"
    return "C"


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, digest_hex):
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return hmac.compare_digest(actual, expected)


def initials_from_name(name):
    parts = [part for part in name.split() if part]
    if not parts:
        return "PS"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


class SlotStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = threading.RLock()
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0,
                    total_deposit INTEGER NOT NULL DEFAULT 0,
                    last_spin TEXT NOT NULL DEFAULT '[["A","A","A"],["A","A","A"],["A","A","A"]]',
                    last_win INTEGER NOT NULL DEFAULT 0,
                    last_net INTEGER NOT NULL DEFAULT 0,
                    winning_lines TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'Add funds to start spinning.',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS spin_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    win_amount INTEGER NOT NULL,
                    bet_amount INTEGER NOT NULL,
                    luck_multiplier REAL NOT NULL,
                    deposit_total INTEGER NOT NULL,
                    deposit_tier TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_spin_results_tier_multiplier
                    ON spin_results(deposit_tier, luck_multiplier DESC, win_amount DESC, id ASC);
                CREATE INDEX IF NOT EXISTS idx_spin_results_user_id ON spin_results(user_id);
                """
            )
        self._ensure_user_columns()

    def _ensure_user_columns(self):
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(users)").fetchall()
        }
        additions = {
            "display_name": "TEXT NOT NULL DEFAULT ''",
            "bio": "TEXT NOT NULL DEFAULT ''",
            "selected_skin": "TEXT NOT NULL DEFAULT 'skyline'",
            "selected_banner": "TEXT NOT NULL DEFAULT 'aurora'",
            "selected_avatar": "TEXT NOT NULL DEFAULT 'orbit'",
            "custom_avatar_path": "TEXT NOT NULL DEFAULT ''",
            "custom_banner_path": "TEXT NOT NULL DEFAULT ''",
        }
        with self.conn:
            for name, definition in additions.items():
                if name not in columns:
                    self.conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

    def _user_row(self, user_id):
        return self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def _spin_stats(self, user_id):
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total_spins,
                   SUM(CASE WHEN win_amount > 0 THEN 1 ELSE 0 END) AS winning_spins,
                   COALESCE(AVG(luck_multiplier), 0) AS average_multiplier,
                   COALESCE(MAX(luck_multiplier), 0) AS best_multiplier,
                   COALESCE(MAX(win_amount), 0) AS best_win,
                   COALESCE(SUM(win_amount), 0) AS total_winnings,
                   MIN(created_at) AS first_spin_at,
                   MAX(created_at) AS last_spin_at
            FROM spin_results
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        total_spins = row["total_spins"] or 0
        winning_spins = row["winning_spins"] or 0
        return {
            "totalSpins": total_spins,
            "winningSpins": winning_spins,
            "losingSpins": max(total_spins - winning_spins, 0),
            "hitRate": round((winning_spins / total_spins), 4) if total_spins else 0,
            "averageMultiplier": round(row["average_multiplier"] or 0, 4),
            "bestMultiplier": round(row["best_multiplier"] or 0, 4),
            "bestWin": row["best_win"] or 0,
            "totalWinnings": row["total_winnings"] or 0,
            "firstSpinAt": row["first_spin_at"],
            "lastSpinAt": row["last_spin_at"],
        }

    def _rank_map_top_spins(self):
        rows = self.conn.execute(
            """
            SELECT user_id,
                   MAX(luck_multiplier) AS best_multiplier,
                   MAX(win_amount) AS best_win
            FROM spin_results
            GROUP BY user_id
            ORDER BY best_multiplier DESC, best_win DESC, user_id ASC
            """
        ).fetchall()
        return {
            row["user_id"]: index
            for index, row in enumerate(rows, start=1)
        }

    def _rank_map_frequent_winners(self):
        rows = self.conn.execute(
            """
            SELECT user_id,
                   COUNT(CASE WHEN win_amount > 0 THEN 1 END) AS lucky_roll_count,
                   COUNT(*) AS total_spins,
                   ROUND(CAST(COUNT(CASE WHEN win_amount > 0 THEN 1 END) AS REAL) / COUNT(*), 4) AS hit_rate,
                   MAX(luck_multiplier) AS best_multiplier
            FROM spin_results
            GROUP BY user_id
            HAVING lucky_roll_count > 0
            ORDER BY lucky_roll_count DESC, hit_rate DESC, best_multiplier DESC, user_id ASC
            """
        ).fetchall()
        return {
            row["user_id"]: index
            for index, row in enumerate(rows, start=1)
        }

    def _rank_context(self, user_id):
        top_spin_ranks = self._rank_map_top_spins()
        frequent_ranks = self._rank_map_frequent_winners()
        return {
            "globalTopSpinRank": top_spin_ranks.get(user_id),
            "frequentWinnerRank": frequent_ranks.get(user_id),
            "isTopTen": (
                (top_spin_ranks.get(user_id) is not None and top_spin_ranks[user_id] <= 10)
                or (frequent_ranks.get(user_id) is not None and frequent_ranks[user_id] <= 10)
            ),
        }

    def _cosmetics(self, can_use_elite):
        return {
            "skins": BASE_SKINS + (ELITE_SKINS if can_use_elite else []),
            "banners": BASE_BANNERS + (ELITE_BANNERS if can_use_elite else []),
            "avatars": BASE_AVATARS + (ELITE_AVATARS if can_use_elite else []),
        }

    def _valid_cosmetic_ids(self, can_use_elite):
        cosmetics = self._cosmetics(can_use_elite)
        return {
            "skins": {item["id"] for item in cosmetics["skins"]},
            "banners": {item["id"] for item in cosmetics["banners"]},
            "avatars": {item["id"] for item in cosmetics["avatars"]},
        }

    def _badges(self, row, stats, ranks):
        created_at = parse_datetime(row["created_at"])
        account_days = max((utcnow() - created_at).days, 0)
        badges = []

        if stats["totalSpins"] >= 1:
            badges.append(
                {
                    "id": "rookie_spinner",
                    "name": "Rookie Spinner",
                    "description": "Started building a real spin history.",
                    "tone": "blue",
                }
            )
        if stats["bestMultiplier"] >= 3:
            badges.append(
                {
                    "id": "jackpot_flash",
                    "name": "Jackpot Flash",
                    "description": "Hit a 3x or better payout on a single spin.",
                    "tone": "gold",
                }
            )
        if stats["hitRate"] >= 0.4 and stats["totalSpins"] >= 10:
            badges.append(
                {
                    "id": "lucky_current",
                    "name": "Lucky Current",
                    "description": "Wins on at least 40% of recorded spins.",
                    "tone": "green",
                }
            )
        if stats["hitRate"] <= 0.15 and stats["totalSpins"] >= 10:
            badges.append(
                {
                    "id": "storm_survivor",
                    "name": "Storm Survivor",
                    "description": "Kept playing through a rough cold streak.",
                    "tone": "rose",
                }
            )
        if account_days >= 7 or stats["totalSpins"] >= 25:
            badges.append(
                {
                    "id": "marathon_player",
                    "name": "Marathon Player",
                    "description": "Spent serious time climbing the reels.",
                    "tone": "indigo",
                }
            )
        if row["total_deposit"] >= 2000:
            badges.append(
                {
                    "id": "high_roller",
                    "name": "High Roller",
                    "description": "Crossed R2000 in total deposits.",
                    "tone": "orange",
                }
            )
        if ranks["globalTopSpinRank"] and ranks["globalTopSpinRank"] <= 10:
            badges.append(
                {
                    "id": "top_ten_legend",
                    "name": "Top 10 Spin Legend",
                    "description": "Owns one of the 10 strongest spin profiles on the site.",
                    "tone": "gold",
                }
            )
        if ranks["frequentWinnerRank"] and ranks["frequentWinnerRank"] <= 10:
            badges.append(
                {
                    "id": "consistency_icon",
                    "name": "Consistency Icon",
                    "description": "Ranks inside the top 10 for repeated lucky rolls.",
                    "tone": "violet",
                }
            )
        return badges

    def _save_data_url_image(self, user_id, prefix, data_url):
        if not data_url:
            return ""
        if not data_url.startswith("data:") or ";base64," not in data_url:
            raise ValueError("Uploaded images must be valid PNG, JPEG, or WEBP files.")
        header, encoded = data_url.split(",", 1)
        mime_type = header[5:].split(";")[0]
        extension = IMAGE_EXTENSIONS.get(mime_type)
        if not extension:
            raise ValueError("Only PNG, JPEG, or WEBP images are supported.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Could not decode the uploaded image.") from exc
        if len(raw) > UPLOAD_SIZE_LIMIT:
            raise ValueError("Uploaded images must be smaller than 2MB.")
        filename = f"{prefix}_{user_id}_{secrets.token_hex(8)}.{extension}"
        path = UPLOADS_DIR / filename
        path.write_bytes(raw)
        return f"/uploads/{filename}"

    def _profile_payload(self, row):
        user_id = row["id"]
        stats = self._spin_stats(user_id)
        ranks = self._rank_context(user_id)
        cosmetics = self._cosmetics(ranks["isTopTen"])
        account_days = max((utcnow() - parse_datetime(row["created_at"])).days, 0)
        play_span_days = 0
        if stats["firstSpinAt"] and stats["lastSpinAt"]:
            play_span_days = max(
                (parse_datetime(stats["lastSpinAt"]) - parse_datetime(stats["firstSpinAt"])).days,
                0,
            )

        display_name = row["display_name"] or row["username"]
        return {
            "profile": {
                "username": row["username"],
                "displayName": display_name,
                "bio": row["bio"],
                "selectedSkin": row["selected_skin"],
                "selectedBanner": row["selected_banner"],
                "selectedAvatar": row["selected_avatar"],
                "avatarPath": row["custom_avatar_path"],
                "bannerPath": row["custom_banner_path"],
                "initials": initials_from_name(display_name),
            },
            "stats": {
                **stats,
                "accountDays": account_days,
                "playSpanDays": play_span_days,
                "depositTier": deposit_tier_for_amount(row["total_deposit"]),
                "totalDeposit": row["total_deposit"],
            },
            "ranks": ranks,
            "badges": self._badges(row, stats, ranks),
            "cosmetics": cosmetics,
        }

    def _user_snapshot(self, row):
        with self.lock:
            profile_meta = self._profile_payload(row)
            return {
                "authenticated": True,
                "user": {
                    "id": row["id"],
                    "username": row["username"],
                    "displayName": profile_meta["profile"]["displayName"],
                    "totalDeposit": row["total_deposit"],
                    "depositTier": deposit_tier_for_amount(row["total_deposit"]),
                    "avatarPath": row["custom_avatar_path"],
                    "bannerPath": row["custom_banner_path"],
                    "selectedSkin": row["selected_skin"],
                    "selectedAvatar": row["selected_avatar"],
                    "isTopTen": profile_meta["ranks"]["isTopTen"],
                },
                "balance": row["balance"],
                "lastSpin": json.loads(row["last_spin"]),
                "lastWin": row["last_win"],
                "lastNet": row["last_net"],
                "winningLines": json.loads(row["winning_lines"]),
                "status": row["status"],
                "limits": {
                    "minBet": MIN_BET,
                    "maxBet": MAX_BET,
                    "maxLines": MAX_LINES,
                    "maxDeposit": MAX_DEPOSIT,
                },
            }

    def guest_snapshot(self):
        return {
            "authenticated": False,
            "user": None,
            "balance": 0,
            "lastSpin": DEFAULT_GRID,
            "lastWin": 0,
            "lastNet": 0,
            "winningLines": [],
            "status": "Sign in to spin and record leaderboard results.",
            "limits": {
                "minBet": MIN_BET,
                "maxBet": MAX_BET,
                "maxLines": MAX_LINES,
                "maxDeposit": MAX_DEPOSIT,
            },
        }

    def register_user(self, username, password):
        username = username.strip()
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")

        salt_hex, digest_hex = hash_password(password)
        created_at = isoformat(utcnow())
        with self.lock, self.conn:
            try:
                self.conn.execute(
                    """
                    INSERT INTO users (
                        username, password_salt, password_hash, created_at, display_name
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (username, salt_hex, digest_hex, created_at, username),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("That username is already taken.") from exc

        return self.authenticate_user(username, password)

    def authenticate_user(self, username, password):
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()

        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            raise ValueError("Invalid username or password.")

        token = secrets.token_urlsafe(32)
        created_at = utcnow()
        expires_at = created_at + timedelta(days=SESSION_TTL_DAYS)
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, row["id"], isoformat(created_at), isoformat(expires_at)),
            )

        return token, self._user_snapshot(row)

    def get_user_by_session(self, token):
        if not token:
            return None

        with self.lock:
            row = self.conn.execute(
                """
                SELECT users.*, sessions.expires_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

        if not row:
            return None

        if parse_datetime(row["expires_at"]) <= utcnow():
            self.delete_session(token)
            return None

        return self._user_snapshot(row)

    def delete_session(self, token):
        if not token:
            return
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def add_funds(self, user_id, amount):
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero.")
        if amount > MAX_DEPOSIT:
            raise ValueError(f"Deposit amount cannot be more than R{MAX_DEPOSIT}.")

        with self.lock, self.conn:
            self.conn.execute(
                """
                UPDATE users
                SET balance = balance + ?,
                    total_deposit = total_deposit + ?,
                    status = ?
                WHERE id = ?
                """,
                (amount, amount, f"Added R{amount}. Your balance is ready for the next spin.", user_id),
            )
            row = self._user_row(user_id)
        return self._user_snapshot(row)

    def spin(self, user_id, bet_per_line):
        lines = MAX_LINES
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User account was not found.")

            balance = row["balance"]
            max_bet_for_round = min(MAX_BET, balance // lines) if balance > 0 else 0
            if max_bet_for_round < MIN_BET:
                raise ValueError(f"You need at least R{MIN_BET * lines} to play all {lines} lines.")
            if not MIN_BET <= bet_per_line <= max_bet_for_round:
                raise ValueError(
                    f"Bet amount must be between R{MIN_BET} and R{max_bet_for_round} for {lines} lines."
                )

            total_bet = lines * bet_per_line
            columns = get_slot_machine_spin(ROWS, COLS, SYMBOL_COUNT)
            winnings, winning_lines = check_winnings(columns, lines, bet_per_line, SYMBOL_VALUE)
            net = winnings - total_bet
            new_balance = balance + net
            total_deposit = row["total_deposit"]
            tier = deposit_tier_for_amount(total_deposit)
            multiplier = round((winnings / total_bet) if total_bet else 0, 4)

            status = (
                f"You won R{winnings}. Net change: R{net}."
                if winnings
                else f"No line match this round. Net change: R{net}."
            )

            self.conn.execute(
                """
                UPDATE users
                SET balance = ?,
                    last_spin = ?,
                    last_win = ?,
                    last_net = ?,
                    winning_lines = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    new_balance,
                    json.dumps(columns),
                    winnings,
                    net,
                    json.dumps(winning_lines),
                    status,
                    user_id,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO spin_results (
                    user_id, win_amount, bet_amount, luck_multiplier, deposit_total, deposit_tier, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    winnings,
                    total_bet,
                    multiplier,
                    total_deposit,
                    tier,
                    isoformat(utcnow()),
                ),
            )
            updated = self._user_row(user_id)

        snapshot = self._user_snapshot(updated)
        snapshot["bet"] = {
            "lines": lines,
            "betPerLine": bet_per_line,
            "total": total_bet,
        }
        return snapshot

    def leaderboard(self, tier):
        if tier not in {"A", "B", "C"}:
            raise ValueError("Tier must be A, B, or C.")

        with self.lock:
            top_spin_rows = self.conn.execute(
                """
                SELECT spin_results.id,
                       users.username,
                       COALESCE(NULLIF(users.display_name, ''), users.username) AS display_name,
                       spin_results.win_amount,
                       spin_results.bet_amount,
                       spin_results.luck_multiplier,
                       spin_results.deposit_tier,
                       spin_results.deposit_total,
                       spin_results.created_at
                FROM spin_results
                JOIN users ON users.id = spin_results.user_id
                WHERE spin_results.deposit_tier = ?
                ORDER BY spin_results.luck_multiplier DESC,
                         spin_results.win_amount DESC,
                         spin_results.id ASC
                LIMIT 100
                """,
                (tier,),
            ).fetchall()
            frequent_winner_rows = self.conn.execute(
                """
                SELECT users.username,
                       COALESCE(NULLIF(users.display_name, ''), users.username) AS display_name,
                       COUNT(CASE WHEN spin_results.win_amount > 0 THEN 1 END) AS lucky_roll_count,
                       COUNT(*) AS total_spins,
                       ROUND(
                           CAST(COUNT(CASE WHEN spin_results.win_amount > 0 THEN 1 END) AS REAL) / COUNT(*),
                           4
                       ) AS hit_rate,
                       MAX(spin_results.luck_multiplier) AS best_multiplier,
                       MAX(spin_results.win_amount) AS best_win
                FROM spin_results
                JOIN users ON users.id = spin_results.user_id
                WHERE spin_results.deposit_tier = ?
                GROUP BY spin_results.user_id, users.username, users.display_name
                HAVING lucky_roll_count > 0
                ORDER BY lucky_roll_count DESC,
                         hit_rate DESC,
                         best_multiplier DESC,
                         users.username ASC
                LIMIT 100
                """,
                (tier,),
            ).fetchall()

        return {
            "topSpins": [
                {
                    "rank": index,
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "winAmount": row["win_amount"],
                    "betAmount": row["bet_amount"],
                    "luckMultiplier": row["luck_multiplier"],
                    "depositTier": row["deposit_tier"],
                    "depositTotal": row["deposit_total"],
                    "createdAt": row["created_at"],
                }
                for index, row in enumerate(top_spin_rows, start=1)
            ],
            "frequentWinners": [
                {
                    "rank": index,
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "luckyRollCount": row["lucky_roll_count"],
                    "totalSpins": row["total_spins"],
                    "hitRate": row["hit_rate"],
                    "bestMultiplier": row["best_multiplier"],
                    "bestWin": row["best_win"],
                }
                for index, row in enumerate(frequent_winner_rows, start=1)
            ],
        }

    def profile(self, user_id):
        with self.lock:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User account was not found.")
            profile = self._profile_payload(row)
        return profile

    def update_profile(self, user_id, payload):
        display_name = str(payload.get("displayName", "")).strip()
        bio = str(payload.get("bio", "")).strip()
        selected_skin = str(payload.get("selectedSkin", "")).strip()
        selected_banner = str(payload.get("selectedBanner", "")).strip()
        selected_avatar = str(payload.get("selectedAvatar", "")).strip()
        avatar_upload = str(payload.get("avatarUpload", "")).strip()
        banner_upload = str(payload.get("bannerUpload", "")).strip()
        clear_avatar = bool(payload.get("clearAvatar", False))
        clear_banner = bool(payload.get("clearBanner", False))

        if not display_name:
            raise ValueError("Display name cannot be empty.")
        if len(display_name) > 32:
            raise ValueError("Display name must be 32 characters or fewer.")
        if len(bio) > 240:
            raise ValueError("Bio must be 240 characters or fewer.")

        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User account was not found.")
            ranks = self._rank_context(user_id)
            valid = self._valid_cosmetic_ids(ranks["isTopTen"])

            if selected_skin and selected_skin not in valid["skins"]:
                raise ValueError("That skin is not unlocked for this profile.")
            if selected_banner and selected_banner not in valid["banners"]:
                raise ValueError("That banner is not unlocked for this profile.")
            if selected_avatar and selected_avatar not in valid["avatars"]:
                raise ValueError("That avatar is not unlocked for this profile.")

            avatar_path = row["custom_avatar_path"]
            banner_path = row["custom_banner_path"]

            if clear_avatar:
                avatar_path = ""
            elif avatar_upload:
                avatar_path = self._save_data_url_image(user_id, "avatar", avatar_upload)

            if clear_banner:
                banner_path = ""
            elif banner_upload:
                banner_path = self._save_data_url_image(user_id, "banner", banner_upload)

            self.conn.execute(
                """
                UPDATE users
                SET display_name = ?,
                    bio = ?,
                    selected_skin = ?,
                    selected_banner = ?,
                    selected_avatar = ?,
                    custom_avatar_path = ?,
                    custom_banner_path = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    display_name,
                    bio,
                    selected_skin or row["selected_skin"],
                    selected_banner or row["selected_banner"],
                    selected_avatar or row["selected_avatar"],
                    avatar_path,
                    banner_path,
                    "Profile updated.",
                    user_id,
                ),
            )
            updated = self._user_row(user_id)

        return {
            "snapshot": self._user_snapshot(updated),
            **self._profile_payload(updated),
        }


STORE = SlotStore(DB_PATH)


class SlotMachineHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(self._current_snapshot())
            return
        if parsed.path == "/api/leaderboard":
            query = parse_qs(parsed.query)
            tier = query.get("tier", ["A"])[0].upper()
            try:
                results = STORE.leaderboard(tier)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"tier": tier, **results})
            return
        if parsed.path == "/api/profile":
            snapshot = self._require_user()
            if not snapshot:
                return
            self._send_json(STORE.profile(snapshot["user"]["id"]))
            return
        if parsed.path == "/":
            self.path = "/index.html"
        elif parsed.path == "/leaderboard":
            self.path = "/leaderboard.html"
        elif parsed.path == "/profile":
            self.path = "/profile.html"
        elif parsed.path == "/creator":
            self.path = "/creator.html"
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        routes = {
            "/api/register": self._handle_register,
            "/api/login": self._handle_login,
            "/api/logout": self._handle_logout,
            "/api/deposit": self._handle_deposit,
            "/api/spin": self._handle_spin,
            "/api/profile": self._handle_profile_update,
        }
        handler = routes.get(parsed.path)
        if not handler:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")
            return

        try:
            payload = self._read_json()
            handler(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self._send_json({"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        return json.loads(body.decode("utf-8"))

    def _parse_cookies(self):
        raw_cookie = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        if raw_cookie:
            cookie.load(raw_cookie)
        return cookie

    def _session_token(self):
        cookie = self._parse_cookies()
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _current_snapshot(self):
        token = self._session_token()
        snapshot = STORE.get_user_by_session(token)
        return snapshot or STORE.guest_snapshot()

    def _require_user(self):
        token = self._session_token()
        snapshot = STORE.get_user_by_session(token)
        if not snapshot:
            self._send_json(
                {"error": "You need to sign in before using this feature."},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return None
        return snapshot

    def _send_json(self, payload, status=HTTPStatus.OK, cookies=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookies:
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie.OutputString())
        self.end_headers()
        self.wfile.write(body)

    def _session_cookie(self, token):
        expires_at = utcnow() + timedelta(days=SESSION_TTL_DAYS)
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        cookie[SESSION_COOKIE]["expires"] = expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
        return cookie[SESSION_COOKIE]

    def _expired_cookie(self):
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        cookie[SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        return cookie[SESSION_COOKIE]

    def _handle_register(self, payload):
        token, snapshot = STORE.register_user(
            username=str(payload.get("username", "")),
            password=str(payload.get("password", "")),
        )
        self._send_json(snapshot, status=HTTPStatus.CREATED, cookies=[self._session_cookie(token)])

    def _handle_login(self, payload):
        token, snapshot = STORE.authenticate_user(
            username=str(payload.get("username", "")),
            password=str(payload.get("password", "")),
        )
        self._send_json(snapshot, cookies=[self._session_cookie(token)])

    def _handle_logout(self, _payload):
        STORE.delete_session(self._session_token())
        self._send_json(
            {"ok": True, "message": "Signed out."},
            cookies=[self._expired_cookie()],
        )

    def _handle_deposit(self, payload):
        snapshot = self._require_user()
        if not snapshot:
            return
        state = STORE.add_funds(
            user_id=snapshot["user"]["id"],
            amount=int(payload.get("amount", 0)),
        )
        self._send_json(state)

    def _handle_spin(self, payload):
        snapshot = self._require_user()
        if not snapshot:
            return
        state = STORE.spin(
            user_id=snapshot["user"]["id"],
            bet_per_line=int(payload.get("bet", 0)),
        )
        self._send_json(state)

    def _handle_profile_update(self, payload):
        snapshot = self._require_user()
        if not snapshot:
            return
        profile = STORE.update_profile(snapshot["user"]["id"], payload)
        self._send_json(profile)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), SlotMachineHandler)
    print("Serving Pixel Slot Studio at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
