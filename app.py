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
                "rate": 1.0,
                "message": "Same currency, no conversion."
            })
        
        pair = f"BRL-{target_currency}"
        url = f"https://economia.awesomeapi.com.br/last/{pair}"
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            return jsonify({"error": "Error querying external exchange rate API"}), 502
        
        api_data = response.json()
        key = pair.replace('-', '')

        if key not in api_data:
            return jsonify({"error": f"Currency {target_currency} not found or unavailable."}), 404
    
        # Get the 'bid' quote
        exchange_rate = float(api_data[key]['bid'])

        # Business Rule: We add a 2% margin (Spread) to the conversion.
        margin = 1.02
        final_price = (base_price_brl * exchange_rate) * margin

        return jsonify({
            "currency": target_currency,
            "original_price_brl": base_price_brl,
            "rate_used": exchange_rate,
            "converted_price": round(final_price, 2),
            "note": "Includes a 2% safety margin."
        })
    
    except ValueError:
        return jsonify({"error": "Price value must be numeric."}), 400
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500
    
if __name__ == '__main__':
    # Running application on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
