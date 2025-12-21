import json
import redis
import websocket
import threading
import time
import os
import random

# --- Test Panic Scenario ---
SIMULATE_PANIC = False

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"

try:
    cache = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    cache.ping()
    print(f"🐶 WALTER WAGS: Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"🐶 WALTER GROWLS: CRITICAL ERROR - Redis unreachable: {e} ...Grrr")
    cache = None

prices_window = []
WINDOW_SIZE = 20

def trigger_panic(volatility):
    """
    Broadcast an emergency market state via the distributed caching layer.

    This function triggers a system-wide 'Panic Mode' when anomalous market 
    fluctuations are detected. It utilizes Redis to set a short-lived semaphore, 
    effectively signaling all downstream microservices to bypass standard 
    optimization and adopt a high-risk mitigation strategy (Hard-Hedge).

    Args:
        volatility (float): The detected instantaneous market variance percentage 
            that triggered the emergency threshold.

    Behavior:
        - TTL (Time-To-Live): The panic state is transient and expires 
          automatically after 10 seconds to prevent permanent system lock-out.
        - Idempotency: Subsequent triggers within the 10s window will refresh 
          the expiration timer to the latest peak volatility.

    Notes:
        Requires an active 'cache' (Redis) connection. If the cache layer is 
        disconnected, the panic state fails silently to prevent a cascading 
        system failure (Fail-Open approach).
    """
    if cache:
        print(f"🚨 PANIC MODE ACTIVE! Instant Volatility: {volatility:.4f}% 🐶 WOOF WOOF!")
        cache.setex("MARKET_PANIC_MODE", 10, "TRUE")
        cache.setex("MARKET_LAST_VOLATILITY", 10, str(volatility))

def on_message(ws, message):
    """
    Handle real-time market data ingestion and execute sliding-window volatility analysis.

    This callback processes incoming tick data from the WebSocket stream. It maintains 
    a rolling memory of recent price points to compute high-frequency variance. 
    If the calculated volatility exceeds the safety threshold, it orchestrates 
    a system-wide risk mitigation sequence.

    Args:
        ws (websocket.WebSocketApp): The active WebSocket client instance.
        message (str): Raw JSON payload received from the exchange containing 
            price tick data (e.g., symbol, price, quantity).

    Logic:
        - Memory Management: Implements a FIFO (First-In-First-Out) buffer using 
          'prices_window' to maintain a constant-time complexity window.
        - Volatility Calculation: Computes the peak-to-trough percentage change 
          within the defined temporal window.
        - Panic Dispatcher: Evaluates two conditions for emergency state:
            1. Deterministic: Real-time volatility > 0.2%.
            2. Stochastic: Simulated panic triggers based on a probability 
               distribution (if SIMULATE_PANIC is enabled).

    Side Effects:
        - Updates the global 'prices_window' state.
        - May invoke 'trigger_panic()' to update the distributed Redis cache.

    Raises:
        Caught Internally: Any parsing or mathematical errors are caught to 
        prevent the WebSocket thread from terminating, ensuring continuous 
        market monitoring.
    """
    global prices_window

    try:
        data = json.loads(message)
        current_price = float(data['p'])

        prices_window.append(current_price)
        if len(prices_window) > WINDOW_SIZE:
            prices_window.pop(0)
        
        if len(prices_window) == WINDOW_SIZE:
            max_p = max(prices_window)
            min_p = min(prices_window)

            if min_p > 0:
                volatility = ((max_p - min_p) / min_p) * 100
            else:
                volatility = 0.0
            
            # TRIGGER RULE:
            # If volatility rises 0.2% in a matter of seconds, it's a Crash or Pump.
            # Or if a simulation is running.
            if volatility > 0.2 or (SIMULATE_PANIC and random.random() < 0.1):
                trigger_panic(volatility if volatility > 0.2 else 9.99)
    except Exception as e:
        print(f"🐶 GRRR: Data processing failure: {e}")

def on_error(ws, error):
    """
    Handle and log unexpected exceptions within the WebSocket lifecycle.

    This callback acts as the primary diagnostic point for network-level failures, 
    protocol violations, or stream interruptions. It ensures that connection 
    anomalies are captured and reported without causing the parent process 
    to terminate unexpectedly.

    Args:
        ws (websocket.WebSocketApp): The active WebSocket client instance where 
            the exception occurred.
        error (Exception): The error object or exception instance raised during 
            the stream operation (e.g., ConnectionRefused, Timeout, or SocketError).

    Observability:
        - Logs the incident to the standard output using the 'WATCHER' prefix 
          for easier log aggregation and troubleshooting in containerized 
          environments (Docker).

    Notes:
        In a production environment, this function can be extended to trigger 
        circuit-breaker patterns or send alerts to external monitoring 
        tools (e.g., Sentry, Slack Webhooks).
    """
    print("🐶 GRRR: : Connection Error Detected: {error}")

def on_close(ws, close_status_code, close_msg):
    """
    Handle the WebSocket termination event and initiate a reconnection sequence.

    This callback is triggered whenever the connection to the external market data 
    stream is severed, whether by the remote host or due to network instability. 
    It implements a basic 'Retry' policy to maintain persistent telemetry.

    Args:
        ws (websocket.WebSocketApp): The instance of the closing WebSocket.
        close_status_code (int): The RFC 6455 status code indicating the reason 
            for the closure (e.g., 1000 for normal closure, 1006 for abnormal).
        close_msg (str): A human-readable string clarifying the termination reason.

    Reconnection Strategy:
        - Backoff Interval: Enforces a 5-second mandatory cooldown period to 
          prevent rapid-fire reconnection attempts (spamming the exchange API).
        - Recursive Restart: Invokes 'start_vigia()' to re-initialize the socket 
          handshake and restore real-time monitoring.

    Side Effects:
        - Blocks the current thread for 5 seconds during the sleep phase.
        - Spawns a new connection cycle, effectively keeping the watcher alive 
          indefinitely (daemon-like behavior).
    """
    print("🐶 WOOF WOOF: Connection closed. Attempting to reconnect in 5s...")
    time.sleep(5)
    start_walter()

def on_open(ws):
    """
    Establish the initial handshake and initialize stream telemetry.

    This callback is invoked once the WebSocket connection is successfully 
    authenticated and opened. It serves as the activation point for the 
    monitoring logic, signaling that the system is ready to ingest and 
    process real-time market data.

    Args:
        ws (websocket.WebSocketApp): The instance of the newly opened WebSocket.

    Environment States:
        - Production Mode: Standard monitoring of the BTC/USDT ticker.
        - Simulation Mode: If 'SIMULATE_PANIC' is enabled, the system 
          acknowledges that stochastic triggers will be generated for 
          stress-testing the hedge logic.

    Observability:
        - Logs the successful connection to the console using the 'WATCHER' 
          prefix to provide immediate feedback on system readiness during 
          the container bootstrap.
    """
    print(f"🐶 WALTER WOOFS: Connection established. Eyes open on Binance BTC/USDT...")
    if SIMULATE_PANIC:
        print("⚠️ SIMULATION MODE ACTIVE: Artificial panic signals will be generated.")

def start_walter():
    """
    Initialize the market watcher service and maintain a persistent stream connection.

    This function acts as the orchestrator for the WebSocket client lifecycle. It 
    configures the event-driven callbacks (Handshake, Message Processing, Error 
    Handling, and Termination) and enters a blocking execution loop to ensure 
    continuous market surveillance.

    Lifecycle Management:
        - Connection Setup: Instantiates the 'WebSocketApp' pointing to the 
          Binance raw stream endpoint.
        - Event Mapping: Hooks internal handler functions to the asynchronous 
          events emitted by the data provider.
        - Blocking Loop: Executes 'run_forever()', which manages the socket's 
          keep-alive mechanism and internal heartbeats.

    Concurrency Note:
        This function is blocking. If integrated into a multi-service Flask 
        application, it should be dispatched within a dedicated Daemon Thread 
        to prevent blocking the web server's main event loop.

    Observability:
        Any disruption in this loop will trigger the 'on_close' callback, 
        initiating the system's self-healing (reconnection) logic.
    """
    ws = websocket.WebSocketApp(BINANCE_WS_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    start_walter()
