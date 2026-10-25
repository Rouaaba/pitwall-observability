// Panel: Next session (panel-30)
const c = context.panel.chart;
const W = (window.__pw = window.__pw || {});
clearInterval(W.cd);
const url = context.grafana.replaceVariables(
  "https://rouaaba.github.io/pitwall-data/data/snapshots/${meeting}.json",
);
const pad = (n) => String(n).padStart(2, "0");
fetch(url)
  .then((r) => r.json())
  .then((d) => {
    const ss = (d.sessions || []).map((s) => ({
      n: s.name,
      s: Date.parse(s.start),
      e: Date.parse(s.end),
    }));
    const ns = d.meeting && d.meeting.next_session;
    const tick = () => {
      const now = Date.now();
      const live = ss.find((s) => now >= s.s && now < s.e);
      let txt,
        sub = "",
        col = "#e8e8e8";
      if (live) {
        txt = "Live now";
        sub = live.n;
        col = "#ff3b3b";
      } else {
        let nx = ss.filter((s) => s.s > now).sort((a, b) => a.s - b.s)[0];
        if (!nx && ns && Date.parse(ns.start) > now) {
          nx = { n: ns.name, s: Date.parse(ns.start) };
        }
        if (!nx) {
          txt = "Weekend complete";
        } else {
          const t = Math.floor((nx.s - now) / 1000);
          const dd = Math.floor(t / 86400),
            h = Math.floor((t % 86400) / 3600),
            m = Math.floor((t % 3600) / 60),
            s = t % 60;
          txt =
            nx.n +
            " in " +
            (dd > 0 ? dd + "d " : "") +
            pad(h) +
            ":" +
            pad(m) +
            ":" +
            pad(s);
          sub = new Date(nx.s).toLocaleString([], {
            weekday: "short",
            hour: "2-digit",
            minute: "2-digit",
          });
        }
      }
      c.setOption({
        graphic: [
          {
            type: "text",
            id: "t",
            left: "center",
            top: "28%",
            style: { text: txt, fill: col, font: "bold 26px sans-serif" },
          },
          {
            type: "text",
            id: "s",
            left: "center",
            top: "68%",
            style: { text: sub, fill: "#999", font: "12px sans-serif" },
          },
          {
            type: "circle",
            id: "dot",
            left: 12,
            top: "middle",
            shape: { r: 7 },
            invisible: !live,
            style: { fill: "#ff3b3b" },
            keyframeAnimation: {
              duration: 1200,
              loop: true,
              keyframes: [
                {
                  percent: 0.5,
                  style: { opacity: 0.15 },
                  scaleX: 1.5,
                  scaleY: 1.5,
                },
                { percent: 1, style: { opacity: 1 }, scaleX: 1, scaleY: 1 },
              ],
            },
          },
        ],
      });
    };
    tick();
    W.cd = setInterval(tick, 1000);
  });
return {
  backgroundColor: "transparent",
  animationDuration: 1000,
  animationEasing: "cubicOut",
};
