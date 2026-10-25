// Panel: Qualifying gap to pole (panel-31)
const c = context.panel.chart;
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const Q = (d.qualifying_gaps || [])
      .filter((q) => q.gap_to_pole !== null && q.gap_to_pole !== undefined)
      .sort((a, b) => a.position - b.position);
    if (!Q.length) {
      c.setOption(
        {
          title: {
            text: "Qualifying not run yet",
            left: "center",
            top: "middle",
            textStyle: { color: "#999" },
          },
        },
        true,
      );
      return;
    }
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        grid: { left: 70, right: 70, top: 8, bottom: 20 },
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          formatter: (ps) => {
            const q = Q[ps[0].dataIndex];
            return (
              "P" +
              q.position +
              " " +
              q.driver +
              "<br/>" +
              q.best_time.toFixed(3) +
              "s (+" +
              q.gap_to_pole.toFixed(3) +
              "s)"
            );
          },
        },
        xAxis: {
          type: "value",
          axisLabel: {
            color: "#999",
            formatter: (v) => "+" + v.toFixed(1) + "s",
          },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: Q.map((q) => "P" + q.position + "  " + q.driver),
          axisLabel: { color: "#ccc", fontSize: 10 },
          axisTick: { show: false },
        },
        series: [
          {
            type: "bar",
            barWidth: "68%",
            data: Q.map((q) => ({
              value: q.gap_to_pole,
              itemStyle: { color: q.team_colour, borderRadius: [0, 3, 3, 0] },
            })),
            label: {
              show: true,
              position: "right",
              color: "#ddd",
              fontSize: 10,
              formatter: (p) =>
                p.value === 0 ? "Pole" : "+" + p.value.toFixed(3) + "s",
            },
            animationDelay: (i) => i * 40,
          },
        ],
      },
      true,
    );
  });
return { backgroundColor: "transparent" };
