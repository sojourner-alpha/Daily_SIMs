import os
import yfinance as yf
from notion_client import Client
import datetime
from llamaapi import LlamaAPI
import json

# Sojourn Inisght LLC: CL -  Critical System: Information; Sub System: Financial Markets. 
# APIs: yfinance, Notion, and LLaMA 3.1
# Function: Automate the collection, computation, synthesis and analysis of the Sojourn Insight Metrics (SIMs).
# SIMs data: current price, 1 day previous close price, 1 month previous close price, 1 year previous close price, and % change from current to each.  
# Run: Daily on weekdays at 7:20am CT to give a premarket report on the metrics.
# Version: 1.4 - includes a 2 stage LLM analysis = summary of the SIMs, market sentiment and SIMs weighted risk score    

# Set the API token as an environment variable
os.environ["LLAMA_API_TOKEN"] = "insert ID here"

# Initialize Notion client with your integration token for Daily SIMs
notion = Client(auth="insert token here")

database_id = "insert token here"  # Daily SIMs database ID
llm_analysis_database_id = "insert token here"  # LLM Analysis database ID

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

def fetch_1month_historical(ticker):
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period='1mo')  # Get the last month of data
        if not history.empty:
            price = history['Close'].iloc[0]  # Get the close price of 1 month ago
            return round(price, 2)
        else:
            print(f"Not enough data to fetch 1 month historical price for {ticker}")
            return None
    except Exception as e:
        print(f"Error fetching 1 month historical price for {ticker}: {e}")
        return None

def fetch_1year_historical(ticker):
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period='1y')  # Get the last year of data
        if not history.empty:
            price = history['Close'].iloc[0]  # Get the close price of 1 year ago
            return round(price, 2)
        else:
            print(f"Not enough data to fetch 1 year historical price for {ticker}")
            return None
    except Exception as e:
        print(f"Error fetching 1 year historical price for {ticker}: {e}")
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
        properties[f"{metric} 1D % Change"] = {
            "number": data["percent_change"]
        }
        properties[f"{metric} 1M % Change"] = {
            "number": data["1mo_percent_change"]
        }
        properties[f"{metric} 1Y % Change"] = {
            "number": data["1yr_percent_change"]
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
    For the data from {date}, Provide a one-sentence summary identifying the most significant movements without repeating the data. Compile a bullet point list of the Daily Sojourn Insight Metrics (SIMs) price and change [price  (%change)] using $ and % signs except for on yields and currencies only % signs with no commentary segmented into "bullish", "neutral" and "bearish" based on the percent change.
    - Sort bullets from most positive % change at the top of bullish to most negative % change at the bottom of bearish
    
    Also, summarize into a hiku.
    
    Summary:
    """

    insight_prompt = daily_sims_context + f"""
    Analyze the Daily Sojourn Insight Metrics (SIMs) for {date} with emphasis on their economic implications and market sentiment shift or continuation indicators.  Detail 1 critical insight one liner for each of the following:
    
    - Risk On/Risk Off
    - Economic Implications
    - Trends or Shifts

    Insight:
    """

    watchlist_prompt = daily_sims_context + f"""
    From the {date}'s Daily Sojourn Insight Metrics (SIMs), identify the top 3 tickers to watch and list only the tickers separated by ", "

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

def calculate_risk_on_score(metrics_data):
    # Assume risk on criteria for each metric
    risk_on_indicators = {
        'S&P 500 ETF': True,
        'Russell 2000 ETF': True,
        'VIX': False,
        'Crude Oil': True,
        'Natural Gas': True,
        'Gold': False,
        'Copper': True,
        'Euro Exchange Rate': True,
        'Japanese Yen Exchange Rate': False,
        'Bitcoin USD Exchange Rate': True,
        '10-Year Treasury Yield': False,
        '2-Year Treasury Yield': False
    }
    
    risk_on_count = 0
    total_count = len(risk_on_indicators)
    
    for metric, data in metrics_data.items():
        if metric in risk_on_indicators:
            if (data['percent_change'] > 0 and risk_on_indicators[metric]) or (data['percent_change'] < 0 and not risk_on_indicators[metric]):
                risk_on_count += 1

    risk_on_score = round((risk_on_count / total_count) * 10)
    return risk_on_score

def get_compiled_analysis_from_llama(combined_context, first_analysis, risk_on_score):
    compiled_prompt = f"""
    Using the following Daily Sojourn Insight Metrics (SIMs) and analysis:

    SIMs Context:
    {combined_context}

    First Analysis:
    {first_analysis['Summary']}
    {first_analysis['Insight']}
    {first_analysis['Watchlist']}

    Provide a succinct summary integrating all the inputs being clear and objective but withuot unnecessary embellishments inspired by the style of Charlie Munger . Additionally, comment on {risk_on_score} and the overall market sentiment.
    """
    
    try:
        api_request_json = {
            "model": "llama3.1-70b",
            "messages": [
                {"role": "user", "content": compiled_prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        response = llama.run_sync(api_request_json)
        response_json = response.json()
        if 'choices' in response_json and len(response_json['choices']) > 0:
            compiled_analysis = response_json['choices'][0]['message']['content']
        else:
            print(f"Error in LLaMA compiled analysis response: {response_json}")
            compiled_analysis = "Error in generating compiled analysis"
    except Exception as e:
        print(f"Error generating compiled analysis: {e}")
        compiled_analysis = "Error in generating compiled analysis"

    return compiled_analysis

def get_sentiment(risk_on_score):
    if risk_on_score in [0, 1, 2, 3]:
        return "Bearish"
    elif risk_on_score in [4, 5, 6]:
        return "Neutral"
    elif risk_on_score in [7, 8, 9, 10]:
        return "Bullish"

def create_compiled_analysis_page(database_id, date, day_name, compiled_analysis, risk_on_score, watchlist):
    sentiment = get_sentiment(risk_on_score)

    # Split the compiled_analysis text into chunks of 2000 characters
    chunks = [compiled_analysis[i:i+2000] for i in range(0, len(compiled_analysis), 2000)]
    ai_analysis_text = [{"text": {"content": chunk}} for chunk in chunks]

    properties = {
        "Name": {"title": [{"text": {"content": day_name}}]},
        "Date": {"date": {"start": date}},
        "AI Analysis": {"rich_text": ai_analysis_text},
        "Risk On": {"number": risk_on_score},
        "Sentiment": {"select": {"name": sentiment}},
        "Watchlist": {"rich_text": [{"text": {"content": watchlist}}]}
    }

    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )
        return response
    except Exception as e:
        print(f"Error when trying to create page in Notion: {e}")
        return None


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
        one_month_price = fetch_1month_historical(ticker)
        one_year_price = fetch_1year_historical(ticker)

        if current_price is not None and previous_close is not None and one_month_price is not None and one_year_price is not None:
            percent_change = ((current_price - previous_close) / previous_close) * 100  # Daily percent change
            percent_change_1mo = ((current_price - one_month_price) / one_month_price) * 100  # 1 Month percent change
            percent_change_1yr = ((current_price - one_year_price) / one_year_price) * 100  # 1 Year percent change
            
            metrics_data[metric] = {
                "current": current_price,
                "percent_change": round(percent_change, 2),
                "1mo_price": one_month_price,
                "1mo_percent_change": round(percent_change_1mo, 2),
                "1yr_price": one_year_price,
                "1yr_percent_change": round(percent_change_1yr, 2)
            }
            print(f"{metric} ({ticker}): Current=${current_price} | Previous=${previous_close} | 1 Month=${one_month_price} | 1 Year=${one_year_price} | % Change: {percent_change}%, 1 Month % Change: {percent_change_1mo}%, 1 Year % Change: {percent_change_1yr}%")
        else:
            print(f"Failed to fetch data for {ticker} (current: {current_price}, previous: {previous_close}, 1 month: {one_month_price}, 1 year: {one_year_price})")

    if metrics_data:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        day_name = datetime.datetime.now().strftime("%A, %B %d, %Y")
        
        # Initial Risk On score calculation
        risk_on_score = calculate_risk_on_score(metrics_data)

        # First Analysis and Publish
        response = create_notion_page(database_id, today, metrics_data)
        print("Page created:", response)

        # Fetch the latest Daily SIMs entry
        daily_sims_page = fetch_latest_daily_sims()

        # Prepare context and prompt for LLaMA
        prompts = prepare_context_and_prompt(daily_sims_page)

        # Get the first analysis from LLaMA
        analysis = get_analysis_from_llama(prompts)
        watchlist = analysis['Watchlist']  # Ensure this is the key where the watchlist data is stored
        print("LLaMA Analysis:", analysis)

        # Push the first analysis back into Notion
        create_analysis_page(daily_sims_page['properties']['Date']['date']['start'], analysis)

        # Second Analysis: Combine the original SIMs and the first analysis
        combined_context = prompts['Summary'] + "\n" + analysis['Summary']
        compiled_analysis = get_compiled_analysis_from_llama(combined_context, analysis,risk_on_score)
        print("LLaMA Compiled Analysis:", compiled_analysis)

        # Calculate risk on score
        risk_on_score = calculate_risk_on_score(metrics_data)

        # Push the compiled analysis into the third Notion database
        llm_compiled_analysis_id = "9c6e5eb5c7c84d139d869b4ac73da3b6"  # Compiled Analysis database ID
        compiled_response = create_compiled_analysis_page(
            llm_compiled_analysis_id,
            daily_sims_page['properties']['Date']['date']['start'],
            day_name,
            compiled_analysis,
            risk_on_score,
            watchlist
        )
        print("Compiled Analysis Page created:", compiled_response)

if __name__ == "__main__":
    main()
