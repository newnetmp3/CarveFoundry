import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box, Circle, Download, FilePlus2, FolderOpen, HardDriveDownload,
  Layers, Leaf, MousePointer2, Play, Rotate3D, ShieldAlert, SlidersHorizontal,
} from 'lucide-react';
import { Viewport } from './Viewport';
import {
  defaultProject, parseProject,
  type DesignShape, type PocketPreview, type PocketSettings,
  type SavedProject, type Stock,
} from './types';

function NumberSetting({ label, value, unit = 'mm', min = 0, max = 2000, step = 1, onChange }: {
  label: string; value: number; unit?: string; min?: number; max?: number;
  step?: number; onChange: (value: number) => void;
}) {
  return <label className="field"><span>{label}</span><span className="number-input">
    <input type="number" value={value} min={min} max={max} step={step}
      onChange={(event) => {
        const number = event.target.valueAsNumber;
        if (Number.isFinite(number) && number >= min && number <= max) onChange(number);
      }} />
    <small>{unit}</small>
  </span></label>;
}

export function App() {
  const [project, setProject] = useState<SavedProject>(defaultProject);
  const [selectedId, setSelectedId] = useState<string | null>('shape-1');
  const [preview, setPreview] = useState<PocketPreview | null>(null);
  const [activeTab, setActiveTab] = useState<'design' | 'cam'>('cam');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('Your design stays on this device. Cloud saving is not enabled.');
  const filePicker = useRef<HTMLInputElement>(null);
  const worker = useRef<Worker | null>(null);
  const selected = project.shapes.find((item) => item.id === selectedId) ?? null;
  const selectShape = useCallback((id: string | null) => setSelectedId(id), []);

  useEffect(() => {
    const instance = new Worker(new URL('./cam.worker.ts', import.meta.url), { type: 'module' });
    worker.current = instance;
    instance.onmessage = (event: MessageEvent<{
      ok: boolean; preview?: PocketPreview; error?: string;
    }>) => {
      setLoading(false);
      if (event.data.ok && event.data.preview) {
        setPreview(event.data.preview);
        setError('');
        setNotice('Local WebAssembly toolpath demonstration finished. G-code export remains disabled.');
      } else {
        setPreview(null);
        setError(event.data.error || 'Unable to calculate toolpath preview');
      }
    };
    instance.onerror = () => {
      setLoading(false);
      setPreview(null);
      setError('Browser CAM worker failed to load. Check WebAssembly support and build assets.');
    };
    return () => { instance.terminate(); worker.current = null; };
  }, []);

  const updateStock = (field: keyof Stock, value: number) => {
    setProject((prev) => ({ ...prev, stock: { ...prev.stock, [field]: value } }));
    setPreview(null);
  };
  const updatePocket = (field: keyof PocketSettings, value: number) => {
    setProject((prev) => ({ ...prev, pocket: { ...prev.pocket, [field]: value } }));
    setPreview(null);
  };
  const updateShape = (field: keyof DesignShape, value: number | string) => {
    if (!selectedId) return;
    setProject((prev) => ({
      ...prev,
      shapes: prev.shapes.map((shape) =>
        shape.id === selectedId ? { ...shape, [field]: value } : shape
      ),
    }));
  };
  const addShape = (kind: DesignShape['kind']) => {
    const id = crypto.randomUUID();
    const shape: DesignShape = {
      id, kind, name: kind === 'ellipse' ? 'Circle' : 'Rectangle',
      xMm: Math.round(project.stock.widthMm * 0.35),
      yMm: Math.round(project.stock.heightMm * 0.35),
      widthMm: 40, heightMm: 30,
    };
    setProject((prev) => ({ ...prev, shapes: [...prev.shapes, shape] }));
    setSelectedId(id);
    setActiveTab('design');
  };
  const runPreview = () => {
    if (!worker.current) {
      setError('WebAssembly worker is unavailable');
      return;
    }
    setError('');
    setPreview(null);
    setLoading(true);
    worker.current.postMessage({ stock: project.stock, pocket: project.pocket });
  };
  const saveProject = () => {
    const content = JSON.stringify(project, null, 2);
    const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${project.title.trim().replace(/[^a-z0-9_-]+/gi, '-') || 'carvefoundry'}.cfweb.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice('Project downloaded locally. Cloud accounts and sync will be added later.');
  };
  const openProject = async (file?: File) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setError('Project file exceeds the 2 MB limit');
      return;
    }
    try {
      const next = parseProject(await file.text());
      setProject(next);
      setPreview(null);
      setSelectedId(null);
      setError('');
      setNotice('Local project opened successfully.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not open project');
    }
  };

  return <div className="app-shell">
    <header className="top-bar">
      <div className="brand">
        <span className="brand-mark"><Leaf size={21} strokeWidth={2.5} /></span>
        <span className="brand-name">Carve<span>Foundry</span><small>WEB</small></span>
        <span className="preview-pill">EARLY PREVIEW</span>
      </div>
      <nav className="menu">
        <button onClick={() => {
          if (window.confirm('Create a new local project? Unsaved changes will be discarded.')) {
            setProject(defaultProject()); setSelectedId('shape-1'); setPreview(null);
          }
        }}><FilePlus2 size={15} /> New</button>
        <button onClick={() => filePicker.current?.click()}><FolderOpen size={15} /> Open</button>
        <button onClick={saveProject}><HardDriveDownload size={15} /> Save local</button>
        <input ref={filePicker} type="file" accept=".json,.cfweb.json,application/json"
          hidden onChange={(event) => {
            void openProject(event.target.files?.[0]);
            event.target.value = '';
          }} />
      </nav>
      <div className="top-right"><span className="local-flag"><span className="signal-dot" />Local browser processing</span></div>
    </header>
    <div className="workspace">
      <aside className="tool-rail" aria-label="Design tools">
        <button className="rail-button active" title="Select objects"><MousePointer2 size={19} /></button>
        <button className="rail-button" title="Add rectangle" onClick={() => addShape('rectangle')}><Box size={19} /></button>
        <button className="rail-button" title="Add ellipse" onClick={() => addShape('ellipse')}><Circle size={19} /></button>
        <div className="rail-spacer" />
        <button className="rail-button" title="Orbit: drag; Pan: right drag; Zoom: scroll"><Rotate3D size={19} /></button>
      </aside>

      <section className="center-stage">
        <div className="stage-toolbar">
          <div className="breadcrumb"><span>WORKSPACE</span><span className="breadcrumb-separator">/</span>
            <input aria-label="Project name" value={project.title} maxLength={120}
              onChange={(event) => setProject((prev) => ({ ...prev, title: event.target.value }))} />
          </div>
          <div className="stage-meta"><span>XY origin: bottom left</span><span>Z0: stock top</span></div>
        </div>
        <div className="canvas-wrap">
          <Viewport stock={project.stock} shapes={project.shapes} selectedId={selectedId}
            pocket={project.pocket} preview={preview} onSelect={selectShape} />
          <div className="canvas-hint">Left drag to orbit · Right drag to pan · Scroll to zoom · Click to select</div>
          <div className="axis-legend"><span className="axis-x">X</span><span className="axis-y">Y</span><span className="axis-z">Z</span></div>
        </div>
        <footer className="stage-footer">
          <span><span className="status-dot" /> Browser workspace ready</span>
          <span>{project.stock.widthMm} × {project.stock.heightMm} × {project.stock.thicknessMm} mm</span>
        </footer>
      </section>

      <aside className="right-panel">
        <div className="panel-tabs">
          <button className={activeTab === 'design' ? 'selected' : ''}
            onClick={() => setActiveTab('design')}><Layers size={16} /> Design</button>
          <button className={activeTab === 'cam' ? 'selected' : ''}
            onClick={() => setActiveTab('cam')}><SlidersHorizontal size={16} /> CAM preview</button>
        </div>
        <div className="panel-body">
          {activeTab === 'design' ? <>
            <h3>Stock setup</h3>
            <p className="subtle">All measurements use millimeters.</p>
            <NumberSetting label="Width" value={project.stock.widthMm} min={10} onChange={(v) => updateStock('widthMm', v)} />
            <NumberSetting label="Height" value={project.stock.heightMm} min={10} onChange={(v) => updateStock('heightMm', v)} />
            <NumberSetting label="Thickness" value={project.stock.thicknessMm} min={1} onChange={(v) => updateStock('thicknessMm', v)} />
            <div className="panel-section-header"><h3>Objects</h3><span>{project.shapes.length}</span></div>
            <div className="objects">
              {project.shapes.map((item) =>
                <button key={item.id} className={item.id === selectedId ? 'object selected' : 'object'}
                  onClick={() => setSelectedId(item.id)}>
                  {item.kind === 'ellipse' ? <Circle size={15} /> : <Box size={15} />}
                  {item.name}
                </button>
              )}
            </div>
            {selected && <>
              <div className="panel-section-header"><h3>Selected shape</h3></div>
              <label className="field"><span>Name</span><input className="text-input" value={selected.name}
                maxLength={120} onChange={(e) => updateShape('name', e.target.value)} /></label>
              <NumberSetting label="X" value={selected.xMm} onChange={(v) => updateShape('xMm', v)} />
              <NumberSetting label="Y" value={selected.yMm} onChange={(v) => updateShape('yMm', v)} />
              <NumberSetting label="Width" value={selected.widthMm} min={0.1} onChange={(v) => updateShape('widthMm', v)} />
              <NumberSetting label="Height" value={selected.heightMm} min={0.1} onChange={(v) => updateShape('heightMm', v)} />
              <button className="secondary full" onClick={() => {
                setProject((prev) => ({ ...prev, shapes: prev.shapes.filter((item) => item.id !== selectedId) }));
                setSelectedId(null);
              }}>Remove selected object</button>
            </>}
            <div className="info-note">These are editable design objects. The CAM tab currently demonstrates an independent rectangular pocket; design-to-CAM integration comes next.</div>
          </> : <>
            <h3>Local CNC calculation</h3>
            <p className="subtle">This Rust/WebAssembly demonstration runs on your own computer.</p>
            <div className="warning-note"><ShieldAlert size={17} />
              <span><strong>Not machine-ready.</strong> Preview only. Fixture, holder, tool entry, and G-code verification are not implemented.</span>
            </div>
            <h4>Demonstration pocket</h4>
            <div className="two-col">
              <NumberSetting label="X" value={project.pocket.xMm} onChange={(v) => updatePocket('xMm', v)} />
              <NumberSetting label="Y" value={project.pocket.yMm} onChange={(v) => updatePocket('yMm', v)} />
              <NumberSetting label="Width" value={project.pocket.widthMm} min={1} onChange={(v) => updatePocket('widthMm', v)} />
              <NumberSetting label="Height" value={project.pocket.heightMm} min={1} onChange={(v) => updatePocket('heightMm', v)} />
            </div>
            <h4>Flat end mill</h4>
            <NumberSetting label="Diameter" value={project.pocket.cutterDiameterMm} min={0.1} step={0.5}
              onChange={(v) => updatePocket('cutterDiameterMm', v)} />
            <NumberSetting label="Cut depth" value={project.pocket.targetDepthMm} min={0.1} step={0.5}
              onChange={(v) => updatePocket('targetDepthMm', v)} />
            <NumberSetting label="Stepover" value={project.pocket.stepoverMm} min={0.1} step={0.5}
              onChange={(v) => updatePocket('stepoverMm', v)} />
            <NumberSetting label="Stepdown" value={project.pocket.stepdownMm} min={0.1} step={0.5}
              onChange={(v) => updatePocket('stepdownMm', v)} />
            <NumberSetting label="Safe Z" value={project.pocket.safeZMm} min={0.1} step={0.5}
              onChange={(v) => updatePocket('safeZMm', v)} />
            <button className="primary full" onClick={runPreview} disabled={loading}>
              <Play size={16} /> {loading ? 'Calculating…' : 'Calculate local preview'}
            </button>
            {preview && <div className="result">
              <strong>Preview calculated</strong>
              <span>{preview.passes} depth passes · {preview.rowsPerPass} raster rows per pass</span>
              <span>{preview.moves.length.toLocaleString()} planned motion points</span>
            </div>}
            {error && <div className="error" role="alert">{error}</div>}
            <button className="disabled-export full" disabled title="Blocked until real G-code verification exists">
              <Download size={16} /> G-code export — locked
            </button>
          </>}
        </div>
      </aside>
    </div>
    <div className="bottom-banner"><ShieldAlert size={16} />
      <span><strong>Development preview:</strong> local data only. CNC motion is visualization-only; no G-code or machine control.</span>
      <span className="banner-note">{notice}</span>
    </div>
  </div>;
}
