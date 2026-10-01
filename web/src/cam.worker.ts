import init, { preview_pocket } from './wasm/pkg/carvefoundry_web_engine.js';
import wasmUrl from './wasm/pkg/carvefoundry_web_engine_bg.wasm?url';
import type { PocketPreview, PocketSettings, Stock } from './types';

interface PreviewRequest {
  stock: Stock;
  pocket: PocketSettings;
}

let initialized: Promise<unknown> | null = null;

self.onmessage = async (event: MessageEvent<PreviewRequest>) => {
  try {
    if (!initialized) initialized = init(wasmUrl);
    await initialized;
    const { stock, pocket } = event.data;
    const payload = {
      stockWidthMm: stock.widthMm,
      stockHeightMm: stock.heightMm,
      stockThicknessMm: stock.thicknessMm,
      ...pocket,
    };
    const result = preview_pocket(payload) as PocketPreview;
    self.postMessage({ ok: true, preview: result });
  } catch (error) {
    self.postMessage({ ok: false, error: String(error) });
  }
};
