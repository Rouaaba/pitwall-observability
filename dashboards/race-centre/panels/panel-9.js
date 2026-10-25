// Panel: Strategy forecast: stop count (panel-9)
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
fetch(
  context.grafana.replaceVariables(
    "https://rouaaba.github.io/pitwall-data/data/snapshots/race_${meeting}.json",
  ),
)
  .then((r) => r.json())
  .then((d) => {
    const sd = (d.strategy_forecast || {}).stop_distribution || {};
    const D = Object.entries(sd)
      .filter(([, v]) => v > 0)
      .map(([k, v]) => ({
        name: +k === 0 ? "No-stop" : k + "-stop",
        value: Math.round(v * 1000) / 10,
      }));
    if (!D.length) return E("No strategy forecast");
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1200,
        animationEasing: "cubicOut",
        color: ["#888", "#00D7B6", "#FFD12E", "#FF3333", "#9B59B6"],
        tooltip: { trigger: "item", formatter: "{b}: {c}%" },
        legend: { bottom: 0, textStyle: { color: "#bbb" } },
        series: [
          {
            type: "pie",
            radius: ["45%", "70%"],
            center: ["50%", "48%"],
            itemStyle: {
              borderColor: "#181b1f",
              borderWidth: 2,
              borderRadius: 4,
            },
            label: { color: "#ddd", formatter: "{b}\n{c}%" },
            data: D,
          },
        ],
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
