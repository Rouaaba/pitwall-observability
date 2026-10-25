// Panel: Starting grid (panel-8)
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
    const G = (d.starting_grid || [])
      .slice()
      .sort((a, b) => a.position - b.position);
    if (!G.length) return E("Starting grid not published yet");
    const n = G.length,
      X = (p) => (p % 2 ? 0.3 : 0.7),
      Y = (p) => (p - 1) * 0.5;
    const mk = (drop) =>
      G.map((g) => ({
        value: [X(g.position), Y(g.position) - (drop ? 3 : 0)],
        name: g.driver,
        pos: g.position,
        team: g.team,
        itemStyle: {
          color: g.team_colour,
          opacity: drop ? 0 : 1,
          shadowBlur: 10,
          shadowColor: g.team_colour,
        },
      }));
    c.setOption(
      {
        backgroundColor: "transparent",
        tooltip: {
          formatter: (p) =>
            p.data.pos
              ? "P" + p.data.pos + " · " + p.data.name + " · " + p.data.team
              : "",
        },
        grid: { left: 10, right: 10, top: 10, bottom: 10 },
        xAxis: { type: "value", min: 0, max: 1, show: false },
        yAxis: {
          type: "value",
          inverse: true,
          min: -0.6,
          max: Y(n) + 0.6,
          show: false,
        },
        series: [
          {
            type: "scatter",
            silent: true,
            symbol: "rect",
            symbolSize: [96, 3],
            symbolOffset: [0, 16],
            itemStyle: { color: "#666" },
            animation: false,
            data: G.map((g) => [X(g.position), Y(g.position)]),
          },
          {
            id: "cars",
            type: "scatter",
            symbol: "roundRect",
            symbolSize: [96, 26],
            data: mk(true),
            label: {
              show: true,
              formatter: (p) => "P" + p.data.pos + "  " + p.data.name,
              color: "#fff",
              fontWeight: "bold",
              fontSize: 12,
              textShadowColor: "#000",
              textShadowBlur: 3,
            },
          },
        ],
      },
      true,
    );
    setTimeout(
      () =>
        c.setOption({
          animationDurationUpdate: 700,
          animationEasingUpdate: "bounceOut",
          series: [
            {},
            {
              id: "cars",
              data: mk(false),
              animationDelayUpdate: (i) => i * 180,
            },
          ],
        }),
      150,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
