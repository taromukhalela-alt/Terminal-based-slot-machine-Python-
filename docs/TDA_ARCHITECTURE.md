# TDA (Total Depositable Amount) Economy Architecture

## Overview

The TDA economy system is a new economy model for the Pixel Slot game that provides:
- **Bankruptcy protection** for careful players
- **Tiered class system** (Easy/Medium/Hard) with different risk/reward profiles
- **Profit bonuses** for skilled players (Medium Mode +2%)
- **Transparent transaction ledger** for tracking all economy changes

## Class Configuration

### Easy Mode
- **Starting TDA**: R1,500
- **Profit Multiplier**: 1.0 (1:1 profit)
- **Bankruptcy Protection**: Yes (R10 minimum floor)
- **Recharge Cooldown**: 24 hours
- **A-Denominator**: 200 (very favorable odds)
- **Deposit Cap**: R1,000 per transfer

### Medium Mode
- **Starting TDA**: R1,000
- **Profit Multiplier**: 1.02 (+2% bonus on net profits)
- **Bankruptcy Protection**: Yes (R10 minimum floor)
- **Recharge Cooldown**: 48 hours
- **A-Denominator**: 500 (moderate odds)
- **Deposit Cap**: R500 per transfer

### Hard Mode
- **Starting TDA**: R500
- **Profit Multiplier**: 1.0 (1:1 profit)
- **Bankruptcy Protection**: No (can reach R0)
- **Recharge Cooldown**: None (no recharge available)
- **A-Denominator**: 1000 (moderate odds, better than before)
- **Deposit Cap**: None (unlimited transfers)

## Core Concepts

### TDA (Total Depositable Amount)
The core currency that represents your total wealth in the game. It serves as:
- The ranking metric for the leaderboard
- The source of funds for deposits to play balance
- The protected balance (with floor in Easy/Medium modes)

### Play Balance
The amount available for immediate betting. Flow:
1. Deposit from TDA to Play Balance
2. Use Play Balance to place bets
3. Winnings go back to TDA (via `update_tda()`)

### Transaction Ledger
All economy changes are recorded in the `transaction_ledger` table:
- `spin_win`: Net profit from a winning spin
- `spin_loss`: Net loss from a losing spin
- `deposit_to_play`: Moving funds from TDA to play balance
- `recharge`: Using recharge feature to restore TDA

## Key Functions

### `update_tda(user_id, amount, transaction_type, metadata=None)`
Updates TDA based on net spin result:
- Positive `amount`: Add to TDA (winnings)
- Negative `amount`: Subtract from TDA (losses)
- **Medium Mode**: Applies +2% bonus automatically if profit
- **Bankruptcy Protection**: Ensures TDA never drops below floor

### `deposit_to_play(user_id, amount)`
Moves funds from TDA to play balance:
- Respects class deposit cap
- Records transaction in ledger
- Returns error if insufficient TDA

### `select_class(user_id, class_name)`
Allows users to choose their class:
- Resets all game statistics on switch
- Initializes TDA and play balance with class starting amount
- Sets appropriate deposit limits

### `recharge_tda(user_id)`
Recharges TDA using accumulated balance:
- Only available after cooldown period
- Transfers accumulated `balance` back to TDA
- Updates cooldown timer

## Database Schema

### New User Columns
```sql
selected_class TEXT,           -- 'easy', 'medium', or 'hard'
total_depositable_amount REAL, -- TDA balance
play_balance REAL,            -- Available for betting
tda_recharge_available_at TEXT, -- ISO timestamp for recharge cooldown
```

### Transaction Ledger Table
```sql
CREATE TABLE transaction_ledger (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    amount REAL NOT NULL,
    tda_before REAL NOT NULL,
    tda_after REAL NOT NULL,
    play_balance_before REAL NOT NULL,
    play_balance_after REAL NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
```

## API Changes

### New Endpoints
- `POST /api/select-class` - Select class (replaces select-difficulty)
- `POST /api/recharge` - Recharge TDA (to be implemented in frontend)

### Updated Endpoints
- `POST /api/spin` - Now uses TDA economy
- `GET /api/profile` - Includes TDA stats
- `GET /api/snapshot` - Includes TDA stats

## Frontend Integration

### The Vault Component
A new UI element showing:
- Current TDA with animated counter
- Play balance for betting
- Recharge button with cooldown timer
- Class badge and multiplier info

### Class Selection Modal
Displayed on first login or when changing class:
- Shows all class options with descriptions
- Explains risk/reward tradeoffs
- Warns about history reset on switch

### Betting Interface
- Shows play balance instead of main balance
- Displays TDA reference nearby
- "Deposit to Play" button to transfer funds

## Migration Strategy

### Backward Compatibility
- `difficulty_mode` column still exists for legacy data
- `MODE_CONFIG` is aliased to `CLASS_CONFIG`
- `select_difficulty()` calls `select_class()` internally

### Data Migration
For existing users:
- `selected_class` starts as NULL
- Falls back to `difficulty_mode` if `selected_class` is NULL
- Users without a class are prompted to select one

## Security Considerations

1. **Server-side validation**: All TDA operations happen server-side
2. **Atomic updates**: TDA changes use database transactions
3. **Audit trail**: All changes recorded in transaction ledger
4. **Cooldown enforcement**: Recharge cooldowns enforced server-side

## Testing Checklist

- [ ] New user can select a class
- [ ] TDA initializes correctly for each class
- [ ] Deposits move funds correctly between TDA and play balance
- [ ] Spins deduct from play balance and update TDA
- [ ] Medium Mode applies 2% bonus correctly
- [ ] Bankruptcy protection works in Easy/Medium modes
- [ ] Hard Mode allows TDA to reach zero
- [ ] Leaderboard ranks by TDA
- [ ] Recharge feature works after cooldown
- [ ] Class switch resets statistics
- [ ] Transaction ledger records all operations
