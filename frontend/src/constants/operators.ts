/** Operator definitions — colors, labels, MCC+MNC codes */

export interface Operator {
  id: string
  label: string
  color: string        // primary brand color for hexagons
  colorLight: string   // lighter tint for backgrounds
  colorBorder: string  // subtle border
}

export const OPERATORS: Operator[] = [
  {
    id: '28601',
    label: 'Turkcell',
    color: '#FFD200',
    colorLight: 'rgba(255,210,0,0.12)',
    colorBorder: 'rgba(255,210,0,0.35)',
  },
  {
    id: '28602',
    label: 'Vodafone',
    color: '#E60000',
    colorLight: 'rgba(230,0,0,0.10)',
    colorBorder: 'rgba(230,0,0,0.30)',
  },
  {
    id: '28603',
    label: 'Türk Telekom',
    color: '#005CFF',
    colorLight: 'rgba(0,92,255,0.10)',
    colorBorder: 'rgba(0,92,255,0.30)',
  },
]

export const OPERATOR_MAP = new Map(OPERATORS.map((op) => [op.id, op]))

/** Get operator or fallback */
export function getOperator(id: string): Operator {
  return OPERATOR_MAP.get(id) ?? {
    id,
    label: id,
    color: '#94A3B8',
    colorLight: 'rgba(148,163,184,0.10)',
    colorBorder: 'rgba(148,163,184,0.30)',
  }
}
