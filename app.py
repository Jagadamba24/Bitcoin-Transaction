from flask import Flask, render_template, request
from blockchain import *

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():

    result = []

    if request.method == "POST":

        sender = request.form["sender"]
        receiver = request.form["receiver"]
        amount = int(request.form["amount"])

        message, signature = create_transaction(sender, receiver, amount)

        result.append("Transaction Created ✔")

        # Input verification
        if verify_input(sender, amount):
            result.append("Input Verified ✔")
        else:
            result.append("Input Verification Failed ❌")
            return render_template("index.html", result=result)

        # Signature verification
        if verify_signature(message, signature):
            result.append("Digital Signature Verified ✔")
        else:
            result.append("Digital Signature Invalid ❌")
            return render_template("index.html", result=result)

        # Double spending check
        if double_spending(1):
            result.append("Double Spending Check Passed ✔")
        else:
            result.append("Double Spending Detected ❌")
            return render_template("index.html", result=result)

        block = add_block(message)

        result.append(f"Block Added to Blockchain ✔ (hash: {block[:10]})")

    return render_template("index.html", result=result)


if __name__ == "__main__":
    app.run(debug=True)
