import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from 'react';
import CheckRounded from '@mui/icons-material/CheckRounded';
import ZoomInRounded from '@mui/icons-material/ZoomInRounded';
import ZoomOutRounded from '@mui/icons-material/ZoomOutRounded';
import CenterFocusStrongOutlined from '@mui/icons-material/CenterFocusStrongOutlined';
import { nodeCopy } from './presentation';
import type { ArchitectureEdge, ArchitectureNode, SimulationEvent } from './model';

interface Item { node: ArchitectureNode; event?: SimulationEvent; eventIndex?: number }
interface Props {
  items: Item[];
  edges: ArchitectureEdge[];
  currentIndex: number;
  selectedNodeId: string;
  overview: boolean;
  playing: boolean;
  onSelect: (item: Item) => void;
}
interface Line { id: string; path: string; active: boolean; label?: string }

function meaningfulStatus(item: Item): string | null {
  if (!item.event) return null;
  if (item.event.title === 'Verifica non eseguita') return 'NOT_RUN';
  if (item.node.id === 'dossier') return item.event.title.includes('FAIL') ? 'Accounting FAIL' : 'Accounting PASS';
  return ['quote', 'structural', 'statement'].includes(item.node.id) ? item.event.state : null;
}

export default function FlowDiagram({ items, edges, currentIndex, selectedNodeId, overview, playing, onSelect }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [columns, setColumns] = useState(4);
  const [zoom, setZoom] = useState(1);
  const [lines, setLines] = useState<Line[]>([]);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const canvas = canvasRef.current;
    if (!viewport || !canvas) return undefined;
    const measure = () => {
      const available = viewport.clientWidth;
      const nextColumns = available >= 780 ? 4 : available >= 560 ? 3 : available >= 380 ? 2 : 1;
      setColumns(nextColumns);
      const origin = canvas.getBoundingClientRect();
      const rectangles = new Map(Array.from(canvas.querySelectorAll<HTMLElement>('[data-flow-node]')).map((element) => {
        const rect = element.getBoundingClientRect();
        return [element.dataset.flowNode!, { x: (rect.left - origin.left) / zoom, y: (rect.top - origin.top) / zoom, width: rect.width / zoom, height: rect.height / zoom }];
      }));
      const connections = overview ? edges : items.slice(1).flatMap((item, index) => {
        // In guided mode the arrows show the declared ordered demo events;
        // overview mode draws the canonical conditional data/control edges.
        const previous = items[index];
        return [{ id: `step-${index}`, from: previous.node.id, to: item.node.id }];
      });
      const nextLines = connections.flatMap((edge, index) => {
        const from = rectangles.get(edge.from); const to = rectangles.get(edge.to);
        if (!from || !to || !from.width || !to.width) return [];
        let path: string;
        const sameRow = Math.abs(from.y - to.y) < 10;
        if (sameRow) {
          const rightward = to.x > from.x;
          const x1 = from.x + (rightward ? from.width : 0);
          const x2 = to.x + (rightward ? 0 : to.width);
          const y1 = from.y + from.height / 2; const y2 = to.y + to.height / 2;
          const adjacent = Math.abs(x1 - x2) < 60;
          path = adjacent
            ? `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`
            : `M ${from.x + from.width / 2} ${from.y} V ${from.y - 14} H ${to.x + to.width / 2} V ${to.y}`;
        } else {
          const downward = to.y > from.y;
          const x1 = from.x + from.width / 2; const y1 = downward ? from.y + from.height : from.y;
          const x2 = to.x + to.width / 2; const y2 = downward ? to.y : to.y + to.height;
          const direct = !overview || (Math.abs(x1 - x2) < 10 && Math.abs(y1 - y2) < 50);
          if (direct) {
            path = `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`;
          } else {
            // Conditional bypasses go through row gaps and outside gutters,
            // never underneath an unrelated component card.
            const gutter = edge.id === 'gca-kg-only' ? 8 : canvas.clientWidth - 8;
            const startGap = y1 + (downward ? 16 : -16);
            const endGap = y2 + (downward ? -16 : 16);
            path = `M ${x1} ${y1} V ${startGap} H ${gutter} V ${endGap} H ${x2} V ${y2}`;
          }
        }
        return [{ id: edge.id, path, active: overview ? edge.to === selectedNodeId || edge.from === selectedNodeId : index < currentIndex, label: 'label' in edge ? edge.label as string : undefined }];
      });
      setLines((previous) => JSON.stringify(previous) === JSON.stringify(nextLines) ? previous : nextLines);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [items, edges, overview, currentIndex, selectedNodeId, zoom, columns]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const element = Array.from(canvasRef.current?.querySelectorAll<HTMLElement>('[data-flow-node]') ?? []).find((node) => node.dataset.flowNode === selectedNodeId);
    if (!viewport || !element) return;
    const bounds = viewport.getBoundingClientRect();
    const rect = element.getBoundingClientRect();
    if (!rect.height || !bounds.height) return;
    const outsideVertical = rect.top < bounds.top + 12 || rect.bottom > bounds.bottom - 12;
    const outsideHorizontal = rect.left < bounds.left + 12 || rect.right > bounds.right - 12;
    if (!outsideVertical && !outsideHorizontal) return;
    viewport.scrollTo?.({
      top: outsideVertical ? Math.max(0, viewport.scrollTop + rect.top - bounds.top - (bounds.height - rect.height) / 2) : viewport.scrollTop,
      left: outsideHorizontal ? Math.max(0, viewport.scrollLeft + rect.left - bounds.left - (bounds.width - rect.width) / 2) : viewport.scrollLeft,
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
  }, [selectedNodeId, items, zoom, columns]);

  const beginPan = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as Element).closest('button')) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    drag.current = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const movePan = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current || !viewportRef.current) return;
    viewportRef.current.scrollLeft = drag.current.left - (event.clientX - drag.current.x);
    viewportRef.current.scrollTop = drag.current.top - (event.clientY - drag.current.y);
  };

  return <div className="flow-diagram">
    <div className="flow-tools">
      <div className="flow-legend"><span><i className="legend-current" />{overview ? 'Componente selezionato' : 'Passaggio corrente'}</span>{!overview && <span><i className="legend-done" />Già percorso</span>}<span><i className="legend-waiting" />Da esplorare</span></div>
      <div className="flow-zoom" aria-label="Zoom del diagramma">
        <button type="button" onClick={() => setZoom(Math.max(0.8, Number((zoom - 0.1).toFixed(1))))} aria-label="Riduci zoom" disabled={zoom <= 0.8}><ZoomOutRounded /></button>
        <span>{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={() => setZoom(Math.min(1.5, Number((zoom + 0.1).toFixed(1))))} aria-label="Aumenta zoom" disabled={zoom >= 1.5}><ZoomInRounded /></button>
        <button type="button" onClick={() => { setZoom(1); viewportRef.current?.scrollTo?.({ left: 0, top: 0 }); }} aria-label="Ripristina vista"><CenterFocusStrongOutlined /></button>
      </div>
    </div>
    <div className="flow-viewport" ref={viewportRef} onPointerDown={beginPan} onPointerMove={movePan} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <div className="flow-canvas" ref={canvasRef} style={{ zoom, gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        <svg className={`flow-lines${playing ? ' is-playing' : ''}`} aria-hidden="true">
          <defs><marker id="flow-arrow" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="context-stroke" /></marker></defs>
          {lines.map((line) => <path key={line.id} d={line.path} className={`${line.active ? 'is-traversed' : ''}${!overview && line.id === `step-${currentIndex - 1}` ? ' is-current' : ''}`} markerEnd="url(#flow-arrow)">{line.label && <title>{line.label}</title>}</path>)}
        </svg>
        {items.map((item, index) => {
          const row = Math.floor(index / columns);
          const column = row % 2 === 0 ? index % columns + 1 : columns - index % columns;
          const selected = item.node.id === selectedNodeId;
          const completed = item.eventIndex !== undefined && item.eventIndex < currentIndex;
          const copy = nodeCopy[item.node.id];
          const status = meaningfulStatus(item);
          return <button key={item.node.id} type="button" data-flow-node={item.node.id}
            className={`flow-node${selected ? ' is-selected' : ''}${completed ? ' is-completed' : ''}${selected && status === 'MISMATCH' ? ' is-mismatch' : ''}${selected && status === 'UNRESOLVED' ? ' is-unresolved' : ''}`}
            style={{ gridColumn: column, gridRow: row + 1 }}
            aria-label={overview ? `Ispeziona ${item.node.title}` : `Vai al passaggio ${index + 1}: ${copy.title}`}
            aria-pressed={selected} onClick={() => onSelect(item)}>
            <span className="flow-node-meta"><span className="flow-step-number">{!overview && (completed ? <CheckRounded /> : String(index + 1).padStart(2, '0'))}</span><span>{copy.phase}</span>{copy.version && <small>{copy.version}</small>}</span>
            <strong>{copy.title}</strong>
            <span className="flow-node-summary">{copy.summary}</span>
            {selected && <span className="flow-node-foot">{status ?? (overview ? 'Componente selezionato' : 'Passaggio corrente')}</span>}
          </button>;
        })}
      </div>
    </div>
    <p className="flow-caption">{overview ? 'Mappa dei componenti. I rami di verifica dipendono dalla famiglia dell’evidenza.' : 'Le frecce seguono l’ordine dei passaggi di questa demo. Seleziona un nodo per raggiungerlo.'}</p>
  </div>;
}
