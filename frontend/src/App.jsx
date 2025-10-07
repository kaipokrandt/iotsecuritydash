import React, { useEffect, useState, useRef } from "react";
import Plot from "react-plotly.js";

const MAX_EVENTS = 200; // keep only the last 200 events for performance

function App() {
  const [events, setEvents] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

  const eventListRef = useRef(null);
  const anomalyListRef = useRef(null);
  const wsRef = useRef(null);
  const retryRef = useRef(1000); // start backoff at 1s

  // === ENVIRONMENT VARIABLES ===
  const WS_URL = process.env.REACT_APP_WS_URL;
  const WS_TOKEN = process.env.REACT_APP_WS_TOKEN;
  const WS_FULL_URL = `${WS_URL}?token=${WS_TOKEN}`;

  // === WebSocket Setup with Reconnection ===
  useEffect(() => {
    let stop = false;

    const connect = () => {
      const ws = new WebSocket(WS_FULL_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("✅ WebSocket connected");
        setWsConnected(true);
        retryRef.current = 1000; // reset retry
        ws.send("frontend:ready");
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "anomaly") {
          setAnomalies((prev) => [
            ...prev,
            {
              timestamp: new Date().toLocaleTimeString(),
              device_id: data.device_id,
              metrics: data.payload.metrics,
              message: data.message || "Anomaly detected",
              event: data,
            },
          ]);
        } else {
          const newEvents = Array.isArray(data) ? data : [data];
          setEvents((prev) => {
            const combined = [...prev, ...newEvents];
            return combined.slice(-MAX_EVENTS);
          });
        }
      };

      ws.onclose = () => {
        console.warn("⚠️ WebSocket disconnected");
        setWsConnected(false);
        if (!stop) {
          // exponential backoff reconnect
          setTimeout(() => connect(), retryRef.current);
          retryRef.current = Math.min(retryRef.current * 2, 10000);
        }
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
      };
    };

    connect();
    return () => {
      stop = true;
      wsRef.current?.close();
    };
  }, [WS_FULL_URL]);

  // === Auto-scroll ===
  useEffect(() => {
    if (eventListRef.current) {
      eventListRef.current.scrollTop = eventListRef.current.scrollHeight;
    }
  }, [events]);

  useEffect(() => {
    if (anomalyListRef.current) {
      anomalyListRef.current.scrollTop = anomalyListRef.current.scrollHeight;
    }
  }, [anomalies]);

  // === Prepare data for charts ===
  const deviceEvents = events.filter((e) => e.payload?.metrics);
  const timestamps = deviceEvents.map((e) =>
    new Date(e.timestamp).toLocaleTimeString()
  );
  const temperatures = deviceEvents.map((e) => e.payload.metrics.temperature);
  const vibrations = deviceEvents.map((e) => e.payload.metrics.vibration);

  const anomalyIndices = anomalies
    .map((a) => deviceEvents.findIndex((ev) => ev.id === a.event?.id))
    .filter((i) => i !== -1);

  const tempHighlight = temperatures.map((t, idx) =>
    anomalyIndices.includes(idx) ? t : null
  );
  const vibHighlight = vibrations.map((v, idx) =>
    anomalyIndices.includes(idx) ? v : null
  );

  const listStyle = {
    height: "200px",
    overflowY: "auto",
    border: "1px solid #ccc",
    padding: "0.5rem",
    marginBottom: "1rem",
    borderRadius: "5px",
    background: "#f9f9f9",
  };

  // === Render ===
  return (
    <div style={{ padding: "2rem" }}>
      <h1>IoT Dashboard (Secure Live Updates)</h1>
      <p>
        WebSocket:{" "}
        <strong style={{ color: wsConnected ? "green" : "red" }}>
          {wsConnected ? "Connected" : "Disconnected"}
        </strong>
      </p>

      <h2>Event List (last {MAX_EVENTS})</h2>
      <div ref={eventListRef} style={listStyle}>
        {events.length === 0 ? (
          <p>Waiting for events...</p>
        ) : (
          <ul>
            {events.map((ev) => (
              <li key={ev.id}>
                <strong>{ev.device_id}</strong> | Temp:{" "}
                {ev.payload.metrics.temperature.toFixed(2)}°C | Vibration:{" "}
                {ev.payload.metrics.vibration.toFixed(2)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <h2>Live Metrics Chart</h2>
      <Plot
        data={[
          {
            x: timestamps,
            y: temperatures,
            type: "scatter",
            mode: "lines+markers",
            name: "Temperature",
            line: { color: "red" },
          },
          {
            x: timestamps,
            y: vibrations,
            type: "scatter",
            mode: "lines+markers",
            name: "Vibration",
            line: { color: "blue" },
          },
          {
            x: timestamps,
            y: tempHighlight,
            type: "scatter",
            mode: "markers",
            name: "Temp Anomaly",
            marker: { color: "darkred", size: 10, symbol: "x" },
          },
          {
            x: timestamps,
            y: vibHighlight,
            type: "scatter",
            mode: "markers",
            name: "Vibration Anomaly",
            marker: { color: "darkblue", size: 10, symbol: "x" },
          },
        ]}
        layout={{
          width: 800,
          height: 400,
          title: "Temperature & Vibration",
          paper_bgcolor: "#f4f4f4",
          plot_bgcolor: "#fafafa",
        }}
      />

      <h2>Anomaly Tracker</h2>
      <div ref={anomalyListRef} style={listStyle}>
        {anomalies.length === 0 ? (
          <p>No anomalies detected yet.</p>
        ) : (
          <ul>
            {anomalies.map((a, idx) => (
              <li key={idx}>
                [{a.timestamp}] <strong>{a.device_id}</strong> – Temp:{" "}
                {a.metrics.temperature.toFixed(2)}°C, Vib:{" "}
                {a.metrics.vibration.toFixed(2)} ({a.message})
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default App;
