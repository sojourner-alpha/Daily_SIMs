from finvizfinance.quote import finvizfinance

def get_all_stock_info(ticker):
    stock = finvizfinance(ticker)

    # Check all available methods and attributes
    data_categories = {
        'Description': stock.ticker_description,
        'Fundamentals': stock.ticker_fundament,
        'Insider Trading': stock.ticker_inside_trader,  # Corrected method name
        # Add more categories as available in the documentation
    }

    # Iterating through categories and fetching data
    for category, func in data_categories.items():
        try:
            data = func()
            print(f"\n{category}:")
            if isinstance(data, dict):
                for key, value in data.items():
                    print(f"{key}: {value}")
            else:
                print(data)
        except Exception as e:
            print(f"Failed to retrieve {category}: {e}")

# Example usage
if __name__ == "__main__":
    ticker = 'TSLA'  # Using Tesla as an example
    get_all_stock_info(ticker)
