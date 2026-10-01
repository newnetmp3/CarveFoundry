export interface Stock {
  widthMm: number;
  heightMm: number;
  thicknessMm: number;
}

export interface DesignShape {
  id: string;
  kind: 'rectangle' | 'ellipse';
  name: string;
  xMm: number;
  yMm: number;
  widthMm: number;
  heightMm: number;
}

export interface PocketSettings {
  xMm: number;
  yMm: number;
  widthMm: number;
  heightMm: number;
  cutterDiameterMm: number;
  targetDepthMm: number;
  stepoverMm: number;
  stepdownMm: number;
  safeZMm: number;
}

export type MotionKind = 'rapid' | 'plunge' | 'cut' | 'retract';

export interface Motion {
  xMm: number;
  yMm: number;
  zMm: number;
  kind: MotionKind;
}

export interface PocketPreview {
  moves: Motion[];
  passes: number;
  rowsPerPass: number;
  warning: string;
}

export interface SavedProject {
  version: 1;
  title: string;
  stock: Stock;
  shapes: DesignShape[];
  pocket: PocketSettings;
}

export function defaultProject(): SavedProject {
  return {
    version: 1,
    title: 'My first carving',
    stock: { widthMm: 200, heightMm: 120, thicknessMm: 18 },
    shapes: [
      { id: 'shape-1', kind: 'rectangle', name: 'Nameplate', xMm: 42, yMm: 34, widthMm: 116, heightMm: 52 },
    ],
    pocket: {
      xMm: 40, yMm: 30, widthMm: 120, heightMm: 60,
      cutterDiameterMm: 6, targetDepthMm: 3,
      stepoverMm: 3, stepdownMm: 1.5, safeZMm: 5,
    },
  };
}

function finiteRange(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum;
}

export function parseProject(text: string): SavedProject {
  const raw: unknown = JSON.parse(text);
  if (!raw || typeof raw !== 'object') throw Error('Invalid project file');
  const p = raw as Partial<SavedProject>;
  if (p.version !== 1 || typeof p.title !== 'string' || p.title.length > 120
      || !p.stock || !p.pocket || !Array.isArray(p.shapes) || p.shapes.length > 100) {
    throw Error('Not a CarveFoundry Web v1 project');
  }
  const s = p.stock;
  if (!finiteRange(s.widthMm, 10, 2000) || !finiteRange(s.heightMm, 10, 2000)
      || !finiteRange(s.thicknessMm, 1, 300)) throw Error('Invalid stock dimensions');
  for (const shape of p.shapes) {
    if (typeof shape?.id !== 'string' || typeof shape.name !== 'string'
        || shape.name.length > 120 || !['rectangle', 'ellipse'].includes(shape.kind)
        || !finiteRange(shape.xMm, 0, 2000) || !finiteRange(shape.yMm, 0, 2000)
        || !finiteRange(shape.widthMm, 0.01, 2000) || !finiteRange(shape.heightMm, 0.01, 2000)) {
      throw Error('Invalid design geometry');
    }
  }
  for (const [key, value] of Object.entries(p.pocket)) {
    if (!finiteRange(value, 0, 10000)) throw Error(`Invalid pocket setting: ${key}`);
  }
  const required: (keyof PocketSettings)[] = [
    'xMm', 'yMm', 'widthMm', 'heightMm', 'cutterDiameterMm',
    'targetDepthMm', 'stepoverMm', 'stepdownMm', 'safeZMm',
  ];
  if (required.some((key) => !finiteRange(p.pocket![key], 0, 10000))) {
    throw Error('Missing pocket settings');
  }
  return p as SavedProject;
}
