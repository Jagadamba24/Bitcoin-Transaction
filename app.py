from flask import Flask, render_template, request, redirect, url_for
from blockchain import (
    create_transaction,
    record_transaction,
    verify_input,
    verify_signature,
    double_spending,
    add_block,
    get_ledger,
    get_spent_ids,
    get_unspent_ids,
    get_wallet_balances,
    get_user_utxos,
    faucet_mint,
    reset_database
)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = []
    status = "info"
    submitted_txid = None

    ledger = get_ledger()
    spent_ids = get_spent_ids()
    unspent_ids = get_unspent_ids()
    wallet_balances = get_wallet_balances()

    # Pre-select next logical txid: first unspent tx or 1 if empty
    suggested_txid = unspent_ids[0] if unspent_ids else (len(ledger) + 1 if ledger else 1)

    if request.method == "POST":
        sender = request.form.get("sender", "").strip()
        receiver = request.form.get("receiver", "").strip()
        amount_raw = request.form.get("amount", "0").strip()
        txid_raw = request.form.get("txid", "").strip()

        try:
            amount = int(amount_raw)
        except ValueError:
            amount = 0

        try:
            txid = int(txid_raw) if txid_raw else suggested_txid
        except ValueError:
            txid = 1

        submitted_txid = txid

        # 1. Transaction Created
        message, signature = create_transaction(sender, receiver, amount)
        result.append("Transaction Created ✔")

        # 2. Input verification (verifies sender, amount, and UTXO ownership/balance)
        input_check = verify_input(sender, amount, txid=txid)
        if input_check:
            result.append("Input Verified ✔")
        else:
            result.append(f"Input Verification Failed ❌ ({input_check.message})")
            return render_template(
                "index.html",
                result=result,
                status="error",
                ledger=get_ledger(),
                spent_ids=get_spent_ids(),
                unspent_ids=get_unspent_ids(),
                wallet_balances=get_wallet_balances(),
                suggested_txid=suggested_txid,
                sender=sender,
                receiver=receiver,
                amount=amount_raw,
                txid=submitted_txid
            )

        # 3. Signature verification
        if verify_signature(message, signature):
            result.append("Digital Signature Verified ✔")
        else:
            result.append("Digital Signature Invalid ❌")
            return render_template(
                "index.html",
                result=result,
                status="error",
                ledger=get_ledger(),
                spent_ids=get_spent_ids(),
                unspent_ids=get_unspent_ids(),
                wallet_balances=get_wallet_balances(),
                suggested_txid=suggested_txid,
                sender=sender,
                receiver=receiver,
                amount=amount_raw,
                txid=submitted_txid
            )

        # 4. Double spending check
        if double_spending(txid):
            result.append(f"Double Spending Check Passed ✔ (Tx #{txid} is unspent)")
        else:
            result.append(f"Double Spending Detected ❌ (Tx #{txid} has already been spent!)")
            return render_template(
                "index.html",
                result=result,
                status="danger",
                ledger=get_ledger(),
                spent_ids=get_spent_ids(),
                unspent_ids=get_unspent_ids(),
                wallet_balances=get_wallet_balances(),
                suggested_txid=suggested_txid,
                sender=sender,
                receiver=receiver,
                amount=amount_raw,
                txid=submitted_txid
            )

        # 5. Add Block to Blockchain and record confirmed transaction
        block = add_block(message)
        record_transaction(sender, receiver, amount, signature)
        result.append(f"Block Added to Blockchain ✔ (hash: {block[:10]}...)")
        status = "success"

        # Refresh ledger and balance state after transaction
        ledger = get_ledger()
        spent_ids = get_spent_ids()
        unspent_ids = get_unspent_ids()
        wallet_balances = get_wallet_balances()
        suggested_txid = unspent_ids[0] if unspent_ids else (len(ledger) + 1)

    return render_template(
        "index.html",
        result=result,
        status=status,
        ledger=ledger,
        spent_ids=spent_ids,
        unspent_ids=unspent_ids,
        wallet_balances=wallet_balances,
        suggested_txid=suggested_txid,
        sender="",
        receiver="",
        amount="",
        txid=suggested_txid
    )


@app.route("/faucet", methods=["POST"])
def faucet():
    receiver = request.form.get("faucet_user", "jyothi").strip()
    amount_raw = request.form.get("faucet_amount", "100").strip()
    try:
        amount = int(amount_raw)
    except ValueError:
        amount = 100

    if receiver and amount > 0:
        faucet_mint(receiver, amount)
    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset():
    reset_database()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)


