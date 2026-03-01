import os
import time
import httpx
from fastapi import Request
from dotenv import load_dotenv
from pricing import (
    BASE_PRICE_INR,
    ADVANCE_PLAN_PRICE,
    DISCOUNT_PERCENT,
    INTERNATIONAL_MARKUP,
    CURRENCY_SYMBOL,
)

load_dotenv()

# Google Sheet CSV export URL
SHEET_CSV_URL = os.getenv("GOOGLE_SHEET_CSV_URL")

# Cache (24 hours)
_cache = {
    "rates": {},
    "timestamp": 0,
}

CACHE_TTL = 24 * 60 * 60  # 24 hours


async def load_currency_rates():
    """
    Fetch currency rates from Google Sheet (CSV) once per day.
    """
    now = time.time()

    if _cache["rates"] and now - _cache["timestamp"] < CACHE_TTL:
        return _cache["rates"]

    # Default rates as fallback
    default_rates = {
        "INR": 1.0,
        "USD": 0.012,
        "AED": 0.044
    }

    if not SHEET_CSV_URL:
        print("⚠️ WARNING: GOOGLE_SHEET_CSV_URL not configured. Using default rates.")
        _cache["rates"] = default_rates
        _cache["timestamp"] = now
        return default_rates

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(SHEET_CSV_URL, timeout=10.0)
            resp.raise_for_status()

        lines = resp.text.splitlines()
        headers = lines[0].split(",")

        currency_idx = headers.index("Curruncy")
        rate_idx = headers.index("Rate")

        rates = {}

        for row in lines[1:]:
            cols = row.split(",")
            currency = cols[currency_idx].strip().upper()
            rate = float(cols[rate_idx])
            rates[currency] = rate

        _cache["rates"] = rates
        _cache["timestamp"] = now

        print("✅ Loaded currency rates from Google Sheet:", rates)
        return rates
    except Exception as e:
        print(f"⚠️ ERROR fetching currency rates: {e}. Using default rates.")
        _cache["rates"] = default_rates
        _cache["timestamp"] = now
        return default_rates


async def calculate_price(currency: str, amount_in_inr: int | None = None):
    """
    Calculate price using rates stored in Google Sheets.

    - Starts from INR base
    - Applies discount
    - Converts using sheet rate
    - Applies international markup (non-INR)
    """
    if amount_in_inr is None:
        amount_in_inr = BASE_PRICE_INR

    # Discount
    price_inr = amount_in_inr * (1 - DISCOUNT_PERCENT / 100)

    if currency == "INR":
        return round(price_inr)

    rates = await load_currency_rates()
    rate = rates.get(currency)

    if not rate:
        print(f"Missing rate for {currency}, defaulting to INR")
        return round(price_inr)

    converted = price_inr * rate
    converted *= 1 + INTERNATIONAL_MARKUP / 100

    return round(converted)


async def get_price_context(request: Request):
    """
    Template context helper
    """
    currency = request.query_params.get("currency", "INR").upper()
    if currency not in CURRENCY_SYMBOL:
        currency = "INR"

    price = await calculate_price(currency, BASE_PRICE_INR)
    adv_price = await calculate_price(currency, ADVANCE_PLAN_PRICE)
    symbol = CURRENCY_SYMBOL.get(currency, "")

    return {
        "currency": currency,
        "price": price,
        "adv_price": adv_price,
        "symbol": symbol,
    }