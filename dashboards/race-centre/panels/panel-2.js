// Panel: Pit stop ranking (panel-2)
const c = context.panel.chart;
const E = (t) =>
  c.setOption(
    {
      title: {
        text: t,
        left: "center",
        top: "middle",
        textStyle: { color: "#999", fontSize: 13 },
      },
    },
    true,
  );
const ax = {
  axisLabel: { color: "#999" },
  axisLine: { lineStyle: { color: "#555" } },
  splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
  nameTextStyle: { color: "#999" },
};
fetch(
  context.grafana.replaceVariables(
    "https://rouaaba.github.io/pitwall-data/data/snapshots/race_${meeting}.json",
  ),
)
  .then((r) => r.json())
  .then((d) => {
    const P = (d.pit_stops || [])
      .map((p) => ({
        ...p,
        t: +(p.stop_duration ?? p.duration ?? p.pit_duration),
      }))
      .filter((p) => p.t > 0)
      .sort((a, b) => a.t - b.t)
      .slice(0, 15);
    if (!P.length) return E("No pit stops");
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        animationDelay: (i) => i * 80,
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          valueFormatter: (v) => v.toFixed(2) + " s",
        },
        grid: { left: 70, right: 50, top: 10, bottom: 30 },
        xAxis: { type: "value", name: "s", min: 0, ...ax },
        yAxis: {
          type: "category",
          inverse: true,
          data: P.map((p) => p.driver + " L" + p.lap),
          ...ax,
          axisLabel: {
            fontSize: 10,
            fontWeight: "bold",
            color: (v, i) => P[i].team_colour,
          },
        },
        series: [
          {
            type: "bar",
            barWidth: "60%",
            data: P.map((p) => ({
              value: p.t,
              itemStyle: { color: p.team_colour, borderRadius: [0, 4, 4, 0] },
            })),
            label: {
              show: true,
              position: "right",
              color: "#ddd",
              fontSize: 10,
              formatter: (p) => p.value.toFixed(2) + "s",
            },
          },
        ],
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
