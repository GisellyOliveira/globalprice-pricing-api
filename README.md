# 🧠 GlobalPrice - Pricing Service (AI Engine)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white) ![Flask](https://img.shields.io/badge/Flask-2.3-000000?style=flat&logo=flask&logoColor=white) ![Gemini](https://img.shields.io/badge/AI-Google_Gemini_2.5-8E75B2?style=flat&logo=google&logoColor=white) ![Redis](https://img.shields.io/badge/Redis-Pub%2FSub-DC382D?style=flat&logo=redis&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-Microservice-2496ED?style=flat&logo=docker&logoColor=white)

> **Secondary Microservice** responsible for complex financial calculations, external data fetching, real-time market monitoring, and AI integration.

## 📋 Project Description
This service acts as the **Financial Risk Engine** for the GlobalPrice architecture. It is a **REST API** designed to isolate business logic from the main application, ensuring separation of concerns.

It performs three critical tasks:
1.  **Data Fetching:** Retrieves real-time exchange rates from **AwesomeAPI**.
2.  **Market Surveillance:** Runs a background 🐶 **Watchdog ("Walter")** connected to **Binance WebSockets** to detect market crashes in real-time.
3.  **Risk Analysis:** Uses 🧠 **Google Gemini 2.5** (or Auto-Hedge logic) to determine dynamic safety margins.
4.  **Config Management:** Persists business rules (fees, thresholds) allowing runtime adjustments without redeployment.

**Architecture Pattern:** **Microservices (Scenario 2.1)**.
*   **Product Service (This Repo):** The user-facing API. It manages the product database (PostgreSQL) and acts as a Proxy/Gateway for price conversion.
*   **Pricing Service:** Encapsulates business logic, AI integration, and currency conversion.
* **Watchdog Service:** A background process that monitors currency exchanges in real-time and broadcasts "Panic Signals" via Redis.

---

## 💡 Key Features & Logic

### 🐶 Real-Time Watchdog ("Walter")
A parallel process that monitors the **BTC/USDT** stream on Binance.
*   **Panic Mode:** If volatility spikes > 0.2% in seconds, Walter activates a "Circuit Breaker" in Redis.
*   **Impact:** The Pricing Engine immediately ignores AI and switches to a mathematical "Hard Hedge" to protect revenue.

### 🤖 AI-Driven Risk Analysis
If the market is calm (Walter is sleeping), the API acts as a Smart Risk Manager:
*   **Decision Making:** Sends volatility data to **Google Gemini**.
*   **Dynamic Spread:** The AI decides the safety margin between **1%** and **5%** based on financial sentiment.

### 🔄 Robust Data Fetching (Inverse Logic)
To ensure high availability for cryptocurrencies:
*   **Direct Strategy:** Tries to fetch `BRL -> TARGET`.
*   **Fallback Strategy:** If the direct pair is unavailable (common for Crypto), it fetches `TARGET -> BRL` and mathematically inverts the rate (`1 / rate`), ensuring 99.9% uptime.

### ⚙️ Dynamic Configuration
Business rules are not hardcoded. Administrators can update:
*   **Admin Fee:** Profit margin per sale.
*   **Volatility Threshold:** When to stop using AI and start using Auto-Hedge.
*   **Panic Ceiling:** Max price increase allowed during a crash.

---

## 🔌 External APIs Used

This project integrates with third-party public services:
1. **AwesomeAPI (Currency Data):** 
    * **Service:** Real-time exchange rates.
    * **License:** Free for public use.
    * **Routes Used:** https://economia.awesomeapi.com.br/last/{coin}-{target}
2. **Google Gemini (Artificial Intelligence):** 
    * **Service:** Generative AI for financial risk analysis.
    * **Access:** Requires API Key (Free Tier).
    * **Model:** Gemini 2.5 Flash.
 3. **Binance WebSocket:**
    * **Service:** For real-time, high-frequency volatility monitoring (Stream).

---

## ⚙️ Installation & Execution

### Option A: Via Orchestrator (Recommended)
This service is designed to run inside the Docker network managed by the **Product API**. Please refer to the [Main Repository](../globalprice-products-api) to run the full stack using `docker-compose`.

### Option B: Standalone (Dev Mode)
If you need to test the logic in isolation:

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set API Key:**
    You need a Google Gemini Key (Get it [here](https://aistudio.google.com/app/apikey)).
    ```bash
    # Linux/Mac
    export GEMINI_API_KEY="YOUR_KEY_HERE"
    
    # Windows (CMD)
    set GEMINI_API_KEY="YOUR_KEY_HERE"
    ```

3.  **Run Application:**
    ```bash
    python app.py
    ```
    *The service will start on port 5000.*

---

## 📨 API Endpoint

### ✅ System Status
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | **Heartbeat:** Returns service status, version, and AI module connectivity (Active/Disabled). |

### 💵 Pricing Engine (Core)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/convert` | **Smart Conversion:** Calculates final price applying AI/Watchdog logic. Supports **simulation overrides** in the request body. |

**Request Body Example (Full capabilities):**
```json
{
  "base_price": 100.00,
  "target_currency": "USD",
  "admin_fee": 0.01,            // Optional: Override profit margin (1%)
  "volatility_threshold": 2.0,  // Optional: Override risk tolerance
  "max_panic_margin": 1.20,     // Optional: Override panic ceiling
  "force_panic": true           // Optional: Simulate a market crash
}
```

### ⚙️ Configuration Management
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/config` | **Read Policy** Retrieves current settings (admin_fee, thresholds, use_ai). |
| `PATCH` | `/config` | **Update Policy:** specific parameters in real-time. |
| `DELETE` | `/config` | **Reset:** Restores all settings to Factory Defaults. |

**PATCH Example (Update Rules):**
```json
{
  "volatility_threshold": 8.0,
  "admin_fee": 0.02,
  "use_ai": false
}
```

---

## 📄 License
This project is licensed under the **MIT License** and is part of the GlobalPrice MVP architecture for the Software Architecture postgraduate course at the Pontifical Catholic University of Rio de Janeiro (PUC-Rio).

See the [LICENSE](LICENSE) file for more details.
