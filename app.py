import os
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.json.sort_keys = False

# AI Setttings
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
#if GEMINI_KEY:
#    genai.configure(api_key=GEMINI_KEY)

# --- Diagnostic Block ---
def list_available_models():
    """
    Display the available models for this API Key in the terminal.
    """
    if not GEMINI_KEY:
        print(">>> DIAGNOSTICS: API key not configured. <<<")
        return
    try:
        genai.configure(api_key=GEMINI_KEY)
        print(">>> DIAGNOSTICS: Available Models for the provided API Key:")
        found_any = False
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"MODEL: {m.name}")
                found_any = True
        if not found_any:
            print("No generative models found for this API key.")
    except Exception as e:
        print(f">>> LISTING MODELS ERROR: {str(e)} <<<")

list_available_models()


@app.route('/', methods=['GET'])
def home():
    """
    API Health Check Route.
    Returns the service status.
    """
    ai_status = "Active" if GEMINI_KEY else "Disabled (No Key Found)"
    return jsonify({
        "status": "Pricing Service is running",
        "version": "2.0.0 (AI Powered)",
        "service": "GlobalPrice Secondary API",
        "ai_module": ai_status
    })

def fetch_exchange_rate(source, target):
    """
    Attempt to retrieve the quote. Fetch the rate, daily high, and daily low. 
    If the direct rate (BRL->TARGET) fails,
    try the inverse rate (TARGET->BRL) and reverse the calculation.
    Returns: (bid, high, low, success)
    """
    # First Attempt (Users choice)
    pair_direct = f"{source}{target}"
    url_direct = f"https://economia.awesomeapi.com.br/last/{source}-{target}"

    try:
        response = requests.get(url_direct, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if pair_direct in data:
                item = data[pair_direct]
                return float(item['bid']), float(item['high']), float(item['low']), True
    except Exception:
        pass
    
    # Second Attempt (Inverts the search to get not found value)
    pair_inverse = f"{target}{source}"
    url_inverse = f"https://economia.awesomeapi.com.br/last/{target}-{source}"

    try:
        response = requests.get(url_inverse, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if pair_inverse in data:
                item = data[pair_inverse]
                rate_inverse = float(item['bid'])
                high_inverse = float(item['high'])
                low_inverse = float(item['low'])

                if rate_inverse > 0 and low_inverse > 0:
                    real_rate = 1 / rate_inverse
                    real_high = 1 / low_inverse
                    real_low = 1 / high_inverse
                    return real_rate, real_high, real_low, True
    except Exception:
        pass
    
    return 0.0, 0.0, 0.0, False

def get_ai_safety_margin(currency, volatility_pct):
    """
    Consult Google Gemini to define the Spread.
    """
    if not GEMINI_KEY:
        return 1.02, "AI Disabled (Standard 2%)"
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""
        Act as a financial risk manager.
        The currency pair BRL-{currency} had a volatility of {volatility_pct:.2f}% in the last 24h.
        
        Determine a safety margin spread multiplier between 1.01 (1%) and 1.05 (5%).
        - Low volatility (<0.5%): return close to 1.01.
        - High volatility (>2%): return close to 1.05.
        
        Return ONLY the number (e.g., 1.03). Do not write text.
        """

        response = model.generate_content(prompt)
        clean_text = response.text.strip().replace('*', '')
        ai_margin = float(clean_text)

        # Safety lock to prevent the AI from hallucinating absurd numbers
        if ai_margin < 1.00 or ai_margin > 1.10:
            return 1.02, "AI Value Out of Bounds (Fallback 2%)"
        
        return ai_margin, f"AI Calculated based on {volatility_pct:.2f}% volatility"
    
    except Exception as e:
        return 1.02, f"AI Error: {str(e)}"


@app.route('/convert', methods=['POST'])
def convert_price():
    """
    Calculates the price of a product in another currency.
    
    Input (JSON):
        - base_price (float): Original price in BRL.
        - target_currency (str): Target currency (e.g., 'USD', 'EUR').
        
    Output (JSON):
        - Converted price with applied safety margin.
    """
    data = request.get_json()

    if not data or 'base_price' not in data or 'target_currency' not in data:
        return jsonify({"error": "Invalid data."}), 400
    
    try:
        base_price_brl = float(data['base_price'])
        target_currency = data['target_currency'].upper()

        if target_currency == 'BRL':
            return jsonify({
                "currency": "BRL",
                "converted_price": base_price_brl,
                "rate": 1.0
            })
        
        exchange_rate, high, low, success = fetch_exchange_rate("BRL", target_currency)

        if not success:
            return jsonify({
                "error": f"Could not fetch rate for {target_currency}. Exchange market might be closed or pair unavailable."
            }), 404
        
        # Calculate Volatility
        volatility = 0.0
        if low > 0:
            volatility = ((high - low) / low) * 100

        margin, reason = get_ai_safety_margin(target_currency, volatility)
        final_price = (base_price_brl * exchange_rate) * margin 

        # Rounding price: if < 0.01 (e.g.: digital currencies) returns 8 decimals, else 2 decimals.
        precision = 8 if exchange_rate < 0.01 else 2
        final_price_formatted = round(final_price, precision)
        spread_pct = (margin - 1) * 100

        return jsonify({
            "original_price_brl": base_price_brl,
            "exchange_currency": target_currency,
            "converted_price": final_price_formatted,
            "rate_used": exchange_rate,
            "margin_applied": margin,
            "spread_percentage": f"{spread_pct:.2f}%",
            "market_volatility_24h": f"{volatility:.2f}%",
            "ai_analysis": reason
        })
    
    except ValueError:
        return jsonify({"error": "Price value must be numeric."}), 400
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500
    
if __name__ == '__main__':
    # Running application on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
