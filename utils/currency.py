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
    try:
        print(f"🔵 [LOAD_CURRENCY_RATES] Checking cache...")
        now = time.time()

        if _cache["rates"] and now - _cache["timestamp"] < CACHE_TTL:
            print(f"✅ [LOAD_CURRENCY_RATES] Using cached rates")
            return _cache["rates"]

        print(f"🔵 [LOAD_CURRENCY_RATES] Cache miss or expired")

        # Default rates as fallback
        default_rates = {
            "INR": 1.0,
            "USD": 0.012,
            "AED": 0.044
        }

        if not SHEET_CSV_URL:
            print(f"⚠️ [LOAD_CURRENCY_RATES] No SHEET_CSV_URL configured, using defaults")
            _cache["rates"] = default_rates
            _cache["timestamp"] = now
            return default_rates

        try:
            print(f"🔵 [LOAD_CURRENCY_RATES] Fetching from Google Sheet...")
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(SHEET_CSV_URL, timeout=10.0)
                resp.raise_for_status()
            
            print(f"🔵 [LOAD_CURRENCY_RATES] Parsing CSV...")
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

            print(f"✅ [LOAD_CURRENCY_RATES] Successfully loaded: {rates}")
            return rates
        except Exception as e:
            print(f"⚠️ [LOAD_CURRENCY_RATES] Failed to fetch: {type(e).__name__}: {str(e)}")
            print(f"🔵 [LOAD_CURRENCY_RATES] Using default rates as fallback")
            _cache["rates"] = default_rates
            _cache["timestamp"] = now
            return default_rates
    except Exception as e:
        print(f"❌ [LOAD_CURRENCY_RATES] Unexpected error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        default_rates = {
            "INR": 1.0,
            "USD": 0.012,
            "AED": 0.044
        }
        _cache["rates"] = default_rates
        _cache["timestamp"] = time.time()
        return default_rates


async def calculate_price(currency: str, amount_in_inr: int | None = None, discount_percent: float | None = None):
    """
    Calculate price using rates stored in Google Sheets.

    - Starts from INR base
    - Applies discount (uses plan-level discount if provided, else global DISCOUNT_PERCENT)
    - Converts using sheet rate
    - Applies international markup (non-INR)
    """
    if amount_in_inr is None:
        amount_in_inr = BASE_PRICE_INR

    # Discount: use plan-level discount if provided, otherwise use global
    discount = discount_percent if discount_percent is not None else DISCOUNT_PERCENT
    price_inr = amount_in_inr * (1 - discount / 100)

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


#never remove this function from any route
async def get_price_context(request: Request):
    """
    Template context helper for prices, including discount.
    """
    try:
        currency = request.query_params.get("currency", "INR").upper()
        if currency not in CURRENCY_SYMBOL:
            currency = "INR"

        # Base prices
        original_base_price = BASE_PRICE_INR
        original_adv_price = ADVANCE_PLAN_PRICE

        # Discounted prices
        discounted_base_price = original_base_price * (1 - DISCOUNT_PERCENT / 100)
        discounted_adv_price = original_adv_price * (1 - DISCOUNT_PERCENT / 100)

        # Convert to currency
        if currency != "INR":
            rates = await load_currency_rates()
            rate = rates.get(currency, 1)
            discounted_base_price = round(discounted_base_price * rate * (1 + INTERNATIONAL_MARKUP / 100))
            discounted_adv_price = round(discounted_adv_price * rate * (1 + INTERNATIONAL_MARKUP / 100))
            original_base_price = round(original_base_price * rate * (1 + INTERNATIONAL_MARKUP / 100))
            original_adv_price = round(original_adv_price * rate * (1 + INTERNATIONAL_MARKUP / 100))
        else:
            discounted_base_price = round(discounted_base_price)
            discounted_adv_price = round(discounted_adv_price)
            original_base_price = round(original_base_price)
            original_adv_price = round(original_adv_price)

        return {
            "currency": currency,
            "symbol": CURRENCY_SYMBOL.get(currency, ""),
            "price": discounted_base_price,
            "original_price": original_base_price,
            "adv_price": discounted_adv_price,
            "original_adv_price": original_adv_price,
            "discount_percent": DISCOUNT_PERCENT,
            "base_url": os.getenv("BASE_URL", "http://localhost:8000")
        }
    except Exception as e:
        return {
            "currency": "INR",
            "symbol": "₹",
            "price": 4999,
            "original_price": 4999,
            "adv_price": 14999,
            "original_adv_price": 14999,
            "discount_percent": 0,
            "base_url": os.getenv("BASE_URL", "http://localhost:8000")
        }