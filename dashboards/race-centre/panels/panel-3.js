// Panel: Degradation: lap time vs tyre age (panel-3)
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
    let L = (d.laps || []).filter(
      (x) => x.lap_time > 0 && x.tyre_age != null && x.compound,
    );
    if (!L.length) return E("No lap time data");
    const ts = L.map((x) => x.lap_time).sort((a, b) => a - b),
      md = ts[ts.length >> 1];
    L = L.filter((x) => x.lap_time < md * 1.07);
    const CC = {
      SOFT: "#FF3333",
      MEDIUM: "#FFD12E",
      HARD: "#EEEEEE",
      INTERMEDIATE: "#39B54A",
      WET: "#00AEEF",
    };
    const by = {};
    L.forEach((x) => {
      const k = String(x.compound).toUpperCase();
      (by[k] = by[k] || []).push(x);
    });
    const ser = [];
    Object.entries(by).forEach(([k, a]) => {
      const cl = CC[k] || "#777";
      ser.push({
        name: k,
        type: "scatter",
        symbolSize: 6,
        itemStyle: { color: cl, opacity: 0.6 },
        data: a.map((x) => ({
          value: [x.tyre_age, x.lap_time],
          dr: x.driver,
          itemStyle: { borderColor: x.team_colour, borderWidth: 1 },
        })),
      });
      const n = a.length;
      if (n > 2) {
        const mx = a.reduce((s, x) => s + x.tyre_age, 0) / n,
          my = a.reduce((s, x) => s + x.lap_time, 0) / n;
        let nu = 0,
          de = 0;
        a.forEach((x) => {
          nu += (x.tyre_age - mx) * (x.lap_time - my);
          de += (x.tyre_age - mx) ** 2;
        });
        const b = de ? nu / de : 0,
          c0 = my - b * mx,
          xs = a.map((x) => x.tyre_age),
          x0 = Math.min(...xs),
          x1 = Math.max(...xs);
        ser.push({
          name: k,
          type: "line",
          showSymbol: false,
          silent: true,
          lineStyle: { color: cl, width: 2.5 },
          data: [
            [x0, c0 + b * x0],
            [x1, c0 + b * x1],
          ],
          endLabel: {
            show: true,
            formatter: (b >= 0 ? "+" : "") + b.toFixed(3) + " s/lap",
            color: cl,
            fontSize: 10,
          },
        });
      }
    });
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1400,
        animationEasing: "cubicOut",
        legend: { top: 0, textStyle: { color: "#bbb" } },
        tooltip: {
          trigger: "item",
          formatter: (p) =>
            p.data && p.data.dr
              ? p.data.dr +
                " · " +
                p.seriesName +
                " · age " +
                p.value[0] +
                " · " +
                p.value[1].toFixed(3) +
                "s"
              : "",
        },
        grid: { left: 55, right: 90, top: 35, bottom: 35 },
        xAxis: {
          type: "value",
          name: "Tyre age (laps)",
          nameLocation: "middle",
          nameGap: 22,
          ...ax,
        },
        yAxis: { type: "value", min: "dataMin", name: "Lap time (s)", ...ax },
        series: ser,
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
