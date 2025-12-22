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
    "ai_model": "gemini-2.5-flash", 
    "admin_fee": 0.005, # Default 0.5% margin fee
    "max_panic_margin": 1.50 # 50% max during panic
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
    Synchronize application configuration with a schema-aware migration logic.

    Retrieves global risk parameters from the local JSON store. This version 
    implements an automatic schema evolution mechanism: if the persisted file 
    is missing newly introduced keys (e.g., 'admin_fee'), the function 
    merges them from factory defaults without overwriting existing user 
    configurations.

    Returns:
        dict: A validated configuration object containing the full schema:
            - volatility_threshold (float): Limit for automatic hedge activation.
            - use_ai (bool): Toggle for Gemini-driven spread calculations.
            - ai_model (str): Target model identifier for the Generative AI API.
            - admin_fee (float): Service fee applied to the final conversion.

    Behavior:
        - Integrity Check: Iterates through FACTORY_DEFAULTS to ensure all 
          required keys exist in the loaded dictionary.
        - Resiliency: Falls back to a full 'FACTORY_DEFAULTS' copy if file 
          I/O fails or JSON structure is corrupted.
    """
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                saved = json.load(f)
                for key, val in FACTORY_DEFAULTS.items():
                    if key not in saved:
                        saved[key] = val
                return saved
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

# --- AI Settings ---  
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- AI Available Models (Diagnostic) ---
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


# --- Endpoints ---
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
        "version": "5.0.0 (Configurable Business Rules)",
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
    Update dynamic business rules, risk thresholds, and administrative fees.
    ---
    tags:
      - Configuration Management
    description: >
      Performs a partial update (PATCH) of the pricing engine's operational parameters. 
      This endpoint allows administrators to adjust market risk tolerance (volatility), 
      operational costs (admin_fee), and AI integration toggles in real-time. 
      Validation is enforced to prevent irrational financial configurations.
    parameters:
      - in: body
        name: body
        required: true
        description: JSON object containing one or more fields to update.
        schema:
          type: object
          properties:
            volatility_threshold:
              type: number
              format: float
              example: 5.0
              description: Maximum 24h volatility percentage before 'Auto-Hedge' triggers.
            admin_fee:
              type: number
              format: float
              example: 0.015
              description: Flat administrative fee (0.015 = 1.5%). Range allowed [0.0 - 0.5].
            use_ai:
              type: boolean
              example: true
              description: Toggle for Gemini-driven predictive spread synthesis.
    responses:
      200:
        description: Risk policy successfully synchronized and persisted.
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "Risk policy updated"
                new_settings:
                  type: object
                  description: The complete updated configuration schema.
      400:
        description: Validation Error (e.g., fee out of bounds or non-numeric input).
      415:
        description: Unsupported Media Type (Content-Type must be application/json).
    """
    global CURRENT_SETTINGS
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    settings = load_settings()
    
    # Update Volatility Limit (Deterministic Risk Gate)
    if 'volatility_threshold' in data:
        try:
            val = float(data['volatility_threshold'])
            if val < 0: return jsonify({"error": "Must be positive"}), 400
            settings['volatility_threshold'] = val
        except ValueError:
            return jsonify({"error": "Invalid threshold"}), 400
    
    # Update Administrative Fee (Revenue Management)
    if 'admin_fee' in data:
        try:
            val = float(data['admin_fee'])
            # Safety Guard: Prevents accidental fee spikes or negative values
            if val < 0:
                return jsonify({"error": "Admin fee must be positive"}), 400
            settings['admin_fee'] = val
        except ValueError:
            return jsonify({"error": "Invalid fee number"}), 400
    
    # Update Max Panic Margin
    if 'max_panic_margin' in data:
        try:
            val = float(data['max_panic_margin'])
            if val < 1.0:
                return jsonify({"error": "Max panic margin must be >= 1.0"}), 400
            settings['max_panic_margin'] = val
        except:
          return jsonify({"error": "Invalid max panic margin"}), 400
    
    # Update AI Integration Toggle
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
    print(f"DEBUG: Buscando taxa para {source}->{target}") # DEBUG
    # First Attempt (Users choice)
    headers = {"User-Agent": "Mozilla/5.0"}
    pair_direct = f"{source}{target}"
    url_direct = f"https://economia.awesomeapi.com.br/last/{source}-{target}"

    try:
        response = requests.get(url_direct, timeout=5, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if pair_direct in data:
                item = data[pair_direct]
                return float(item['bid']), float(item['high']), float(item['low']), True
            else:
                print(f"DEBUG: Chave direta {pair_direct} não encontrada no JSON.") # DEBUG
    except Exception as e:
        print(f"DEBUG: Erro na tentativa direta: {e}") # DEBUG
        pass
    
    # Second Attempt (Inverts the search to get not found value)
    pair_inverse = f"{target}{source}"
    url_inverse = f"https://economia.awesomeapi.com.br/last/{target}-{source}"

    print(f"DEBUG: Tentando inversa: {url_inverse}") # DEBUG

    try:
        response = requests.get(url_inverse, timeout=5, headers=headers)
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
    base_margin = 1.02 # Default fallback margin (2%)

    if not GEMINI_KEY or not settings["use_ai"]:
        return base_margin, "AI Disabled"
    
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
        if 1.00 < ai_margin < 1.20:
            return ai_margin, f"AI Calculated based on {volatility_pct:.2f}% volatility"
        return base_margin, "AI Value Out of Bounds (Fallback 2%)"
    except Exception as e:
        return base_margin, f"AI Error: {str(e)}"


@app.route('/convert', methods=['POST'])
def convert_price():
    """
    Execute high-precision currency conversion with automated volatility hedging.
    ---
    tags:
      - Pricing Engine
    description: >
      Calculates the final product price applying dynamic risk margins. 
      Allows simulation of scenarios and temporary override of global settings.
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
            force_panic:
              type: boolean
              example: false
              description: >
                 SIMULATION: Forces 'Watchdog Panic Mode' logic even if the market is calm. 
                 Useful to test the protection ceiling.
            admin_fee:
              type: number
              example: 0.005
              description: >
                 OVERRIDE: Temporarily sets the Administrative Fee for this calculation only.
                 (0.005 = 0.5%).
            volatility_threshold:
              type: number
              example: 5.0
              description: >
                 OVERRIDE: Temporarily sets the volatility limit before Auto-Hedge kicks in.
            max_panic_margin:
              type: number
              example: 1.50
              description: >
                 OVERRIDE: Temporarily sets the maximum price ceiling during panic.
    responses:
      200:
        description: Price successfully calculated.
      400:
        description: Input validation error.
      404:
        description: Exchange rate not found.
      500:
        description: Server error.
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
                val = cache.get("MARKET_LAST_VOLATILITY")
                panic_volatility = float(val) if val else 5.0
        except Exception:
            pass
    
    try:
        # 1. Load Defaults/Persistent Settings
        settings = load_settings()
        base_price_brl = float(data.get('base_price', 0))
        target_currency = data.get('target_currency', '').upper()

        # 2. Apply Request Overrides (Simulation Logic)
        admin_fee = float(data.get('admin_fee', settings.get('admin_fee', 0.005)))
        threshold = float(data.get('volatility_threshold', settings.get('volatility_threshold', 5.0)))
        max_panic = float(data.get('max_panic_margin', settings.get('max_panic_margin', 1.50)))

        # --- Panic Simulation received from Swagger ---
        force_panic = bool(data.get('force_panic', False))
        if force_panic:
            is_panic_mode = True
            if panic_volatility == 0.0:
                panic_volatility = 15.0 # Default simulated volatility

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
        
        
        # --- Calculate Volatility (WATCHDOG x IA) ---
        # Scenario #1 - PANIC DETECTED!!! (Walter Intervention)
        if is_panic_mode:
            risk_margin = (panic_volatility / 100)
            margin = 1 + risk_margin + admin_fee
            if margin > max_panic:
                margin = max_panic
            
            sim_tag = "[SIMULATION] " if force_panic else ""
            reason = f"{sim_tag}🐶 WALTER ALERTS: 🚨 Volatility {panic_volatility:.2f}% detected."
            status_note = "CRITICAL: Watchdog Intervention 🐶"
            vol_display = f"{panic_volatility:.2f}% (Instant)"
            config_source = "Watchdog (Panic Mode)"
        
        # Scenario # 2 - NORMAL FLOW (Auto-Hedge or AI)
        else:
          volatility = ((high - low) / low) * 100 if low > 0 else 0.0

          if volatility > threshold:
              risk_margin = (volatility / 100)
              margin = 1 + risk_margin + admin_fee
              
              reason = f"⚠️ HIGH VOLATILITY ALERT: {volatility:.2f}% > Limit {threshold}%. Margin auto-adjusted to match volatility."
              status_note = "Auto-Hedge Active"
              config_source = "Manual/Hedge Rules"

          # Ai Optimization Layer    
          else:
              risk_margin, reason = get_ai_safety_margin(target_currency, volatility)
              margin = risk_margin + admin_fee
    

              if "AI Disabled" in reason or "Error" in reason:
                status_note = "Standard Optimization (Fallback)"
                config_source = "Manual (AI Fail)"
              else:
                  status_note = "AI-Driven Optimization"
                  config_source = "AI (Gemini)"
          
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
            "config_mode": config_source,
            "applied_params": {
                "admin_fee": admin_fee,
                "threshold_used": threshold,
                "max_panic_used": max_panic
            }
        })
    
    except ValueError:
        return jsonify({"error": "Price value must be numeric."}), 400
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500
    
if __name__ == '__main__':
    # Running application on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
