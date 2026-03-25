# Pixel Slot Studio

I built Pixel Slot Studio as a full web-based slot machine experience with authentication, persistent profiles, leaderboard tiers, badges, and creator pages. I wanted it to feel playful and polished while still running on a very lightweight Python stack.

I also made this project on a 4GB RAM Intel Celeron Mercer Windows tablet that is actually running Arch Linux with the ML4W dotfiles, which makes this build even more personal to me.

## What I Built

- A browser-based 3x3 slot machine with smooth reel animation
- Secure user registration, login, logout, and cookie-based session management
- Persistent SQLite storage for users, spins, profile data, and leaderboard history
- Tiered leaderboards for top single-spin multipliers and frequent lucky winners
- A polished profile system with editable display name and bio
- Server-side badges for luck, unlucky streaks, grind time, and leaderboard rank
- Top 10 cosmetic unlocks for exclusive skins, banners, and preset profile pics
- Custom avatar and banner uploads for player profiles
- A dedicated creator page for my links, support section, and project backstory

## Tech Stack

- Python 3
- Built-in Python HTTP server
- SQLite
- HTML
- CSS
- JavaScript

## Project Structure

```text
.
├── main.py
├── README.md
├── slots.db
└── web
    ├── app.js
    ├── creator.html
    ├── index.html
    ├── leaderboard.html
    ├── leaderboard.js
    ├── profile.html
    ├── profile.js
    ├── styles.css
    └── uploads
```

## Features

### Gameplay

- 3x3 slot machine layout
- All 3 horizontal lines are always active
- Minimum bet per line: `R1`
- Maximum bet per line: `R300`
- Maximum single deposit: `R3000`
- Server-side win calculation and payout validation

### Accounts

- User registration and login
- Session persistence with secure cookies
- Authenticated spins only for leaderboard recording

### Profiles

- Editable display name and bio
- Custom avatar uploads
- Custom banner uploads
- Unlockable preset skins, banners, and profile pics
- Elite cosmetics for users in the top 10
- Badge system based on luck, unlucky runs, grind time, and leaderboard presence

### Leaderboards

- Tier A: under `R200`
- Tier B: `R200` to `R5000`
- Tier C: over `R5000`
- Top 100 highest single-spin multipliers per tier
- Top 100 most frequent lucky winners per tier

## Running It Locally

```bash
python main.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Notes

- I kept the backend lightweight and dependency-free by using Python’s standard library instead of Flask or Django.
- Leaderboard tiering, win calculations, badge logic, and unlock checks all happen on the server.
- Uploaded profile images are stored locally in `web/uploads`.

## License

This project is licensed under the MIT License. See [LICENSE](/home/valtos/python%20project/LICENSE).
