# SpreadMaker v6.56 (TRAIL)

**SpreadMaker** is a high-performance trading terminal and automated bot designed for **Binance Futures**. It combines advanced grid trading strategies with a powerful market scanner and real-time visualization.

Developed by: *cryptowolf programmer*

---

## 🚀 Key Features

* **Autopilot & Scanner:** Automatically scans the market for the most profitable pairs based on volatility (Standard Deviation) or stability.
* **Trailing Grid Strategy:** Sophisticated trailing logic (Up/Down) that follows price movement to maximize gains and minimize exposure.
* **Zero-Protect Logic:** Advanced safety mechanisms to prevent orders with invalid prices (<= 0) and handle high-volatility spikes.
* **Dual Mode:** Supports both **Paper Trading** (simulation) and **Real Trading** on Binance Futures.
* **Dynamic UI:** A comprehensive Tkinter-based interface with real-time logging, order tracking, and interactive charts (via `mplfinance`).
* **Batch Order Execution:** Optimized API calls using Binance Batch Orders for faster execution and lower latency.

## 🛠 Tech Stack

* **Language:** Python 3.x
* **GUI Framework:** Tkinter
* **Analysis:** NumPy, Pandas
* **Visualization:** Matplotlib, Mplfinance
* **API Integration:** RESTful API with HMAC SHA256 signing

## 📦 Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/SpreadMaker.git](https://github.com/YOUR_USERNAME/SpreadMaker.git)
   cd SpreadMaker


pip install numpy pandas matplotlib mplfinance requests



---

> ⚠️ **Archival experiment (2024–2025).** This is one of a series of personal crypto trading-bot experiments. Active trading has stopped; the code is released as-is for reference and learning. It may not run without adaptation (exchange API changes, missing dependencies, or configuration). **No warranty — never run it against a funded exchange account without a full review.**

## License

MIT — see [LICENSE](LICENSE).
