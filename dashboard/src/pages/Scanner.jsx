import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, Divider, FormControl,
  InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import PageHeader from "../components/layout/PageHeader";

const API = "http://127.0.0.1:8010/manual-scanner";
const PAGE_SIZE = 25;
const TERMINAL = new Set(["completed", "partial", "failed"]);
const SIGNAL_DIRECTIONS = new Set(["up", "down", "long", "short"]);
const summarizeObservations = (items) => ({
  total: items.length,
  signals: items.filter((item) => SIGNAL_DIRECTIONS.has(String(item.direction ?? "").toLowerCase())).length,
  noBreakout: items.filter((item) => item.strategy === "level_breakout" && String(item.direction ?? "").toLowerCase() === "none").length,
});
const LABEL = { up: "Пробій вгору", down: "Пробій вниз", none: "Пробою немає", long: "LONG", short: "SHORT" };
const STRATEGY_LABEL = { level_breakout: "Пробій рівня", compression: "Compression", order_block: "OrderBlock", premium_discount: "PremiumDiscount", breakout: "Breakout", all: "Усі стратегії" };
const formatTime = (value) => value && !Number.isNaN(new Date(value).getTime())
  ? new Date(value).toLocaleString("uk-UA", { timeZone: "UTC", dateStyle: "short", timeStyle: "medium" }) + " UTC" : "—";
const price = (value) => Number.isFinite(Number(value))
  ? Number(value).toLocaleString("uk-UA", { maximumSignificantDigits: 10 }) : "—";

async function api(path, options) {
  const response = await fetch(`${API}${path}`, options);
  let payload;
  try { payload = await response.json(); } catch { throw new Error(`HTTP ${response.status}: некоректна відповідь API`); }
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`);
  return payload;
}

function Filter({ label, value, onChange, options }) {
  return <FormControl size="small" sx={{ minWidth: 0, width: "100%" }}>
    <InputLabel>{label}</InputLabel>
    <Select label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <MenuItem value="all">Усі</MenuItem>
      {options.map(([key, title]) => <MenuItem key={key} value={key}>{title}</MenuItem>)}
    </Select>
  </FormControl>;
}


function CandleChart({ observation, expanded = false }) {
  const [state, setState] = useState({ loading: true, candles: [], error: "" });
  useEffect(() => {
    if (!observation) return undefined;
    const controller = new AbortController();
    setState({ loading: true, candles: [], error: "" });
    const query = new URLSearchParams({
      symbol: observation.symbol, exchange: observation.exchange || "binance", market: observation.market,
      timeframe: observation.timeframe, candle_closed_at: observation.candle_closed_at,
    });
    fetch(`${API}/candles?${query}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
        return data;
      })
      .then((data) => {
        if (!controller.signal.aborted) setState({ loading: false, candles: data.candles || [], error: "" });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ loading: false, candles: [], error: error.message });
      });
    return () => controller.abort();
  }, [observation?.id, observation?.symbol, observation?.market, observation?.timeframe, observation?.candle_closed_at]);

  if (!observation) return null;
  if (state.loading) return <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}><CircularProgress size={18} />Завантаження історичних свічок…</Box>;
  if (state.error) return <Alert severity="warning" sx={{ mt: 2 }}>Графік недоступний: {state.error}</Alert>;
  const candles = state.candles.filter((c) => [c.open, c.high, c.low, c.close, c.close_time].every(Number.isFinite));
  const observationTime = new Date(observation.candle_closed_at).getTime();
  const selectedIndex = candles.findIndex((c) => Math.abs(c.close_time - observationTime) < 2000);
  if (candles.length < 21 || selectedIndex < 20) return <Alert severity="warning" sx={{ mt: 2 }}>Недостатньо історичних свічок для графіка вибраного спостереження.</Alert>;
  const displayed = candles.slice(Math.max(0, selectedIndex - 79), selectedIndex + 1);
  // Only level_breakout persists the previous-20 breakout boundaries.
  // Research observations persist the analyzed candle's high/low in those
  // legacy database columns; never draw them as research strategy levels.
  const showBreakoutLevels = !observation.strategy || observation.strategy === "level_breakout";
  const high = Number(observation.breakout_high);
  const low = Number(observation.breakdown_low);
  const chartLows = displayed.map((c) => c.low);
  const chartHighs = displayed.map((c) => c.high);
  const min = Math.min(...chartLows, ...(showBreakoutLevels ? [low] : []));
  const max = Math.max(...chartHighs, ...(showBreakoutLevels ? [high] : []));
  const padding = Math.max((max - min) * 0.07, Math.abs(max) * 0.00001);
  const bottom = min - padding; const top = max + padding;
  const width = expanded ? 1400 : 800; const height = expanded ? 650 : 340; const left = 14; const right = 110;
  const plotWidth = width - left - right; const plotTop = 12; const plotBottom = height - 30;
  const y = (value) => plotTop + (top - value) / (top - bottom) * (plotBottom - plotTop);
  const step = plotWidth / displayed.length;
  const bodyWidth = Math.max(2, Math.min(expanded ? 15 : 9, step * 0.65));
  const levels = showBreakoutLevels
    ? [{ value: high, label: "Макс. 20", color: "#d9a441" }, { value: low, label: "Мін. 20", color: "#7fb5f5" }]
    : [];
  return <Box sx={{ mt: 2, minWidth: 0 }}>
    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Історичний графік · {observation.symbol} · {(observation.exchange || "binance").toUpperCase()} · {observation.market} · {observation.timeframe}</Typography>
    <Typography variant="caption" color="text.secondary">Остання свічка на графіку відповідає вибраному спостереженню. Наведи курсор на свічку для OHLC.</Typography>
    <Box sx={{ width: "100%", overflowX: "auto", mt: 1 }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Історичний свічковий графік ${observation.symbol}`} style={{ display: "block", width: "100%", minWidth: expanded ? 650 : 420, background: "#111b2a", borderRadius: 8 }}>
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const value = bottom + (top - bottom) * fraction;
          return <g key={fraction}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} stroke="#354255" strokeDasharray="3 4" /><text x={width - right + 7} y={y(value) + 4} fill="#b7c5d8" fontSize="12">{price(value)}</text></g>;
        })}
        {levels.map((level) => <g key={level.label}><line x1={left} x2={width - right} y1={y(level.value)} y2={y(level.value)} stroke={level.color} strokeDasharray="7 4" strokeWidth="1.3" /><text x={width - right + 7} y={y(level.value) - 6} fill={level.color} fontSize="11">{level.label}</text></g>)}
        {displayed.map((c, index) => {
          const x = left + (index + 0.5) * step;
          const color = c.close >= c.open ? "#44c69a" : "#f17679";
          const topBody = Math.min(y(c.open), y(c.close));
          const bodyHeight = Math.max(1.5, Math.abs(y(c.open) - y(c.close)));
          return <g key={`${c.open_time}-${index}`}>
            {index === displayed.length - 1 && <rect x={x - step / 2} y={plotTop} width={step} height={plotBottom - plotTop} fill="#ffffff" opacity="0.08" />}
            <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={color} strokeWidth="1.2" />
            <rect x={x - bodyWidth / 2} y={topBody} width={bodyWidth} height={bodyHeight} fill={color} />
            <title>{`${formatTime(c.close_time)}\nO: ${price(c.open)} H: ${price(c.high)} L: ${price(c.low)} C: ${price(c.close)}`}</title>
          </g>;
        })}
        <text x={left} y={height - 9} fill="#b7c5d8" fontSize="12">{formatTime(displayed[0].close_time)}</text>
        <text x={width - right} y={height - 9} textAnchor="end" fill="#b7c5d8" fontSize="12">{formatTime(displayed[displayed.length - 1].close_time)}</text>
      </svg>
    </Box>
    <Typography variant="caption" color="text.secondary">{showBreakoutLevels
      ? "Пунктирні лінії: максимум і мінімум попередніх 20 свічок для стратегії «Пробій рівня»."
      : "Рівні дослідницької стратегії в цьому записі не збережені, тому графік показує лише фактичні свічки."} Графік історичний, не поточна котировка.</Typography>
  </Box>;
}

export default function Scanner() {
  const [exchange, setExchange] = useState("binance");
  const [market, setMarket] = useState("spot");
  const [timeframe, setTimeframe] = useState("1h");
  const [mode, setMode] = useState("all");
  const [strategy, setStrategy] = useState("level_breakout");
  const [symbols, setSymbols] = useState("BTCUSDT, ETHUSDT");
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState(null);
  const [observations, setObservations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [chartExpanded, setChartExpanded] = useState(false);
  const [filterExchange, setFilterExchange] = useState("all");
  const [filterMarket, setFilterMarket] = useState("all");
  const [filterTimeframe, setFilterTimeframe] = useState("all");
  const [filterDirection, setFilterDirection] = useState("all");
  const [filterStrategy, setFilterStrategy] = useState("all");
  const [filterSymbol, setFilterSymbol] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const loadRun = useCallback(async (id) => {
    const result = await api(`/runs/${encodeURIComponent(id)}`);
    setRun(result.run);
    // Keep the history label in sync with the authoritative single-run response.
    setRuns((previous) => previous.map((item) => item.id === id ? { ...item, ...result.run } : item));
    setObservations(Array.isArray(result.observations) ? result.observations : []);
    setSelectedId((old) => result.observations?.some((item) => item.id === old)
      ? old : (result.observations?.[0]?.id ?? null));
    return result.run;
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError("");
    try {
      const result = await api("/runs");
      const list = Array.isArray(result.runs) ? result.runs : [];
      setRuns(list);
      const id = runId || list[0]?.id;
      if (id) {
        setRunId(id);
        await loadRun(id);
      } else {
        setRun(null);
        setObservations([]);
      }
    } catch (failure) { setError(`Окремий Scanner недоступний: ${failure.message}. Перевір порт 8010.`); }
    finally { setRefreshing(false); setLoading(false); }
  }, [runId, loadRun]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (!runId || run?.status !== "running") return undefined;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const current = await loadRun(runId);
        if (active && TERMINAL.has(current.status)) {
          const result = await api("/runs");
          if (active) setRuns(result.runs || []);
        }
      } catch (failure) { if (active) setError(`Не вдалося оновити стан: ${failure.message}`); }
    }, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [runId, run?.status, loadRun]);

  async function startScan() {
    const list = symbols.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (mode === "selected" && (!list.length || list.length > 20 || new Set(list).size !== list.length || list.some((s) => !/^[A-Z0-9]{2,25}$/.test(s)))) {
      setError("Вкажи від 1 до 20 унікальних символів, наприклад BTCUSDT, ETHUSDT.");
      return;
    }
    setStarting(true);
    setError("");
    try {
      const result = await api("/runs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exchange, market, timeframe, mode, strategy, symbols: mode === "all" ? [] : list }),
      });
      setRunId(result.run_id);
      const initialRun = { id: result.run_id, status: "running", started_at: new Date().toISOString(), exchange, market, timeframe, strategy, symbols_done: 0, symbols_total: mode === "all" ? 0 : list.length };
      setRun(initialRun);
      setRuns((previous) => [initialRun, ...previous.filter((item) => item.id !== result.run_id)].slice(0, 30));
      setObservations([]);
      setSelectedId(null);
      setFilterExchange("all"); setFilterMarket("all"); setFilterTimeframe("all"); setFilterDirection("all"); setFilterStrategy("all"); setFilterSymbol(""); setPage(0);
    } catch (failure) { setError(`Не вдалося запустити сканування: ${failure.message}`); }
    finally { setStarting(false); }
  }

  async function chooseRun(id) {
    setRunId(id); setPage(0); setError("");
    try { await loadRun(id); } catch (failure) { setError(`Не вдалося завантажити запуск: ${failure.message}`); }
  }

  const filtered = useMemo(() => observations.filter((item) =>
    (filterExchange === "all" || (item.exchange || "binance") === filterExchange)
    && (filterMarket === "all" || item.market === filterMarket)
    && (filterTimeframe === "all" || item.timeframe === filterTimeframe)
    && (filterDirection === "all" || item.direction === filterDirection)
    && (filterStrategy === "all" || (item.strategy || "level_breakout") === filterStrategy)
    && item.symbol.toUpperCase().includes(filterSymbol.trim().toUpperCase())
  ), [observations, filterExchange, filterMarket, filterTimeframe, filterDirection, filterStrategy, filterSymbol]);
  const allCounts = useMemo(() => summarizeObservations(observations), [observations]);
  const filteredCounts = useMemo(() => summarizeObservations(filtered), [filtered]);
  const selected = filtered.find((item) => item.id === selectedId) || filtered[0] || null;
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const changeFilter = (setter) => (value) => { setter(value); setPage(0); };

  return <Box sx={{ minWidth: 0, width: "100%", maxWidth: "100%", overflowX: "clip" }}>
    <PageHeader title="Market Scanner" subtitle="Незалежне ручне сканування Binance та WEEX. Лише спостереження, без торгових угод." onRefresh={refresh} refreshing={refreshing} />
    <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 3 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>Окремий ручний сканер</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>«Пробій рівня» перевіряє підтримку/опір за 20 закритими свічками. Інші режими використовують існуючі MarketHunter Research-стратегії. Без торгових угод.</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 1.5, alignItems: "start" }}>
        <FormControl size="small" fullWidth><InputLabel>Біржа</InputLabel><Select label="Біржа" value={exchange} onChange={(e) => setExchange(e.target.value)}><MenuItem value="binance">Binance</MenuItem><MenuItem value="weex">WEEX</MenuItem></Select></FormControl>
        <FormControl size="small" fullWidth><InputLabel>Ринок</InputLabel><Select label="Ринок" value={market} onChange={(e) => setMarket(e.target.value)}><MenuItem value="spot">Spot</MenuItem><MenuItem value="futures">Futures</MenuItem></Select></FormControl>
        <FormControl size="small" fullWidth><InputLabel>Таймфрейм</InputLabel><Select label="Таймфрейм" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>{["15m", "1h", "4h", "1d"].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}</Select></FormControl>
        <FormControl size="small" fullWidth><InputLabel>Стратегія</InputLabel><Select label="Стратегія" value={strategy} onChange={(e) => setStrategy(e.target.value)}>{Object.entries(STRATEGY_LABEL).map(([key,title]) => <MenuItem key={key} value={key}>{title}</MenuItem>)}</Select></FormControl>
        <FormControl size="small" fullWidth><InputLabel>Режим</InputLabel><Select label="Режим" value={mode} onChange={(e) => setMode(e.target.value)}><MenuItem value="all">Усі USDT-пари</MenuItem><MenuItem value="selected">Вибрані монети</MenuItem></Select></FormControl>
        {mode === "selected" && <TextField size="small" label="Монети (до 20)" value={symbols} onChange={(e) => setSymbols(e.target.value)} sx={{ gridColumn: { xs: "1 / -1", xl: "span 2" } }} fullWidth />}
        <Button variant="contained" onClick={startScan} disabled={starting || run?.status === "running"} sx={{ minHeight: 40, width: "100%", whiteSpace: "nowrap", gridColumn: { xs: "1 / -1", sm: "auto" } }}>{starting ? "Запуск…" : run?.status === "running" ? "Сканування…" : "Сканувати зараз"}</Button>
      </Box>
      {run && <>
        <Typography variant="body2" sx={{ mt: 2 }}>Запуск: <b>{run.status}</b> · Опрацьовано: {run.symbols_done ?? 0}/{run.symbols_total ?? "?"} · {(run.exchange || "binance").toUpperCase()} · {run.market} · {run.timeframe}{run.status === "running" && run.symbols_total === 0 ? " · Отримання списку пар…" : ""}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>Записів: {allCounts.total} · Сигнальних спостережень: {allCounts.signals} · Без пробою: {allCounts.noBreakout}</Typography>
      </>}
      {run?.error && <Alert severity={run.status === "failed" ? "error" : "warning"} sx={{ mt: 1 }}>{run.error}</Alert>}
      {!!runs.length && <FormControl size="small" sx={{ minWidth: 280, maxWidth: "100%", mt: 2 }}><InputLabel>Історія ручних запусків</InputLabel><Select label="Історія ручних запусків" value={runId} onChange={(e) => void chooseRun(e.target.value)}>{runs.map((item) => <MenuItem key={item.id} value={item.id}>{formatTime(item.started_at)} · {(item.exchange || "binance").toUpperCase()} {item.market} {item.timeframe} · {run?.id === item.id ? run.status : item.status}</MenuItem>)}</Select></FormControl>}
    </Paper>
    {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
    <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 3 }}><Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 1.5 }}>
      <Filter label="Біржа" value={filterExchange} onChange={changeFilter(setFilterExchange)} options={[["binance", "Binance"], ["weex", "WEEX"]]} />
      <Filter label="Ринок" value={filterMarket} onChange={changeFilter(setFilterMarket)} options={[["spot", "Spot"], ["futures", "Futures"]]} />
      <Filter label="Таймфрейм" value={filterTimeframe} onChange={changeFilter(setFilterTimeframe)} options={["15m", "1h", "4h", "1d"].map((t) => [t, t])} />
      <Filter label="Спостереження" value={filterDirection} onChange={changeFilter(setFilterDirection)} options={Object.entries(LABEL)} />
      <Filter label="Стратегія у результатах" value={filterStrategy} onChange={changeFilter(setFilterStrategy)} options={Object.entries(STRATEGY_LABEL).filter(([key]) => key !== "all")} />
      <TextField
        size="small" label="Знайти монету в результатах" value={filterSymbol}
        onChange={(event) => { setFilterSymbol(event.target.value); setPage(0); }}
        placeholder="BTCUSDT або 0GUSDT"
        sx={{ gridColumn: { xs: "1 / -1", xl: "span 2" } }}
        fullWidth
        inputProps={{ "aria-label": "Пошук монети серед збережених спостережень" }}
      />
    </Box></Paper>
    {loading ? <Box sx={{ display: "grid", placeItems: "center", minHeight: 200 }}><CircularProgress /></Box> :
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: "minmax(0, 1.08fr) minmax(0, 1fr)" }, gap: 2, alignItems: "start", minWidth: 0 }}>
        <Paper variant="outlined" sx={{ minWidth: 0, borderRadius: 3, overflow: "hidden" }}>
          <Box sx={{ p: 2 }}>
            <Typography variant="h6">Спостереження ({filteredCounts.total})</Typography>
            <Typography variant="body2" color="text.secondary">Сигнальних: {filteredCounts.signals} · Без пробою: {filteredCounts.noBreakout}</Typography>
            <Typography variant="caption" color="text.secondary">Пошук монети та фільтр стратегії вище працюють лише з уже збереженим запуском, нове сканування не запускають. Сигнальні спостереження не є командами на торгівлю. Натисни на рядок для деталей.</Typography>
          </Box>
          <TableContainer sx={{ maxHeight: 680, overflowX: "auto" }}><Table stickyHeader size="small" sx={{ tableLayout: "fixed", minWidth: 550 }}>
            <TableHead><TableRow><TableCell>Монета / ринок</TableCell><TableCell>Стратегія</TableCell><TableCell>Спостереження</TableCell><TableCell>Ціна закриття</TableCell><TableCell>Свічка (UTC)</TableCell></TableRow></TableHead>
            <TableBody>{visible.map((item) => <TableRow key={item.id} hover selected={selected?.id === item.id} onClick={() => setSelectedId(item.id)} sx={{ cursor: "pointer" }}>
              <TableCell><Typography fontWeight={700} variant="body2">{item.symbol}</Typography><Typography variant="caption" color="text.secondary">{(item.exchange || "binance").toUpperCase()} · {item.market} · {item.timeframe}</Typography></TableCell>
              <TableCell>{STRATEGY_LABEL[item.strategy] || item.strategy || "Пробій рівня"}</TableCell><TableCell>{LABEL[item.direction] || item.direction}</TableCell><TableCell>{price(item.close_price)}</TableCell><TableCell><Typography variant="caption">{formatTime(item.candle_closed_at)}</Typography></TableCell>
            </TableRow>)}{!visible.length && <TableRow><TableCell colSpan={5} align="center">{run?.status === "running" ? "Сканування триває…" : "Для вибраного запуску спостережень немає."}</TableCell></TableRow>}</TableBody>
          </Table></TableContainer>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ p: 1.5 }}><Typography variant="caption">{filtered.length ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, filtered.length)} із ${filtered.length}` : "0 записів"}</Typography><Stack direction="row" gap={1}><Button size="small" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Назад</Button><Button size="small" disabled={(page + 1) * PAGE_SIZE >= filtered.length} onClick={() => setPage((p) => p + 1)}>Далі</Button></Stack></Stack>
        </Paper>
        <Paper variant="outlined" sx={{ minWidth: 0, p: 2.5, borderRadius: 3, overflowWrap: "anywhere" }}>
          {!selected ? <Typography color="text.secondary">Вибери спостереження у таблиці.</Typography> : <>
            <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}><Typography variant="h5" fontWeight={700}>{selected.symbol}</Typography><Chip label={LABEL[selected.direction] || selected.direction} color={selected.direction === "up" ? "success" : selected.direction === "down" ? "warning" : "default"} /></Stack>
            <Typography variant="body2" color="text.secondary">{(selected.exchange || "binance").toUpperCase()} · {selected.market} · {selected.timeframe} · {STRATEGY_LABEL[selected.strategy] || selected.strategy || "Пробій рівня"}</Typography>
            <Typography variant="caption" color="text.secondary">Закриття свічки: {formatTime(selected.candle_closed_at)}</Typography><Divider sx={{ my: 2 }} />{selected.score != null && <Typography variant="body2" sx={{ mb: 1 }}>Score: <b>{selected.score}</b></Typography>}{selected.reasons && <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{(() => { try { return JSON.parse(selected.reasons).join(" · "); } catch { return selected.reasons; } })()}</Typography>}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>{[
              ["Ціна закриття", selected.close_price],
              [!selected.strategy || selected.strategy === "level_breakout" ? "Максимум попередніх 20" : "Максимум свічки спостереження", selected.breakout_high],
              [!selected.strategy || selected.strategy === "level_breakout" ? "Мінімум попередніх 20" : "Мінімум свічки спостереження", selected.breakdown_low],
            ].map(([label, value]) => <Box key={label}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography fontWeight={600}>{price(value)}</Typography></Box>)}</Box>
            <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
              <Button variant="outlined" size="small" onClick={() => setChartExpanded(true)}>⛶ Відкрити графік на весь екран</Button>
            </Box>
            {!chartExpanded && <CandleChart observation={selected} />}
            <Alert severity="info" sx={{ mt: 2 }}>Це історичне спостереження за закритою свічкою, а не підтвердження актуального входу, оцінка ймовірності чи команда на торгівлю.</Alert>
          </>}
        </Paper>
      </Box>}
      <Dialog fullScreen open={chartExpanded && !!selected} onClose={() => setChartExpanded(false)} PaperProps={{ sx: { bgcolor: "#111b2a", color: "#fff" } }}>
        <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
          <Typography variant="h6">{selected?.symbol} · {selected?.market} · {selected?.timeframe} · історичний графік</Typography>
          <Button variant="outlined" onClick={() => setChartExpanded(false)} autoFocus>Закрити ✕</Button>
        </DialogTitle>
        <DialogContent sx={{ px: { xs: 1, md: 3 }, pb: 3 }}>
          {chartExpanded && selected && <CandleChart observation={selected} expanded />}
        </DialogContent>
      </Dialog>
  </Box>;
}
