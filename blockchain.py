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

    cursor.execute(
        "INSERT INTO transactions(sender,receiver,amount,signature) VALUES (?,?,?,?)",
        (sender, receiver, amount, signature.hex())
    )

    conn.commit()

    return message, signature


def verify_input(sender, amount):

    if sender == "" or amount <= 0:
        return False

    return True


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

    except:
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
