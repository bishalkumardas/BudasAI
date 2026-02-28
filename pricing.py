# Central pricing configuration for the application

# base price in Indian rupees (INR)
BASE_PRICE_INR = 4999
# optional advanced plan price (if different from base)
ADVANCE_PLAN_PRICE = 14999

# percentage discount to apply before any currency conversion
DISCOUNT_PERCENT = 0
# markup for international customers (in percent)
INTERNATIONAL_MARKUP = 30

# currency symbols used throughout templates
CURRENCY_SYMBOL = {
    "INR": "\u20B9",  # rupee symbol
    "USD": "$",
    "AED": "AED"
}