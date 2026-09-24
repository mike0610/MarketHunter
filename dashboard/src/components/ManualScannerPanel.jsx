import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8010/manual-scanner";

export default function ManualScannerPanel() {
  const [market, setMarket] = useState("spot");
  const [timeframe, setTimeframe] = useState("1h");
  const [symbols, setSymbols] = useState("BTCUSDT, ETHUSDT");
  const [run, setRun] = useState(null);
  const [observations, setObservations] = useState([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!run || run.status !== "running") return;
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch(`${API}/runs/${encodeURIComponent(run.id)}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (active) {
          setRun(data.run);
          setObservations(data.observations || []);
        }
      } catch (e) {
        if (active) setError(`Не вдалося отримати стан сканування: ${e.message}`);
      }
    };
    poll();
    const timer = setInterval(poll, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [run?.id, run?.status]);

  async function start() {
    setError("");
    const list = symbols.split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
    if (!list.length || list.length > 20 || new Set(list).size !== list.length || list.some(s => !/^[A-Z0-9]{2,25}$/.test(s))) {
      setError("Вкажи від 1 до 20 унікальних символів Binance, наприклад BTCUSDT, ETHUSDT.");
      return;
    }
    setStarting(true);
    try {
      const response = await fetch(`${API}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, timeframe, symbols: list }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
      setObservations([]);
      setRun({ id: data.run_id, status: data.status, symbols_total: list.length, symbols_done: 0 });
    } catch (e) {
      setError(`Не вдалося запустити сканер: ${e.message}. Перевір, чи працює окремий сервіс на порту 8010.`);
    } finally {
      setStarting(false);
    }
  }

  return (
    <section style={{ background: "#151e2b", color: "#e7edf6", padding: 18, borderRadius: 12, marginBottom: 18 }}>
      <h3 style={{ marginTop: 0 }}>Окремий ручний сканер</h3>
      <p style={{ color: "#aebdd0" }}>Лише спостереження за пробоєм 20 закритих свічок. Не торгові сигнали та не автоматичні угоди.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <select aria-label="Ринок" value={market} onChange={e => setMarket(e.target.value)}><option value="spot">Spot</option><option value="futures">Futures</option></select>
        <select aria-label="Таймфрейм" value={timeframe} onChange={e => setTimeframe(e.target.value)}>{["15m", "1h", "4h", "1d"].map(t => <option key={t}>{t}</option>)}</select>
        <input aria-label="Символи" value={symbols} onChange={e => setSymbols(e.target.value)} style={{ minWidth: 240 }} />
        <button type="button" disabled={starting || run?.status === "running"} onClick={start}> {starting ? "Запуск…" : run?.status === "running" ? "Сканування…" : "Сканувати зараз"}</button>
      </div>
      {error && <p role="alert" style={{ color: "#ff9999" }}>{error}</p>}
      {run && <p>Запуск: {run.status} · Опрацьовано: {run.symbols_done ?? 0}/{run.symbols_total ?? "?"}{run.error ? ` · ${run.error}` : ""}</p>}
      {!!observations.length && <div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left" }}><thead><tr><th>Монета</th><th>Закрита свічка (UTC)</th><th>Ціна закриття</th><th>Макс. 20</th><th>Мін. 20</th><th>Спостереження</th></tr></thead><tbody>{observations.map(o => <tr key={o.id}><td>{o.symbol}</td><td>{o.candle_closed_at}</td><td>{o.close_price}</td><td>{o.breakout_high}</td><td>{o.breakdown_low}</td><td>{o.direction === "up" ? "Пробій вгору" : o.direction === "down" ? "Пробій вниз" : "Пробою немає"}</td></tr>)}</tbody></table></div>}
    </section>
  );
}
