import os
import json
import requests
import redis
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger

app = Flask(__name__)
CORS(app)
app.json.sort_keys = False
swagger = Swagger(app)

# --- Volatility Persistence Logic ---
SETTINGS_PATH = 'settings.json'
FACTORY_DEFAULTS = {
    "volatility_threshold": 5.0, # Maximum of 5%
    "use_ai": True,
    "ai_model": "gemini-2.5-flash" 
}

# --- Redis Settings ---
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
try:
    cache = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True, socket_connect_timeout=1)
    cache.ping()
except Exception:
    cache = None


def load_settings():
    """
    Synchronize application configuration with the local persistence layer.

    Attempts to retrieve the global risk parameters from a JSON file. If the file 
    is missing, inaccessible, or contains invalid JSON data, the function 
    gracefully falls back to a predefined set of factory defaults to ensure 
    system availability.

    Returns:
        dict: A configuration object containing:
            - volatility_threshold (float): Limit for automatic hedge activation.
            - use_ai (bool): Toggle for Gemini-driven spread calculations.
            - ai_model (str): Target model identifier for the Generative AI API.

    Raises:
        Note: Exceptions during file I/O or JSON parsing are caught internally 
        to trigger the fallback mechanism, preventing application crash during 
        the bootstrap phase.
    """
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return FACTORY_DEFAULTS.copy()
    return FACTORY_DEFAULTS.copy()

def save_settings(settings):
    """
    Persist application state to the local storage for cross-process synchronization.

    Writes the current configuration dictionary to a persistent JSON store. 
    This ensures that risk parameters—such as volatility thresholds and 
    AI toggles—remain consistent across server restarts and are accessible 
    to all active worker processes (horizontal scaling).

    Args:
        settings (dict): The configuration schema to be serialized. Must 
            contain keys: 'volatility_threshold', 'use_ai', and 'ai_model'.

    Returns:
        None

    Side Effects:
        Overwrites the existing 'settings.json' file with the new 
        serialized state. Uses a 4-space indentation for human-readability 
        and ease of manual auditing/diagnostics.

    Note:
        This operation performs synchronous I/O. In high-concurrency 
        environments, this serves as the primary 'Source of Truth' for 
        dynamic policy updates.
    """
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=4)

CURRENT_SETTINGS = load_settings()

# --- AI Setttings ---  
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- AI Available Models ---
def list_available_models():
    """
    Perform runtime discovery of available Google Generative AI capabilities.

    Queries the Google AI Model Registry to identify all generative models 
    authorized for the current API credentials. It specifically filters for 
    models supporting the 'generateContent' method, ensuring compatibility 
    with the system's core AI logic.

    This function serves as a critical startup diagnostic tool to verify 
    network connectivity, API key validity, and model availability before 
    the pricing engine begins operations.

    Side Effects:
        - Outputs diagnostic telemetry to the standard output (STDOUT).
        - Triggers an active network handshake with Google's API services.

    Returns:
        None

    Notes:
        Relies on the global `GEMINI_KEY` state. In high-availability production 
        environments, this diagnostic can be used as a 'pre-flight check' 
        to prevent runtime errors caused by deprecated model names.
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


# --- Available endpoints ---
@app.route('/', methods=['GET'])
def home():
    """
    Service Heartbeat and System Metadata Provider.
    ---
    tags:
      - System Connectivity
    description: >
      Performs a high-level health check to verify the operational status of the 
      Pricing Service. This endpoint exposes critical system metadata, including 
      semantic versioning and the readiness state of the Generative AI (Gemini) 
      integration layer.
    responses:
      200:
        description: System is healthy and accepting requests.
        content:
          application/json:
            schema:
              type: object
              required:
                - status
                - version
                - service
                - ai_module
              properties:
                status:
                  type: string
                  example: "Pricing Service is running"
                  description: Current operational state of the Flask instance.
                version:
                  type: string
                  example: "2.0.0 (AI Powered)"
                  description: Semantic versioning of the deployed service.
                service:
                  type: string
                  example: "GlobalPrice Secondary API"
                  description: Official service identifier for microservice discovery.
                ai_module:
                  type: string
                  enum: [Active, Disabled]
                  example: "Active"
                  description: Real-time availability of the Google Gemini API connection.
      503:
        description: Service unavailable or core dependencies failing.
    """
    return jsonify({
        "status": "Pricing Service is running",
        "version": "2.0.0 (AI Powered)",
        "service": "GlobalPrice Secondary API",
        "ai_module": "Active" if GEMINI_KEY else "Disabled"
    })


@app.route('/config', methods=['GET'])
def get_config():
    """
    Retrieve active volatility protection and risk mitigation settings.
    ---
    tags:
      - Configuration Management
    description: >
      Fetches the current operational policy from the persistent storage layer. 
      This includes the active volatility threshold, AI module status, and 
      model identification. It also performs a real-time integrity check 
      against factory defaults.
    responses:
      200:
        description: Active risk policy successfully retrieved.
        content:
          application/json:
            schema:
              type: object
              properties:
                current_policy:
                  type: object
                  description: Map of active parameters (threshold, use_ai, model).
                  example: {
                    "volatility_threshold": 5.0,
                    "use_ai": true,
                    "ai_model": "gemini-1.5-flash"
                  }
                is_default:
                  type: boolean
                  description: Flag indicating if the system is running on baseline factory settings.
                  example: true
      500:
        description: Persistence layer inaccessible.
    """
    # Always reload from disk to ensure sync
    settings = load_settings()
    return jsonify({
        "current_policy": settings,
        "is_default": settings == FACTORY_DEFAULTS
    })


@app.route('/config', methods=['PATCH'])
def update_config():
    """
    Partially update dynamic risk parameters and volatility thresholds.
    ---
    tags:
      - Configuration Management
    description: >
      Updates the active risk policy by modifying specific parameters in the 
      persistence layer. Changes are applied in real-time and broadcasted 
      to all service components. This endpoint supports partial updates (PATCH 
      semantics), allowing for fine-grained control over the pricing engine.
    parameters:
      - in: body
        name: body
        required: true
        description: JSON object containing fields to be updated.
        schema:
          type: object
          properties:
            volatility_threshold:
              type: number
              format: float
              example: 8.5
              description: New maximum tolerance for price variance (percentage).
            use_ai:
              type: boolean
              example: false
              description: Enable or disable the Generative AI risk assessment layer.
    responses:
      200:
        description: Policy synchronized and persisted successfully.
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "Risk policy updated and persisted"
                new_settings:
                  type: object
                  description: The full configuration state after the update.
      400:
        description: Validation failed (e.g., negative threshold or malformed JSON).
      415:
        description: Unsupported Media Type (Content-Type must be application/json).
    """
    global CURRENT_SETTINGS
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    settings = load_settings()
    
    # Update Volatility Limit
    if 'volatility_threshold' in data:
        try:
            val = float(data['volatility_threshold'])
            if val < 0: return jsonify({"error": "Must be positive"}), 400
            CURRENT_SETTINGS['volatility_threshold'] = val
        except ValueError:
            return jsonify({"error": "Invalid number"}), 400
    
    # Update AI Toggle
    if 'use_ai' in data:
        settings['use_ai'] = bool(data['use_ai'])
    save_settings(settings)
  
    CURRENT_SETTINGS = settings
    
    return jsonify({
        "message": "Risk policy updated",
        "new_settings": settings
    })


@app.route('/config', methods=['DELETE'])
def reset_config():
    """
    Restore risk parameters to baseline factory defaults.
    ---
    tags:
      - Configuration Management
    description: >
      Rolls back the current volatility protection policy to the original 
      factory-defined baseline. This operation overwrites the persistent 
      storage layer and is typically used to recover from misconfigurations 
      or to re-synchronize the environment during emergency maintenance.
    responses:
      200:
        description: Configuration successfully rolled back to baseline.
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "Risk policy reset to factory defaults"
                current_settings:
                  type: object
                  description: The restored baseline configuration object.
      500:
        description: Failed to persist the default state to storage.
    """
    global CURRENT_SETTINGS
    CURRENT_SETTINGS = FACTORY_DEFAULTS.copy()
    save_settings(CURRENT_SETTINGS)

    return jsonify({
        "message": "Risk policy reset to factory defaults",
        "current_settings": CURRENT_SETTINGS
    })


# --- Business Rules ---
def fetch_exchange_rate(source, target):
    """
    Acquire real-time exchange rates and market volatility data with inverse-pair fallback logic.

    This function acts as a resilient data fetcher for currency parities. It implements 
    a dual-attempt strategy:
    1. Primary: Attempts to fetch the direct 'source-target' rate.
    2. Fallback: If the direct pair is unavailable, it fetches the 'target-source' inverse 
       rate and applies reciprocal transposition to derive the market price and range.

    Args:
        source (str): ISO 4217 source currency code (e.g., 'BRL').
        target (str): ISO 4217 target currency code (e.g., 'USD').

    Returns:
        tuple (float, float, float, bool): 
            - rate (float): The current bid price.
            - high (float): 24h market ceiling.
            - low (float): 24h market floor.
            - success (bool): Operational flag; False if both attempts fail.

    Mathematical Transformation (Inverse Fallback):
        When a direct rate is unavailable, the function calculates:
        - $Price = 1 / Bid_{inverse}$
        - $High = 1 / Low_{inverse}$ (Upper bound becomes the reciprocal of the lower bound)
        - $Low = 1 / High_{inverse}$ (Lower bound becomes the reciprocal of the upper bound)

    Notes:
        - Network timeouts are capped at 3 seconds to prevent upstream latency propagation.
        - Floating-point division by zero is internally guarded.
    """
    print("DEBUG: Buscando taxa para {source}->{target}") # DEBUG
    # First Attempt (Users choice)
    pair_direct = f"{source}{target}"
    url_direct = f"https://economia.awesomeapi.com.br/last/{source}-{target}"

    try:
        response = requests.get(url_direct, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if pair_direct in data:
                item = data[pair_direct]
                return float(item['bid']), float(item['high']), float(item['low']), True
            else:
                print(f"DEBUG: Chave direta {url_direct} não encontrada no JSON.") # DEBUG
    except Exception as e:
        print(f"DEBUG: Erro na tentativa direta: {e}") # DEBUG
        pass
    
    # Second Attempt (Inverts the search to get not found value)
    pair_inverse = f"{target}{source}"
    url_inverse = f"https://economia.awesomeapi.com.br/last/{target}-{source}"

    print(f"DEBUG: Tentando inversa: {url_inverse}") # DEBUG

    try:
        response = requests.get(url_inverse, timeout=5)
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
            else:
                print(f"DEBUG: Chave inversa {rate_inverse} não encontrada. Veio: {list(data.keys())}") # DEBUG
        else:
            print(f"DEBUG: Falha na API inversa. Status: {response.status_code}") # DEBUG
                  
    except Exception as e:
        #pass
        print(f"DEBUG: Erro na tentativa inversa: {e}") # DEBUG
    
    return 0.0, 0.0, 0.0, False

def get_ai_safety_margin(currency, volatility_pct):
    """
    Heuristic risk assessment engine powered by Generative AI.

    Leverages Large Language Models (LLM) to perform dynamic spread synthesis 
    based on market variance. The engine operates as a non-deterministic 
    layer within a deterministic safety framework, implementing three layers 
    of protection:
    1. Operational Gate: Validates API credentials and user preference toggles.
    2. Prompt Engineering: Contextualizes market data into a zero-shot financial 
       reasoning task.
    3. Output Sanitization: A strict boundary-check (Safety Lock) that 
       neutralizes potential AI hallucinations or out-of-bounds responses.

    Args:
        currency (str): ISO 4217 target currency code for context (e.g., 'EUR').
        volatility_pct (float): Real-time 24-hour market volatility percentage.

    Returns:
        tuple (float, str):
            - margin (float): Risk-adjusted multiplier (e.g., 1.035). 
              Defaults to 1.02 (static 2% hedge) on failure or bypass.
            - status (str): Diagnostic trace indicating whether the result 
              originated from the LLM or a fallback mechanism.

    Safety Logic:
        To mitigate financial risk, the system enforces a hard-coded range:
        $1.00 < \text{multiplier} < 1.10$. Any AI-generated value outside 
        this window is discarded in favor of a conservative default.

    Exception Handling:
        Gracefully handles API timeouts, quota limits, and parsing errors 
        by defaulting to the baseline risk policy.
    """
    settings = load_settings()

    if not GEMINI_KEY or not settings["use_ai"]:
        return 1.02, "AI Disabled (Standard 2%)"
    
    try:
        model = genai.GenerativeModel(settings["ai_model"])
        prompt = f"""
        Act as a financial risk manager.
        The currency pair BRL-{currency} had a volatility of {volatility_pct:.2f}% in the last 24h.
        
        Determine a safety margin spread multiplier between 1.01 (1%) and 1.05 (5%).
        - Low volatility (<0.5%): return close to 1.01.
        - High volatility (>2%): return close to 1.05.
        
        Return ONLY the number (e.g., 1.03). Do not write text.
        """
        response = model.generate_content(prompt)
        ai_margin = float(response.text.strip().replace('*', ''))
        # Safety lock to prevent the AI from hallucinating absurd numbers
        if 1.00 < ai_margin < 1.10:
            return ai_margin, f"AI Calculated based on {volatility_pct:.2f}% volatility"
        return 1.02, "AI Value Out of Bounds (Fallback 2%)"
    except Exception as e:
        return 1.02, f"AI Error: {str(e)}"


@app.route('/convert', methods=['POST'])
def convert_price():
    """
    Execute high-precision currency conversion with automated volatility hedging.
    ---
    tags:
      - Pricing Engine
    description: >
      The core transactional endpoint of the GlobalPrice API. It orchestrates a 
      multi-step valuation pipeline:
      1. Market Data Acquisition: Fetches real-time FX rates and 24h volatility.
      2. Dynamic Risk Assessment: Evaluates market variance against persistent 
         thresholds.
      3. Decision Logic: Executes a 'Hard-Hedge' for high volatility or an 
         'AI-Optimized Spread' for standard market conditions.
      4. Precision Calibration: Calculates final pricing with adaptive rounding 
         for exotic vs. major currency pairs.
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - base_price
            - target_currency
          properties:
            base_price:
              type: number
              example: 1500.00
              description: Unit price in BRL (Base Currency).
            target_currency:
              type: string
              example: "USD"
              description: ISO 4217 code for the destination currency.
    responses:
      200:
        description: Price successfully calculated with applied risk margins.
        content:
          application/json:
            schema:
              type: object
              properties:
                status_note:
                  type: string
                  example: "Standard Optimization"
                converted_price:
                  type: number
                  example: 285.45
                margin_applied:
                  type: number
                  example: 1.025
                spread_percentage:
                  type: string
                  example: "2.50%"
                ai_analysis:
                  type: string
                  description: Narrative justification for the applied spread.
      400:
        description: Payload validation error or non-numeric pricing.
      404:
        description: Currency pair liquidity not found in the exchange market.
      500:
        description: Internal pipeline failure.
    """
    data = request.get_json()
    if not data or 'base_price' not in data or 'target_currency' not in data:
        return jsonify({"error": "Invalid data."}), 400
    
    # --- Check REDIS ---
    is_panic_mode = False
    panic_volatility = 0.0

    if cache:
        try:
            if cache.get("MARKET_PANIC_MODE") == "TRUE":
                is_panic_mode = True
                panic_volatility = float(cache.get("MARKET_LAST_VOLATILITY") or 5.0)
        except Exception:
            pass
    
    try:
        settings = load_settings()
        base_price_brl = float(data.get('base_price', 0))
        target_currency = data.get('target_currency', '').upper()

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
        
        # Calculate Volatility (WATCHDOG x IA)
        # Scenario #1 - PANIC DETECTED!!!
        if is_panic_mode and target_currency in ['BTC', 'ETH']:
            margin = 1 + (panic_volatility * 10 / 100)
            if margin < 1.05: margin = 1.05

            reason = f"🐶 WALTER ALERTS: 🚨 Real-time anomaly on Binance! Volatility {panic_volatility:.2f}%."
            status_note = "CRITICAL: Watchdog Intervention 🐶"
            vol_display = f"{panic_volatility:.2f}% (Instant)"
        
        # Scenario # 2 - NORMAL FLOW (Auto-Hedge or AI)
        else:
          volatility = ((high - low) / low) * 100 if low > 0 else 0.0
          # Logic of "Automatic Profit Protection"
          threshold = settings['volatility_threshold']

          if volatility > threshold:
              margin = 1 + (volatility / 100)
              reason = f"⚠️ HIGH VOLATILITY ALERT: {volatility:.2f}% > Limit {threshold}%. Margin auto-adjusted to match volatility."
              status_note = "Auto-Hedge Active"
          else:
              margin, reason = get_ai_safety_margin(target_currency, volatility)
              status_note = "Standard Optimization"
              vol_display = f"{volatility:.2f}% (24h)"
        
        final_price = (base_price_brl * exchange_rate) * margin
        prec = 8 if exchange_rate < 0.01 else 2
        spread_pct = (margin - 1) * 100

        return jsonify({
            "status_note": status_note,
            "original_price_brl": base_price_brl,
            "exchange_currency": target_currency,
            "converted_price": round(final_price, prec),
            "rate_used": exchange_rate,
            "margin_applied": margin,
            "spread_percentage": f"{spread_pct:.2f}%",
            "market_volatility": vol_display,
            "ai_analysis": reason,
            "config_mode": "Watchdog Override" if is_panic_mode else ("AI" if settings["use_ai"] else "Manual")
        })
    
    except ValueError:
        return jsonify({"error": "Price value must be numeric."}), 400
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500
    
if __name__ == '__main__':
    # Running application on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
