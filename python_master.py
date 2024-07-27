import os
import yfinance as yf
from notion_client import Client
import datetime
from llamaapi import LlamaAPI
import json

# Set the API token as an environment variable
os.environ["LLAMA_API_TOKEN"] = "_insert_your_token_here_"

# Initialize Notion client with your integration token for Daily SIMs
notion = Client(auth="_insert_your_notion_integration_secret_here_")

database_id = "_insert_your_database_ID_here_"  # Daily SIMs database ID
llm_analysis_database_id = "_insert_your_database_ID_here_"  # LLM Analysis database ID

# Initialize Llama API client with api_token
llama_api_token = os.getenv("LLAMA_API_TOKEN")
llama = LlamaAPI(api_token=llama_api_token)

def fetch_yfinance_data(ticker, period='1d'):
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period=period)['Close'].iloc[-1]  # Use iloc to access the last element
        return round(price, 2)
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

def fetch_previous_close(ticker):
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period='5d')  # Get the last 5 days of data
        if len(history) > 1:
            price = history['Close'].iloc[-2]  # Get the close price of the second to last day
            return round(price, 2)
        else:
            print(f"Not enough data to fetch previous close for {ticker}")
            return None
    except Exception as e:
        print(f"Error fetching previous close for {ticker}: {e}")
        return None

def create_notion_page(database_id, date, metrics_data):
    properties = {
        "Date": {
            "date": {
                "start": date
            }
        }
    }
    for metric, data in metrics_data.items():
        properties[metric] = {
            "number": data["current"]
        }
        properties[f"{metric} % Change"] = {
            "number": data["percent_change"]
        }
    response = notion.pages.create(
        parent={"database_id": database_id},
        properties=properties
    )
    return response

def fetch_latest_daily_sims():
    response = notion.databases.query(
        database_id=database_id,  # Daily SIMs database ID
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=1
    )
    return response['results'][0]

def prepare_context_and_prompt(daily_sims_page):
    date = daily_sims_page['properties']['Date']['date']['start']
    daily_sims_context = f"Date: {date}\n"
    for property_name, property_value in daily_sims_page['properties'].items():
        if 'number' in property_value:
            daily_sims_context += f"{property_name}: {property_value['number']}\n"

    summary_prompt = daily_sims_context + f"""
    Based on the Daily Sojourn Insight Metrics (SIMs) provided for {date}, generate a concise summary highlighting the key metrics and their relative changes or momentum.

    Summary:
    """

    insight_prompt = daily_sims_context + f"""
    Based on the Daily Sojourn Insight Metrics (SIMs) provided for {date}, generate a bullet point analysis focusing on the following aspects:

    - Risk On/Risk Off perspective
    - Economic implications of the combined indicators
    - Any notable trends or shifts in the data

    Insight:
    """

    watchlist_prompt = daily_sims_context + f"""
    Based on the Daily Sojourn Insight Metrics (SIMs) provided for {date}, identify the top 2-3 tickers to watch. Consider the following factors in your selection:

    - Momentum in the indices
    - Movements in energy prices and metals
    - Currency fluctuations

    Watchlist:
    """

    prompts = {
        "Summary": summary_prompt,
        "Insight": insight_prompt,
        "Watchlist": watchlist_prompt
    }

    return prompts

def get_analysis_from_llama(prompts):
    responses = {}
    for name, prompt in prompts.items():
        try:
            api_request_json = {
                "model": "llama3.1-70b",  # Specify the model here
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,  # Adjust as needed
                "temperature": 0.7
            }
            response = llama.run_sync(api_request_json)
            response_json = response.json()
            if 'choices' in response_json and len(response_json['choices']) > 0:
                responses[name] = response_json['choices'][0]['message']['content']
            else:
                print(f"Error in LLaMA response for {name}: {response_json}")
                responses[name] = "Error in generating response"
        except Exception as e:
            print(f"Error generating response for {name}: {e}")
            responses[name] = "Error in generating response"
    return responses

def create_rich_text(content):
    # Split content into chunks of 2000 characters or less
    chunks = [content[i:i + 2000] for i in range(0, len(content), 2000)]
    rich_text = []
    for chunk in chunks:
        rich_text.append({"type": "text", "text": {"content": chunk}})
    return rich_text

def create_analysis_page(date, analysis):
    properties = {
        "Date": {"date": {"start": date}},
        "Summary": {"rich_text": create_rich_text(analysis["Summary"])},
        "Insight": {"rich_text": create_rich_text(analysis["Insight"])},
        "Watchlist": {"rich_text": create_rich_text(analysis["Watchlist"])}
    }
    new_page = {
        "parent": {"database_id": llm_analysis_database_id},  # LLM Analysis database ID
        "properties": properties
    }
    notion.pages.create(**new_page)

def main():
    metrics = {
        'S&P 500 ETF': 'SPY',
        'Russell 2000 ETF': 'IWM',
        'VIX': '^VIX',
        'Crude Oil': 'CL=F',
        'Natural Gas': 'NG=F',
        'Gold': 'GC=F',
        'Copper': 'HG=F',
        'Euro Exchange Rate': 'EURUSD=X',
        'Japanese Yen Exchange Rate': 'JPY=X',
        'Bitcoin USD Exchange Rate': 'BTC-USD',
        '10-Year Treasury Yield': '^TNX',
        '2-Year Treasury Yield': '^IRX'
    }

    metrics_data = {}
    for metric, ticker in metrics.items():
        current_price = fetch_yfinance_data(ticker, period='1d')
        previous_close = fetch_previous_close(ticker)
        if current_price is not None and previous_close is not None:
            percent_change = ((current_price - previous_close) / previous_close) * 100  # Calculate percent change correctly
            metrics_data[metric] = {
                "current": current_price,
                "percent_change": round(percent_change, 2)  # Round to two decimal places
            }
            print(f"{metric} ({ticker}): Current=${current_price} | Previous=${previous_close} | % Change: {percent_change}%")
        else:
            print(f"Failed to fetch data for {ticker} (current: {current_price}, previous: {previous_close})")

    if metrics_data:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        response = create_notion_page(database_id, today, metrics_data)
        print("Page created:", response)

        # Fetch the latest Daily SIMs entry
        daily_sims_page = fetch_latest_daily_sims()

        # Prepare context and prompt for LLaMA
        prompts = prepare_context_and_prompt(daily_sims_page)

        # Get analysis from LLaMA
        analysis = get_analysis_from_llama(prompts)
        print("LLaMA Analysis:", analysis)

        # Push the analysis back into Notion
        create_analysis_page(daily_sims_page['properties']['Date']['date']['start'], analysis)

if __name__ == "__main__":
    main()
