import React, { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";

function Dashboard() {
  const [points, setPoints] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      const res = await fetch("http://localhost:8000/events");
      const data = await res.json();
      setPoints(data.reverse());
    };
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const data = {
    labels: points.map(p => new Date(p.timestamp).toLocaleTimeString()),
    datasets: [
      {
        label: "Temperature",
        data: points.map(p => p.payload.metrics.temperature),
        borderColor: "red"
      }
    ]
  };

  return <Line data={data} />;
}

export default Dashboard;
