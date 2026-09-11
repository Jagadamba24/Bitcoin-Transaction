import hashlib
import sqlite3
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

# Generate keys
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

# Database
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
sender TEXT,
receiver TEXT,
amount INTEGER,
signature TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS spent(
txid INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS accounts(
username TEXT PRIMARY KEY COLLATE NOCASE,
balance INTEGER
)
""")

conn.commit()


def create_transaction(sender, receiver, amount):
    message = f"{sender}->{receiver}:{amount}".encode()

    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    return message, signature


def record_transaction(sender, receiver, amount, signature):
    sig_hex = signature.hex() if isinstance(signature, bytes) else str(signature)
    cursor.execute(
        "INSERT INTO transactions(sender,receiver,amount,signature) VALUES (?,?,?,?)",
        (sender, receiver, amount, sig_hex)
    )
    conn.commit()
    return cursor.lastrowid


class VerifyResult:
    def __init__(self, valid, message=""):
        self.valid = valid
        self.message = message

    def __bool__(self):
        return bool(self.valid)

    def __repr__(self):
        return f"<VerifyResult valid={self.valid} message='{self.message}'>"


def verify_input(sender, amount):
    if not sender or str(sender).strip() == "":
        return VerifyResult(False, "Sender name cannot be empty.")

    if amount <= 0:
        return VerifyResult(False, f"Transaction amount must be positive (> 0). Received: {amount}.")

    return VerifyResult(True, "Input Verified ✔")


def verify_signature(message, signature):
    try:
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False


def get_user_balance(username):
    cursor.execute("SELECT balance FROM accounts WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    row = cursor.fetchone()
    return row[0] if row else 0


def set_account_balance(username, amount):
    clean_user = username.strip()
    cursor.execute(
        "INSERT OR REPLACE INTO accounts(username, balance) VALUES(?, ?)",
        (clean_user, amount)
    )
    conn.commit()
    # Create and record funding block on the blockchain
    message, signature = create_transaction("COINBASE_MINT", clean_user, amount)
    add_block(message)
    record_transaction("COINBASE_MINT", clean_user, amount, signature)
    return amount



def deduct_balance(username, amount):
    clean_user = username.strip()
    current = get_user_balance(clean_user)
    new_balance = max(0, current - amount)
    cursor.execute("UPDATE accounts SET balance = ? WHERE LOWER(username) = LOWER(?)", (new_balance, clean_user))
    conn.commit()
    return new_balance


def credit_balance(username, amount):
    clean_user = username.strip()
    cursor.execute("SELECT balance FROM accounts WHERE LOWER(username) = LOWER(?)", (clean_user,))
    row = cursor.fetchone()
    if row:
        new_balance = row[0] + amount
        cursor.execute("UPDATE accounts SET balance = ? WHERE LOWER(username) = LOWER(?)", (new_balance, clean_user))
    else:
        new_balance = amount
        cursor.execute("INSERT INTO accounts(username, balance) VALUES(?, ?)", (clean_user, amount))
    conn.commit()
    return new_balance


def get_wallet_balances():
    """
    Returns live account balances for all participants who have set a balance or received funds.
    """
    cursor.execute("SELECT username, balance FROM accounts WHERE balance > 0 ORDER BY balance DESC")
    rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}


def double_spending(txid=None, sender=None, receiver=None, amount=None):
    clean_sender = sender.strip() if sender else ""
    clean_receiver = receiver.strip() if receiver else ""

    # Check 1: Sending the EXACT same amount to the exact same receiver is detected as double-spending
    if clean_sender and clean_receiver and amount and clean_sender.upper() != "COINBASE_MINT":
        cursor.execute(
            "SELECT id FROM transactions WHERE LOWER(sender) = LOWER(?) AND LOWER(receiver) = LOWER(?) AND amount = ?",
            (clean_sender, clean_receiver, amount)
        )
        duplicate_tx = cursor.fetchone()
        if duplicate_tx:
            return False, f"Sender '{clean_sender}' has already sent {amount} to '{clean_receiver}' in Tx #{duplicate_tx[0]}!"

    # Check 2: Check if sender has enough balance
    if clean_sender and amount and clean_sender.upper() != "COINBASE_MINT":
        sender_bal = get_user_balance(clean_sender)
        if sender_bal <= 0:
            return False, f"Sender '{clean_sender}' has already spent all available funds (Balance is 0)!"
        if amount > sender_bal:
            return False, f"Sender '{clean_sender}' only has {sender_bal} balance, cannot spend {amount}!"

    # Check 3: Check if explicit txid was already spent
    if txid is not None:
        cursor.execute("SELECT * FROM spent WHERE txid=?", (txid,))
        if cursor.fetchone():
            return False, f"Transaction Output #{txid} has already been spent!"

        cursor.execute("INSERT INTO spent(txid) VALUES (?)", (txid,))
        conn.commit()

    return True, "Double Spending Check Passed ✔"


def add_block(message):
    block_hash = hashlib.sha256(message).hexdigest()
    return block_hash


def get_ledger():
    cursor.execute("SELECT id, sender, receiver, amount, signature FROM transactions ORDER BY id ASC")
    rows = cursor.fetchall()
    
    cursor.execute("SELECT txid FROM spent")
    spent_set = set(row[0] for row in cursor.fetchall())
    
    ledger = []
    for row in rows:
        ledger.append({
            "id": row[0],
            "sender": row[1],
            "receiver": row[2],
            "amount": row[3],
            "signature": row[4],
            "is_spent": row[0] in spent_set
        })
    return ledger


def get_spent_ids():
    cursor.execute("SELECT txid FROM spent ORDER BY txid ASC")
    return [row[0] for row in cursor.fetchall()]


def get_unspent_ids():
    cursor.execute("SELECT id FROM transactions ORDER BY id ASC")
    all_ids = [row[0] for row in cursor.fetchall()]
    spent_set = set(get_spent_ids())
    return [txid for txid in all_ids if txid not in spent_set]


def delete_account(username):
    if not username:
        return
    clean_user = username.strip()
    cursor.execute("DELETE FROM accounts WHERE LOWER(username) = LOWER(?)", (clean_user,))
    cursor.execute("DELETE FROM transactions WHERE LOWER(sender) = LOWER(?) OR LOWER(receiver) = LOWER(?)", (clean_user, clean_user))
    conn.commit()


def reset_database():
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM spent")
    cursor.execute("DELETE FROM accounts")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('transactions', 'spent', 'accounts')")
    conn.commit()

