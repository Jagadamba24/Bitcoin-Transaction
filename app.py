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
    get_user_balance,
    set_account_balance,
    deduct_balance,
    credit_balance,
    reset_database
)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = []
    status = "info"

    ledger = get_ledger()
    wallet_balances = get_wallet_balances()

    sender = ""
    receiver = ""
    amount_raw = ""

    if request.method == "POST":
        sender = request.form.get("sender", "").strip()
        receiver = request.form.get("receiver", "").strip()
        amount_raw = request.form.get("amount", "").strip()

        try:
            amount = int(amount_raw)
        except ValueError:
            amount = 0

        # 1. Transaction Created
        message, signature = create_transaction(sender, receiver, amount)
        result.append("Transaction Created ✔")

        # 2. Input verification
        input_check = verify_input(sender, amount)
        if input_check:
            result.append("Input Verified ✔")
        else:
            result.append(f"Input Verification Failed ❌ ({input_check.message})")
            return render_template(
                "index.html",
                result=result,
                status="error",
                ledger=get_ledger(),
                wallet_balances=get_wallet_balances(),
                sender=sender,
                receiver=receiver,
                amount=amount_raw
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
                wallet_balances=get_wallet_balances(),
                sender=sender,
                receiver=receiver,
                amount=amount_raw
            )

        # 4. Double spending check (detects duplicate send to same person OR spending more than balance)
        is_valid, ds_msg = double_spending(sender=sender, receiver=receiver, amount=amount)
        if is_valid:
            result.append(f"Double Spending Check Passed ✔ ({amount} coins available & unspent)")
        else:
            result.append(f"Double Spending Detected ❌ ({ds_msg})")
            return render_template(
                "index.html",
                result=result,
                status="danger",
                ledger=get_ledger(),
                wallet_balances=get_wallet_balances(),
                sender=sender,
                receiver=receiver,
                amount=amount_raw
            )

        # 5. Add Block to Blockchain and record confirmed transaction
        block = add_block(message)
        record_transaction(sender, receiver, amount, signature)
        
        # Deduct sender balance and credit receiver balance
        deduct_balance(sender, amount)
        credit_balance(receiver, amount)

        result.append(f"Block Added to Blockchain ✔ (hash: {block[:10]}...)")
        status = "success"

        # Refresh ledger and balances after transaction
        ledger = get_ledger()
        wallet_balances = get_wallet_balances()

    return render_template(
        "index.html",
        result=result,
        status=status,
        ledger=ledger,
        wallet_balances=wallet_balances,
        sender=sender,
        receiver=receiver,
        amount=amount_raw
    )


@app.route("/set_balance", methods=["POST"])
def set_balance():
    user = request.form.get("user", "").strip()
    amount_raw = request.form.get("balance", "").strip()
    try:
        amount = int(amount_raw)
    except ValueError:
        amount = 0

    if user and amount > 0:
        set_account_balance(user, amount)
    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset():
    reset_database()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
