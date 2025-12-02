from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def home():
    """
    API Health Check Route.
    Returns the service status.
    """
    return jsonify({
        "status": "Pricing Service is running",
        "version": "1.0.0",
        "service": "GlobalPrice Secondary API"
    })

def fetch_exchange_rate(source, target):
    """
    Attempt to retrieve the quote. If the direct rate (BRL->TARGET) fails,
    try the inverse rate (TARGET->BRL) and reverse the calculation.
    Returns: (rate, status_ok?)
    """
    # First Attempt (Users choice)
    pair_direct = f"{source}-{target}"
    url_direct = f"https://economia.awesomeapi.com.br/last/{pair_direct}"

    try:
        response = requests.get(url_direct, timeout=3)
        if response.status_code == 200:
            data = response.json()
            key = f"{source}{target}"
            if key in data:
                return float(data[key]['bid']), True
    except Exception:
        pass
    
    # Second Attempt (Inverts the search to get not found value)
    pair_inverse = f"{target}-{source}"
    url_inverse = f"https://economia.awesomeapi.com.br/last/{pair_inverse}"

    try:
        response = requests.get(url_inverse, timeout=3)
        if response.status_code == 200:
            data = response.json()
            key = f"{target}{source}"
            if key in data:
                rate_inverse = float(data[key]['bid'])
                if rate_inverse > 0:
                    real_rate = 1/ rate_inverse
                    return real_rate, True
    except Exception as e:
        print(f"Error in inverse attempt: {e}")
    
    return 0.0, False


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
        return jsonify({"error": "Invalid data. Please send 'base_price' and 'target_currency'"}), 400
    
    try:
        base_price_brl = float(data['base_price'])
        target_currency = data['target_currency'].upper()

        if target_currency == 'BRL':
            return jsonify({
                "currency": "BRL",
                "converted_price": base_price_brl,
                "rate": 1.0
            })
        
        exchange_rate, success = fetch_exchange_rate("BRL", target_currency)

        if not success:
            return jsonify({
                "error": f"Could not fetch rate for {target_currency}. Exchange market might be closed or pair unavailable."
            }), 404

        # Business Rule: We add a 2% margin (Spread) to the conversion.
        margin = 1.02
        final_price = (base_price_brl * exchange_rate) * margin

        # Rounding price: if < 0.01 returns 8 decimals, else 2 decimals.
        if exchange_rate < 0.01:
            precision = 8
        else:
            precision = 2
        
        final_price_formatted = round(final_price, precision)

        return jsonify({
            "currency": target_currency,
            "original_price_brl": base_price_brl,
            "rate_used": exchange_rate,
            "converted_price": final_price_formatted,
            "note": "Includes a 2% safety margin."
        })
    
    except ValueError:
        return jsonify({"error": "Price value must be numeric."}), 400
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500
    
if __name__ == '__main__':
    # Running application on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
