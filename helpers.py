import os
import requests
import urllib.parse

from flask import redirect, render_template, request, session
from functools import wraps


def apology(message, code=400):
    # Render message as an apology to user

    # Special characters must be replaced as they are inserted into a URL on apology.html
    def escape(s):
        for new, old in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(new, old)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    # Decorate routes to require login
    # https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    # *args allows you to pass a varying number of positional arguments
    # **kwargs allows the use of keyword arguments
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    # Look up quote for symbol

    # Contact API
    try:
        # Retrieve API from evironment variable, set API_KEY in command line with: export API_KEY=value
        api_key = os.environ.get("API_KEY")
        url = f"https://cloud.iexapis.com/stable/stock/{urllib.parse.quote_plus(symbol)}/quote?token={api_key}"
        response = requests.get(url)
        # If error occurs, return a HTTPError object
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        # Returns a json object
        quote = response.json()
        
        # Returns a dictionary with 3 keys
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None

# Formats argument into USD format e.g. 123.4528 = $123.45
def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"
