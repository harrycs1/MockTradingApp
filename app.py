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

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Ensure responses aren't cached
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

    # Query database to select portfolio data from transaction table, and select user cash balance from users table
    with con:
        cur = con.cursor()
        cur.execute("SELECT symbol, SUM(shares) AS shares, SUM(transaction_total), (current_price * SUM(shares)), name, current_price, ((current_price*shares) - transaction_total) FROM transactions WHERE buyer = ? GROUP BY symbol HAVING sum(shares) > 0", [session["user_id"]])
        portfolio_data = cur.fetchall()
        cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
        cash_balance = cur.fetchone()[0]

    # Assign total portfolio value variable
    total_portfolio_value = 0

    # For each row (stock) in users portfolio
    for row in portfolio_data:

        # Get total current value of total shares owned and calculate total portolio value (without cash)
        quote = lookup(row[0])
        current_stock_price = quote["price"]
        total_stock_value = row[1] * current_stock_price
        total_portfolio_value += total_stock_value

        # Query database to update current share price of stocks in portfolio in transactions table
        stock_symbol = quote["symbol"]
        with con:
            cur = con.cursor()
            cur.execute("UPDATE transactions SET current_price = ? WHERE symbol = ?", (current_stock_price, stock_symbol))

    # Get total portfolio value including cash balance
    total_portfolio_value += cash_balance

    # Query database to select unrealised profit/loss from transactions table
    with con:
        cur = con.cursor()
        cur.execute("SELECT IFNULL(SUM(((current_price*shares)-transaction_total)), 0) FROM transactions WHERE buyer = ? ", [session["user_id"]])
        sum_difference = cur.fetchone()[0]

    return render_template("index.html", database = portfolio_data, cash = cash_balance, total = total_portfolio_value, PL = sum_difference)


@app.route("/buy", methods=["GET", "POST"])
# Login required decorator to ensure page can only be viewed by users that are logged in
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("buy.html")
    
    # User reached route via POST (as by submitting a form via POST)
    else:
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))

        # Ensure symbol was submitted
        if not symbol:
            return apology("Must enter shares")

        # Ensure that a whole number of shares was submitted, shares must be a string to use the isdigit() method
        if not request.form.get("shares").isdigit():
            return apology("Can't buy fractional shares")

        # Ensure valid number of shares was submitted
        if not shares or shares < 0:
            return apology("Shares must be greater than zero")

        # Get quote for the stock being purchased
        quote = lookup(symbol.upper())

        # Ensure stock exists
        if not quote:
            return apology("Symbol not found")

        # Get amount due for transaction
        amount_due = quote["price"] * float(shares)

        # Query database to select user cash balance from users table
        with con:
            cur = con.cursor()
            cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
            balance = cur.fetchone()[0]

        # Get time of transaction
        time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Ensure sufficient funds are available for transaction
        if amount_due > balance:
            return apology("Insufficient funds")
        else:

            # Get updated user cash balance
            uptd_cash = balance - amount_due

            # Query database to insert transaction data in transactions table, and update user cash balace in users table
            with con:
                cur = con.cursor()
                cur.execute("INSERT INTO transactions (buyer, name, symbol, transaction_price, shares, date, transaction_total, current_price) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (session["user_id"], quote["name"], quote["symbol"], quote["price"], shares, time, amount_due, quote["price"]))
                cur.execute("UPDATE users SET cash = ? WHERE id = ?", (uptd_cash, session["user_id"]))

            # Show flash message upon complete transaction
            flash(f"Bought for {usd(amount_due)}!")
            return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        
        # Query database to select all user transactions from users table
        with con:
            cur = con.cursor()
            cur.execute("SELECT * FROM transactions WHERE buyer = ?", [session["user_id"]])
            userTransactions = cur.fetchall()

        return render_template("history.html", userTransactions = userTransactions)


@app.route("/addCash", methods=["GET", "POST"])
@login_required
def addCash():
    """Add more cash"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("addCash.html")
    
    # User reached route via POST (as by submitting a form via POST)
    else:
        new_cash = float(request.form.get("newCash"))

        # Ensure deposit amount was subitted
        if not new_cash:
            return apology("Add deposit amount")
        
        # Ensure deposit greater than zero
        if new_cash < 0:
            return apology("Deposit must be greater than zero")

        # Query database to select cash balance of user
        with con:
            cur = con.cursor()
            cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
            cash = cur.fetchone()

        # Get updated cash balance
        updt_cash = float(cash[0]) + new_cash

        # Query database to update cash balance in users table
        with con:
            cur = con.cursor()
            cur.execute("UPDATE users SET cash = ? WHERE id = ?", (updt_cash, session["user_id"]))

        # Show flash message upon complete deposit   
        flash(f"Deposited {usd(new_cash)}!")
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
    symbol = request.form.get("symbol")

    # User reached route via POST (as by submitting a form via POST)    
    if request.method == "POST":

        # Get quote for requested stock symbol
        quote = lookup(symbol)

        # Ensure symbol has been submitted
        if quote == None:
            return apology("Symbol not found")
        else:
            return render_template("quoted.html", symbol=quote)
        
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Query database for registered usernames
        with con:
            cur = con.cursor()
            cur.execute("SELECT username FROM users")
            usernames = cur.fetchall()

        # Ensure username is not already taken
        for row in usernames:
            if username == row[0]:
                return apology("username already exists")

        # Ensure username has been submitted
        if not username:
            return apology("username blank")

        # Ensure password has been submitted, and that password is the same as confirmation password
        if not password or password != confirmation:
            return apology("password blank/does not match")
        else:
            # Query database to insert username and generated password hash into users table
            with con:
                con.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, generate_password_hash(password)))

            return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":

        # Query database for symbols of stocks owned by user so they can be displayed in dropdown list
        with con:
            cur = con.cursor()
            cur.execute("SELECT symbol FROM transactions WHERE buyer = ? GROUP BY name HAVING SUM(shares) > 0 ORDER BY symbol ASC", [session["user_id"]])
            symbols = cur.fetchall()
        
        return render_template("sell.html", symbols = symbols)
    
    # User reached route via POST (as by submitting a form via POST)
    else:
        stock_to_sell = request.form.get("symbol")
        shares_to_sell = int(request.form.get("shares"))

        # Ensure stock was submitted
        if not stock_to_sell:
            return apology("Must give symbol")

        # Ensure valid number of shares was submitted
        if shares_to_sell < 0:
            return apology("Shares must be greater than 0")

        # Query database for number of shares that the user owns
        with con:
            cur = con.cursor()
            cur.execute("SELECT SUM(shares) AS shares FROM transactions WHERE symbol = ?", [stock_to_sell])
            userShares = cur.fetchone()

        shares = int(userShares[0])

        # Ensure the user has enough shares to sell
        if shares < shares_to_sell:
            return apology("You don't have that many shares")
        else:

            # Query database for user cash and convert to a float
            with con:
                cur = con.cursor()
                cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
                user_cash = cur.fetchone()[0]

            cash = float(user_cash)

            # Return a quote for the stock to sell
            quote = lookup(stock_to_sell)

            # Get price of stock to sell as a float
            price = quote["price"]

            # Get transaction value as a float
            transaction_value = price * float(shares_to_sell)

            # Get new cash balance as a float
            updt_cash = cash + transaction_value

            # Get time of transaction
            time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Query database to insert transaction data into transaction table
            # Query database to update cash balance in users table
            with con:
                cur = con.cursor()
                cur.execute("INSERT INTO transactions (buyer, name, symbol, transaction_price, shares, date, transaction_total, current_price) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (session["user_id"], quote["name"], quote["symbol"], price, (-1*shares_to_sell), time, (-1*transaction_value), quote["price"]))
                cur.execute("UPDATE users SET cash = ? WHERE id = ?", (updt_cash, session["user_id"]))

            # Show flash message upon complete transaction
            flash(f"Sold for {usd(transaction_value)}!")
            return redirect("/")
