# Import randomness for slot selection.
import random

# Betting limits used during user input validation.
MAX_LINES = 3
MAX_BET =100
MIN_BET = 1

# Slot machine dimensions.
ROWS = 3
COLS = 3

# Number of each symbol available in the symbol pool.
symbol_count = {
    "A" : 2,
    "B" : 4,
    "C" : 6,
    "D" : 8
}

symbol_value = {
    # Rebalanced payouts so common wins still feel rewarding
    # while rarer symbols remain the highest-value outcomes.
    "A" : 25,
    "B" : 15,
    "C" : 10,
    "D" : 8
}

def check_winnings(columns, lines, bet, values):
    winnings = 0
    winning_lines = []
    for line in range(lines):
        symbol = columns[0][line]
        for column in columns:
            symbol_to_check = column[line]
            if symbol != symbol_to_check:
                break
        else:
            winnings += values[symbol] * bet
            winning_lines.append(line + 1)
    
    return winnings, winning_lines

# Build a random slot result as a list of columns.
def get_slot_machine_spin(ROWS, COLS,  symbols):
    # Expand the symbol counts into a flat pool (e.g., ["A", "A", "B", ...]).
    all_symbols = []
    for symbol, symbol_count in symbols.items():
        for _ in range(symbol_count):
            all_symbols.append(symbol)
    
    # Generate each column by drawing symbols without replacement per column.
    columns = []
    for col in range(COLS):
        column = []
        current_symbols = all_symbols[:]
        for row in range(ROWS):
            value = random.choice(current_symbols)
            current_symbols.remove(value)
            column.append(value)
        
        columns.append(column)

    # Return the completed slot columns.
    return columns

# Print the slot machine row-by-row with separators.
def print_slot_machine(columns):
    for row in range(len(columns[0])):
        for i, column in enumerate(columns):
            if i != len(columns) -1:
                print(column[row], end=" | ")
            else:
                print(column[row])

# Ask user for deposit amount and validate it.
def deposit():
    while True:
        amount = input("What would you like to deposit?    R")
        if amount.isdigit():
            amount = int(amount)
            if amount > 0:
                break
            else:
                print("Amount must be greater thsan 0")
        else:
            print("Please enter a valid number.")
    
    # Return the validated deposit.
    return amount

# Ask user for number of lines and validate input.
def get_number_of_lines():
    while True:
        lines = input("Enter the number of lines to bet on (1-" + str(MAX_LINES) + ")")
        if lines.isdigit():
            lines = int(lines)
            if 1 <= lines <= MAX_LINES:
                break
            else:
                print("Enter a valid number of lines")
        else:
            print("Please enter a number")
    # Return the validated line count.
    return lines

# Ask user for bet amount per line and validate against min/max.
def get_bet(balance, lines):
    max_bet_for_round = min(MAX_BET, balance // lines)
    while True:
        amount = input("What would you like to bet? R")
        if amount.isdigit():
            amount = int(amount)
            if MIN_BET <= amount <= max_bet_for_round:
                break
            else:
                print(f"Bet amount must be between R{MIN_BET} and R{max_bet_for_round} for {lines} lines.")
        else:
            print("Please enter a number.")
    # Return the validated bet amount.
    return amount

def spin(balance):
    lines  = get_number_of_lines()
    if balance < MIN_BET * lines:
        print(f"You need at least R{MIN_BET * lines} to bet on {lines} lines.")
        return 0
    # Keep prompting until total bet is within available balance.
    while True:
        bet= get_bet(balance, lines)
        total_bet = bet * lines
        if total_bet > balance:
            print(f"You do not have that kind of money, you actually have R{balance}")
        else:
            break
    # Show betting summary.
    print(f"You are betting R{bet} on {lines} lines. Total is equal to:  R{total_bet}")
    
    # Generate and display slot machine output.
    slots = get_slot_machine_spin(ROWS, COLS, symbol_count)
    print_slot_machine(slots)
    winnings, winning_lines = check_winnings(slots, lines, bet, symbol_value)
    print(f"You won R{winnings}")
    print(f"You won on:", *winning_lines)
    return winnings - total_bet

# Main game flow: gather input, validate affordability, spin, and print.
def main():
    # Collect starting balance and selected lines.
    balance = deposit()
    while True:
        print(f"Current balance is R{balance}")
        user = input("Press enter to spin(q to quit).")
        if user == "q":
            break
        balance += spin(balance)
    print(f"You left with R{balance}")
# Start the program.
main()
