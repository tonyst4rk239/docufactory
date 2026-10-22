import React, { useState, useRef } from 'react';
import { DEFAULT_CONFIG } from './constants/presets';
import { ThumbnailConfig } from './types/thumbnail';
import { ThumbnailCanvas, ThumbnailCanvasHandle } from './components/ThumbnailCanvas';
import { ControlPanel } from './components/ControlPanel';
import { YouTubePreviewModal } from './components/YouTubePreviewModal';
import { CtrAnalyzerModal } from './components/CtrAnalyzerModal';
import {
  Sparkles,
  Download,
  Copy,
  Eye,
  Flame,
  Maximize2,
  Grid,
  Check,
  Video,
  Layers,
  HelpCircle,
  Clapperboard,
  Tv,
} from 'lucide-react';

export default function App() {
  const [config, setConfig] = useState<ThumbnailConfig>(DEFAULT_CONFIG);
  const [showSafeZones, setShowSafeZones] = useState(false);
  const [showYouTubeModal, setShowYouTubeModal] = useState(false);
  const [showCtrModal, setShowCtrModal] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const canvasRef = useRef<ThumbnailCanvasHandle>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const handleConfigChange = (updates: Partial<ThumbnailConfig>) => {
    setConfig((prev) => ({ ...prev, ...updates }));
  };

  const handleResetToPrompt = () => {
    setConfig(DEFAULT_CONFIG);
    showToast('Restaurado a los parámetros exactos del prompt original');
  };

  const handleExport = async (format: 'png' | 'jpeg', res: '1080p' | '720p') => {
    if (canvasRef.current) {
      showToast(`Generando y descargando miniatura ${res.toUpperCase()} (.${format})...`);
      try {
        await canvasRef.current.exportImage(format, res);
        showToast(`¡Miniatura descargada con éxito en ${res.toUpperCase()}!`);
      } catch (err) {
        showToast('Error al exportar. Intente nuevamente.');
      }
    }
  };

  const handleCopyClipboard = async () => {
    if (canvasRef.current) {
      const ok = await canvasRef.current.copyToClipboard();
      if (ok) {
        showToast('¡Miniatura copiada al portapapeles!');
      } else {
        showToast('Descarga la imagen para usarla en tu creador de YouTube');
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#090b10] text-zinc-100 flex flex-col font-sans selection:bg-amber-500 selection:text-black">
      {/* =========================================================================
          TOP NAVIGATION BAR
          ========================================================================= */}
      <header className="h-16 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-40 px-4 md:px-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-red-600 via-amber-500 to-cyan-400 p-[1.5px] shadow-lg shadow-red-950/40">
            <div className="w-full h-full bg-zinc-950 rounded-[10px] flex items-center justify-center">
              <Clapperboard className="w-5 h-5 text-amber-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm md:text-base font-black tracking-tight text-white flex items-center gap-1.5">
                CINE<span className="text-amber-400">THUMB</span> STUDIO
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-red-500/15 text-red-400 border border-red-500/30 uppercase">
                Doc Thriller 16:9
              </span>
            </div>
            <p className="text-[11px] text-zinc-400 hidden sm:block">
              Sala de Control CCTV • Host Alerta con Contorno 8px • "¡FUE UN FRAUDE!" #FFE600
            </p>
          </div>
        </div>

        {/* Quick Actions Header */}
        <div className="flex items-center gap-2 md:gap-3">
          {/* Quick Title Toggle */}
          <div className="hidden lg:flex items-center bg-zinc-900 border border-zinc-800 rounded-xl p-1 text-xs">
            <button
              onClick={() => handleConfigChange({ primaryText: '¡FUE UN FRAUDE!' })}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                config.primaryText === '¡FUE UN FRAUDE!'
                  ? 'bg-amber-500 text-black shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              ¡FUE UN FRAUDE!
            </button>
            <button
              onClick={() => handleConfigChange({ primaryText: 'NOS ENGAÑARON' })}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                config.primaryText === 'NOS ENGAÑARON'
                  ? 'bg-amber-500 text-black shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              NOS ENGAÑARON
            </button>
          </div>

          {/* YouTube Preview Trigger */}
          <button
            onClick={() => setShowYouTubeModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-800 text-xs font-bold transition-all"
            title="Ver miniatura en YouTube real"
          >
            <Eye className="w-4 h-4 text-red-500" />
            <span className="hidden md:inline">Simular YouTube</span>
          </button>

          {/* CTR Score Trigger */}
          <button
            onClick={() => setShowCtrModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/40 text-xs font-bold transition-all shadow-sm"
          >
            <Flame className="w-4 h-4 text-amber-400 animate-pulse" />
            <span>9.8 CTR</span>
          </button>

          {/* Main Download Button */}
          <button
            onClick={() => handleExport('png', '720p')}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-black text-xs md:text-sm uppercase tracking-wider transition-all shadow-lg shadow-amber-500/25 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Exportar 720p</span>
            <span className="sm:hidden">Descargar</span>
          </button>
        </div>
      </header>

      {/* =========================================================================
          MAIN WORKSPACE (CANVAS + CONTROLS)
          ========================================================================= */}
      <main className="flex-1 max-w-[1720px] w-full mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: THE THUMBNAIL CANVAS STAGE (7 or 8 Cols) */}
        <section className="lg:col-span-7 xl:col-span-8 flex flex-col space-y-4">
          {/* Canvas Toolbar */}
          <div className="flex items-center justify-between bg-zinc-900/70 border border-zinc-800/80 px-4 py-2.5 rounded-xl text-xs text-zinc-400">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5 font-mono font-bold text-zinc-300">
                <Tv className="w-4 h-4 text-cyan-400" />
                16:9 • 1280x720 / 1920x1080 UHD
              </span>
              <span className="h-3 w-px bg-zinc-800 hidden sm:block" />
              <div className="hidden sm:flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-zinc-300 font-medium">Contraste #FFE600 Óptimo</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Safe Zone Overlay Toggle */}
              <button
                onClick={() => setShowSafeZones(!showSafeZones)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg border transition-all ${
                  showSafeZones
                    ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300'
                    : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200'
                }`}
                title="Mostrar zonas de recorte y badge de duración de YouTube"
              >
                <Grid className="w-3.5 h-3.5" />
                <span className="text-[11px] font-semibold">Zonas Seguras</span>
              </button>

              <button
                onClick={handleCopyClipboard}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 text-[11px] font-semibold transition-all"
                title="Copiar imagen al portapapeles"
              >
                <Copy className="w-3.5 h-3.5 text-zinc-400" />
                <span className="hidden sm:inline">Copiar</span>
              </button>
            </div>
          </div>

          {/* THE 16:9 INTERACTIVE CANVAS */}
          <div className="relative group">
            <ThumbnailCanvas ref={canvasRef} config={config} />

            {/* Optional Safe Zone & YouTube UI Overlay */}
            {showSafeZones && (
              <div className="absolute inset-0 pointer-events-none rounded-xl border border-dashed border-cyan-500/40 z-30">
                {/* Safe Grid Lines */}
                <div className="w-full h-full grid grid-cols-3 grid-rows-3">
                  {[...Array(9)].map((_, i) => (
                    <div key={i} className="border border-cyan-500/15" />
                  ))}
                </div>

                {/* Simulated YouTube Duration Badge Safe Zone (Bottom Right) */}
                <div className="absolute bottom-4 right-4 bg-red-600/30 border border-red-500 text-red-200 font-mono text-[10px] px-2.5 py-1 rounded flex items-center gap-1.5 shadow-lg backdrop-blur-sm">
                  <span>⚠️ Zona Badge Tiempo (38:42)</span>
                </div>

                {/* Title Safety Indicator */}
                <div className="absolute top-4 left-4 bg-cyan-600/30 border border-cyan-400 text-cyan-200 font-mono text-[10px] px-2 py-0.5 rounded">
                  ✓ Zona de Mayor Atención Visual (Focal Point)
                </div>
              </div>
            )}
          </div>

          {/* Prompt Specification Tags & CTR Insight Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800/80 flex items-start gap-3">
              <div className="p-2 rounded-lg bg-amber-500/15 text-amber-400 shrink-0">
                <span className="font-mono font-bold text-xs">#1</span>
              </div>
              <div>
                <h4 className="text-xs font-bold text-zinc-200">Texto #FFE600 & Borde</h4>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Tipografía gruesa tipo Arial Black / Bebas Neue con sombra profunda para lectura instantánea.
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800/80 flex items-start gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/15 text-cyan-400 shrink-0">
                <span className="font-mono font-bold text-xs">#2</span>
              </div>
              <div>
                <h4 className="text-xs font-bold text-zinc-200">Host con Contorno 8px</h4>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  01_host_alerta.png en esquina inferior con reborde blanco/cian para recorte perfecto.
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-950/70 border border-zinc-800/80 flex items-start gap-3">
              <div className="p-2 rounded-lg bg-red-500/15 text-red-400 shrink-0">
                <span className="font-mono font-bold text-xs">#3</span>
              </div>
              <div>
                <h4 className="text-xs font-bold text-zinc-200">Sala de Control Siniestra</h4>
                <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed">
                  Monitores CCTV con concursantes llorando, silueta de productor y botones rojos de alerta.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* RIGHT COLUMN: EDITOR CONTROL PANEL (5 or 4 Cols) */}
        <section className="lg:col-span-5 xl:col-span-4 h-full min-h-[640px]">
          <ControlPanel
            config={config}
            onChange={handleConfigChange}
            onReset={handleResetToPrompt}
            onExport={handleExport}
            onOpenPreview={() => setShowYouTubeModal(true)}
            onOpenCtrReport={() => setShowCtrModal(true)}
          />
        </section>
      </main>

      {/* =========================================================================
          TOAST NOTIFICATION
          ========================================================================= */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 bg-zinc-900 border border-amber-500/40 text-amber-300 text-xs font-bold rounded-xl shadow-2xl backdrop-blur-md animate-bounce">
          <Check className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* =========================================================================
          MODALS: YOUTUBE PREVIEW & CTR AUDIT
          ========================================================================= */}
      <YouTubePreviewModal
        isOpen={showYouTubeModal}
        onClose={() => setShowYouTubeModal(false)}
        config={config}
        thumbnailRenderNode={<ThumbnailCanvas config={config} />}
      />

      <CtrAnalyzerModal
        isOpen={showCtrModal}
        onClose={() => setShowCtrModal(false)}
        config={config}
      />
    </div>
  );
}
