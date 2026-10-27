export function scoreColor(score: number | null) {
  if (score == null) return "var(--line)";
  if (score >= 70) return "var(--teal)";
  if (score >= 45) return "var(--saffron)";
  return "var(--rose)";
}

export default function ScoreRing({ score, size = 52 }: { score: number | null; size?: number }) {
  const stroke = Math.max(4, Math.round(size / 11));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={score == null ? "لم تُقيَّم" : `توافق ${score} من 100`}>
      <svg width={size} height={size}>
        <circle className="bg" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        <circle
          className="fg"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={scoreColor(score)}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
        />
      </svg>
      <span className="val" style={{ fontSize: size * 0.32 }}>{score ?? "–"}</span>
    </div>
  );
}
