// Panel: Strategy forecast: pit windows (panel-10)
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
    const sf = d.strategy_forecast || {};
    const P = (sf.typical_pit_laps || []).slice().sort((a, b) => a - b);
    if (!P.length) return E("No pit window forecast");
    const cnt = {};
    P.forEach((l) => (cnt[l] = (cnt[l] || 0) + 1));
    const W = [];
    let s = P[0],
      e = P[0];
    for (let i = 1; i < P.length; i++) {
      if (P[i] - e > 4) {
        W.push([s, e]);
        s = P[i];
      }
      e = P[i];
    }
    W.push([s, e]);
    const st = sf.median_stint_length_by_compound || {};
    const max = Math.max(d.total_laps || 0, P[P.length - 1] + 10);
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        tooltip: { trigger: "axis" },
        grid: { left: 40, right: 20, top: 36, bottom: 40 },
        xAxis: {
          type: "value",
          min: 1,
          max: max,
          name: "Lap",
          nameLocation: "middle",
          nameGap: 24,
          ...ax,
        },
        yAxis: {
          type: "value",
          name: "Historic stops",
          minInterval: 1,
          ...ax,
        },
        graphic: [
          {
            type: "text",
            left: 45,
            top: 6,
            style: {
              text:
                "Median stint: " +
                Object.entries(st)
                  .map(([k, v]) => k + " " + v + " laps")
                  .join(" · "),
              fill: "#999",
              fontSize: 11,
            },
          },
        ],
        series: [
          {
            type: "bar",
            name: "Stops",
            barWidth: 6,
            itemStyle: { color: "#e10600", borderRadius: [3, 3, 0, 0] },
            data: Object.entries(cnt).map(([l, v]) => [+l, v]),
            markArea: {
              itemStyle: { color: "rgba(0,215,182,0.15)" },
              label: { color: "#bbb", fontSize: 10 },
              data: W.map((w, i) => [
                {
                  xAxis: w[0] - 0.5,
                  name: "Window " + (i + 1) + "\nL" + w[0] + "–" + w[1],
                },
                { xAxis: w[1] + 0.5 },
              ]),
            },
          },
        ],
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
