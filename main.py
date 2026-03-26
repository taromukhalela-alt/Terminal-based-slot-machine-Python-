import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session

from database import create_database


ROWS = 3
COLS = 3
LINES = 3
MIN_BET = 1
UPLOAD_SIZE_LIMIT = 2 * 1024 * 1024
FLASK_SECRET = os.environ.get("SESSION_SECRET", "pixel-slot-studio-dev-secret")
PP_RATE = 10  # R10 = 1 Prestige Point

MODE_CONFIG = {
    "easy": {
        "label": "Easy",
        "starting_limit": 100000.0,
        "a_denominator": 1000.0,
        "cap": 100000.0,
    },
    "medium": {
        "label": "Medium",
        "starting_limit": 1000.0,
        "a_denominator": 200.0,
        "cap": 50000.0,
    },
    "hard": {
        "label": "Hard",
        "starting_limit": 200.0,
        "a_denominator": 10.0,
        "cap": 200.0,
    },
}

# Store Items: Boosters and Cosmetic Themes
STORE_ITEMS = {
    "boosters": [
        {
            "id": "shield_basic",
            "name": "Basic Shield",
            "description": "Protects 10% of max_deposit_limit from Easy mode loss penalties",
            "pp_cost": 50,
            "sacrifice": 0,
            "effect": {"type": "loss_protection", "value": 0.10},
            "stackable": True,
        },
        {
            "id": "shield_advanced",
            "name": "Advanced Shield",
            "description": "Protects 25% of max_deposit_limit from Easy mode loss penalties",
            "pp_cost": 150,
            "sacrifice": 1000,
            "effect": {"type": "loss_protection", "value": 0.25},
            "stackable": True,
        },
        {
            "id": "magnet_small",
            "name": "Small Magnet",
            "description": "Increases A-value probability by 2% for 50 spins",
            "pp_cost": 75,
            "sacrifice": 500,
            "effect": {"type": "odds_boost", "value": 0.02, "duration": 50},
            "stackable": True,
        },
        {
            "id": "magnet_large",
            "name": "Large Magnet",
            "description": "Increases A-value probability by 5% for 100 spins",
            "pp_cost": 200,
            "sacrifice": 2000,
            "effect": {"type": "odds_boost", "value": 0.05, "duration": 100},
            "stackable": True,
        },
        {
            "id": "streak_preserver",
            "name": "Streak Preserver",
            "description": "Protects win streak from single losses (3 uses)",
            "pp_cost": 100,
            "sacrifice": 1500,
            "effect": {"type": "streak_protect", "value": 3},
            "stackable": True,
        },
    ],
    "cosmetic_themes": [
        {"id": "cyber_neon", "name": "Cyber Neon", "pp_cost": 300, "sacrifice": 5000, "rarity": "legendary"},
        {"id": "crystal_ice", "name": "Crystal Ice", "pp_cost": 250, "sacrifice": 3000, "rarity": "epic"},
        {"id": "phoenix_fire", "name": "Phoenix Fire", "pp_cost": 350, "sacrifice": 7000, "rarity": "legendary"},
        {"id": "void_shadow", "name": "Void Shadow", "pp_cost": 400, "sacrifice": 10000, "rarity": "mythic"},
        {"id": "galaxy_dust", "name": "Galaxy Dust", "pp_cost": 200, "sacrifice": 2000, "rarity": "rare"},
        {"id": "golden_age", "name": "Golden Age", "pp_cost": 500, "sacrifice": 15000, "rarity": "mythic"},
    ],
}

# 200+ Achievement Definitions
ACHIEVEMENTS = {
    # Milestone Wins (1-1000)
    **{f"wins_{n}": {"name": f"{n}-Win Club", "description": f"Won {n} spins", "category": "milestone", "requirement": {"type": "wins", "value": n}, "rarity": "bronze" if n <= 10 else "silver" if n <= 50 else "gold" if n <= 100 else "platinum" if n <= 500 else "diamond", "shape": "hexagon" if n % 3 == 0 else "shield" if n % 3 == 1 else "star"} for n in [1, 5, 10, 25, 50, 100, 200, 500, 1000]},
    # Game Play Milestones
    **{f"games_{n}": {"name": f"{n}-Game Veteran", "description": f"Played {n} games", "category": "milestone", "requirement": {"type": "games", "value": n}, "rarity": "bronze" if n <= 50 else "silver" if n <= 200 else "gold", "shape": "circle" if n % 2 == 0 else "diamond"} for n in [10, 25, 50, 100, 250, 500, 1000]},
    # Difficulty-Specific Achievements
    "hard_survivor": {"name": "Hard Mode Survivor", "description": "Completed 50 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 50}, "rarity": "gold", "shape": "hexagon"},
    "hard_elite": {"name": "Hard Mode Elite", "description": "Completed 200 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 200}, "rarity": "platinum", "shape": "star"},
    "hard_legend": {"name": "Hard Mode Legend", "description": "Completed 500 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 500}, "rarity": "diamond", "shape": "crown"},
    "medium_master": {"name": "Medium Mode Master", "description": "Reached R25,000 cap in Medium mode", "category": "difficulty", "requirement": {"type": "medium_cap", "value": 25000}, "rarity": "gold", "shape": "shield"},
    "easy_tycoon": {"name": "Easy Street Tycoon", "description": "Reached R50,000 cap in Easy mode", "category": "difficulty", "requirement": {"type": "easy_cap", "value": 50000}, "rarity": "platinum", "shape": "star"},
    # Wealth Achievements (Total Deposit)
    **{f"wealth_{n}": {"name": f"R{n:,} Club", "description": f"Accumulated R{n:,} in total deposits", "category": "wealth", "requirement": {"type": "total_deposit", "value": n}, "rarity": "bronze" if n <= 1000 else "silver" if n <= 10000 else "gold" if n <= 50000 else "platinum", "shape": "hexagon"} for n in [500, 1000, 5000, 10000, 25000, 50000, 75000, 100000]},
    # A-Value Streak Achievements
    "first_a": {"name": "First A-Value", "description": "Hit your first A-value symbol", "category": "rarity", "requirement": {"type": "a_hits", "value": 1}, "rarity": "bronze", "shape": "hexagon"},
    "a_triple": {"name": "Triple A-Value", "description": "Hit 3 consecutive A-values in a single spin", "category": "rarity", "requirement": {"type": "a_streak_single", "value": 3}, "rarity": "gold", "shape": "star"},
    **{f"a_hits_{n}": {"name": f"{n}x A-Hitter", "description": f"Hit A-value symbols {n} times", "category": "rarity", "requirement": {"type": "a_hits", "value": n}, "rarity": "silver" if n <= 10 else "gold" if n <= 50 else "platinum", "shape": "hexagon"} for n in [5, 10, 25, 50, 100]},
    **{f"a_streak_{n}": {"name": f"{n}-Spin A-Streak", "description": f"Hit A-values for {n} consecutive spins", "category": "rarity", "requirement": {"type": "a_streak", "value": n}, "rarity": "platinum" if n >= 5 else "diamond", "shape": "star"} for n in [3, 5, 10]},
    # Win Streak Achievements
    **{f"streak_{n}": {"name": f"{n}-Win Streak", "description": f"Won {n} spins in a row", "category": "milestone", "requirement": {"type": "win_streak", "value": n}, "rarity": "bronze" if n <= 5 else "silver" if n <= 10 else "gold", "shape": "shield"} for n in [3, 5, 10, 25, 50]},
    # Hit Rate Achievements
    "lucky_30": {"name": "Lucky 30%", "description": "Achieved a 30% hit rate over 50 games", "category": "rarity", "requirement": {"type": "hit_rate", "value": 0.30, "games": 50}, "rarity": "silver", "shape": "circle"},
    "lucky_50": {"name": "Lucky 50%", "description": "Achieved a 50% hit rate over 100 games", "category": "rarity", "requirement": {"type": "hit_rate", "value": 0.50, "games": 100}, "rarity": "gold", "shape": "star"},
    "lucky_70": {"name": "Lucky 70%", "description": "Achieved a 70% hit rate over 200 games", "category": "rarity", "requirement": {"type": "hit_rate", "value": 0.70, "games": 200}, "rarity": "platinum", "shape": "crown"},
    # Balance Achievements
    **{f"balance_{n}": {"name": f"Balance R{n:,}", "description": f"Had R{n:,} in balance at once", "category": "wealth", "requirement": {"type": "max_balance", "value": n}, "rarity": "silver" if n <= 5000 else "gold" if n <= 25000 else "platinum", "shape": "hexagon"} for n in [1000, 5000, 10000, 25000, 50000]},
    # Leaderboard Achievements
    "top_25": {"name": "Top 25", "description": "Reached rank 25 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 25}, "rarity": "silver", "shape": "shield"},
    "top_10": {"name": "Top 10 Elite", "description": "Reached rank 10 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 10}, "rarity": "gold", "shape": "star"},
    "top_5": {"name": "Top 5 Master", "description": "Reached rank 5 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 5}, "rarity": "platinum", "shape": "crown"},
    "global_1": {"name": "Global Champion", "description": "Reached rank 1 on the Global leaderboard", "category": "difficulty", "requirement": {"type": "global_rank", "value": 1}, "rarity": "diamond", "shape": "crown", "animation": "rainbow"},
    # Deposit Achievements
    **{f"deposits_{n}": {"name": f"{n} Deposits", "description": f"Made {n} deposit transactions", "category": "milestone", "requirement": {"type": "deposits", "value": n}, "rarity": "bronze", "shape": "circle"} for n in [5, 10, 25, 50, 100]},
    # Double A-Value Hit (rare event)
    "double_a_hit": {"name": "Double A-Value Hit", "description": "Got A-values on two lines in one spin", "category": "rarity", "requirement": {"type": "double_a_line", "value": 1}, "rarity": "platinum", "shape": "star", "animation": "pulse"},
    # Deposit Tier Achievements
    **{f"deposit_tier_{tier}": {"name": f"{tier.title()} Tier Depositor", "description": f"Deposited in the {tier} deposit tier", "category": "wealth", "requirement": {"type": "deposit_tier", "value": tier}, "rarity": "silver", "shape": "hexagon"} for tier in ["bronze", "silver", "gold", "platinum", "diamond", "radiant"]},
    # Consecutive Loss Recovery
    "comeback_kid": {"name": "Comeback Kid", "description": "Recovered from 0 balance to R1,000+", "category": "milestone", "requirement": {"type": "comeback", "value": 1000}, "rarity": "gold", "shape": "shield"},
    # PP Earned Achievements
    **{f"pp_earned_{n}": {"name": f"{n} PP Earned", "description": f"Earned {n} total Prestige Points", "category": "wealth", "requirement": {"type": "pp_earned", "value": n}, "rarity": "bronze" if n <= 100 else "silver" if n <= 500 else "gold" if n <= 2000 else "platinum", "shape": "hexagon"} for n in [50, 100, 250, 500, 1000, 2500, 5000]},
    # Store Purchases
    **{f"store_purchases_{n}": {"name": f"Shopper Lv.{n}", "description": f"Made {n} store purchases", "category": "milestone", "requirement": {"type": "store_purchases", "value": n}, "rarity": "bronze" if n <= 3 else "silver", "shape": "circle"} for n in [1, 3, 5, 10, 25]},
    # Streak Multiplier Achievements (Medium mode)
    "medium_10x": {"name": "10x Medium Streak", "description": "Achieved a 10x win streak multiplier in Medium mode", "category": "difficulty", "requirement": {"type": "medium_streak_mult", "value": 10}, "rarity": "gold", "shape": "star"},
    # Pity Breaker
    "pity_breaker": {"name": "Pity Breaker", "description": "Hit an A-value after the pity threshold in Medium mode", "category": "difficulty", "requirement": {"type": "pity_break"}, "rarity": "silver", "shape": "hexagon"},
    # First Time Achievements
    "first_spin": {"name": "First Spin", "description": "Completed your first spin", "category": "milestone", "requirement": {"type": "games", "value": 1}, "rarity": "bronze", "shape": "circle"},
    "first_win": {"name": "First Win", "description": "Won your first spin", "category": "milestone", "requirement": {"type": "wins", "value": 1}, "rarity": "bronze", "shape": "circle"},
    "first_deposit": {"name": "First Deposit", "description": "Made your first deposit", "category": "milestone", "requirement": {"type": "deposits", "value": 1}, "rarity": "bronze", "shape": "circle"},
    "first_rank": {"name": "Ranked Player", "description": "Entered any leaderboard for the first time", "category": "milestone", "requirement": {"type": "leaderboard_enter"}, "rarity": "bronze", "shape": "shield"},
    # Long Haul (time-based)
    "week_warrior": {"name": "Week Warrior", "description": "Kept account active for 7 days", "category": "milestone", "requirement": {"type": "account_days", "value": 7}, "rarity": "silver", "shape": "circle"},
    "monthly_master": {"name": "Monthly Master", "description": "Kept account active for 30 days", "category": "milestone", "requirement": {"type": "account_days", "value": 30}, "rarity": "gold", "shape": "star"},
    # Efficiency Achievements
    "big_win_small_bet": {"name": "Big Win, Small Bet", "description": "Won 100x your bet in a single spin", "category": "rarity", "requirement": {"type": "win_to_bet_ratio", "value": 100}, "rarity": "platinum", "shape": "star", "animation": "neon"},
    # Bankruptcy Survivor (Hard mode)
    "bankruptcy_survivor": {"name": "Bankruptcy Survivor", "description": "Recovered from bankruptcy in Hard mode", "category": "difficulty", "requirement": {"type": "bankruptcy_recovery"}, "rarity": "gold", "shape": "shield"},
}

SYMBOL_VALUE = {
    "A": 35,
    "B": 25,
    "C": 15,
    "D": 5,
}

NON_A_WEIGHTS = [("B", 4), ("C", 6), ("D", 8)]

DEFAULT_GRID = [["A"] * ROWS for _ in range(COLS)]
WEB_DIR = Path(__file__).parent / "web"
UPLOADS_DIR = WEB_DIR / "uploads"

DEFAULT_COSMETICS = {
    "skin": "skyline",
    "banner": "aurora",
    "avatar": "orbit",
}

BASE_SKINS = [
    {"id": "skyline", "name": "Skyline Glass", "elite": False, "requirement": {"type": "always", "label": "Starter palette"}},
    {"id": "mint_mesh", "name": "Mint Mesh", "elite": False, "requirement": {"type": "always", "label": "Starter palette"}},
    {"id": "sunrise", "name": "Sunrise Pop", "elite": False, "requirement": {"type": "always", "label": "Starter palette"}},
    {"id": "ocean_ink", "name": "Ocean Ink", "elite": False, "requirement": {"type": "games", "value": 5, "label": "Play 5 games"}},
    {"id": "ember_frost", "name": "Ember Frost", "elite": False, "requirement": {"type": "wins", "value": 5, "label": "Win 5 spins"}},
    {
        "id": "mono_drift",
        "name": "Mono Drift",
        "elite": False,
        "requirement": {"type": "hit_rate", "value": 0.30, "games": 10, "label": "Reach a 30% hit rate after 10 games"},
    },
]
ELITE_SKINS = [
    {"id": "top10_prism", "name": "Top 10 Prism", "elite": True, "requirement": {"type": "top_ten_global", "label": "Reach Global Top 10"}},
    {"id": "royal_circuit", "name": "Royal Circuit", "elite": True, "requirement": {"type": "top_ten_mode", "label": "Reach Class Top 10"}},
]
BASE_BANNERS = [
    {"id": "aurora", "name": "Aurora Flow", "elite": False, "requirement": {"type": "always", "label": "Starter banner"}},
    {"id": "mint_wave", "name": "Mint Wave", "elite": False, "requirement": {"type": "always", "label": "Starter banner"}},
    {"id": "peach_glow", "name": "Peach Glow", "elite": False, "requirement": {"type": "always", "label": "Starter banner"}},
    {"id": "ocean_signal", "name": "Ocean Signal", "elite": False, "requirement": {"type": "games", "value": 8, "label": "Play 8 games"}},
    {"id": "citrus_haze", "name": "Citrus Haze", "elite": False, "requirement": {"type": "wins", "value": 8, "label": "Win 8 spins"}},
    {
        "id": "night_shift",
        "name": "Night Shift",
        "elite": False,
        "requirement": {"type": "difficulty", "value": "hard", "label": "Play Hard mode"},
    },
]
ELITE_BANNERS = [
    {"id": "legend_ribbon", "name": "Legend Ribbon", "elite": True, "requirement": {"type": "top_ten_global", "label": "Reach Global Top 10"}},
    {"id": "crown_beam", "name": "Crown Beam", "elite": True, "requirement": {"type": "top_ten_mode", "label": "Reach Class Top 10"}},
    {"id": "streak_lattice", "name": "Streak Lattice", "elite": True, "requirement": {"type": "a_streak", "label": "Trigger the A-Streak banner event"}},
]
BASE_AVATARS = [
    {"id": "orbit", "name": "Orbit", "elite": False, "requirement": {"type": "always", "label": "Starter avatar"}},
    {"id": "spark", "name": "Spark", "elite": False, "requirement": {"type": "always", "label": "Starter avatar"}},
    {"id": "pulse", "name": "Pulse", "elite": False, "requirement": {"type": "always", "label": "Starter avatar"}},
    {"id": "glint", "name": "Glint", "elite": False, "requirement": {"type": "games", "value": 6, "label": "Play 6 games"}},
    {"id": "flare", "name": "Flare", "elite": False, "requirement": {"type": "wins", "value": 6, "label": "Win 6 spins"}},
]
ELITE_AVATARS = [
    {"id": "trophy", "name": "Trophy Crest", "elite": True, "requirement": {"type": "top_ten_global", "label": "Reach Global Top 10"}},
    {"id": "nova", "name": "Nova Sigil", "elite": True, "requirement": {"type": "a_streak", "label": "Trigger the A-Streak banner event"}},
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


def score_from_values(total_deposit, total_wins, total_games):
    ratio = (total_wins / total_games) if total_games else 0
    return round(total_deposit + ratio, 4)


def check_winnings(columns, bet_per_line):
    winnings = 0
    winning_lines = []
    for row in range(ROWS):
        symbols = [columns[column][row] for column in range(COLS)]
        if symbols.count(symbols[0]) == COLS:
            winnings += SYMBOL_VALUE[symbols[0]] * bet_per_line
            winning_lines.append(row + 1)
    return winnings, winning_lines


def check_consecutive_a(columns):
    for row in range(ROWS):
        if all(columns[column][row] == "A" for column in range(COLS)):
            return True
    return False


def weighted_symbol(denominator):
    if random.random() < (1 / denominator):
        return "A"
    population = [symbol for symbol, _weight in NON_A_WEIGHTS]
    weights = [weight for _symbol, weight in NON_A_WEIGHTS]
    return random.choices(population, weights=weights, k=1)[0]


def generate_grid(denominator):
    columns = []
    for _column in range(COLS):
        column = []
        for _row in range(ROWS):
            column.append(weighted_symbol(denominator))
        columns.append(column)
    return columns


class SlotStore:
    def __init__(self, db_path=None):
        self.lock = threading.RLock()
        # Use PostgreSQL database from database module
        self._db = create_database()
        self.conn = self._db  # Alias for compatibility with existing code
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self.conn:
            # Check if using SQLite for compatibility
            is_sqlite = not os.environ.get("DATABASE_URL")
            if is_sqlite:
                # SQLite uses AUTOINCREMENT instead of BIGSERIAL
                self.conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        password_salt TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        display_name TEXT NOT NULL DEFAULT '',
                        bio TEXT NOT NULL DEFAULT '',
                        balance REAL NOT NULL DEFAULT 0,
                        total_deposit REAL NOT NULL DEFAULT 0,
                        max_deposit_limit REAL NOT NULL DEFAULT 0,
                        difficulty_mode TEXT NOT NULL DEFAULT '',
                        current_a_denominator REAL NOT NULL DEFAULT 0,
                        total_games INTEGER NOT NULL DEFAULT 0,
                        total_wins INTEGER NOT NULL DEFAULT 0,
                        win_streak INTEGER NOT NULL DEFAULT 0,
                        consecutive_a_hits INTEGER NOT NULL DEFAULT 0,
                        profile_banner_status TEXT NOT NULL DEFAULT 'standard',
                        last_spin TEXT NOT NULL DEFAULT '[["A","A","A"],["A","A","A"],["A","A","A"]]',
                        last_win REAL NOT NULL DEFAULT 0,
                        last_net REAL NOT NULL DEFAULT 0,
                        winning_lines TEXT NOT NULL DEFAULT '[]',
                        selected_skin TEXT NOT NULL DEFAULT 'skyline',
                        selected_banner TEXT NOT NULL DEFAULT 'aurora',
                        selected_avatar TEXT NOT NULL DEFAULT 'orbit',
                        custom_avatar_path TEXT NOT NULL DEFAULT '',
                        custom_banner_path TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'Choose a difficulty to begin.',
                        created_at TEXT NOT NULL,
                        prestige_points REAL NOT NULL DEFAULT 0,
                        total_pp_earned REAL NOT NULL DEFAULT 0,
                        unlocked_assets TEXT NOT NULL DEFAULT '[]',
                        inventory TEXT NOT NULL DEFAULT '{}',
                        total_deposits_count INTEGER NOT NULL DEFAULT 0,
                        max_balance REAL NOT NULL DEFAULT 0,
                        total_a_hits INTEGER NOT NULL DEFAULT 0,
                        max_win_streak INTEGER NOT NULL DEFAULT 0,
                        store_purchases INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS spin_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        difficulty_mode TEXT NOT NULL,
                        win_amount REAL NOT NULL,
                        bet_amount REAL NOT NULL,
                        luck_multiplier REAL NOT NULL DEFAULT 0,
                        deposit_total REAL NOT NULL DEFAULT 0,
                        deposit_tier TEXT NOT NULL DEFAULT '',
                        total_deposit_snapshot REAL NOT NULL,
                        a_denominator_snapshot REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                    );
                    """
                )
            else:
                # PostgreSQL uses BIGSERIAL
                self.conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_salt TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        display_name TEXT NOT NULL DEFAULT '',
                        bio TEXT NOT NULL DEFAULT '',
                        balance REAL NOT NULL DEFAULT 0,
                        total_deposit REAL NOT NULL DEFAULT 0,
                        max_deposit_limit REAL NOT NULL DEFAULT 0,
                        difficulty_mode TEXT NOT NULL DEFAULT '',
                        current_a_denominator REAL NOT NULL DEFAULT 0,
                        total_games INTEGER NOT NULL DEFAULT 0,
                        total_wins INTEGER NOT NULL DEFAULT 0,
                        win_streak INTEGER NOT NULL DEFAULT 0,
                        consecutive_a_hits INTEGER NOT NULL DEFAULT 0,
                        profile_banner_status TEXT NOT NULL DEFAULT 'standard',
                        last_spin TEXT NOT NULL DEFAULT '[["A","A","A"],["A","A","A"],["A","A","A"]]',
                        last_win REAL NOT NULL DEFAULT 0,
                        last_net REAL NOT NULL DEFAULT 0,
                        winning_lines TEXT NOT NULL DEFAULT '[]',
                        selected_skin TEXT NOT NULL DEFAULT 'skyline',
                        selected_banner TEXT NOT NULL DEFAULT 'aurora',
                        selected_avatar TEXT NOT NULL DEFAULT 'orbit',
                        custom_avatar_path TEXT NOT NULL DEFAULT '',
                        custom_banner_path TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'Choose a difficulty to begin.',
                        created_at TEXT NOT NULL,
                        prestige_points REAL NOT NULL DEFAULT 0,
                        total_pp_earned REAL NOT NULL DEFAULT 0,
                        unlocked_assets TEXT NOT NULL DEFAULT '[]',
                        inventory TEXT NOT NULL DEFAULT '{}',
                        total_deposits_count INTEGER NOT NULL DEFAULT 0,
                        max_balance REAL NOT NULL DEFAULT 0,
                        total_a_hits INTEGER NOT NULL DEFAULT 0,
                        max_win_streak INTEGER NOT NULL DEFAULT 0,
                        store_purchases INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS spin_results (
                        id BIGSERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        difficulty_mode TEXT NOT NULL,
                        win_amount REAL NOT NULL,
                        bet_amount REAL NOT NULL,
                        luck_multiplier REAL NOT NULL DEFAULT 0,
                        deposit_total REAL NOT NULL DEFAULT 0,
                        deposit_tier TEXT NOT NULL DEFAULT '',
                        total_deposit_snapshot REAL NOT NULL,
                        a_denominator_snapshot REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                    );
                    """
                )
            self._ensure_table_columns(
                "users",
                {
                    "display_name": "TEXT NOT NULL DEFAULT ''",
                    "bio": "TEXT NOT NULL DEFAULT ''",
                    "max_deposit_limit": "REAL NOT NULL DEFAULT 0",
                    "difficulty_mode": "TEXT NOT NULL DEFAULT ''",
                    "current_a_denominator": "REAL NOT NULL DEFAULT 0",
                    "total_games": "INTEGER NOT NULL DEFAULT 0",
                    "total_wins": "INTEGER NOT NULL DEFAULT 0",
                    "win_streak": "INTEGER NOT NULL DEFAULT 0",
                    "consecutive_a_hits": "INTEGER NOT NULL DEFAULT 0",
                    "profile_banner_status": "TEXT NOT NULL DEFAULT 'standard'",
                    "selected_skin": "TEXT NOT NULL DEFAULT 'skyline'",
                    "selected_banner": "TEXT NOT NULL DEFAULT 'aurora'",
                    "selected_avatar": "TEXT NOT NULL DEFAULT 'orbit'",
                    "custom_avatar_path": "TEXT NOT NULL DEFAULT ''",
                    "custom_banner_path": "TEXT NOT NULL DEFAULT ''",
                    "prestige_points": "REAL NOT NULL DEFAULT 0",
                    "total_pp_earned": "REAL NOT NULL DEFAULT 0",
                    "unlocked_assets": "TEXT NOT NULL DEFAULT '[]'",
                    "inventory": "TEXT NOT NULL DEFAULT '{}'",
                    "total_deposits_count": "INTEGER NOT NULL DEFAULT 0",
                    "max_balance": "REAL NOT NULL DEFAULT 0",
                    "total_a_hits": "INTEGER NOT NULL DEFAULT 0",
                    "max_win_streak": "INTEGER NOT NULL DEFAULT 0",
                    "store_purchases": "INTEGER NOT NULL DEFAULT 0",
                },
            )
            self._ensure_table_columns(
                "spin_results",
                {
                    "difficulty_mode": "TEXT NOT NULL DEFAULT ''",
                    "luck_multiplier": "REAL NOT NULL DEFAULT 0",
                    "deposit_total": "REAL NOT NULL DEFAULT 0",
                    "deposit_tier": "TEXT NOT NULL DEFAULT ''",
                    "total_deposit_snapshot": "REAL NOT NULL DEFAULT 0",
                    "a_denominator_snapshot": "REAL NOT NULL DEFAULT 0",
                },
            )
            self.conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_users_difficulty ON users(difficulty_mode);
                CREATE INDEX IF NOT EXISTS idx_spin_results_user_id ON spin_results(user_id);
                CREATE INDEX IF NOT EXISTS idx_spin_results_difficulty ON spin_results(difficulty_mode);
                """
            )

    def _table_columns(self, table_name):
        is_sqlite = not os.environ.get("DATABASE_URL")
        if is_sqlite:
            # SQLite uses PRAGMA table_info
            rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            return {row["name"] for row in rows}
        else:
            rows = self.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (table_name,)
            ).fetchall()
            return {row["column_name"] for row in rows}

    def _ensure_table_columns(self, table_name, required_columns):
        existing_columns = self._table_columns(table_name)
        for column_name, definition in required_columns.items():
            if column_name in existing_columns:
                continue
            self.conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _user_row(self, user_id):
        return self.conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()

    def _leaderboard_rows(self, difficulty=None, limit=100):
        if difficulty and difficulty not in MODE_CONFIG:
            raise ValueError("Unknown difficulty.")

        sql = """
            SELECT id,
                   username,
                   COALESCE(NULLIF(display_name, ''), username) AS display_name,
                   difficulty_mode,
                   total_deposit,
                   total_wins,
                   total_games,
                   max_deposit_limit,
                   balance,
                   (CASE WHEN total_games > 0 THEN CAST(total_wins AS REAL) / total_games ELSE 0 END) AS lucky_ratio
            FROM users
            WHERE difficulty_mode <> ''
              AND total_games > 0
        """
        params = []
        if difficulty:
            sql += " AND difficulty_mode = %s"
            params.append(difficulty)
        sql += """
            ORDER BY (total_deposit + (CASE WHEN total_games > 0 THEN CAST(total_wins AS REAL) / total_games ELSE 0 END)) DESC,
                     total_deposit DESC,
                     total_wins DESC,
                     username ASC
            LIMIT %s
        """
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for index, row in enumerate(rows, start=1):
            lucky_ratio = round(row["lucky_ratio"] or 0, 4)
            results.append(
                {
                    "rank": index,
                    "userId": row["id"],
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "difficulty": row["difficulty_mode"],
                    "difficultyLabel": MODE_CONFIG[row["difficulty_mode"]]["label"],
                    "totalDeposit": round(row["total_deposit"], 2),
                    "luckyRatio": lucky_ratio,
                    "unluckyRatio": round(1 - lucky_ratio, 4) if row["total_games"] else 0,
                    "totalWins": row["total_wins"],
                    "totalGames": row["total_games"],
                    "maxDepositLimit": round(row["max_deposit_limit"], 2),
                    "score": score_from_values(row["total_deposit"], row["total_wins"], row["total_games"]),
                }
            )
        return results

    def _global_rank(self, user_id):
        for row in self._leaderboard_rows(None, 1000):
            if row["userId"] == user_id:
                return row["rank"]
        return None

    def _mode_rank(self, user_id, difficulty):
        if not difficulty:
            return None
        for row in self._leaderboard_rows(difficulty, 1000):
            if row["userId"] == user_id:
                return row["rank"]
        return None

    def _unlock_context(self, row, global_rank, mode_rank):
        total_games = row["total_games"]
        lucky_ratio = (row["total_wins"] / total_games) if total_games else 0
        return {
            "difficulty": row["difficulty_mode"],
            "total_games": total_games,
            "total_wins": row["total_wins"],
            "hit_rate": lucky_ratio,
            "global_rank": global_rank,
            "mode_rank": mode_rank,
            "profile_banner_status": row["profile_banner_status"],
        }

    def _requirement_unlocked(self, requirement, context):
        requirement = requirement or {"type": "always", "label": "Starter unlock"}
        kind = requirement.get("type", "always")
        if kind == "always":
            return True
        if kind == "games":
            return context["total_games"] >= requirement.get("value", 0)
        if kind == "wins":
            return context["total_wins"] >= requirement.get("value", 0)
        if kind == "hit_rate":
            return (
                context["total_games"] >= requirement.get("games", 0)
                and context["hit_rate"] >= requirement.get("value", 0)
            )
        if kind == "difficulty":
            return context["difficulty"] == requirement.get("value")
        if kind == "top_ten_global":
            return bool(context["global_rank"] and context["global_rank"] <= 10)
        if kind == "top_ten_mode":
            return bool(context["mode_rank"] and context["mode_rank"] <= 10)
        if kind == "a_streak":
            return context["profile_banner_status"] == "a_streak"
        return False

    def _cosmetic_tag(self, item, unlocked):
        if not unlocked:
            return "Locked"
        requirement_type = (item.get("requirement") or {}).get("type", "always")
        if requirement_type == "top_ten_global":
            return "Global Top 10"
        if requirement_type == "top_ten_mode":
            return "Class Top 10"
        if requirement_type == "a_streak":
            return "A-Streak"
        if requirement_type == "difficulty":
            return f"{item['requirement']['value'].title()} mode"
        if item["elite"]:
            return "Elite"
        if requirement_type == "always":
            return "Unlocked"
        return "Earned"

    def _serialize_cosmetics(self, items, context):
        serialized = []
        for item in items:
            unlocked = self._requirement_unlocked(item.get("requirement"), context)
            serialized.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "elite": item["elite"],
                    "unlocked": unlocked,
                    "tag": self._cosmetic_tag(item, unlocked),
                    "requirementText": item["requirement"]["label"],
                }
            )
        return serialized

    def _cosmetics(self, row, global_rank, mode_rank):
        context = self._unlock_context(row, global_rank, mode_rank)
        return {
            "skins": self._serialize_cosmetics(BASE_SKINS + ELITE_SKINS, context),
            "banners": self._serialize_cosmetics(BASE_BANNERS + ELITE_BANNERS, context),
            "avatars": self._serialize_cosmetics(BASE_AVATARS + ELITE_AVATARS, context),
        }

    def _valid_cosmetic_ids(self, cosmetics):
        return {
            "skins": {item["id"] for item in cosmetics["skins"] if item["unlocked"]},
            "banners": {item["id"] for item in cosmetics["banners"] if item["unlocked"]},
            "avatars": {item["id"] for item in cosmetics["avatars"] if item["unlocked"]},
        }

    def _effective_cosmetics(self, row, cosmetics):
        valid = self._valid_cosmetic_ids(cosmetics)
        return {
            "selectedSkin": row["selected_skin"] if row["selected_skin"] in valid["skins"] else DEFAULT_COSMETICS["skin"],
            "selectedBanner": row["selected_banner"] if row["selected_banner"] in valid["banners"] else DEFAULT_COSMETICS["banner"],
            "selectedAvatar": row["selected_avatar"] if row["selected_avatar"] in valid["avatars"] else DEFAULT_COSMETICS["avatar"],
        }

    def _badges(self, row, global_rank, mode_rank):
        total_games = row["total_games"]
        lucky_ratio = (row["total_wins"] / total_games) if total_games else 0
        account_days = max((utcnow() - datetime.fromisoformat(row["created_at"])).days, 0)
        badges = []
        if total_games:
            badges.append({"name": "Rookie Spinner", "description": "Started a real leaderboard run.", "tone": "blue"})
        if row["difficulty_mode"] == "hard":
            badges.append({"name": "Hard Mode", "description": "Playing with the sharpest constraints.", "tone": "rose"})
        if lucky_ratio >= 0.45 and total_games >= 10:
            badges.append({"name": "Lucky Current", "description": "Wins on at least 45% of spins.", "tone": "green"})
        if lucky_ratio <= 0.15 and total_games >= 10:
            badges.append({"name": "Storm Survivor", "description": "Stuck with it through brutal losses.", "tone": "orange"})
        if account_days >= 7 or total_games >= 25:
            badges.append({"name": "Long Haul", "description": "Kept the profile active over time.", "tone": "indigo"})
        if global_rank and global_rank <= 10:
            badges.append({"name": "Global Top 10", "description": "Unlocked elite cosmetics.", "tone": "gold"})
        if mode_rank and mode_rank <= 10:
            badges.append({"name": "Mode Top 10", "description": "Top 10 inside the current difficulty.", "tone": "violet"})
        if row["profile_banner_status"] == "a_streak":
            badges.append({"name": "A-Streak", "description": "Triggered the consecutive A banner event.", "tone": "gold"})
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
        raw = base64.b64decode(encoded)
        if len(raw) > UPLOAD_SIZE_LIMIT:
            raise ValueError("Uploaded images must be smaller than 2MB.")
        filename = f"{prefix}_{user_id}_{secrets.token_hex(8)}.{extension}"
        (UPLOADS_DIR / filename).write_bytes(raw)
        return f"/uploads/{filename}"

    def _profile_payload(self, row):
        global_rank = self._global_rank(row["id"])
        mode_rank = self._mode_rank(row["id"], row["difficulty_mode"])
        is_top_ten = global_rank is not None and global_rank <= 10
        lucky_ratio = (row["total_wins"] / row["total_games"]) if row["total_games"] else 0
        profile_name = row["display_name"] or row["username"]
        cosmetics = self._cosmetics(row, global_rank, mode_rank)
        effective = self._effective_cosmetics(row, cosmetics)
        return {
            "profile": {
                "username": row["username"],
                "displayName": profile_name,
                "bio": row["bio"],
                "selectedSkin": effective["selectedSkin"],
                "selectedBanner": effective["selectedBanner"],
                "selectedAvatar": effective["selectedAvatar"],
                "avatarPath": row["custom_avatar_path"],
                "bannerPath": row["custom_banner_path"],
                "initials": initials_from_name(profile_name),
            },
            "stats": {
                "totalDeposit": round(row["total_deposit"], 2),
                "balance": round(row["balance"], 2),
                "maxDepositLimit": round(row["max_deposit_limit"], 2),
                "difficulty": row["difficulty_mode"],
                "difficultyLabel": MODE_CONFIG[row["difficulty_mode"]]["label"] if row["difficulty_mode"] else "Unset",
                "totalGames": row["total_games"],
                "totalWins": row["total_wins"],
                "hitRate": round(lucky_ratio, 4),
                "accountDays": max((utcnow() - datetime.fromisoformat(row["created_at"])).days, 0),
                "profileBannerStatus": row["profile_banner_status"],
                "prestigePoints": round(row["prestige_points"], 2),
                "totalPP": round(row["total_pp_earned"], 2),
            },
            "ranks": {
                "globalRank": global_rank,
                "modeRank": mode_rank,
                "isTopTen": is_top_ten,
            },
            "badges": self._badges(row, global_rank, mode_rank),
            "cosmetics": cosmetics,
            "achievements": self._get_achievements(row, global_rank, mode_rank),
        }

    def _check_achievement(self, achievement_id, row, global_rank, mode_rank):
        """Check if a single achievement is unlocked."""
        if achievement_id not in ACHIEVEMENTS:
            return False
        achievement = ACHIEVEMENTS[achievement_id]
        req = achievement.get("requirement", {})
        req_type = req.get("type", "always")
        
        if req_type == "always":
            return True
        elif req_type == "games":
            return row["total_games"] >= req.get("value", 0)
        elif req_type == "wins":
            return row["total_wins"] >= req.get("value", 0)
        elif req_type == "hit_rate":
            return (row["total_games"] >= req.get("games", 0) and 
                    (row["total_wins"] / row["total_games"] if row["total_games"] else 0) >= req.get("value", 0))
        elif req_type == "difficulty":
            return row["difficulty_mode"] == req.get("value")
        elif req_type == "top_ten_global":
            return bool(global_rank and global_rank <= 10)
        elif req_type == "top_ten_mode":
            return bool(mode_rank and mode_rank <= 10)
        elif req_type == "a_streak":
            return row["profile_banner_status"] == "a_streak"
        elif req_type == "total_deposit":
            return row["total_deposit"] >= req.get("value", 0)
        elif req_type == "max_balance":
            return row["max_balance"] >= req.get("value", 0)
        elif req_type == "win_streak":
            return row["max_win_streak"] >= req.get("value", 0)
        elif req_type == "leaderboard_rank":
            return bool(global_rank and global_rank <= req.get("value", 100))
        elif req_type == "global_rank":
            return global_rank == req.get("value", 1)
        elif req_type == "deposits":
            return row["total_deposits_count"] >= req.get("value", 0)
        elif req_type == "a_hits":
            return row["total_a_hits"] >= req.get("value", 0)
        elif req_type == "a_streak":
            return row["consecutive_a_hits"] >= req.get("value", 0)
        elif req_type == "account_days":
            return max((utcnow() - datetime.fromisoformat(row["created_at"])).days, 0) >= req.get("value", 0)
        elif req_type == "pp_earned":
            return row["total_pp_earned"] >= req.get("value", 0)
        elif req_type == "store_purchases":
            return row["store_purchases"] >= req.get("value", 0)
        elif req_type == "difficulty_games":
            return row["difficulty_mode"] == req.get("value") and row["total_games"] >= req.get("games", 0)
        elif req_type == "medium_cap":
            return row["difficulty_mode"] == "medium" and row["max_deposit_limit"] >= req.get("value", 0)
        elif req_type == "easy_cap":
            return row["difficulty_mode"] == "easy" and row["max_deposit_limit"] >= req.get("value", 0)
        elif req_type == "comeback":
            return row["max_balance"] >= req.get("value", 0) and row["total_deposit"] >= req.get("value", 0)
        elif req_type == "deposit_tier":
            return row["total_deposit"] >= {"bronze": 100, "silver": 1000, "gold": 10000, "platinum": 50000, "diamond": 100000, "radiant": 500000}.get(req.get("value"), 0)
        elif req_type == "a_streak_single":
            return row["consecutive_a_hits"] >= req.get("value", 0)
        elif req_type == "double_a_line":
            return row["consecutive_a_hits"] >= 2  # Simplified check
        elif req_type == "win_to_bet_ratio":
            return row["last_win"] >= req.get("value", 0) * (row["last_net"] + row["last_win"]) if row["last_net"] else False
        elif req_type == "leaderboard_enter":
            return bool(global_rank)
        elif req_type == "pity_break":
            return row["current_a_denominator"] < MODE_CONFIG.get(row["difficulty_mode"], {}).get("a_denominator", 200)
        elif req_type == "medium_streak_mult":
            return row["difficulty_mode"] == "medium" and row["win_streak"] >= req.get("value", 0)
        elif req_type == "bankruptcy_recovery":
            return row["total_games"] > 0 and row["balance"] > 0  # Simplified
        return False

    def _get_achievements(self, row, global_rank, mode_rank):
        """Get all achievements with their unlock status."""
        unlocked_ids = set(json.loads(row["unlocked_assets"] or "[]"))
        achievements_list = []
        for achievement_id, achievement in ACHIEVEMENTS.items():
            is_unlocked = achievement_id in unlocked_ids or self._check_achievement(achievement_id, row, global_rank, mode_rank)
            achievements_list.append({
                "id": achievement_id,
                "name": achievement["name"],
                "description": achievement["description"],
                "category": achievement.get("category", "milestone"),
                "rarity": achievement.get("rarity", "bronze"),
                "shape": achievement.get("shape", "hexagon"),
                "animation": achievement.get("animation", None),
                "unlocked": is_unlocked,
            })
        return achievements_list

    def _check_and_unlock_achievements(self, row, global_rank, mode_rank):
        """Check and unlock new achievements, return list of newly unlocked IDs."""
        unlocked_ids = set(json.loads(row["unlocked_assets"] or "[]"))
        newly_unlocked = []
        for achievement_id in ACHIEVEMENTS:
            if achievement_id not in unlocked_ids:
                if self._check_achievement(achievement_id, row, global_rank, mode_rank):
                    unlocked_ids.add(achievement_id)
                    newly_unlocked.append(achievement_id)
        return list(unlocked_ids), newly_unlocked

    def add_prestige_points(self, user_id, amount):
        """Add PP based on deposits (R10 = 1 PP)."""
        pp_earned = amount / PP_RATE
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            self.conn.execute(
                """
                UPDATE users
                SET prestige_points = prestige_points + %s,
                    total_pp_earned = total_pp_earned + %s
                WHERE id = %s
                """,
                (pp_earned, pp_earned, user_id),
            )
        return round(pp_earned, 2)

    def spend_prestige_points(self, user_id, amount):
        """Spend PP from user's balance."""
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            if row["prestige_points"] < amount:
                raise ValueError(f"Insufficient Prestige Points. You have {row['prestige_points']:.2f} PP.")
            self.conn.execute(
                """
                UPDATE users
                SET prestige_points = prestige_points - %s
                WHERE id = %s
                """,
                (amount, user_id),
            )
            updated = self._user_row(user_id)
        return updated["prestige_points"]

    def get_store_items(self):
        """Get all store items with prices."""
        inventory = {}
        # Format boosters and cosmetics for the store
        all_items = []
        for item in STORE_ITEMS["boosters"]:
            all_items.append({
                "type": "booster",
                **item,
            })
        for item in STORE_ITEMS["cosmetic_themes"]:
            all_items.append({
                "type": "theme",
                **item,
            })
        return all_items

    def purchase_item(self, user_id, item_id, item_type):
        """Purchase an item from the store using PP and sacrifice."""
        # Find the item
        item = None
        if item_type == "booster":
            for i in STORE_ITEMS["boosters"]:
                if i["id"] == item_id:
                    item = i
                    break
        elif item_type == "theme":
            for i in STORE_ITEMS["cosmetic_themes"]:
                if i["id"] == item_id:
                    item = i
                    break
        
        if not item:
            raise ValueError("Item not found in store.")
        
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            
            # Check PP balance
            if row["prestige_points"] < item["pp_cost"]:
                raise ValueError(f"Insufficient Prestige Points. You need {item['pp_cost']} PP but have {row['prestige_points']:.2f} PP.")
            
            # Apply sacrifice (permanent deduction from max_deposit_limit)
            sacrifice = item.get("sacrifice", 0)
            if sacrifice > 0 and row["max_deposit_limit"] > 0:
                new_limit = max(0, row["max_deposit_limit"] - sacrifice)
                # Update inventory
                inventory = json.loads(row["inventory"] or "{}")
                if item_type == "booster":
                    if "boosters" not in inventory:
                        inventory["boosters"] = {}
                    if item["id"] not in inventory["boosters"]:
                        inventory["boosters"][item["id"]] = 0
                    inventory["boosters"][item["id"]] += 1
                elif item_type == "theme":
                    if "themes" not in inventory:
                        inventory["themes"] = []
                    if item["id"] not in inventory["themes"]:
                        inventory["themes"].append(item["id"])
                
                self.conn.execute(
                    """
                    UPDATE users
                    SET prestige_points = prestige_points - %s,
                        max_deposit_limit = %s,
                        inventory = %s,
                        store_purchases = store_purchases + 1
                    WHERE id = %s
                    """,
                    (item["pp_cost"], new_limit, json.dumps(inventory), user_id),
                )
            else:
                # No sacrifice needed (e.g., starting balance or no limit yet)
                inventory = json.loads(row["inventory"] or "{}")
                if item_type == "booster":
                    if "boosters" not in inventory:
                        inventory["boosters"] = {}
                    if item["id"] not in inventory["boosters"]:
                        inventory["boosters"][item["id"]] = 0
                    inventory["boosters"][item["id"]] += 1
                elif item_type == "theme":
                    if "themes" not in inventory:
                        inventory["themes"] = []
                    if item["id"] not in inventory["themes"]:
                        inventory["themes"].append(item["id"])
                
                self.conn.execute(
                    """
                    UPDATE users
                    SET prestige_points = prestige_points - %s,
                        inventory = %s,
                        store_purchases = store_purchases + 1
                    WHERE id = %s
                    """,
                    (item["pp_cost"], json.dumps(inventory), user_id),
                )
            
            updated = self._user_row(user_id)
        
        return {
            "success": True,
            "item": item,
            "remaining_pp": round(updated["prestige_points"], 2),
            "new_limit": round(updated["max_deposit_limit"], 2),
        }

    def get_inventory(self, user_id):
        """Get user's inventory."""
        with self.lock:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            return json.loads(row["inventory"] or "{}")

    def _snapshot(self, row):
        lucky_ratio = (row["total_wins"] / row["total_games"]) if row["total_games"] else 0
        denominator = row["current_a_denominator"] or 0
        global_rank = self._global_rank(row["id"])
        mode_rank = self._mode_rank(row["id"], row["difficulty_mode"])
        cosmetics = self._cosmetics(row, global_rank, mode_rank)
        effective = self._effective_cosmetics(row, cosmetics)
        return {
            "authenticated": True,
            "needsDifficultySelection": not bool(row["difficulty_mode"]),
            "difficultyOptions": [
                {
                    "id": mode,
                    "label": config["label"],
                    "startingLimit": config["starting_limit"],
                    "aDenominator": config["a_denominator"],
                }
                for mode, config in MODE_CONFIG.items()
            ],
            "user": {
                "id": row["id"],
                "username": row["username"],
                "displayName": row["display_name"] or row["username"],
                "difficulty": row["difficulty_mode"],
                "difficultyLabel": MODE_CONFIG[row["difficulty_mode"]]["label"] if row["difficulty_mode"] else "Unset",
                "balance": round(row["balance"], 2),
                "totalDeposit": round(row["total_deposit"], 2),
                "maxDepositLimit": round(row["max_deposit_limit"], 2),
                "aOddsText": f"1 in {denominator:.2f}" if denominator else "Choose a mode",
                "aDenominator": round(denominator, 2) if denominator else None,
                "hitRate": round(lucky_ratio, 4),
                "totalGames": row["total_games"],
                "totalWins": row["total_wins"],
                "selectedSkin": effective["selectedSkin"],
                "selectedBanner": effective["selectedBanner"],
                "selectedAvatar": effective["selectedAvatar"],
                "avatarPath": row["custom_avatar_path"],
                "bannerPath": row["custom_banner_path"],
                "profileBannerStatus": row["profile_banner_status"],
                "isTopTen": bool(global_rank and global_rank <= 10),
                "prestigePoints": round(row["prestige_points"], 2),
                "totalPP": round(row["total_pp_earned"], 2),
                "inventory": json.loads(row["inventory"] or "{}"),
            },
            "balance": round(row["balance"], 2),
            "lastSpin": json.loads(row["last_spin"]),
            "lastWin": round(row["last_win"], 2),
            "lastNet": round(row["last_net"], 2),
            "winningLines": json.loads(row["winning_lines"]),
            "status": row["status"],
            "limits": {
                "minBet": MIN_BET,
                "maxLines": LINES,
            },
            "modeSelection": {
                "canChange": True,
                "current": row["difficulty_mode"] or "",
                "historyResetsOnChange": True,
                "modeRank": mode_rank,
            },
        }

    def guest_snapshot(self):
        return {
            "authenticated": False,
            "needsDifficultySelection": False,
            "difficultyOptions": [
                {
                    "id": mode,
                    "label": config["label"],
                    "startingLimit": config["starting_limit"],
                    "aDenominator": config["a_denominator"],
                }
                for mode, config in MODE_CONFIG.items()
            ],
            "user": None,
            "balance": 0,
            "lastSpin": DEFAULT_GRID,
            "lastWin": 0,
            "lastNet": 0,
            "winningLines": [],
            "status": "Sign in and choose a difficulty to begin.",
            "limits": {"minBet": MIN_BET, "maxLines": LINES},
        }

    def register_user(self, username, password):
        username = username.strip()
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        salt_hex, digest_hex = hash_password(password)
        with self.lock, self.conn:
            try:
                self.conn.execute(
                    """
                    INSERT INTO users (username, password_salt, password_hash, display_name, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (username, salt_hex, digest_hex, username, isoformat(utcnow())),
                )
            except Exception as exc:
                if "unique constraint" in str(exc).lower() or "duplicate key" in str(exc).lower():
                    raise ValueError("That username is already taken.") from exc
                raise
            row = self.conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()
        return self._snapshot(row)

    def authenticate_user(self, username, password):
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE username = %s", (username.strip(),)).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            raise ValueError("Invalid username or password.")
        return self._snapshot(row)

    def current_user(self, user_id):
        if not user_id:
            return None
        with self.lock:
            row = self._user_row(user_id)
        return self._snapshot(row) if row else None

    def select_difficulty(self, user_id, difficulty):
        difficulty = difficulty.lower()
        if difficulty not in MODE_CONFIG:
            raise ValueError("Please choose easy, medium, or hard.")
        config = MODE_CONFIG[difficulty]
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            previous_mode = row["difficulty_mode"]
            if previous_mode == difficulty:
                snapshot = self._snapshot(row)
                snapshot["status"] = f"{config['label']} mode is already active."
                return snapshot

            history_reset = bool(previous_mode and previous_mode != difficulty)
            if history_reset:
                self.conn.execute("DELETE FROM spin_results WHERE user_id = %s", (user_id,))
                status = (
                    f"Switched from {MODE_CONFIG[previous_mode]['label']} to {config['label']}. "
                    f"Previous run history, leaderboard score, and balance were reset."
                )
            else:
                status = f"{config['label']} mode selected. Add funds to begin."
            self.conn.execute(
                """
                UPDATE users
                SET difficulty_mode = %s,
                    balance = 0,
                    total_deposit = 0,
                    max_deposit_limit = %s,
                    current_a_denominator = %s,
                    total_games = 0,
                    total_wins = 0,
                    win_streak = 0,
                    consecutive_a_hits = 0,
                    profile_banner_status = 'standard',
                    last_spin = %s,
                    last_win = 0,
                    last_net = 0,
                    winning_lines = '[]',
                    status = %s
                WHERE id = %s
                """,
                (
                    difficulty,
                    config["starting_limit"],
                    config["a_denominator"],
                    json.dumps(DEFAULT_GRID),
                    status,
                    user_id,
                ),
            )
            updated = self._user_row(user_id)
        snapshot = self._snapshot(updated)
        snapshot["historyReset"] = history_reset
        snapshot["previousMode"] = previous_mode or ""
        return snapshot

    def add_funds(self, user_id, amount):
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero.")
        pp_earned = amount / PP_RATE
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            if not row["difficulty_mode"]:
                raise ValueError("Choose a difficulty before depositing.")
            if amount > row["max_deposit_limit"]:
                raise ValueError(
                    f"Deposit amount cannot exceed your current limit of R{row['max_deposit_limit']:.2f}."
                )
            new_total_deposits = row["total_deposits_count"] + 1
            new_max_balance = max(row["max_balance"], row["balance"] + amount)
            self.conn.execute(
                """
                UPDATE users
                SET balance = balance + %s,
                    total_deposit = total_deposit + %s,
                    prestige_points = prestige_points + %s,
                    total_pp_earned = total_pp_earned + %s,
                    total_deposits_count = %s,
                    max_balance = %s,
                    status = %s
                WHERE id = %s
                """,
                (amount, amount, pp_earned, pp_earned, new_total_deposits, new_max_balance, f"Added R{amount:.2f}. +{pp_earned:.1f} PP earned!", user_id),
            )
            updated = self._user_row(user_id)
        return self._snapshot(updated)

    def demote_user_rank(self, user_id, current_total_deposit):
        rank = self._global_rank(user_id)
        if rank is None:
            return current_total_deposit, ""
        if rank <= 10:
            penalty = 0.35
        elif rank <= 25:
            penalty = 0.25
        else:
            penalty = 0.15
        new_total = max(0, round(current_total_deposit * (1 - penalty), 2))
        return new_total, f"Bankruptcy penalty applied. Global rank #{rank} lost {int(penalty * 100)}% of total deposit score."

    def spin(self, user_id, bet_per_line):
        if bet_per_line < MIN_BET:
            raise ValueError(f"Bet per line must be at least R{MIN_BET}.")
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            difficulty = row["difficulty_mode"]
            if not difficulty:
                raise ValueError("Choose a difficulty before spinning.")

            total_bet = bet_per_line * LINES
            if total_bet > row["balance"]:
                raise ValueError("You cannot bet more than your balance.")
            if total_bet > row["max_deposit_limit"]:
                raise ValueError("You cannot bet more than your current max deposit limit.")

            denominator = row["current_a_denominator"] or MODE_CONFIG[difficulty]["a_denominator"]
            columns = generate_grid(denominator)
            winnings, winning_lines = check_winnings(columns, bet_per_line)
            new_balance = row["balance"] - total_bet + winnings
            total_deposit = row["total_deposit"] + winnings
            total_games = row["total_games"] + 1
            total_wins = row["total_wins"] + (1 if winnings > 0 else 0)
            previous_streak = row["win_streak"]
            win_streak = previous_streak + 1 if winnings > 0 else 0
            max_deposit_limit = row["max_deposit_limit"]
            next_denominator = denominator
            banner_status = row["profile_banner_status"]
            consecutive_a_hits = row["consecutive_a_hits"]
            total_a_hits = row["total_a_hits"]
            max_win_streak = max(row["max_win_streak"], win_streak)
            max_balance = max(row["max_balance"], new_balance)
            notes = []

            # Count A-hits in this spin
            a_count = sum(1 for col in columns for sym in col if sym == "A")
            total_a_hits += a_count

            if difficulty == "hard":
                max_deposit_limit = MODE_CONFIG["hard"]["cap"]
                next_denominator = MODE_CONFIG["hard"]["a_denominator"]
                if check_consecutive_a(columns):
                    consecutive_a_hits += 1
                    banner_status = "a_streak"
                    notes.append("Consecutive A banner unlocked.")
                if new_balance <= 0:
                    total_deposit, note = self.demote_user_rank(user_id, total_deposit)
                    if note:
                        notes.append(note)
            elif difficulty == "medium":
                if winnings > 0:
                    multiplier = 1.2 if previous_streak >= 1 else 1.0
                    max_deposit_limit = min(
                        MODE_CONFIG["medium"]["cap"],
                        round(max_deposit_limit + (winnings * multiplier), 2),
                    )
                    next_denominator = MODE_CONFIG["medium"]["a_denominator"]
                    notes.append("Medium pity reset after a cap increase.")
                else:
                    next_denominator = max(10.0, round(denominator * 0.99, 2))
            elif difficulty == "easy":
                next_denominator = MODE_CONFIG["easy"]["a_denominator"]
                if winnings > 0:
                    max_deposit_limit = min(
                        MODE_CONFIG["easy"]["cap"],
                        round(max_deposit_limit + winnings, 2),
                    )
                else:
                    max_deposit_limit = max(3.0, round(max_deposit_limit - (total_bet / 2), 2))
                    notes.append("Easy mode loss penalty reduced the deposit limit.")

            status = (
                f"You won R{winnings:.2f}. Net change: R{(winnings - total_bet):.2f}."
                if winnings
                else f"No line match this round. Net change: R{-total_bet:.2f}."
            )
            if notes:
                status = f"{status} {' '.join(notes)}"

            self.conn.execute(
                """
                UPDATE users
                SET balance = %s,
                    total_deposit = %s,
                    max_deposit_limit = %s,
                    current_a_denominator = %s,
                    total_games = %s,
                    total_wins = %s,
                    win_streak = %s,
                    consecutive_a_hits = %s,
                    profile_banner_status = %s,
                    last_spin = %s,
                    last_win = %s,
                    last_net = %s,
                    winning_lines = %s,
                    status = %s,
                    total_a_hits = %s,
                    max_win_streak = %s,
                    max_balance = %s
                WHERE id = %s
                """,
                (
                    round(new_balance, 2),
                    round(total_deposit, 2),
                    round(max_deposit_limit, 2),
                    round(next_denominator, 2),
                    total_games,
                    total_wins,
                    win_streak,
                    consecutive_a_hits,
                    banner_status,
                    json.dumps(columns),
                    round(winnings, 2),
                    round(winnings - total_bet, 2),
                    json.dumps(winning_lines),
                    status,
                    total_a_hits,
                    max_win_streak,
                    round(max_balance, 2),
                    user_id,
                ),
            )
            
            # Check and unlock achievements
            updated_row = self._user_row(user_id)
            global_rank = self._global_rank(user_id)
            mode_rank = self._mode_rank(user_id, difficulty)
            unlocked_ids, newly_unlocked = self._check_and_unlock_achievements(updated_row, global_rank, mode_rank)
            
            if newly_unlocked:
                self.conn.execute(
                    "UPDATE users SET unlocked_assets = %s WHERE id = %s",
                    (json.dumps(list(unlocked_ids)), user_id),
                )
                achievement_notes = [f"🏆 Unlocked: {ACHIEVEMENTS[a]['name']}!" for a in newly_unlocked[:3]]
                if len(newly_unlocked) > 3:
                    achievement_notes.append(f"+{len(newly_unlocked) - 3} more achievements!")
                notes.extend(achievement_notes)
            self.conn.execute(
                """
                INSERT INTO spin_results (
                    user_id,
                    difficulty_mode,
                    win_amount,
                    bet_amount,
                    luck_multiplier,
                    deposit_total,
                    deposit_tier,
                    total_deposit_snapshot,
                    a_denominator_snapshot,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    difficulty,
                    round(winnings, 2),
                    round(total_bet, 2),
                    round((winnings / total_bet) if total_bet else 0, 4),
                    round(total_deposit, 2),
                    difficulty,
                    round(total_deposit, 2),
                    round(denominator, 2),
                    isoformat(utcnow()),
                ),
            )
            updated = self._user_row(user_id)
        snapshot = self._snapshot(updated)
        snapshot["bet"] = {"lines": LINES, "betPerLine": bet_per_line, "total": round(total_bet, 2)}
        return snapshot

    def leaderboard_payload(self):
        with self.lock:
            return {
                "all": self._leaderboard_rows(None, 100),
                "easy": self._leaderboard_rows("easy", 100),
                "medium": self._leaderboard_rows("medium", 100),
                "hard": self._leaderboard_rows("hard", 100),
            }

    def profile(self, user_id):
        with self.lock:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            return self._profile_payload(row)

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
                raise ValueError("User not found.")
            global_rank = self._global_rank(user_id)
            mode_rank = self._mode_rank(user_id, row["difficulty_mode"])
            cosmetics = self._cosmetics(row, global_rank, mode_rank)
            valid = self._valid_cosmetic_ids(cosmetics)
            effective = self._effective_cosmetics(row, cosmetics)
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
                SET display_name = %s,
                    bio = %s,
                    selected_skin = %s,
                    selected_banner = %s,
                    selected_avatar = %s,
                    custom_avatar_path = %s,
                    custom_banner_path = %s,
                    status = %s
                WHERE id = %s
                """,
                (
                    display_name,
                    bio,
                    selected_skin or effective["selectedSkin"],
                    selected_banner or effective["selectedBanner"],
                    selected_avatar or effective["selectedAvatar"],
                    avatar_path,
                    banner_path,
                    "Profile updated.",
                    user_id,
                ),
            )
            updated = self._user_row(user_id)
        return {"snapshot": self._snapshot(updated), **self._profile_payload(updated)}


store = SlotStore()

app = Flask(__name__, static_folder=None)
app.secret_key = FLASK_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


@app.errorhandler(ValueError)
def handle_value_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(error)}), 400
    return str(error), 400


def current_user_id():
    return session.get("user_id")


def require_user():
    user_id = current_user_id()
    if not user_id:
        return None
    return user_id


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/profile")
def profile_page():
    return send_from_directory(WEB_DIR, "profile.html")


@app.get("/leaderboard")
def leaderboard_page():
    return send_from_directory(WEB_DIR, "leaderboard.html")


@app.get("/creator")
def creator_page():
    return send_from_directory(WEB_DIR, "creator.html")


@app.get("/store")
def store_page():
    return send_from_directory(WEB_DIR, "store.html")


@app.get("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.get("/api/state")
def api_state():
    user = store.current_user(current_user_id())
    return jsonify(user or store.guest_snapshot())


@app.post("/api/register")
def api_register():
    payload = request.get_json(force=True)
    snapshot = store.register_user(str(payload.get("username", "")), str(payload.get("password", "")))
    session["user_id"] = snapshot["user"]["id"]
    return jsonify(snapshot), 201


@app.post("/api/login")
def api_login():
    payload = request.get_json(force=True)
    snapshot = store.authenticate_user(str(payload.get("username", "")), str(payload.get("password", "")))
    session["user_id"] = snapshot["user"]["id"]
    return jsonify(snapshot)


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/select-difficulty")
def api_select_difficulty():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before choosing a difficulty."}), 401
    payload = request.get_json(force=True)
    snapshot = store.select_difficulty(user_id, str(payload.get("difficulty", "")))
    return jsonify(snapshot)


@app.post("/api/deposit")
def api_deposit():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    snapshot = store.add_funds(user_id, float(payload.get("amount", 0)))
    return jsonify(snapshot)


@app.post("/api/spin")
def api_spin():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    snapshot = store.spin(user_id, float(payload.get("bet", 0)))
    return jsonify(snapshot)


@app.get("/api/leaderboard")
def api_leaderboard():
    return jsonify(store.leaderboard_payload())


@app.get("/api/profile")
def api_profile():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    return jsonify(store.profile(user_id))


@app.post("/api/profile")
def api_profile_update():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    return jsonify(store.update_profile(user_id, payload))


@app.get("/api/store")
def api_store():
    """Get all store items."""
    return jsonify({"items": store.get_store_items()})


@app.post("/api/store/purchase")
def api_store_purchase():
    """Purchase an item from the store."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    item_id = str(payload.get("itemId", ""))
    item_type = str(payload.get("itemType", ""))
    try:
        result = store.purchase_item(user_id, item_id, item_type)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/inventory")
def api_inventory():
    """Get user's inventory."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    return jsonify({"inventory": store.get_inventory(user_id)})


@app.get("/api/achievements")
def api_achievements():
    """Get user's achievements."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    with store.lock:
        row = store._user_row(user_id)
        if not row:
            return jsonify({"error": "User not found."}), 404
        global_rank = store._global_rank(user_id)
        mode_rank = store._mode_rank(user_id, row["difficulty_mode"])
        achievements = store._get_achievements(row, global_rank, mode_rank)
        unlocked_count = sum(1 for a in achievements if a["unlocked"])
        return jsonify({
            "achievements": achievements,
            "total": len(achievements),
            "unlocked": unlocked_count,
            "progress": round((unlocked_count / len(achievements)) * 100, 1) if achievements else 0,
        })


@app.get("/api/pp")
def api_pp():
    """Get user's PP balance."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    with store.lock:
        row = store._user_row(user_id)
        if not row:
            return jsonify({"error": "User not found."}), 404
        return jsonify({
            "prestigePoints": round(row["prestige_points"], 2),
            "totalPP": round(row["total_pp_earned"], 2),
        })


def main():
    app.run(host="127.0.0.1", port=8000, debug=False)


if __name__ == "__main__":
    main()
