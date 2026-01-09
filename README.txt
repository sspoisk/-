This package is an extension of the `scalper_agent_channel_full` project that adds a manual cycle trigger directly in the dashboard.  In addition to all of the existing features (persistent configuration/state, channel‐based strategy, equity tracking and a web UI), it includes:

* **Force Cycle Button** on the dashboard: runs a full `agent_cycle` immediately, without waiting for the scheduled interval.  Useful for testing or when you need to fetch new market data on demand.
* **/api/force_cycle** API endpoint: accepts a POST request and performs one immediate cycle.  The server responds once the cycle is finished.
* Console logging: messages written via `log(...)` are echoed to the terminal for easier debugging on Windows 7.

Unzip this folder into your working directory (e.g. `C:\СКАЛЬПЕР.РУ\`) and run `start_agent.bat` or `python agent_channel.py`.  Visit `http://127.0.0.1:8080` in your browser.  You'll see the new “Прогнать цикл сейчас” button in the **Состояние** section.