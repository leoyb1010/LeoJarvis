// 轻量 star 走势迷你图：根据历史快照画折线 + 面积，端点高亮。
type Point = { ts: number; stars: number };

export function Sparkline({
  points,
  width = 132,
  height = 38,
  trend = "up",
}: {
  points: Point[];
  width?: number;
  height?: number;
  trend?: "up" | "down" | "flat";
}) {
  const pts = (points || []).filter((p) => typeof p.stars === "number");
  if (pts.length < 2) {
    return <div className="spark-empty">数据点不足，下次扫描后生成走势</div>;
  }
  const xs = pts.map((p) => p.ts);
  const ys = pts.map((p) => p.stars);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 4;
  const sx = (x: number) => pad + ((x - minX) / (maxX - minX || 1)) * (width - pad * 2);
  const sy = (y: number) => height - pad - ((y - minY) / (maxY - minY || 1)) * (height - pad * 2);
  const line = pts.map((p) => `${sx(p.ts).toFixed(1)},${sy(p.stars).toFixed(1)}`).join(" ");
  const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
  const last = pts[pts.length - 1];
  const cls = trend === "down" ? "down" : trend === "flat" ? "flat" : "up";
  return (
    <svg className={`spark ${cls}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none">
      <polygon className="spark-area" points={area} />
      <polyline className="spark-line" points={line} fill="none" />
      <circle className="spark-dot" cx={sx(last.ts)} cy={sy(last.stars)} r={2.6} />
    </svg>
  );
}
