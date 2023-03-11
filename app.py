import os
import datetime
import sqlite3

#from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# create a Connection object that represents the SQLite database
con = sqlite3.connect("finance.db", check_same_thread=False)

# Configure CS50 Library to use SQLite database
# db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    with con:
        cur = con.cursor()
        cur.execute("SELECT symbol, SUM(shares) AS shares, SUM(total) AS total, (current_price * SUM(shares)), name, current_price, ((current_price*shares) - total) FROM purchases WHERE buyer = ? GROUP BY symbol HAVING sum(shares) > 0", [session["user_id"]])
        rows = cur.fetchall()
        cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
        cash_db = cur.fetchone()

    cash_value = cash_db[0] #cash row in users table
    total = 0

    for row in rows:
        result = lookup(row[0])
        current_stock_price = result["price"]
        total_stock_value = row[1] * current_stock_price
        total += total_stock_value

    total += cash_value
    
    for row in rows:
        result = lookup(row[0])
        current_stock_price = result["price"]
        stock_symbol = result["symbol"]
        with con:
            cur = con.cursor()
            cur.execute("UPDATE purchases SET current_price = ? WHERE symbol = ?", (current_stock_price, stock_symbol))

    with con:
        cur = con.cursor()
        cur.execute("SELECT SUM(((current_price*shares)-total)) FROM purchases WHERE buyer = ?", [session["user_id"]])
        sum_difference = cur.fetchone()[0]

    return render_template("index.html", database = rows, cash = cash_value, total = total, PL = sum_difference)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not shares.isdigit():
            return apology("Can't buy fractional shares")

        if not int(shares) or int(shares) < 0:
            return apology("Shares must be greater than zero")

        stock = lookup(symbol.upper())

        if not stock:
            return apology("Symbol not found")

        amount_due = stock["price"] * int(shares)

        with con:
            cur = con.cursor()
            cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
            balance = cur.fetchall()[0]

        time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if amount_due > int(balance[0]):
            return apology("Not enough cash")
        else:
            with con:
                cur = con.cursor()
                cur.execute("INSERT INTO purchases (buyer, name, symbol, price, shares, date, total, current_price) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (session["user_id"], stock["name"], stock["symbol"], stock["price"], shares, time, amount_due, stock["price"]))
                uptdCash = int(balance[0]) - amount_due
                cur.execute("UPDATE users SET cash = ? WHERE id = ?", (uptdCash, session["user_id"]))
                #cur.execute("INSERT or REPLACE INTO current_stock_prices (stock_name, stock_symbol, current_price) VALUES(?, ?, ?)", (stock["name"], stock["symbol"], stock["price"]))

            flash(f"Bought for {usd(amount_due)}!")
            return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if request.method == "GET":
        with con:
            cur = con.cursor()
            cur.execute("SELECT * FROM purchases WHERE buyer = ?", [session["user_id"]])
            userTransactions = cur.fetchall()

        return render_template("history.html", userTransactions = userTransactions)


@app.route("/addCash", methods=["GET", "POST"])
@login_required
def addCash():
    """Add more cash"""
    if request.method == "GET":
        return render_template("addCash.html")
    else:
        newCash = int(request.form.get("newCash"))

        if not newCash:
            return apology("Add deposit amount")
        
        if newCash < 0:
            return apology("Deposit must be greater than zero")

        with con:
            cur = con.cursor()
            cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
            cash = cur.fetchone()

        updtCash = int(cash[0]) + newCash
        with con:
            cur = con.cursor()
            cur.execute("UPDATE users SET cash = ? WHERE id = ?", (updtCash, session["user_id"]))
        
        flash(f"Deposited {usd(newCash)}!")
        return redirect("/addCash")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        with con: 
            cur = con.cursor()
            cur.execute("SELECT * FROM users WHERE username = ?", [request.form.get("username")])
            rows = cur.fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    ticker = request.form.get("symbol")

    if request.method == "POST":
        symbol = lookup(ticker)
        if symbol == None:
            return apology("Symbol not found")
        else:
            return render_template("quoted.html", symbol=symbol)

    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        with con:
            cur = con.cursor()
            cur.execute("SELECT username FROM users")
            usernames = cur.fetchall()

        for row in usernames:
            if username == row:
                return apology("username already exists")


        if not username:
            return apology("username blank")

        if not password or password != confirmation:
            return apology("password blank/does not match")
        else:
            with con:
                con.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, generate_password_hash(password)))

            return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        with con:
            cur = con.cursor()
            cur.execute("SELECT symbol FROM purchases WHERE buyer = ? GROUP BY name HAVING SUM(shares) > 0 ORDER BY symbol ASC", [session["user_id"]])
            symbols = cur.fetchall()
        
        return render_template("sell.html", names = symbols)

    else:
        stockToSell = request.form.get("symbol")
        sharesToSell = int(request.form.get("shares"))

        if not stockToSell:
            return apology("Must give symbol")

        if sharesToSell < 0:
            return apology("Shares must be greater than 0")

        with con:
            cur = con.cursor()
            cur.execute("SELECT SUM(shares) AS shares FROM purchases WHERE symbol = ?", [stockToSell])
            userShares = cur.fetchone()

        shares = int(userShares[0])

        if shares < sharesToSell:
            return apology("You don't have that many shares")
        else:
            with con:
                cur = con.cursor()
                cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
                userCash = cur.fetchone()[0]

            look = lookup(stockToSell)
            price = look["price"]

            cash = int(userCash)

            transaction_value = price * sharesToSell
            updtCash = cash + transaction_value
            time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with con:
                cur = con.cursor()
                cur.execute("INSERT INTO purchases (buyer, name, symbol, price, shares, date, total, current_price) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (session["user_id"], look["name"], look["symbol"], price, (-1*sharesToSell), time, (-1*transaction_value), look["price"]))
                cur.execute("UPDATE users SET cash = ? WHERE id = ?", (updtCash, session["user_id"]))

            flash(f"Sold for {usd(transaction_value)}!")
            return redirect("/")
