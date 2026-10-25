// Panel: Gap to leader (panel-6)
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
    const L = (d.laps || (d.race_replay || {}).laps || []).filter(
      (x) => x.gap_to_leader != null,
    );
    if (!L.length) return E("No gap data");
    const dr = [...new Set(L.map((x) => x.driver))];
    const col = {};
    L.forEach((x) => (col[x.driver] = x.team_colour));
    const lab = (t) => {
      t = String(t || "").toUpperCase();
      return t === "VSC" || t.includes("VIRTUAL")
        ? "VSC"
        : t.includes("RED")
          ? "RED"
          : t === "SC" || t.includes("SAFETY")
            ? "SC"
            : t.includes("PEN")
              ? "penalty"
              : t;
    };
    const kc = {
      SC: "#FFD12E",
      VSC: "#FF8C00",
      RED: "#e10600",
      penalty: "#bbb",
    };
    const KM = (d.key_moments || []).map((k) => {
      const t = lab(k.type || k.category || k.kind);
      return {
        xAxis: k.lap,
        label: {
          formatter: t + (k.driver ? " " + k.driver : ""),
          color: kc[t] || "#bbb",
          fontSize: 10,
        },
        lineStyle: { color: kc[t] || "#bbb", type: "dashed" },
      };
    });
    c.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 1500,
        animationEasing: "cubicOut",
        tooltip: {
          trigger: "axis",
          order: "valueAsc",
          valueFormatter: (v) => "+" + (+v).toFixed(1) + "s",
        },
        legend: { type: "scroll", top: 0, textStyle: { color: "#bbb" } },
        grid: { left: 50, right: 55, top: 40, bottom: 60 },
        xAxis: {
          type: "value",
          min: 1,
          name: "Lap",
          nameLocation: "middle",
          nameGap: 24,
          ...ax,
        },
        yAxis: {
          type: "value",
          inverse: true,
          min: 0,
          name: "Gap (s)",
          ...ax,
        },
        dataZoom: [
          {
            type: "slider",
            xAxisIndex: 0,
            bottom: 6,
            height: 18,
            textStyle: { color: "#999" },
          },
          { type: "inside", xAxisIndex: 0 },
        ],
        series: dr.map((n, i) => ({
          name: n,
          type: "line",
          smooth: 0.3,
          showSymbol: false,
          lineStyle: { width: 1.8, color: col[n] },
          itemStyle: { color: col[n] },
          endLabel: { show: true, formatter: n, color: col[n], fontSize: 10 },
          emphasis: { focus: "series" },
          data: L.filter((x) => x.driver === n)
            .sort((a, b) => a.lap - b.lap)
            .map((x) => [x.lap, x.gap_to_leader]),
          markLine:
            i === 0 ? { symbol: "none", silent: true, data: KM } : undefined,
        })),
      },
      true,
    );
  })
  .catch(() => E("Race data unavailable"));
return { backgroundColor: "transparent" };
