// Panel: Tyre strategy (panel-1)
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
    const S = d.stints || [];
    if (!S.length) return E("No stint data");
    const CC = {
      SOFT: "#FF3333",
      MEDIUM: "#FFD12E",
      HARD: "#EEEEEE",
      INTERMEDIATE: "#39B54A",
      WET: "#00AEEF",
    };
    const R = (d.results || [])
      .slice()
      .sort((a, b) => a.position - b.position);
    const dr = [
      ...new Set([...R.map((r) => r.driver), ...S.map((s) => s.driver)]),
    ].filter((x) => S.some((s) => s.driver === x));
    const col = {};
    R.forEach((r) => (col[r.driver] = r.team_colour));
    S.forEach((s) => (col[s.driver] = s.team_colour || col[s.driver]));
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1200,
        animationEasing: "cubicOut",
        tooltip: {
          formatter: (p) =>
            p.data.d +
            " · " +
            p.data.c +
            " · L" +
            p.value[1] +
            "–" +
            p.value[2],
        },
        grid: { left: 50, right: 20, top: 10, bottom: 35 },
        xAxis: {
          type: "value",
          min: 1,
          name: "Lap",
          nameLocation: "middle",
          nameGap: 22,
          ...ax,
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: dr,
          ...ax,
          axisLabel: {
            fontSize: 10,
            fontWeight: "bold",
            color: (v) => col[v] || "#999",
          },
        },
        series: [
          {
            type: "custom",
            encode: { x: [1, 2], y: 0 },
            renderItem: (p, api) => {
              const y = api.value(0),
                a = api.coord([api.value(1) - 0.5, y]),
                b = api.coord([api.value(2) + 0.5, y]),
                h = api.size([0, 1])[1] * 0.6;
              return {
                type: "rect",
                shape: {
                  x: a[0],
                  y: a[1] - h / 2,
                  width: Math.max(b[0] - a[0] - 2, 1),
                  height: h,
                  r: 3,
                },
                style: api.style(),
              };
            },
            data: S.map((s) => ({
              value: [dr.indexOf(s.driver), s.lap_start, s.lap_end],
              d: s.driver,
              c: s.compound,
              itemStyle: {
                color: CC[String(s.compound).toUpperCase()] || "#777",
                borderColor: col[s.driver],
                borderWidth: 1.5,
              },
            })),
          },
        ],
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
