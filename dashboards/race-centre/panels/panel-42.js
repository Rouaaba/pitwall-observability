// Panel: Championship progression (panel-42)
const c = context.panel.chart;
const W = (window.__pw = window.__pw || {});
clearInterval(W.br);
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const P = d.standings_progression || [];
    if (!P.length) {
      c.setOption(
        {
          title: {
            text: "Standings update after each race",
            left: "center",
            top: "middle",
            textStyle: { color: "#999" },
          },
        },
        true,
      );
      return;
    }
    const rounds = [...new Set(P.map((p) => p.round))].sort((a, b) => a - b);
    const rn = {};
    const col = {};
    P.forEach((p) => {
      rn[p.round] = p.race_name;
      col[p.driver] = p.team_colour;
    });
    const drivers = [...new Set(P.map((p) => p.driver))];
    const vals = (r) => {
      const m = {};
      P.filter((p) => p.round === r).forEach((p) => (m[p.driver] = p.points));
      return drivers.map((dr) => ({
        value: m[dr] || 0,
        itemStyle: { color: col[dr] },
      }));
    };
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        animationDurationUpdate: 1100,
        animationEasingUpdate: "linear",
        grid: { left: 50, right: 70, top: 10, bottom: 20 },
        xAxis: {
          type: "value",
          max: "dataMax",
          axisLabel: { color: "#999" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
        },
        yAxis: {
          type: "category",
          data: drivers,
          inverse: true,
          max: Math.min(drivers.length, 20) - 1,
          animationDuration: 300,
          animationDurationUpdate: 300,
          axisTick: { show: false },
          axisLabel: { fontSize: 11, color: (v) => col[v] || "#ccc" },
        },
        series: [
          {
            type: "bar",
            realtimeSort: true,
            barWidth: "70%",
            data: vals(rounds[0]),
            itemStyle: { borderRadius: [0, 3, 3, 0] },
            label: {
              show: true,
              position: "right",
              valueAnimation: true,
              color: "#ddd",
              fontSize: 11,
            },
          },
        ],
        graphic: [
          {
            type: "text",
            id: "rn",
            right: 80,
            bottom: 40,
            style: {
              text: "R" + rounds[0] + " · " + rn[rounds[0]],
              fill: "rgba(255,255,255,0.28)",
              font: "bold 30px sans-serif",
              textAlign: "right",
            },
          },
        ],
      },
      true,
    );
    let i = 0;
    W.br = setInterval(() => {
      i++;
      if (i >= rounds.length) {
        clearInterval(W.br);
        return;
      }
      const r = rounds[i];
      c.setOption({
        series: [{ data: vals(r) }],
        graphic: [{ id: "rn", style: { text: "R" + r + " · " + rn[r] } }],
      });
    }, 1300);
  });
return { backgroundColor: "transparent" };
