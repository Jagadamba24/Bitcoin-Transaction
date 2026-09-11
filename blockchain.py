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


def verify_input(sender, amount, txid=None):

    if not sender or str(sender).strip() == "":
        return VerifyResult(False, "Sender name cannot be empty.")

    if amount <= 0:
        return VerifyResult(False, f"Transaction amount must be positive (> 0 BTC). Received: {amount}.")

    # If an existing transaction ID is being spent, verify ownership and sufficient balance in that UTXO
    if txid is not None:
        try:
            tx_id_int = int(txid)
            cursor.execute("SELECT receiver, amount FROM transactions WHERE id = ?", (tx_id_int,))
            row = cursor.fetchone()
            if row:
                utxo_owner, utxo_amount = row[0], row[1]
                # Check ownership (case-insensitive)
                if sender.strip().lower() != utxo_owner.strip().lower():
                    return VerifyResult(
                        False, 
                        f"Sender '{sender}' is not the owner of Tx #{tx_id_int}. (UTXO belongs to '{utxo_owner}')."
                    )
                # Check sufficient funds in this UTXO
                if amount > utxo_amount:
                    return VerifyResult(
                        False, 
                        f"Insufficient funds in Tx #{tx_id_int}: Requested {amount} BTC, but UTXO only holds {utxo_amount} BTC."
                    )
        except (ValueError, TypeError):
            pass

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


def double_spending(txid):

    cursor.execute("SELECT * FROM spent WHERE txid=?", (txid,))
    result = cursor.fetchone()

    if result:
        return False

    cursor.execute("INSERT INTO spent(txid) VALUES (?)", (txid,))
    conn.commit()

    return True


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


def get_wallet_balances():
    """
    Calculates the live wallet balance for all users based on Unspent Transaction Outputs (UTXOs).
    Balance(user) = sum(amount for all unspent transactions where receiver == user)
    """
    spent_set = set(get_spent_ids())
    cursor.execute("SELECT id, receiver, amount FROM transactions ORDER BY id ASC")
    rows = cursor.fetchall()

    balances = {}
    for tx_id, receiver, amount in rows:
        if tx_id not in spent_set:
            user_key = receiver.strip()
            balances[user_key] = balances.get(user_key, 0) + amount
    return balances


def get_user_utxos(user_name=None):
    """
    Returns unspent transaction outputs (UTXOs).
    If user_name is specified, filters only for that recipient.
    """
    spent_set = set(get_spent_ids())
    cursor.execute("SELECT id, sender, receiver, amount FROM transactions ORDER BY id ASC")
    rows = cursor.fetchall()

    utxos = []
    for tx_id, sender, receiver, amount in rows:
        if tx_id not in spent_set:
            if not user_name or receiver.strip().lower() == user_name.strip().lower():
                utxos.append({
                    "txid": tx_id,
                    "sender": sender,
                    "receiver": receiver,
                    "amount": amount
                })
    return utxos


def faucet_mint(receiver, amount=100):
    """
    Creates a Coinbase / Faucet transaction to credit initial BTC to a user.
    """
    clean_receiver = receiver.strip()
    message, signature = create_transaction("COINBASE_FAUCET", clean_receiver, amount)
    add_block(message)
    tx_id = record_transaction("COINBASE_FAUCET", clean_receiver, amount, signature)
    return tx_id


def reset_database():
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM spent")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('transactions', 'spent')")
    conn.commit()


