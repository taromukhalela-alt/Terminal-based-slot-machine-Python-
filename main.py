import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException

from database import create_database


ROWS = 3
COLS = 3
LINES = 3
MIN_BET = 1
UPLOAD_SIZE_LIMIT = 2 * 1024 * 1024
FLASK_SECRET = os.environ.get("SESSION_SECRET", "pixel-slot-studio-dev-secret")
PP_RATE = 10  # R10 = 1 Prestige Point

# =============================================================================
# CLASS CONFIGURATION (TDA Economy System)
# =============================================================================
# Each class has:
#   - starting_tda: Initial Total Depositable Amount
#   - profit_multiplier: Bonus applied to net profits (1.02 = +2% for Medium)
#   - bankruptcy_protection: Whether TDA has a minimum floor
#   - min_tda_floor: Minimum TDA when bankruptcy protection is active
#   - recharge_cooldown_hours: Hours between recharges (None = no recharge)
#   - a_denominator: Base odds for A-value symbols
#   - deposit_cap: Maximum amount that can be moved to play balance (None = unlimited)
# =============================================================================

CLASS_CONFIG = {
    "easy": {
        "name": "Easy",
        "starting_tda": 1500.0,
        "profit_multiplier": 1.0,  # 1:1 profit
        "bankruptcy_protection": True,
        "min_tda_floor": 10.0,
        "recharge_cooldown_hours": 24,
        "a_denominator": 1000.0,
        "deposit_cap": 1000.0,  # Can move up to R1,000 to play balance
    },
    "medium": {
        "name": "Medium",
        "starting_tda": 1000.0,
        "profit_multiplier": 1.02,  # 2% bonus on net profit
        "bankruptcy_protection": True,
        "min_tda_floor": 10.0,
        "recharge_cooldown_hours": 48,
        "a_denominator": 200.0,
        "deposit_cap": 500.0,  # Can move up to R500 to play balance
    },
    "hard": {
        "name": "Hard",
        "starting_tda": 500.0,
        "profit_multiplier": 1.0,  # 1:1 profit
        "bankruptcy_protection": False,  # Game Over allowed
        "min_tda_floor": 0.0,
        "recharge_cooldown_hours": None,  # No recharge available
        "a_denominator": 50.0,  # Better odds than before (was 10)
        "deposit_cap": None,  # No limit - can transfer any amount
    },
}

# Backward compatibility alias
MODE_CONFIG = CLASS_CONFIG

# Profile Badges for PP Store
PROFILE_BADGES = {
    "badge_veteran": {
        "name": "Veteran Badge",
        "description": "Shows you've been playing since the early days",
        "pp_cost": 100,
        "icon": "🎖️",
        "rarity": "common",
    },
    "badge_whale": {
        "name": "Whale Badge",
        "description": "Earned by depositing over R50,000 total",
        "pp_cost": 200,
        "icon": "🐋",
        "rarity": "rare",
        "unlock_requirement": {"type": "total_deposit", "value": 50000},
    },
    "badge_lucky": {
        "name": "Lucky Charm Badge",
        "description": "Awarded for hitting a 50x+ multiplier",
        "pp_cost": 150,
        "icon": "🍀",
        "rarity": "epic",
        "unlock_requirement": {"type": "multiplier", "value": 50},
    },
    "badge_streak": {
        "name": "Streak Master Badge",
        "description": "Unlocked for a 25-win streak",
        "pp_cost": 175,
        "icon": "🔥",
        "rarity": "epic",
        "unlock_requirement": {"type": "win_streak", "value": 25},
    },
    "badge_top10": {
        "name": "Elite Top 10 Badge",
        "description": "Exclusive badge for reaching Top 10",
        "pp_cost": 300,
        "icon": "👑",
        "rarity": "legendary",
        "unlock_requirement": {"type": "leaderboard_rank", "value": 10},
    },
    "badge_global1": {
        "name": "Champion Badge",
        "description": "Awarded for reaching #1 globally",
        "pp_cost": 500,
        "icon": "🏆",
        "rarity": "mythic",
        "unlock_requirement": {"type": "global_rank", "value": 1},
    },
    "badge_collector": {
        "name": "Theme Collector Badge",
        "description": "Own 5 or more themes",
        "pp_cost": 125,
        "icon": "🎨",
        "rarity": "rare",
        "unlock_requirement": {"type": "themes_owned", "value": 5},
    },
    "badge_night_owl": {
        "name": "Night Owl Badge",
        "description": "Play during late hours",
        "pp_cost": 75,
        "icon": "🦉",
        "rarity": "common",
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
        # Retro/Synth Themes
        {"id": "synthwave", "name": "Synthwave", "pp_cost": 300, "sacrifice": 5000, "rarity": "epic", "category": "Retro/Synth"},
        {"id": "synthwave90s", "name": "Synthwave 90s", "pp_cost": 350, "sacrifice": 7000, "rarity": "epic", "category": "Retro/Synth"},
        # Developer Favorites
        {"id": "gruvbox", "name": "Gruvbox", "pp_cost": 200, "sacrifice": 3000, "rarity": "rare", "category": "Developer"},
        {"id": "tokyo-night", "name": "Tokyo Night", "pp_cost": 250, "sacrifice": 4000, "rarity": "rare", "category": "Developer"},
        {"id": "catppuccin-frappe", "name": "Catppuccin Frappé", "pp_cost": 200, "sacrifice": 3000, "rarity": "rare", "category": "Developer"},
        {"id": "catppuccin-latte", "name": "Catppuccin Latte", "pp_cost": 200, "sacrifice": 3000, "rarity": "rare", "category": "Developer"},
        # Clean/Modern Themes
        {"id": "off-white", "name": "Off-White", "pp_cost": 150, "sacrifice": 2000, "rarity": "common", "category": "Clean/Modern"},
        {"id": "oneui", "name": "One UI", "pp_cost": 175, "sacrifice": 2500, "rarity": "common", "category": "Clean/Modern"},
        {"id": "apple-glass", "name": "Apple Glass", "pp_cost": 250, "sacrifice": 4000, "rarity": "epic", "category": "Clean/Modern"},
        # Legacy Themes
        {"id": "cyber_neon", "name": "Cyber Neon", "pp_cost": 300, "sacrifice": 5000, "rarity": "legendary", "category": "Legacy"},
        {"id": "crystal_ice", "name": "Crystal Ice", "pp_cost": 250, "sacrifice": 3000, "rarity": "epic", "category": "Legacy"},
        {"id": "phoenix_fire", "name": "Phoenix Fire", "pp_cost": 350, "sacrifice": 7000, "rarity": "legendary", "category": "Legacy"},
        {"id": "void_shadow", "name": "Void Shadow", "pp_cost": 400, "sacrifice": 10000, "rarity": "mythic", "category": "Legacy"},
        {"id": "galaxy_dust", "name": "Galaxy Dust", "pp_cost": 200, "sacrifice": 2000, "rarity": "rare", "category": "Legacy"},
        {"id": "golden_age", "name": "Golden Age", "pp_cost": 500, "sacrifice": 15000, "rarity": "mythic", "category": "Legacy"},
    ],
    "badges": [
        {"id": "badge_veteran", "name": "Veteran Badge", "pp_cost": 100, "sacrifice": 0, "rarity": "common", "icon": "🎖️"},
        {"id": "badge_whale", "name": "Whale Badge", "pp_cost": 200, "sacrifice": 0, "rarity": "rare", "icon": "🐋"},
        {"id": "badge_lucky", "name": "Lucky Charm Badge", "pp_cost": 150, "sacrifice": 0, "rarity": "epic", "icon": "🍀"},
        {"id": "badge_streak", "name": "Streak Master Badge", "pp_cost": 175, "sacrifice": 0, "rarity": "epic", "icon": "🔥"},
        {"id": "badge_top10", "name": "Elite Top 10 Badge", "pp_cost": 300, "sacrifice": 0, "rarity": "legendary", "icon": "👑"},
        {"id": "badge_global1", "name": "Champion Badge", "pp_cost": 500, "sacrifice": 0, "rarity": "mythic", "icon": "🏆"},
        {"id": "badge_collector", "name": "Theme Collector Badge", "pp_cost": 125, "sacrifice": 0, "rarity": "rare", "icon": "🎨"},
        {"id": "badge_night_owl", "name": "Night Owl Badge", "pp_cost": 75, "sacrifice": 0, "rarity": "common", "icon": "🦉"},
    ],
}

# 500+ Achievement Definitions
ACHIEVEMENTS = {
    # =============================================
    # 1. THE SPIN CYCLE (100 levels)
    # Criteria: total_games >= level * 500
    # =============================================
    **{f"spin_cycle_{level}": {
        "name": f"Spin Init {level}",
        "description": f"Complete {level * 500:,} total spins",
        "category": "spin_cycle",
        "requirement": {"type": "total_games", "value": level * 500},
        "rarity": "bronze" if level <= 20 else "silver" if level <= 40 else "gold" if level <= 60 else "platinum" if level <= 80 else "diamond",
        "shape": "hexagon" if level % 5 == 0 else "circle" if level % 3 == 0 else "star",
        "icon": "🎰",
    } for level in range(1, 101)},
    
    # =============================================
    # 2. MULTIPLIER MADNESS (100 levels)
    # Criteria: max_multiplier >= (level * 0.5) + 1.5
    # =============================================
    **{f"multiplier_madness_{level}": {
        "name": f"Luck Factor {level}",
        "description": f"Achieve a {(level * 0.5) + 1.5:.1f}x multiplier",
        "category": "multiplier",
        "requirement": {"type": "max_multiplier", "value": (level * 0.5) + 1.5},
        "rarity": "bronze" if level <= 20 else "silver" if level <= 40 else "gold" if level <= 60 else "platinum" if level <= 80 else "mythic",
        "shape": "star" if level % 10 == 0 else "diamond" if level % 5 == 0 else "hexagon",
        "icon": "⚡",
    } for level in range(1, 101)},
    
    # =============================================
    # 3. BALANCE BOSS (100 levels)
    # Criteria: max_balance >= level * 1000
    # =============================================
    **{f"balance_boss_{level}": {
        "name": f"Wealth Tier {level}",
        "description": f"Hold R{level * 1000:,} in balance",
        "category": "balance",
        "requirement": {"type": "max_balance", "value": level * 1000},
        "rarity": "bronze" if level <= 25 else "silver" if level <= 50 else "gold" if level <= 75 else "platinum" if level <= 90 else "diamond",
        "shape": "shield" if level % 10 == 0 else "hexagon" if level % 5 == 0 else "circle",
        "icon": "💰",
    } for level in range(1, 101)},
    
    # =============================================
    # 4. THE BIG SPENDER (100 levels)
    # Criteria: total_pp_spent >= level * 250
    # =============================================
    **{f"big_spender_{level}": {
        "name": f"PP Investor {level}",
        "description": f"Spend {level * 250:,} PP in the store",
        "category": "spending",
        "requirement": {"type": "total_pp_spent", "value": level * 250},
        "rarity": "bronze" if level <= 25 else "silver" if level <= 50 else "gold" if level <= 75 else "platinum" if level <= 90 else "legendary",
        "shape": "star" if level % 25 == 0 else "circle" if level % 10 == 0 else "diamond",
        "icon": "🛒",
    } for level in range(1, 101)},
    
    # =============================================
    # 5. THEME MASTER (50 levels)
    # Criteria: theme_switches >= level * 5 (5, 10, 15... 250)
    # =============================================
    **{f"theme_master_{level}": {
        "name": f"Theme Dancer {level}",
        "description": f"Switch themes {level * 5} times",
        "category": "themes",
        "requirement": {"type": "theme_switches", "value": level * 5},
        "rarity": "common" if level <= 10 else "rare" if level <= 25 else "epic" if level <= 40 else "legendary",
        "shape": "hexagon" if level % 5 == 0 else "circle",
        "icon": "🎨",
    } for level in range(1, 51)},
    
    # =============================================
    # 6. THE SA SPECIAL (50 levels)
    # Specific winning amounts for SA players
    # =============================================
    # R200 milestones
    **{f"sa_win_200_{level}": {
        "name": f"R200 Winner {level}",
        "description": f"Win exactly R200 in {level} different spins",
        "category": "sa_special",
        "requirement": {"type": "exact_win_count", "value": 200, "count": level},
        "rarity": "bronze",
        "shape": "circle",
        "icon": "🇿🇦",
    } for level in [1, 5, 10, 25, 50]},
    # R500 milestones
    **{f"sa_win_500_{level}": {
        "name": f"R500 Winner {level}",
        "description": f"Win exactly R500 in {level} different spins",
        "category": "sa_special",
        "requirement": {"type": "exact_win_count", "value": 500, "count": level},
        "rarity": "silver",
        "shape": "diamond",
        "icon": "🇿🇦",
    } for level in [1, 5, 10, 25]},
    # R1000 milestones
    **{f"sa_win_1000_{level}": {
        "name": f"R1K Winner {level}",
        "description": f"Win exactly R1,000 in {level} different spins",
        "category": "sa_special",
        "requirement": {"type": "exact_win_count", "value": 1000, "count": level},
        "rarity": "gold",
        "shape": "star",
        "icon": "🇿🇦",
    } for level in [1, 5, 10, 25]},
    # R2000 milestones
    **{f"sa_win_2000_{level}": {
        "name": f"R2K Winner {level}",
        "description": f"Win exactly R2,000 in {level} different spins",
        "category": "sa_special",
        "requirement": {"type": "exact_win_count", "value": 2000, "count": level},
        "rarity": "platinum",
        "shape": "crown",
        "icon": "🇿🇦",
    } for level in [1, 5, 10]},
    # R5000 milestones
    **{f"sa_win_5000_{level}": {
        "name": f"R5K Legend {level}",
        "description": f"Win exactly R5,000 in {level} different spins",
        "category": "sa_special",
        "requirement": {"type": "exact_win_count", "value": 5000, "count": level},
        "rarity": "mythic",
        "shape": "crown",
        "icon": "👑",
    } for level in [1, 5, 10]},
    # Single spin SA wins
    **{f"sa_single_200": {"name": "R200 Single Spin", "description": "Win exactly R200 in a single spin", "category": "sa_special", "requirement": {"type": "single_spin_win", "value": 200}, "rarity": "bronze", "shape": "circle", "icon": "💵"}},
    **{f"sa_single_500": {"name": "R500 Single Spin", "description": "Win exactly R500 in a single spin", "category": "sa_special", "requirement": {"type": "single_spin_win", "value": 500}, "rarity": "silver", "shape": "diamond", "icon": "💵"}},
    **{f"sa_single_1000": {"name": "R1K Single Spin", "description": "Win exactly R1,000 in a single spin", "category": "sa_special", "requirement": {"type": "single_spin_win", "value": 1000}, "rarity": "gold", "shape": "star", "icon": "💵"}},
    **{f"sa_single_2000": {"name": "R2K Single Spin", "description": "Win exactly R2,000 in a single spin", "category": "sa_special", "requirement": {"type": "single_spin_win", "value": 2000}, "rarity": "platinum", "shape": "star", "icon": "💵"}},
    **{f"sa_single_5000": {"name": "R5K Single Spin", "description": "Win exactly R5,000 in a single spin", "category": "sa_special", "requirement": {"type": "single_spin_win", "value": 5000}, "rarity": "mythic", "shape": "crown", "icon": "👑"}},
    
    # =============================================
    # LEGACY ACHIEVEMENTS (kept for compatibility)
    # =============================================
    # Milestone Wins
    **{f"wins_{n}": {"name": f"{n}-Win Club", "description": f"Won {n} spins", "category": "milestone", "requirement": {"type": "wins", "value": n}, "rarity": "bronze" if n <= 10 else "silver" if n <= 50 else "gold" if n <= 100 else "platinum" if n <= 500 else "diamond", "shape": "hexagon" if n % 3 == 0 else "shield" if n % 3 == 1 else "star"} for n in [1, 5, 10, 25, 50, 100, 200, 500, 1000]},
    # Difficulty-Specific
    "hard_survivor": {"name": "Hard Mode Survivor", "description": "Completed 50 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 50}, "rarity": "gold", "shape": "hexagon", "icon": "⚔️"},
    "hard_elite": {"name": "Hard Mode Elite", "description": "Completed 200 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 200}, "rarity": "platinum", "shape": "star", "icon": "🏆"},
    "hard_legend": {"name": "Hard Mode Legend", "description": "Completed 500 spins in Hard mode", "category": "difficulty", "requirement": {"type": "difficulty_games", "value": "hard", "games": 500}, "rarity": "diamond", "shape": "crown", "icon": "👑"},
    "medium_master": {"name": "Medium Mode Master", "description": "Reached R25,000 cap in Medium mode", "category": "difficulty", "requirement": {"type": "medium_cap", "value": 25000}, "rarity": "gold", "shape": "shield", "icon": "🛡️"},
    "easy_tycoon": {"name": "Easy Street Tycoon", "description": "Reached R50,000 cap in Easy mode", "category": "difficulty", "requirement": {"type": "easy_cap", "value": 50000}, "rarity": "platinum", "shape": "star", "icon": "💎"},
    # A-Value Achievements
    "first_a": {"name": "First A-Value", "description": "Hit your first A-value symbol", "category": "rarity", "requirement": {"type": "a_hits", "value": 1}, "rarity": "bronze", "shape": "hexagon", "icon": "🅰️"},
    "a_triple": {"name": "Triple A-Value", "description": "Hit 3 consecutive A-values in a single spin", "category": "rarity", "requirement": {"type": "a_streak_single", "value": 3}, "rarity": "gold", "shape": "star", "icon": "🅰️"},
    **{f"a_hits_{n}": {"name": f"{n}x A-Hitter", "description": f"Hit A-value symbols {n} times", "category": "rarity", "requirement": {"type": "a_hits", "value": n}, "rarity": "silver" if n <= 10 else "gold" if n <= 50 else "platinum", "shape": "hexagon", "icon": "🅰️"} for n in [5, 10, 25, 50, 100]},
    **{f"a_streak_{n}": {"name": f"{n}-Spin A-Streak", "description": f"Hit A-values for {n} consecutive spins", "category": "rarity", "requirement": {"type": "a_streak", "value": n}, "rarity": "platinum" if n >= 5 else "diamond", "shape": "star", "icon": "🔥"} for n in [3, 5, 10]},
    # Win Streaks
    **{f"streak_{n}": {"name": f"{n}-Win Streak", "description": f"Won {n} spins in a row", "category": "milestone", "requirement": {"type": "win_streak", "value": n}, "rarity": "bronze" if n <= 5 else "silver" if n <= 10 else "gold", "shape": "shield", "icon": "🔥"} for n in [3, 5, 10, 25, 50]},
    # Leaderboard
    "top_25": {"name": "Top 25", "description": "Reached rank 25 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 25}, "rarity": "silver", "shape": "shield", "icon": "🏅"},
    "top_10": {"name": "Top 10 Elite", "description": "Reached rank 10 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 10}, "rarity": "gold", "shape": "star", "icon": "🥇"},
    "top_5": {"name": "Top 5 Master", "description": "Reached rank 5 on any leaderboard", "category": "difficulty", "requirement": {"type": "leaderboard_rank", "value": 5}, "rarity": "platinum", "shape": "crown", "icon": "🥈"},
    "global_1": {"name": "Global Champion", "description": "Reached rank 1 on the Global leaderboard", "category": "difficulty", "requirement": {"type": "global_rank", "value": 1}, "rarity": "diamond", "shape": "crown", "icon": "🏆", "animation": "rainbow"},
    # First Times
    "first_spin": {"name": "First Spin", "description": "Completed your first spin", "category": "milestone", "requirement": {"type": "games", "value": 1}, "rarity": "bronze", "shape": "circle", "icon": "🎲"},
    "first_win": {"name": "First Win", "description": "Won your first spin", "category": "milestone", "requirement": {"type": "wins", "value": 1}, "rarity": "bronze", "shape": "circle", "icon": "🎉"},
    "first_deposit": {"name": "First Deposit", "description": "Made your first deposit", "category": "milestone", "requirement": {"type": "deposits", "value": 1}, "rarity": "bronze", "shape": "circle", "icon": "💳"},
    # Efficiency
    "big_win_small_bet": {"name": "Big Win, Small Bet", "description": "Won 100x your bet in a single spin", "category": "rarity", "requirement": {"type": "win_to_bet_ratio", "value": 100}, "rarity": "platinum", "shape": "star", "icon": "💫", "animation": "neon"},
    # Bankruptcy
    "bankruptcy_survivor": {"name": "Bankruptcy Survivor", "description": "Recovered from bankruptcy in Hard mode", "category": "difficulty", "requirement": {"type": "bankruptcy_recovery"}, "rarity": "gold", "shape": "shield", "icon": "💪"},
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
                    "total_pp_spent": "REAL NOT NULL DEFAULT 0",
                    "unlocked_assets": "TEXT NOT NULL DEFAULT '[]'",
                    "inventory": "TEXT NOT NULL DEFAULT '{}'",
                    "total_deposits_count": "INTEGER NOT NULL DEFAULT 0",
                    "max_balance": "REAL NOT NULL DEFAULT 0",
                    "total_a_hits": "INTEGER NOT NULL DEFAULT 0",
                    "max_win_streak": "INTEGER NOT NULL DEFAULT 0",
                    "max_multiplier": "REAL NOT NULL DEFAULT 0",
                    "theme_switches": "INTEGER NOT NULL DEFAULT 0",
                    "single_spin_wins": "TEXT NOT NULL DEFAULT '{}'",
                    "store_purchases": "INTEGER NOT NULL DEFAULT 0",
                    "selected_badge": "TEXT NOT NULL DEFAULT ''",
                    "selected_theme": "TEXT NOT NULL DEFAULT ''",
                    # TDA Economy System columns
                    "total_depositable_amount": "REAL NOT NULL DEFAULT 0",
                    "play_balance": "REAL NOT NULL DEFAULT 0",
                    "selected_class": "TEXT NOT NULL DEFAULT ''",
                    "tda_recharge_available_at": "TEXT",
                },
            )
            # Create transaction ledger table for TDA atomic transactions
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS transaction_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    tda_before REAL NOT NULL,
                    tda_after REAL NOT NULL,
                    play_balance_before REAL NOT NULL,
                    play_balance_after REAL NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ledger_user_id ON transaction_ledger(user_id);
                CREATE INDEX IF NOT EXISTS idx_ledger_created_at ON transaction_ledger(created_at);
                """
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
        """
        Get leaderboard rows ranked by Total Depositable Amount (TDA).
        
        TDA is the primary ranking metric in the new economy system.
        """
        if difficulty and difficulty not in CLASS_CONFIG:
            raise ValueError("Unknown difficulty.")

        sql = """
            SELECT id,
                   username,
                   COALESCE(NULLIF(display_name, ''), username) AS display_name,
                   selected_class,
                   total_depositable_amount,
                   total_deposit,
                   total_wins,
                   total_games,
                   (CASE WHEN total_games > 0 THEN CAST(total_wins AS REAL) / total_games ELSE 0 END) AS lucky_ratio
            FROM users
            WHERE selected_class <> ''
              AND total_games > 0
        """
        params = []
        if difficulty:
            sql += " AND selected_class = %s"
            params.append(difficulty)
        sql += """
            ORDER BY total_depositable_amount DESC,
                     lucky_ratio DESC,
                     total_games DESC,
                     username ASC
            LIMIT %s
        """
        params.append(limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        results = []
        for index, row in enumerate(rows, start=1):
            lucky_ratio = round(row["lucky_ratio"] or 0, 4)
            unlucky_ratio = round(1 - lucky_ratio, 4)
            # Use TDA as primary, fallback to total_deposit for legacy users
            tda = row["total_depositable_amount"] or row["total_deposit"]
            class_mode = row["selected_class"] or row.get("difficulty_mode", "easy")
            # Score = TDA + lucky_ratio (same formula as legacy score_from_values)
            score = round(tda + lucky_ratio, 4)
            results.append(
                {
                    "rank": index,
                    "userId": row["id"],
                    "username": row["username"],
                    "displayName": row["display_name"],
                    "class": class_mode,
                    "classLabel": CLASS_CONFIG[class_mode]["name"] if class_mode in CLASS_CONFIG else class_mode.title(),
                    "difficultyLabel": CLASS_CONFIG[class_mode]["name"] if class_mode in CLASS_CONFIG else class_mode.title(),
                    "tda": round(tda, 2),
                    "totalDeposit": round(tda, 2),
                    "luckyRatio": lucky_ratio,
                    "unluckyRatio": unlucky_ratio,
                    "score": score,
                    "totalWins": row["total_wins"],
                    "totalGames": row["total_games"],
                }
            )
        return results

    def _global_rank(self, user_id):
        """Get the user's rank in the global TDA leaderboard."""
        for row in self._leaderboard_rows(None, 1000):
            if row["userId"] == user_id:
                return row["rank"]
        return None

    def _class_rank(self, user_id, selected_class):
        """Get the user's rank within their class."""
        if not selected_class:
            return None
        for row in self._leaderboard_rows(selected_class, 1000):
            if row["userId"] == user_id:
                return row["rank"]
        return None

    def _unlock_context(self, row, global_rank, class_rank):
        """Build context for checking achievement unlocks."""
        total_games = row["total_games"]
        lucky_ratio = (row["total_wins"] / total_games) if total_games else 0
        # Support both legacy (difficulty_mode) and new (selected_class) columns
        selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
        return {
            "class": selected_class,
            # Backwards-compatible alias used by some unlock requirements.
            "difficulty": selected_class,
            "total_games": total_games,
            "total_wins": row["total_wins"],
            "hit_rate": lucky_ratio,
            "global_rank": global_rank,
            "class_rank": class_rank,
            # Backwards-compatible alias used by some unlock requirements.
            "mode_rank": class_rank,
            "profile_banner_status": row.get("profile_banner_status"),
            "total_depositable_amount": row.get("total_depositable_amount"),
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

    def _store_badges(self, row):
        """Get purchasable store badges that the user owns."""
        inventory = json.loads(row.get("inventory") or "{}")
        owned_badges = inventory.get("badges", [])
        store_badges = []
        for badge in STORE_ITEMS.get("badges", []):
            store_badges.append({
                "id": badge["id"],
                "name": badge["name"],
                "description": badge.get("description", ""),
                "icon": badge.get("icon", "🏅"),
                "rarity": badge.get("rarity", "common"),
                "owned": badge["id"] in owned_badges,
            })
        return store_badges

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
        """Build the profile payload with TDA economy stats."""
        global_rank = self._global_rank(row["id"])
        # Support both legacy (difficulty_mode) and new (selected_class) columns
        selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
        class_rank = self._class_rank(row["id"], selected_class)
        is_top_ten = global_rank is not None and global_rank <= 10
        lucky_ratio = (row["total_wins"] / row["total_games"]) if row["total_games"] else 0
        profile_name = row["display_name"] or row["username"]
        cosmetics = self._cosmetics(row, global_rank, class_rank)
        effective = self._effective_cosmetics(row, cosmetics)
        
        # TDA stats
        tda = row.get("total_depositable_amount") or 0
        play_balance = row.get("play_balance") or 0
        
        return {
            "profile": {
                "username": row["username"],
                "displayName": profile_name,
                "bio": row["bio"],
                "selectedSkin": effective["selectedSkin"],
                "selectedBanner": effective["selectedBanner"],
                "selectedAvatar": effective["selectedAvatar"],
                "selectedBadge": row.get("selected_badge", ""),
                "selectedTheme": row.get("selected_theme", ""),
                "avatarPath": row["custom_avatar_path"],
                "bannerPath": row["custom_banner_path"],
                "initials": initials_from_name(profile_name),
            },
            "stats": {
                "totalDeposit": round(row["total_deposit"], 2),
                "balance": round(row["balance"], 2),
                "maxDepositLimit": round(row["max_deposit_limit"], 2),
                "selectedClass": selected_class,
                "classLabel": CLASS_CONFIG[selected_class]["name"] if selected_class in CLASS_CONFIG else selected_class.title(),
                "classConfig": CLASS_CONFIG[selected_class] if selected_class in CLASS_CONFIG else None,
                "totalGames": row["total_games"],
                "totalWins": row["total_wins"],
                "hitRate": round(lucky_ratio, 4),
                "accountDays": max((utcnow() - datetime.fromisoformat(row["created_at"])).days, 0),
                "profileBannerStatus": row.get("profile_banner_status"),
                "prestigePoints": round(row["prestige_points"], 2),
                "totalPP": round(row["total_pp_earned"], 2),
            },
            "tda": {
                "total": round(tda, 2),
                "playBalance": round(play_balance, 2),
                "rechargeAvailableAt": row.get("tda_recharge_available_at"),
            },
            "ranks": {
                "globalRank": global_rank,
                "classRank": class_rank,
                "isTopTen": is_top_ten,
            },
            "badges": self._badges(row, global_rank, class_rank),
            "storeBadges": self._store_badges(row),
            "cosmetics": cosmetics,
            "achievements": self._get_achievements(row, global_rank, class_rank),
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
            selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
            return row["current_a_denominator"] < CLASS_CONFIG.get(selected_class, {}).get("a_denominator", 200)
        elif req_type == "medium_streak_mult":
            selected_class = row.get("selected_class") or row.get("difficulty_mode")
            return selected_class == "medium" and row["win_streak"] >= req.get("value", 0)
        elif req_type == "bankruptcy_recovery":
            return row["total_games"] > 0 and row.get("total_depositable_amount", 0) > 0
        # =============================================
        # NEW 500+ ACHIEVEMENT TYPES
        # =============================================
        elif req_type == "total_games":
            # Spin Cycle achievements
            return row.get("total_games", 0) >= req.get("value", 0)
        elif req_type == "max_multiplier":
            # Multiplier Madness achievements
            return row.get("max_multiplier", 0) >= req.get("value", 0)
        elif req_type == "total_pp_spent":
            # Big Spender achievements
            return row.get("total_pp_spent", 0) >= req.get("value", 0)
        elif req_type == "theme_switches":
            # Theme Master achievements
            return row.get("theme_switches", 0) >= req.get("value", 0)
        elif req_type == "exact_win_count":
            # SA Special achievements - count of exact win amounts
            single_spin_wins = json.loads(row.get("single_spin_wins") or "{}")
            win_amount = str(req.get("value", 0))
            count_needed = req.get("count", 1)
            return single_spin_wins.get(win_amount, 0) >= count_needed
        elif req_type == "single_spin_win":
            # SA Special achievements - any single spin win of exact amount
            single_spin_wins = json.loads(row.get("single_spin_wins") or "{}")
            win_amount = str(req.get("value", 0))
            return win_amount in single_spin_wins
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

    # =============================================================================
    # TDA (Total Depositable Amount) Economy System Functions
    # =============================================================================

    def _record_transaction(self, entry):
        """Record a transaction in the ledger."""
        self.conn.execute(
            """
            INSERT INTO transaction_ledger 
            (user_id, transaction_type, amount, tda_before, tda_after, 
             play_balance_before, play_balance_after, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                entry['user_id'],
                entry['transaction_type'],
                entry['amount'],
                entry['tda_before'],
                entry['tda_after'],
                entry.get('play_balance_before', 0),
                entry.get('play_balance_after', 0),
                entry.get('metadata', '{}'),
                utcnow().isoformat(),
            ),
        )

    def update_tda(self, user_id, amount, transaction_type, metadata=None):
        """
        Centralized TDA update with transaction ledger entry and profit multiplier.
        
        For Medium mode wins, automatically applies the 0.02x (2%) bonus.
        
        Args:
            user_id: User ID
            amount: Amount to add (positive) or subtract (negative) from TDA
            transaction_type: 'spin_win', 'spin_loss', 'deposit_to_play', 'recharge'
            metadata: Additional context
        
        Returns:
            dict with {tda_before, tda_after, bonus_applied, bankruptcy_protected}
        """
        with self.lock, self.conn:
            row = self._user_row(user_id)
            
            tda_before = row['total_depositable_amount']
            class_mode = row['selected_class'] or 'easy'
            config = CLASS_CONFIG.get(class_mode, CLASS_CONFIG['easy'])
            
            # Apply profit multiplier for Medium mode wins
            bonus_applied = 0
            final_amount = amount
            
            if transaction_type == 'spin_win' and config['profit_multiplier'] > 1.0:
                bonus_applied = amount * (config['profit_multiplier'] - 1.0)
                final_amount = amount + bonus_applied
                metadata = metadata or {}
                metadata['bonus_applied'] = bonus_applied
            
            # Calculate new TDA
            tda_after = tda_before + final_amount
            
            # Bankruptcy protection (Easy/Medium)
            bankruptcy_protected = False
            if config['bankruptcy_protection'] and tda_after < config['min_tda_floor']:
                tda_after = config['min_tda_floor']
                bankruptcy_protected = True
                metadata = metadata or {}
                metadata['bankruptcy_protection_triggered'] = True
            
            # Hard mode game over check
            game_over = False
            if not config['bankruptcy_protection'] and tda_after <= 0:
                tda_after = 0
                game_over = True
                metadata = metadata or {}
                metadata['game_over'] = True
            
            # Atomic update
            self.conn.execute(
                """
                UPDATE users 
                SET total_depositable_amount = %s,
                    status = %s
                WHERE id = %s
                """,
                (tda_after, f"TDA update: {transaction_type}", user_id),
            )
            
            # Record in transaction ledger
            self._record_transaction({
                'user_id': user_id,
                'transaction_type': transaction_type,
                'amount': final_amount,
                'tda_before': tda_before,
                'tda_after': tda_after,
                'play_balance_before': row['play_balance'],
                'play_balance_after': row['play_balance'],
                'metadata': json.dumps(metadata) if metadata else '{}',
            })
            
            return {
                'tda_before': tda_before,
                'tda_after': tda_after,
                'amount_changed': final_amount,
                'bonus_applied': bonus_applied,
                'bankruptcy_protected': bankruptcy_protected,
                'game_over': game_over,
            }

    def deposit_to_play(self, user_id, amount):
        """
        Move money from TDA to Play Balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        
        with self.lock, self.conn:
            row = self._user_row(user_id)
            
            if amount > row['total_depositable_amount']:
                raise ValueError(f"Insufficient TDA. Have: R{row['total_depositable_amount']:.2f}")
            
            # Check deposit cap for Easy/Medium
            class_mode = row['selected_class'] or 'easy'
            config = CLASS_CONFIG.get(class_mode, CLASS_CONFIG['easy'])
            
            if config.get('deposit_cap') is not None:
                max_deposit = min(row['total_depositable_amount'], config['deposit_cap'])
                if amount > max_deposit:
                    raise ValueError(f"Deposit cap: R{max_deposit:.2f}")
            
            # Atomic transfer
            tda_before = row['total_depositable_amount']
            play_before = row['play_balance']
            
            self.conn.execute(
                """
                UPDATE users
                SET total_depositable_amount = total_depositable_amount - %s,
                    play_balance = play_balance + %s,
                    status = %s
                WHERE id = %s
                """,
                (amount, amount, f"Moved R{amount:.2f} to play balance", user_id),
            )
            
            # Record transaction
            self._record_transaction({
                'user_id': user_id,
                'transaction_type': 'deposit_to_play',
                'amount': -amount,
                'tda_before': tda_before,
                'tda_after': tda_before - amount,
                'play_balance_before': play_before,
                'play_balance_after': play_before + amount,
            })
            
            return {
                'tda': tda_before - amount,
                'play_balance': play_before + amount,
            }

    def recharge_tda(self, user_id):
        """
        Recharge TDA for Easy/Medium mode users who hit bankruptcy.
        """
        with self.lock, self.conn:
            row = self._user_row(user_id)
            class_mode = row['selected_class'] or 'easy'
            config = CLASS_CONFIG.get(class_mode)
            
            if not config or not config['bankruptcy_protection']:
                raise ValueError("Recharge not available for this class.")
            
            if row['total_depositable_amount'] > config['min_tda_floor']:
                raise ValueError("TDA is above bankruptcy threshold.")
            
            # Check cooldown
            if row['tda_recharge_available_at']:
                recharge_time = datetime.fromisoformat(row['tda_recharge_available_at'])
                if datetime.now() < recharge_time:
                    raise ValueError(f"Recharge available at {recharge_time}")
            
            # Calculate recharge amount (50% of starting TDA)
            recharge_amount = config['starting_tda'] * 0.5
            next_recharge = datetime.now() + timedelta(hours=config['recharge_cooldown_hours'])
            
            self.conn.execute(
                """
                UPDATE users
                SET total_depositable_amount = %s,
                    tda_recharge_available_at = %s,
                    status = %s
                WHERE id = %s
                """,
                (
                    recharge_amount,
                    next_recharge.isoformat(),
                    f"TDA recharged to R{recharge_amount:.2f}",
                    user_id
                )
            )
            
            # Record transaction
            self._record_transaction({
                'user_id': user_id,
                'transaction_type': 'recharge',
                'amount': recharge_amount,
                'tda_before': row['total_depositable_amount'],
                'tda_after': recharge_amount,
                'play_balance_before': row['play_balance'],
                'play_balance_after': row['play_balance'],
                'metadata': json.dumps({'next_recharge': next_recharge.isoformat()}),
            })
            
            return {
                'recharged_amount': recharge_amount,
                'new_tda': recharge_amount,
                'next_recharge': next_recharge.isoformat(),
            }

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
        # Format boosters, cosmetics, and badges for the store
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
        for item in STORE_ITEMS.get("badges", []):
            all_items.append({
                "type": "badge",
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
        elif item_type == "badge":
            for i in STORE_ITEMS.get("badges", []):
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
            
            # Check if already owned (for themes and badges)
            inventory = json.loads(row["inventory"] or "{}")
            if item_type == "theme":
                owned_themes = inventory.get("themes", [])
                if item_id in owned_themes:
                    raise ValueError("You already own this theme.")
            elif item_type == "badge":
                owned_badges = inventory.get("badges", [])
                if item_id in owned_badges:
                    raise ValueError("You already own this badge.")
            
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
                elif item_type == "badge":
                    if "badges" not in inventory:
                        inventory["badges"] = []
                    if item["id"] not in inventory["badges"]:
                        inventory["badges"].append(item["id"])
                
                self.conn.execute(
                    """
                    UPDATE users
                    SET prestige_points = prestige_points - %s,
                        max_deposit_limit = %s,
                        inventory = %s,
                        store_purchases = store_purchases + 1,
                        total_pp_spent = total_pp_spent + %s
                    WHERE id = %s
                    """,
                    (item["pp_cost"], new_limit, json.dumps(inventory), item["pp_cost"], user_id),
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
                elif item_type == "badge":
                    if "badges" not in inventory:
                        inventory["badges"] = []
                    if item["id"] not in inventory["badges"]:
                        inventory["badges"].append(item["id"])
                
                self.conn.execute(
                    """
                    UPDATE users
                    SET prestige_points = prestige_points - %s,
                        inventory = %s,
                        store_purchases = store_purchases + 1,
                        total_pp_spent = total_pp_spent + %s
                    WHERE id = %s
                    """,
                    (item["pp_cost"], json.dumps(inventory), item["pp_cost"], user_id),
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
        """Build the game snapshot with TDA economy stats."""
        lucky_ratio = (row["total_wins"] / row["total_games"]) if row["total_games"] else 0
        denominator = row["current_a_denominator"] or 0
        global_rank = self._global_rank(row["id"])
        # Support both legacy (difficulty_mode) and new (selected_class) columns
        selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
        class_rank = self._class_rank(row["id"], selected_class)
        cosmetics = self._cosmetics(row, global_rank, class_rank)
        effective = self._effective_cosmetics(row, cosmetics)

        # TDA stats
        tda = row.get("total_depositable_amount") or 0
        play_balance = row.get("play_balance") or 0
        recharge_available_at = row.get("tda_recharge_available_at")
        class_config = CLASS_CONFIG.get(selected_class, CLASS_CONFIG["easy"])

        return {
            "authenticated": True,
            "needsClassSelection": not bool(selected_class),
            "classOptions": [
                {
                    "id": mode,
                    "name": config["name"],
                    "startingTda": config["starting_tda"],
                    "profitMultiplier": config["profit_multiplier"],
                    "bankruptcyProtection": config["bankruptcy_protection"],
                    "depositCap": config["deposit_cap"],
                }
                for mode, config in CLASS_CONFIG.items()
            ],
            "user": {
                "id": row["id"],
                "username": row["username"],
                "displayName": row["display_name"] or row["username"],
                "selectedClass": selected_class,
                "classLabel": class_config["name"],
                "classConfig": class_config,
                # Play balance is the betting balance in TDA system
                "balance": round(play_balance, 2),
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
                "profileBannerStatus": row.get("profile_banner_status"),
                "isTopTen": bool(global_rank and global_rank <= 10),
                "prestigePoints": round(row["prestige_points"], 2),
                "totalPP": round(row["total_pp_earned"], 2),
                "inventory": json.loads(row["inventory"] or "{}"),
                "depositCap": class_config["deposit_cap"],
            },
            # Top-level balance = play_balance (what you can bet with)
            "balance": round(play_balance, 2),
            "lastSpin": json.loads(row["last_spin"]),
            "lastWin": round(row["last_win"], 2),
            "lastNet": round(row["last_net"], 2),
            "winningLines": json.loads(row["winning_lines"]),
            "status": row["status"],
            "limits": {
                "minBet": MIN_BET,
                "maxLines": LINES,
            },
            "tda": {
                "total": round(tda, 2),
                "playBalance": round(play_balance, 2),
                "rechargeAvailableAt": recharge_available_at,
            },
            "classSelection": {
                "canChange": True,
                "current": selected_class or "",
                "historyResetsOnChange": True,
                "classRank": class_rank,
            },
        }

    def guest_snapshot(self):
        """Return a snapshot for unauthenticated users."""
        return {
            "authenticated": False,
            "needsClassSelection": False,
            "classOptions": [
                {
                    "id": mode,
                    "name": config["name"],
                    "startingTda": config["starting_tda"],
                    "profitMultiplier": config["profit_multiplier"],
                    "bankruptcyProtection": config["bankruptcy_protection"],
                    "depositCap": config["deposit_cap"],
                }
                for mode, config in CLASS_CONFIG.items()
            ],
            "user": None,
            "balance": 0,
            "lastSpin": DEFAULT_GRID,
            "lastWin": 0,
            "lastNet": 0,
            "winningLines": [],
            "status": "Sign in and choose a class to begin.",
            "limits": {"minBet": MIN_BET, "maxLines": LINES},
            "tda": None,
            "classSelection": None,
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

    def select_class(self, user_id, class_name):
        """Select a class (easy/medium/hard) in the TDA economy system.
        
        This is a major economy change - switching classes resets:
        - TDA (Total Depositable Amount)
        - Play balance
        - All game statistics
        """
        class_name = class_name.lower()
        if class_name not in CLASS_CONFIG:
            raise ValueError("Please choose easy, medium, or hard.")
        config = CLASS_CONFIG[class_name]
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            previous_class = row.get("selected_class") or row.get("difficulty_mode")
            
            # Check if already selected
            if previous_class == class_name:
                snapshot = self._snapshot(row)
                snapshot["status"] = f"You're already in {config['name']} class."
                return snapshot

            # History always resets when switching classes
            history_reset = bool(previous_class and previous_class != class_name)
            if history_reset:
                self.conn.execute("DELETE FROM spin_results WHERE user_id = %s", (user_id,))
                status = (
                    f"Switched from {CLASS_CONFIG.get(previous_class, {}).get('name', previous_class)} "
                    f"to {config['name']}. "
                    f"Your Vault was reset."
                )
            else:
                status = f"{config['name']} class selected. Your Vault starts with R{config['starting_tda']:.2f}."
            
            # Initialize with class settings
            self.conn.execute(
                """
                UPDATE users
                SET selected_class = %s,
                    difficulty_mode = %s,  -- Keep for legacy compatibility
                    total_depositable_amount = %s,
                    play_balance = %s,
                    tda_recharge_available_at = %s,
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
                    class_name,
                    class_name,  # Also set difficulty_mode for legacy
                    config["starting_tda"],
                    0,  # play_balance starts at 0; user deposits from TDA
                    None,  # No cooldown on first selection
                    config["starting_tda"] * 10,  # Max deposit 10x starting TDA
                    config["a_denominator"],
                    json.dumps(DEFAULT_GRID),
                    status,
                    user_id,
                ),
            )
            updated = self._user_row(user_id)
        snapshot = self._snapshot(updated)
        snapshot["historyReset"] = history_reset
        snapshot["previousClass"] = previous_class or ""
        return snapshot

    def add_funds(self, user_id, amount):
        """Deposit funds into the user's TDA.

        Per TDA architecture:
        - Funds go directly to TDA (total_depositable_amount)
        - Deposits count towards total_deposit for leaderboard scoring
        - User then separately calls deposit_to_play() to move funds to play balance
        """
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero.")
        pp_earned = amount / PP_RATE
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")

            # Check class selection
            selected_class = row.get("selected_class") or row.get("difficulty_mode")
            if not selected_class:
                raise ValueError("Choose a class before depositing.")

            # Check deposit limit
            max_deposit_limit = row.get("max_deposit_limit", 10000)
            if amount > max_deposit_limit:
                raise ValueError(
                    f"Deposit amount cannot exceed your current limit of R{max_deposit_limit:.2f}."
                )

            new_total_deposits = row["total_deposits_count"] + 1
            new_max_balance = max(row["max_balance"], amount)

            # Deposit goes to TDA only — user transfers to play_balance separately
            self.conn.execute(
                """
                UPDATE users
                SET total_depositable_amount = total_depositable_amount + %s,
                    total_deposit = total_deposit + %s,
                    prestige_points = prestige_points + %s,
                    total_pp_earned = total_pp_earned + %s,
                    total_deposits_count = %s,
                    max_balance = %s,
                    status = %s
                WHERE id = %s
                """,
                (amount, amount, pp_earned, pp_earned, new_total_deposits, new_max_balance,
                 f"Deposited R{amount:.2f} to your Vault. +{pp_earned:.1f} PP earned! Use 'Deposit to Play' to move funds.", user_id),
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
        """
        Execute a spin using the TDA economy system.
        
        Flow:
        1. Deduct bet from play_balance
        2. Calculate winnings
        3. Apply net result (winnings - bet) to TDA via update_tda()
        4. update_tda() handles Medium Mode 2% bonus automatically
        """
        if bet_per_line < MIN_BET:
            raise ValueError(f"Bet per line must be at least R{MIN_BET}.")
        
        with self.lock, self.conn:
            row = self._user_row(user_id)
            if not row:
                raise ValueError("User not found.")
            
            # Use selected_class for TDA system (fallback to difficulty_mode for legacy)
            class_mode = row["selected_class"] or row["difficulty_mode"]
            if not class_mode:
                raise ValueError("Choose a class before spinning.")

            total_bet = bet_per_line * LINES
            
            # TDA System: Bet from play_balance
            if total_bet > row["play_balance"]:
                raise ValueError("You cannot bet more than your play balance. Deposit from your TDA first.")
            
            # Get class config
            config = CLASS_CONFIG.get(class_mode, CLASS_CONFIG['easy'])
            denominator = row["current_a_denominator"] or config["a_denominator"]
            
            # Generate spin result
            columns = generate_grid(denominator)
            winnings, winning_lines = check_winnings(columns, bet_per_line)
            
            # Calculate net result
            net_result = winnings - total_bet
            
            # Update game stats
            total_games = row["total_games"] + 1
            total_wins = row["total_wins"] + (1 if winnings > 0 else 0)
            previous_streak = row["win_streak"]
            win_streak = previous_streak + 1 if winnings > 0 else 0
            max_win_streak = max(row["max_win_streak"], win_streak)
            banner_status = row["profile_banner_status"]
            consecutive_a_hits = row["consecutive_a_hits"]
            notes = []
            
            # Count A-hits
            a_count = sum(1 for col in columns for sym in col if sym == "A")
            total_a_hits = row["total_a_hits"] + a_count
            
            # Calculate multiplier
            multiplier = (winnings / total_bet) if total_bet > 0 else 0
            max_multiplier = max(row.get("max_multiplier") or 0, multiplier)
            
            # Track exact win amounts
            single_spin_wins = json.loads(row.get("single_spin_wins") or "{}")
            if winnings > 0:
                win_key = str(int(winnings))
                single_spin_wins[win_key] = single_spin_wins.get(win_key, 0) + 1
            
            # Update play_balance (deduct bet, winnings go to TDA)
            new_play_balance = row["play_balance"] - total_bet
            
            # Apply TDA update (handles 2% Medium bonus, bankruptcy protection)
            transaction_type = 'spin_win' if net_result > 0 else 'spin_loss'
            tda_result = self.update_tda(
                user_id, 
                net_result, 
                transaction_type,
                metadata={
                    'bet': total_bet,
                    'winnings': winnings,
                    'net_result': net_result,
                    'winning_lines': winning_lines,
                }
            )
            
            # Handle difficulty-specific logic
            next_denominator = denominator
            
            if class_mode == "hard":
                next_denominator = CLASS_CONFIG["hard"]["a_denominator"]
                if check_consecutive_a(columns):
                    consecutive_a_hits += 1
                    banner_status = "a_streak"
                    notes.append("Consecutive A banner unlocked!")
            elif class_mode == "medium":
                if winnings > 0:
                    next_denominator = CLASS_CONFIG["medium"]["a_denominator"]
                else:
                    next_denominator = max(10.0, round(denominator * 0.99, 2))
            elif class_mode == "easy":
                next_denominator = CLASS_CONFIG["easy"]["a_denominator"]
            
            # Build status message
            if winnings > 0:
                status = f"You won R{winnings:.2f}! Net change: R{net_result:.2f}."
                if tda_result['bonus_applied'] > 0:
                    status += f" (+R{tda_result['bonus_applied']:.2f} Medium bonus!)"
            else:
                status = f"No match. Net change: R{net_result:.2f}."
            
            if tda_result.get('bankruptcy_protected'):
                status += " TDA protected by bankruptcy floor."
            if tda_result.get('game_over'):
                status = "Game Over! Your TDA is depleted."
            
            # Update user record
            self.conn.execute(
                """
                UPDATE users
                SET play_balance = %s,
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
                    max_multiplier = %s,
                    single_spin_wins = %s
                WHERE id = %s
                """,
                (
                    round(new_play_balance, 2),
                    round(next_denominator, 2),
                    total_games,
                    total_wins,
                    win_streak,
                    consecutive_a_hits,
                    banner_status,
                    json.dumps(columns),
                    round(winnings, 2),
                    round(net_result, 2),
                    json.dumps(winning_lines),
                    status,
                    total_a_hits,
                    max_win_streak,
                    round(max_multiplier, 4),
                    json.dumps(single_spin_wins),
                    user_id,
                ),
            )
            
            # Check achievements
            updated_row = self._user_row(user_id)
            global_rank = self._global_rank(user_id)
            class_rank = self._class_rank(user_id, class_mode)
            unlocked_ids, newly_unlocked = self._check_and_unlock_achievements(updated_row, global_rank, class_rank)
            
            if newly_unlocked:
                self.conn.execute(
                    "UPDATE users SET unlocked_assets = %s WHERE id = %s",
                    (json.dumps(list(unlocked_ids)), user_id),
                )
                achievement_notes = [f"🏆 {ACHIEVEMENTS[a]['name']}!" for a in newly_unlocked[:3]]
                if len(newly_unlocked) > 3:
                    achievement_notes.append(f"+{len(newly_unlocked) - 3} more!")
                notes.extend(achievement_notes)
            
            # Record spin result
            self.conn.execute(
                """
                INSERT INTO spin_results (
                    user_id, difficulty_mode, win_amount, bet_amount,
                    luck_multiplier, deposit_total, deposit_tier,
                    total_deposit_snapshot, a_denominator_snapshot, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, class_mode, round(winnings, 2), round(total_bet, 2),
                    round(multiplier, 4),
                    round(tda_result['tda_after'], 2),  # Use TDA as deposit for history
                    class_mode,
                    round(tda_result['tda_after'], 2),
                    round(denominator, 2),
                    isoformat(utcnow()),
                ),
            )
            
            updated = self._user_row(user_id)
        
        snapshot = self._snapshot(updated)
        snapshot["bet"] = {"lines": LINES, "betPerLine": bet_per_line, "total": round(total_bet, 2)}
        snapshot["bonus_applied"] = tda_result['bonus_applied']
        snapshot["tda"] = tda_result['tda_after']
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
        selected_badge = str(payload.get("selectedBadge", "")).strip()
        selected_theme = str(payload.get("selectedTheme", "")).strip()
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
            selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
            class_rank = self._class_rank(user_id, selected_class)
            cosmetics = self._cosmetics(row, global_rank, class_rank)
            valid = self._valid_cosmetic_ids(cosmetics)
            effective = self._effective_cosmetics(row, cosmetics)
            if selected_skin and selected_skin not in valid["skins"]:
                raise ValueError("That skin is not unlocked for this profile.")
            if selected_banner and selected_banner not in valid["banners"]:
                raise ValueError("That banner is not unlocked for this profile.")
            if selected_avatar and selected_avatar not in valid["avatars"]:
                raise ValueError("That avatar is not unlocked for this profile.")

            # Validate selected badge - must be owned
            inventory = json.loads(row.get("inventory") or "{}")
            owned_badges = inventory.get("badges", [])
            if selected_badge and selected_badge not in owned_badges:
                raise ValueError("You don't own that badge.")
            
            # Track theme switches for achievements
            theme_switch_increment = 0
            current_theme = row.get("selected_theme", "")
            if selected_theme and selected_theme != current_theme:
                # Check if the new theme is valid (owned or default)
                owned_themes = inventory.get("themes", [])
                default_themes = ["apple", "dark", "light"]
                if selected_theme not in default_themes and selected_theme not in owned_themes:
                    raise ValueError("You don't own that theme.")
                theme_switch_increment = 1

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
                    status = %s,
                    selected_badge = %s,
                    selected_theme = %s,
                    theme_switches = theme_switches + %s
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
                    selected_badge,
                    selected_theme,
                    theme_switch_increment,
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


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """
    Ensure API endpoints always return JSON, even on unexpected exceptions.
    Without this, Flask returns an HTML error page, which causes frontend
    `response.json()` / `JSON.parse()` failures.
    """
    if not request.path.startswith("/api/"):
        # For non-API routes, fall back to Flask's default error rendering.
        raise error

    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code

    app.logger.exception("Unhandled API exception")
    return jsonify({"error": "Internal server error."}), 500


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


@app.post("/api/select-class")
def api_select_class():
    """API endpoint for selecting a class in the TDA economy system."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before choosing a class."}), 401
    payload = request.get_json(force=True)
    # Accept both 'class' and 'difficulty' for backward compatibility
    class_name = str(payload.get("class") or payload.get("difficulty", ""))
    snapshot = store.select_class(user_id, class_name)
    return jsonify(snapshot)

# Keep backward compatibility endpoint
@app.post("/api/select-difficulty")
def api_select_difficulty():
    """Legacy endpoint - redirects to select_class."""
    return api_select_class()


@app.post("/api/deposit")
def api_deposit():
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    snapshot = store.add_funds(user_id, float(payload.get("amount", 0)))
    return jsonify(snapshot)


@app.post("/api/deposit-to-play")
def api_deposit_to_play():
    """Transfer funds from TDA to play balance."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    payload = request.get_json(force=True)
    amount = float(payload.get("amount", 0))
    try:
        result = store.deposit_to_play(user_id, amount)
        # Return updated snapshot
        snapshot = store.current_user(user_id)
        snapshot["depositResult"] = result
        return jsonify(snapshot)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/recharge")
def api_recharge():
    """Recharge TDA for Easy/Medium mode users after cooldown."""
    user_id = require_user()
    if not user_id:
        return jsonify({"error": "You need to sign in before using this feature."}), 401
    try:
        result = store.recharge_tda(user_id)
        snapshot = store.current_user(user_id)
        snapshot["rechargeResult"] = result
        return jsonify(snapshot)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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
        selected_class = row.get("selected_class") or row.get("difficulty_mode", "easy")
        class_rank = store._class_rank(user_id, selected_class)
        achievements = store._get_achievements(row, global_rank, class_rank)
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
