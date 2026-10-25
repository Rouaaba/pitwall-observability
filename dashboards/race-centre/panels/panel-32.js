// Panel: Conditions, latest session (panel-32)
const c = context.panel.chart;
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
const g = (name, val, min, max, center, color) => ({
  type: "gauge",
  center,
  radius: "78%",
  min,
  max,
  startAngle: 210,
  endAngle: -30,
  splitNumber: 4,
  progress: { show: true, width: 12, roundCap: true, itemStyle: { color } },
  axisLine: {
    roundCap: true,
    lineStyle: { width: 12, color: [[1, "rgba(255,255,255,0.08)"]] },
  },
  axisTick: { show: false },
  splitLine: { show: false },
  axisLabel: { color: "#777", fontSize: 9, distance: 16 },
  pointer: { show: false },
  anchor: { show: false },
  title: { offsetCenter: [0, "72%"], color: "#aaa", fontSize: 12 },
  detail: {
    valueAnimation: true,
    offsetCenter: [0, "0%"],
    fontSize: 22,
    fontWeight: "bold",
    color: "#eee",
    formatter: (v) => (v == null ? "–" : v.toFixed(1)) + " °C",
  },
  data: [{ value: val, name }],
  animationDuration: 1000,
  animationEasing: "cubicOut",
});
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const cd = d.conditions || {};
    const rain = !!cd.rain;
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        series: [
          g("Track", cd.track_temperature, 0, 60, ["18%", "58%"], "#ff7043"),
          g("Air", cd.air_temperature, 0, 45, ["50%", "58%"], "#29b6f6"),
        ],
        graphic: [
          {
            type: "circle",
            left: "78%",
            top: "26%",
            shape: { r: 26 },
            style: { fill: rain ? "#0067ff" : "rgba(255,255,255,0.08)" },
            keyframeAnimation: rain
              ? {
                  duration: 1500,
                  loop: true,
                  keyframes: [
                    { percent: 0.5, scaleX: 1.12, scaleY: 1.12 },
                    { percent: 1, scaleX: 1, scaleY: 1 },
                  ],
                }
              : undefined,
          },
          {
            type: "text",
            left: "78%",
            top: "60%",
            style: {
              text: rain ? "Rain: Yes" : "Rain: No",
              fill: rain ? "#6aa6ff" : "#ccc",
              font: "bold 16px sans-serif",
            },
          },
          {
            type: "text",
            left: "78%",
            top: "74%",
            style: {
              text:
                "Humidity " +
                (cd.humidity != null ? Math.round(cd.humidity) + "%" : "–") +
                "  ·  Wind " +
                (cd.wind_speed != null
                  ? cd.wind_speed.toFixed(1) + " m/s"
                  : "–"),
              fill: "#999",
              font: "11px sans-serif",
            },
          },
        ],
      },
      true,
    );
  });
return { backgroundColor: "transparent" };
