# 🧠 GlobalPrice - Pricing Service (AI Engine)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white) ![Flask](https://img.shields.io/badge/Flask-2.0-000000?style=flat&logo=flask&logoColor=white) ![Gemini](https://img.shields.io/badge/AI-Google_Gemini_2.5-8E75B2?style=flat&logo=google&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-Microservice-2496ED?style=flat&logo=docker&logoColor=white)

> **Secondary Microservice** responsible for complex financial calculations, external data fetching, and Artificial Intelligence integration.

## 📋 Project Description
This service acts as the **Financial Risk Engine** for the GlobalPrice architecture. It is a **REST API** designed to isolate business logic from the main application, ensuring separation of concerns.

It performs three critical tasks:
1.  **Data Fetching:** Retrieves real-time exchange rates from **AwesomeAPI**.
2.  **Risk Analysis:** Uses **Google Gemini 2.5** to analyze market volatility and determine a dynamic safety margin (spread).
3.  **Smart Calculation:** Applies mathematical rules for precision (e.g., handling Crypto vs. Fiat decimals).

---

## 💡 Key Features & Logic

### 🤖 AI-Driven Risk Analysis
Instead of a fixed profit margin, this API acts as a Risk Manager:
*   **Volatility Check:** Calculates the 24h variation `(High - Low) / Low`.
*   **Decision Making:** Sends market data to **Google Gemini**.
*   **Dynamic Spread:** The AI decides the safety margin between **1%** (Stable Market) and **5%** (High Volatility).

### 📐 Smart Precision (Rounding)
The system automatically adjusts decimal precision based on asset value:
*   **Fiat (USD, EUR, JPY):** Standard **2 decimal places** (e.g., `$ 250.50`).
*   **Crypto (BTC, ETH):** Extended **8 decimal places** (e.g., `₿ 0.00421893`) to prevent value loss.

### 🔄 Robust Data Fetching (Inverse Logic)
To ensure high availability for cryptocurrencies:
*   **Direct Strategy:** Tries to fetch `BRL -> TARGET`.
*   **Fallback Strategy:** If the direct pair is unavailable (common for Crypto), it fetches `TARGET -> BRL` and mathematically inverts the rate (`1 / rate`), ensuring 99.9% uptime.

---

## 🔌 External APIs Used

1.  **AwesomeAPI**
    *   **Purpose:** Real-time Exchange Rates & Daily High/Low.
    *   **Endpoint:** `https://economia.awesomeapi.com.br/last/{coin}-{target}`
2.  **Google Gemini AI**
    *   **Purpose:** Generative AI for volatility interpretation and spread decision.
    *   **Model:** `gemini-2.5-flash`.

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

### `POST /convert`
Converts a base price in BRL (Brazilian Real) to a target currency.

**Request Body:**
```json
{
  "base_price": 15000.00,
  "target_currency": "BTC"
}
{
  "original_price_brl": 15000.0,
  "exchange_currency": "BTC",
  "converted_price": 0.03224261,
  "rate_used": 0.00000204,
  "margin_applied": 1.05,
  "spread_percentage": "5.00%",
  "market_volatility_24h": "6.50%",
  "ai_analysis": "AI Calculated based on 6.50% volatility"
}
```

---

## 📄 License
This project is licensed under the **MIT License** and is part of the GlobalPrice MVP architecture for the Software Architecture postgraduate course at the Pontifical Catholic University of Rio de Janeiro (PUC-Rio).

See the [LICENSE](LICENSE) file for more details.
