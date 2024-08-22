import yfinance as yf

# Accessing the attributes available for yfinance Ticker object
aapl = yf.Ticker("AAPL")
attributes = dir(aapl)

# Filter out private and built-in methods/attributes
public_attributes = [attr for attr in attributes if not attr.startswith('_')]
print(public_attributes)
