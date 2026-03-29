import { Star } from 'lucide-react'

interface StarRatingProps {
  /** Score 0-5 */
  score: number | null
  size?: number
}

export default function StarRating({ score, size = 16 }: StarRatingProps) {
  if (score == null) return <span className="star-na">—</span>

  const full = Math.floor(score)
  const fraction = score - full
  const empty = 5 - full - (fraction > 0 ? 1 : 0)

  return (
    <div className="star-rating">
      {Array.from({ length: full }, (_, i) => (
        <Star key={`f${i}`} size={size} className="star star--full" />
      ))}
      {fraction > 0 && (
        <span className="star-partial-wrap" style={{ width: size }}>
          <Star
            size={size}
            className="star star--full star-partial-fg"
            style={{ clipPath: `inset(0 ${(1 - fraction) * 100}% 0 0)` }}
          />
          <Star size={size} className="star star--empty star-partial-bg" />
        </span>
      )}
      {Array.from({ length: empty }, (_, i) => (
        <Star key={`e${i}`} size={size} className="star star--empty" />
      ))}
    </div>
  )
}
