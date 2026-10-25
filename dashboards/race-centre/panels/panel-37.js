// Panel: Tyre strategy, last year at this circuit (panel-37)
const c = context.panel.chart;
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
const C = {
  SOFT: "#ff3333",
  MEDIUM: "#ffd700",
  HARD: "#f0f0f0",
  INTERMEDIATE: "#39b54a",
  WET: "#0067ff",
};
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const T = d.tyre_strategy || [];
    if (!T.length) {
      c.setOption(
        {
          title: {
            text: "No tyre data",
            left: "center",
            top: "middle",
            textStyle: { color: "#999" },
          },
        },
        true,
      );
      return;
    }
    const drivers = T.map((t) => t.driver);
    const maxLap = Math.max(
      ...T.flatMap((t) => t.stints.map((s) => s.lap_end)),
    );
    const rItem = (p, api) => {
      const y = api.value(0);
      const s = api.coord([api.value(1), y]);
      const e = api.coord([api.value(2), y]);
      const h = api.size([0, 1])[1] * 0.62;
      return {
        type: "rect",
        shape: {
          x: s[0],
          y: s[1] - h / 2,
          width: Math.max(e[0] - s[0] - 1, 1),
          height: h,
          r: 3,
        },
        style: api.style(),
        enterFrom: { shape: { width: 0 } },
        transition: ["shape"],
      };
    };
    const series = Object.keys(C).map((k) => ({
      name: k,
      type: "custom",
      renderItem: rItem,
      encode: { x: [1, 2], y: 0 },
      itemStyle: { color: C[k] },
      animationDuration: 1000,
      animationEasing: "cubicOut",
      animationDelay: (i) => i * 25,
      data: T.flatMap((t, i) =>
        t.stints
          .filter((s) => (s.compound || "").toUpperCase() === k)
          .map((s) => [
            i,
            s.lap_start - 1,
            s.lap_end,
            s.lap_end - s.lap_start + 1,
          ]),
      ),
    }));
    series.push({
      name: "Pit stop",
      type: "scatter",
      symbol: "triangle",
      symbolRotate: 180,
      symbolSize: 9,
      itemStyle: { color: "#ffffff", borderColor: "#000", borderWidth: 1 },
      z: 5,
      animationDelay: (i) => 1000 + i * 10,
      data: T.flatMap((t, i) =>
        (t.pit_stops || []).map((p) => [p.lap, i, p.duration]),
      ),
    });
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1000,
        animationEasing: "cubicOut",
        legend: {
          top: 0,
          textStyle: { color: "#ccc", fontSize: 10 },
          itemWidth: 14,
          itemHeight: 8,
        },
        tooltip: {
          trigger: "item",
          formatter: (p) =>
            p.seriesName === "Pit stop"
              ? drivers[p.value[1]] +
                " · pit lap " +
                p.value[0] +
                (p.value[2] ? " · " + p.value[2].toFixed(1) + "s" : "")
              : drivers[p.value[0]] +
                " · " +
                p.seriesName +
                " · laps " +
                (p.value[1] + 1) +
                "–" +
                p.value[2] +
                " (" +
                p.value[3] +
                ")",
        },
        grid: { left: 45, right: 20, top: 26, bottom: 24 },
        xAxis: {
          type: "value",
          min: 0,
          max: maxLap,
          axisLabel: { color: "#999" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
          name: "Lap",
          nameLocation: "middle",
          nameGap: 18,
          nameTextStyle: { color: "#999" },
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: drivers,
          axisTick: { show: false },
          axisLabel: {
            fontSize: 10,
            color: (v, i) => (T[i] && T[i].team_colour) || "#ccc",
          },
        },
        series,
      },
      true,
    );
  });
return { backgroundColor: "transparent" };
