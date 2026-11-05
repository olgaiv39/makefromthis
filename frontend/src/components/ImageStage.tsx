import { useRef, type ReactNode, type PointerEvent } from 'react';
import type { Material, Point } from '../types';
export function pointerPoint(event: PointerEvent<SVGSVGElement>, material: Material): Point {
  const svg = event.currentTarget;
  const p = svg.createSVGPoint(); p.x = event.clientX; p.y = event.clientY;
  const matrix = svg.getScreenCTM();
  const q = matrix ? p.matrixTransform(matrix.inverse()) : p;
  return [Math.max(0,Math.min(material.width,q.x)), Math.max(0,Math.min(material.height,q.y))];
}
export default function ImageStage({ material, children, onPoint, onMove, onRelease, interactive = false }: { material: Material; children?: ReactNode; onPoint?: (p: Point) => void; onMove?: (p: Point) => void; onRelease?: () => void; interactive?: boolean }) {
  const svgRef = useRef<SVGSVGElement>(null);
  return <div className="image-stage"><svg ref={svgRef} viewBox={`0 0 ${material.width} ${material.height}`} role="img" aria-label={`${material.name}${interactive ? '. Tap the two reference points here.' : ''}`} className={interactive ? 'interactive' : ''}
    onPointerDown={e => { if (interactive) { e.currentTarget.setPointerCapture(e.pointerId); onPoint?.(pointerPoint(e,material)); } }}
    onPointerMove={e => onMove?.(pointerPoint(e,material))} onPointerUp={onRelease} onPointerCancel={onRelease}>
    <image href={material.image} width={material.width} height={material.height}/>{children}
  </svg></div>;
}
