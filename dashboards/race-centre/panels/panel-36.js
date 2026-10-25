// Panel: Race replay, last year at this circuit (panel-36)
const c = context.panel.chart;
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const rr = d.race_replay || {};
    const L = rr.laps || [];
    if (!L.length) {
      c.setOption(
        {
          title: {
            text: "No race replay available",
            left: "center",
            top: "middle",
            textStyle: { color: "#999" },
          },
        },
        true,
      );
      return;
    }
    const maxLap = Math.max(...L.map((x) => x.lap));
    const drivers = [...new Set(L.map((x) => x.driver))];
    const col = {};
    L.forEach((x) => (col[x.driver] = x.team_colour));
    const bandsFor = (key, color, label) => {
      const ls = [...new Set(L.filter((x) => x[key]).map((x) => x.lap))].sort(
        (a, b) => a - b,
      );
      const out = [];
      let s = null,
        p = null;
      ls.forEach((l) => {
        if (s === null) {
          s = l;
          p = l;
        } else if (l === p + 1) {
          p = l;
        } else {
          out.push([s, p]);
          s = l;
          p = l;
        }
      });
      if (s !== null) out.push([s, p]);
      return out.map(([a, b]) => [
        { xAxis: a - 0.5, name: label, itemStyle: { color } },
        { xAxis: b + 0.5 },
      ]);
    };
    const bands = [
      ...bandsFor("safety_car", "rgba(255,215,0,0.16)", "SC"),
      ...bandsFor("virtual_safety_car", "rgba(255,140,0,0.14)", "VSC"),
      ...bandsFor("red_flag", "rgba(255,0,0,0.2)", "RED"),
    ];
    const byD = {};
    drivers.forEach(
      (dr) =>
        (byD[dr] = L.filter((x) => x.driver === dr).sort(
          (a, b) => a.lap - b.lap,
        )),
    );
    const mk = (upto) =>
      drivers.map((dr, i) => ({
        name: dr,
        type: "line",
        smooth: 0.3,
        showSymbol: true,
        symbol: "none",
        lineStyle: { width: 2, color: col[dr] },
        itemStyle: { color: col[dr] },
        endLabel: { show: true, formatter: dr, color: col[dr], fontSize: 10 },
        emphasis: { focus: "series" },
        data: byD[dr]
          .filter((x) => x.lap <= upto)
          .map((x) =>
            x.pit
              ? { value: [x.lap, x.position], symbol: "pin", symbolSize: 16 }
              : { value: [x.lap, x.position] },
          ),
        markArea:
          i === 0
            ? {
                silent: true,
                label: { color: "#bbb", fontSize: 10, position: "insideTop" },
                data: bands,
              }
            : undefined,
      }));
    const laps = [...Array(maxLap).keys()].map((i) => i + 1);
    c.setOption(
      {
        baseOption: {
          backgroundColor: "transparent",
          animationDuration: 1000,
          animationEasing: "cubicOut",
          animationDurationUpdate: 280,
          animationEasingUpdate: "linear",
          title: {
            text:
              ((d.meeting && d.meeting.name) || "Race") +
              " " +
              (rr.year || "") +
              " · race replay",
            left: "center",
            top: 4,
            textStyle: { color: "#e8e8e8", fontSize: 14 },
          },
          timeline: {
            axisType: "category",
            data: laps,
            autoPlay: true,
            loop: false,
            playInterval: 300,
            bottom: 4,
            left: 50,
            right: 50,
            label: { color: "#888", interval: 4 },
            lineStyle: { color: "#555" },
            checkpointStyle: { color: "#e10600", borderColor: "#e10600" },
            controlStyle: { color: "#ccc", borderColor: "#ccc" },
            itemStyle: { color: "#666" },
            progress: {
              lineStyle: { color: "#e10600" },
              itemStyle: { color: "#e10600" },
            },
            symbolSize: 6,
          },
          tooltip: {
            trigger: "item",
            formatter: (p) =>
              p.seriesName + " · lap " + p.value[0] + " · P" + p.value[1],
          },
          grid: { left: 45, right: 60, top: 36, bottom: 70 },
          xAxis: {
            type: "value",
            min: 1,
            max: maxLap,
            name: "Lap",
            nameLocation: "middle",
            nameGap: 22,
            nameTextStyle: { color: "#999" },
            axisLabel: { color: "#999" },
            splitLine: { show: false },
          },
          yAxis: {
            type: "value",
            inverse: true,
            min: 1,
            max: drivers.length,
            interval: 1,
            axisLabel: { color: "#999", formatter: "P{value}" },
            splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
          },
        },
        options: laps.map((l) => ({ series: mk(l) })),
      },
      true,
    );
  });
return { backgroundColor: "transparent" };
