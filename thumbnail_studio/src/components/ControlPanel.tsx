import React, { useState } from 'react';
import { ThumbnailConfig, HostOutlineColor, HostPosition } from '../types/thumbnail';
import { QUICK_TITLES } from '../constants/presets';
import {
  Type,
  User,
  Film,
  Sliders,
  Sparkles,
  Upload,
  RotateCcw,
  Eye,
  AlertTriangle,
  Flame,
  CheckCircle2,
  Copy,
  Download,
} from 'lucide-react';

interface ControlPanelProps {
  config: ThumbnailConfig;
  onChange: (updates: Partial<ThumbnailConfig>) => void;
  onReset: () => void;
  onExport: (format: 'png' | 'jpeg', res: '1080p' | '720p') => void;
  onOpenPreview: () => void;
  onOpenCtrReport: () => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  config,
  onChange,
  onReset,
  onExport,
  onOpenPreview,
  onOpenCtrReport,
}) => {
  const [activeTab, setActiveTab] = useState<'text' | 'host' | 'bg' | 'fx'>('text');
  const [copiedNotification, setCopiedNotification] = useState(false);

  // File upload handlers
  const handleHostUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        onChange({ hostCustomImage: event.target?.result as string });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleBgUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        onChange({ customBackgroundImage: event.target?.result as string });
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl flex flex-col h-full shadow-2xl overflow-hidden">
      {/* Top Tabs */}
      <div className="flex border-b border-zinc-800 bg-zinc-950/60 p-1.5 gap-1">
        <button
          onClick={() => setActiveTab('text')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${
            activeTab === 'text'
              ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
          }`}
        >
          <Type className="w-4 h-4" />
          <span>Texto & CTR</span>
        </button>

        <button
          onClick={() => setActiveTab('host')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${
            activeTab === 'host'
              ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
          }`}
        >
          <User className="w-4 h-4" />
          <span>Host Alerta</span>
        </button>

        <button
          onClick={() => setActiveTab('bg')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${
            activeTab === 'bg'
              ? 'bg-red-500/15 text-red-400 border border-red-500/30 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
          }`}
        >
          <Film className="w-4 h-4" />
          <span>Control Room</span>
        </button>

        <button
          onClick={() => setActiveTab('fx')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${
            activeTab === 'fx'
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>Grading</span>
        </button>
      </div>

      {/* Tab Content Area */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6 text-sm">
        {/* ========================================================= */}
        {/* TAB 1: TEXT & CTR VIRAL */}
        {/* ========================================================= */}
        {activeTab === 'text' && (
          <div className="space-y-5">
            {/* Quick Titles Presets */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">
                Títulos de Alto Impacto (1 Clic)
              </label>
              <div className="grid grid-cols-2 gap-2">
                {QUICK_TITLES.map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => onChange({ primaryText: item.text })}
                    className={`flex flex-col text-left p-2.5 rounded-xl border text-xs font-bold transition-all ${
                      config.primaryText === item.text
                        ? 'bg-amber-500/20 border-amber-500 text-amber-300 shadow-md shadow-amber-950/40'
                        : 'bg-zinc-950/60 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/50'
                    }`}
                  >
                    <span className="text-[10px] text-amber-500/80 uppercase font-mono font-normal">
                      {item.tag}
                    </span>
                    <span className="truncate">{item.text}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Primary Text Input */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Texto Principal (Impacto Viral)
                </label>
                <span className="text-[11px] text-amber-400 font-mono font-bold">
                  {config.primaryTextColor}
                </span>
              </div>
              <input
                type="text"
                value={config.primaryText}
                onChange={(e) => onChange({ primaryText: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-3.5 py-2.5 text-zinc-100 font-black text-lg focus:outline-none focus:border-amber-500 shadow-inner"
                placeholder="Ej. ¡FUE UN FRAUDE!"
              />
            </div>

            {/* Secondary Text Input */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Subtítulo / Remate
              </label>
              <input
                type="text"
                value={config.secondaryText}
                onChange={(e) => onChange({ secondaryText: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-3.5 py-2 text-zinc-200 text-sm focus:outline-none focus:border-amber-500"
                placeholder="Ej. DOCUMENTAL DE INVESTIGACIÓN"
              />
            </div>

            {/* Color Palette Selection */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">
                Color del Texto
              </label>
              <div className="flex items-center gap-2">
                {[
                  { name: 'Amarillo CTR (#FFE600)', color: '#FFE600' },
                  { name: 'Blanco Puro (#FFFFFF)', color: '#FFFFFF' },
                  { name: 'Rojo Alerta (#EF4444)', color: '#EF4444' },
                  { name: 'Cian Neón (#22D3EE)', color: '#22D3EE' },
                ].map((palette) => (
                  <button
                    key={palette.color}
                    onClick={() => onChange({ primaryTextColor: palette.color })}
                    className={`flex-1 py-2 rounded-xl text-xs font-bold border transition-all flex items-center justify-center gap-1.5 ${
                      config.primaryTextColor.toLowerCase() === palette.color.toLowerCase()
                        ? 'border-white ring-2 ring-amber-500/50 scale-105'
                        : 'border-zinc-800 hover:border-zinc-700'
                    }`}
                    style={{ backgroundColor: `${palette.color}22` }}
                  >
                    <span
                      className="w-3.5 h-3.5 rounded-full border border-black/40 shadow-sm"
                      style={{ backgroundColor: palette.color }}
                    />
                  </button>
                ))}
              </div>
            </div>

            {/* Typography & Style Sliders */}
            <div className="space-y-4 pt-2 border-t border-zinc-800">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Borde Negro (Contorno)</span>
                  <span className="font-mono text-zinc-300">{config.strokeWidth}px</span>
                </div>
                <input
                  type="range"
                  min="6"
                  max="22"
                  step="1"
                  value={config.strokeWidth}
                  onChange={(e) => onChange({ strokeWidth: Number(e.target.value) })}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Ángulo de Inclinación (Tensión)</span>
                  <span className="font-mono text-zinc-300">{config.textRotation}°</span>
                </div>
                <input
                  type="range"
                  min="-8"
                  max="8"
                  step="1"
                  value={config.textRotation}
                  onChange={(e) => onChange({ textRotation: Number(e.target.value) })}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Tamaño del Texto</span>
                  <span className="font-mono text-zinc-300">{(config.textSize * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.35"
                  step="0.05"
                  value={config.textSize}
                  onChange={(e) => onChange({ textSize: Number(e.target.value) })}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>
            </div>

            {/* Badges & Clickbait Elements */}
            <div className="space-y-3 pt-3 border-t border-zinc-800">
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
                Ganchos Visuales & Overlays
              </label>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  onClick={() => onChange({ showRecBadge: !config.showRecBadge })}
                  className={`p-2.5 rounded-xl border flex items-center justify-between ${
                    config.showRecBadge
                      ? 'bg-red-500/15 border-red-500/50 text-red-300'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400'
                  }`}
                >
                  <span>🔴 REC Timecode</span>
                  <span className="font-bold">{config.showRecBadge ? 'ON' : 'OFF'}</span>
                </button>

                <button
                  onClick={() => onChange({ showSecretStamp: !config.showSecretStamp })}
                  className={`p-2.5 rounded-xl border flex items-center justify-between ${
                    config.showSecretStamp
                      ? 'bg-amber-500/15 border-amber-500/50 text-amber-300'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400'
                  }`}
                >
                  <span>⚠️ Sello Confidencial</span>
                  <span className="font-bold">{config.showSecretStamp ? 'ON' : 'OFF'}</span>
                </button>

                <button
                  onClick={() => onChange({ showRedCircle: !config.showRedCircle })}
                  className={`p-2.5 rounded-xl border flex items-center justify-between ${
                    config.showRedCircle
                      ? 'bg-red-500/15 border-red-500/50 text-red-300'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400'
                  }`}
                >
                  <span>⭕ Círculo Filtrado</span>
                  <span className="font-bold">{config.showRedCircle ? 'ON' : 'OFF'}</span>
                </button>

                <button
                  onClick={() => onChange({ showClickbaitArrow: !config.showClickbaitArrow })}
                  className={`p-2.5 rounded-xl border flex items-center justify-between ${
                    config.showClickbaitArrow
                      ? 'bg-red-500/15 border-red-500/50 text-red-300'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400'
                  }`}
                >
                  <span>↗️ Flecha Clickbait</span>
                  <span className="font-bold">{config.showClickbaitArrow ? 'ON' : 'OFF'}</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 2: HOST ALERTA (01_host_alerta.png) */}
        {/* ========================================================= */}
        {activeTab === 'host' && (
          <div className="space-y-5">
            {/* Host Visibility Toggle */}
            <div className="flex items-center justify-between p-3 bg-zinc-950 rounded-xl border border-zinc-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400">
                  <User className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-zinc-200 uppercase">Capa del Host</h4>
                  <p className="text-[11px] text-zinc-400">01_host_alerta.png / Reacción</p>
                </div>
              </div>
              <button
                onClick={() => onChange({ hostVisible: !config.hostVisible })}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  config.hostVisible
                    ? 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/30'
                    : 'bg-zinc-800 text-zinc-400'
                }`}
              >
                {config.hostVisible ? 'Activo' : 'Oculto'}
              </button>
            </div>

            {/* Position: Bottom-Right vs Bottom-Left */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">
                Posición en la Miniatura
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => onChange({ hostPosition: 'bottom-right' })}
                  className={`p-3 rounded-xl border text-xs font-bold flex flex-col items-center gap-1 transition-all ${
                    config.hostPosition === 'bottom-right'
                      ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-950/40'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <span>Esquina Derecha</span>
                  <span className="text-[10px] text-cyan-400 font-normal">Recomendado</span>
                </button>

                <button
                  onClick={() => onChange({ hostPosition: 'bottom-left' })}
                  className={`p-3 rounded-xl border text-xs font-bold flex flex-col items-center gap-1 transition-all ${
                    config.hostPosition === 'bottom-left'
                      ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-950/40'
                      : 'bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <span>Esquina Izquierda</span>
                  <span className="text-[10px] text-zinc-500 font-normal">Alternativo</span>
                </button>
              </div>
            </div>

            {/* Contour / Outline Style (Prompt: "contorno blanco/cian sutil de 8px para que resalte") */}
            <div className="p-4 bg-zinc-950 rounded-xl border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                  Contorno de Resalte (Sticker 8px)
                </label>
                <span className="px-2 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-[10px] text-cyan-300 font-mono">
                  {config.hostOutlineWidth}px
                </span>
              </div>

              {/* Color options */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { id: 'cyan', label: 'Cian Neón', color: '#22d3ee' },
                  { id: 'white', label: 'Blanco', color: '#ffffff' },
                  { id: 'yellow', label: 'Amarillo', color: '#FFE600' },
                  { id: 'none', label: 'Sin Borde', color: 'transparent' },
                ].map((opt) => (
                  <button
                    key={opt.id}
                    onClick={() => onChange({ hostOutlineColor: opt.id as HostOutlineColor })}
                    className={`p-2 rounded-lg border text-[11px] font-bold flex flex-col items-center gap-1.5 transition-all ${
                      config.hostOutlineColor === opt.id
                        ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200'
                        : 'border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700'
                    }`}
                  >
                    <span
                      className="w-4 h-4 rounded-full border border-zinc-700"
                      style={{ backgroundColor: opt.color }}
                    />
                    <span>{opt.label}</span>
                  </button>
                ))}
              </div>

              {/* Outline width slider */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Grosor del Contorno</span>
                  <span className="font-mono text-cyan-400 font-bold">
                    {config.hostOutlineWidth === 8 ? '8px (Prompt Exacto)' : `${config.hostOutlineWidth}px`}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="20"
                  step="1"
                  value={config.hostOutlineWidth}
                  onChange={(e) => onChange({ hostOutlineWidth: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Glow intensity slider */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Intensidad del Brillo / Glow</span>
                  <span className="font-mono text-zinc-300">{config.hostGlowIntensity}px</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="35"
                  step="1"
                  value={config.hostGlowIntensity}
                  onChange={(e) => onChange({ hostGlowIntensity: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>
            </div>

            {/* Transform Controls */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-400 font-bold uppercase">Espejo Horizontal</span>
                <button
                  onClick={() => onChange({ hostFlipX: !config.hostFlipX })}
                  className={`px-3 py-1 rounded-lg text-xs font-bold border transition-all ${
                    config.hostFlipX
                      ? 'bg-zinc-800 border-cyan-500 text-cyan-400'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-400'
                  }`}
                >
                  {config.hostFlipX ? 'Invertido' : 'Normal'}
                </button>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Escala / Zoom del Host</span>
                  <span className="font-mono text-zinc-300">{(config.hostScale * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.3"
                  step="0.05"
                  value={config.hostScale}
                  onChange={(e) => onChange({ hostScale: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>
            </div>

            {/* Upload Custom Cutout Button */}
            <div className="pt-2">
              <label className="flex items-center justify-center gap-2 w-full p-3 bg-zinc-950 hover:bg-zinc-900 border border-dashed border-zinc-700 hover:border-cyan-500 rounded-xl cursor-pointer text-xs font-semibold text-zinc-300 transition-all">
                <Upload className="w-4 h-4 text-cyan-400" />
                <span>
                  {config.hostCustomImage ? 'Reemplazar Imagen del Host (.PNG)' : 'Subir 01_host_alerta.png Propio'}
                </span>
                <input
                  type="file"
                  accept="image/png,image/webp,image/jpeg"
                  className="hidden"
                  onChange={handleHostUpload}
                />
              </label>
              {config.hostCustomImage && (
                <button
                  onClick={() => onChange({ hostCustomImage: null })}
                  className="mt-1.5 text-[11px] text-red-400 hover:underline w-full text-center"
                >
                  Restaurar ilustración original
                </button>
              )}
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 3: CONTROL ROOM BACKGROUND (08_fondo_miniatura_ai.jpg) */}
        {/* ========================================================= */}
        {activeTab === 'bg' && (
          <div className="space-y-5">
            {/* Ambient Lighting Scheme */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">
                Atmósfera & Contraste Cinemático
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  {
                    id: 'red-cyan',
                    label: 'Rojo y Cian (Thriller)',
                    desc: 'Dual tone de investigación psicológica',
                  },
                  {
                    id: 'pure-red',
                    label: 'Alarma Roja Total',
                    desc: 'Emergencia y fraude inminente',
                  },
                  {
                    id: 'cyber-cyan',
                    label: 'Cian CCTV Tecnológico',
                    desc: 'Cámaras de vigilancia digital',
                  },
                  {
                    id: 'monochrome-cold',
                    label: 'Documental Frío',
                    desc: 'Estilo archivo judicial',
                  },
                ].map((mode) => (
                  <button
                    key={mode.id}
                    onClick={() => onChange({ ambientLighting: mode.id as any })}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      config.ambientLighting === mode.id
                        ? 'bg-red-500/15 border-red-500 text-red-300 shadow-md shadow-red-950/40'
                        : 'bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                    }`}
                  >
                    <div className="text-xs font-bold text-zinc-200">{mode.label}</div>
                    <div className="text-[10px] text-zinc-500 leading-tight mt-0.5">{mode.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Story Elements (Prompt specifications) */}
            <div className="space-y-2.5 p-4 bg-zinc-950 rounded-xl border border-zinc-800">
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-300">
                Elementos Narrativos del Prompt
              </label>

              {/* Producer silhouette */}
              <div className="flex items-center justify-between py-1">
                <div>
                  <div className="text-xs font-bold text-zinc-200">Silueta del Productor</div>
                  <div className="text-[11px] text-zinc-400">De espaldas frente a la consola de TV</div>
                </div>
                <button
                  onClick={() => onChange({ producerSilhouette: !config.producerSilhouette })}
                  className={`px-3 py-1 rounded-lg text-xs font-bold ${
                    config.producerSilhouette ? 'bg-red-600 text-white' : 'bg-zinc-800 text-zinc-400'
                  }`}
                >
                  {config.producerSilhouette ? 'Visible' : 'Oculto'}
                </button>
              </div>

              {/* Red warning buttons */}
              <div className="flex items-center justify-between py-1 border-t border-zinc-800/80">
                <div>
                  <div className="text-xs font-bold text-zinc-200">Botones Rojos de Advertencia</div>
                  <div className="text-[11px] text-zinc-400">Luces de ALERTA y OVERRIDE encendidas</div>
                </div>
                <button
                  onClick={() => onChange({ redAlertButtons: !config.redAlertButtons })}
                  className={`px-3 py-1 rounded-lg text-xs font-bold ${
                    config.redAlertButtons ? 'bg-red-600 text-white' : 'bg-zinc-800 text-zinc-400'
                  }`}
                >
                  {config.redAlertButtons ? 'Encendidos' : 'Apagados'}
                </button>
              </div>

              {/* Scanlines CRT */}
              <div className="flex items-center justify-between py-1 border-t border-zinc-800/80">
                <div>
                  <div className="text-xs font-bold text-zinc-200">Scanlines de Monitores CCTV</div>
                  <div className="text-[11px] text-zinc-400">Líneas de transmisión televisiva analógica</div>
                </div>
                <button
                  onClick={() => onChange({ scanlines: !config.scanlines })}
                  className={`px-3 py-1 rounded-lg text-xs font-bold ${
                    config.scanlines ? 'bg-cyan-600 text-white' : 'bg-zinc-800 text-zinc-400'
                  }`}
                >
                  {config.scanlines ? 'Activo' : 'Inactivo'}
                </button>
              </div>
            </div>

            {/* Atmospheric Sliders */}
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Niebla Volumétrica (Atmósfera)</span>
                  <span className="font-mono text-zinc-300">{config.volumetricHaze}%</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={config.volumetricHaze}
                  onChange={(e) => onChange({ volumetricHaze: Number(e.target.value) })}
                  className="w-full accent-red-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Viñeta Oscura (Foco Central)</span>
                  <span className="font-mono text-zinc-300">{config.vignetteStrength}%</span>
                </div>
                <input
                  type="range"
                  min="20"
                  max="100"
                  value={config.vignetteStrength}
                  onChange={(e) => onChange({ vignetteStrength: Number(e.target.value) })}
                  className="w-full accent-red-500 cursor-pointer"
                />
              </div>
            </div>

            {/* Custom Background Upload */}
            <div className="pt-2">
              <label className="flex items-center justify-center gap-2 w-full p-3 bg-zinc-950 hover:bg-zinc-900 border border-dashed border-zinc-700 hover:border-red-500 rounded-xl cursor-pointer text-xs font-semibold text-zinc-300 transition-all">
                <Upload className="w-4 h-4 text-red-400" />
                <span>
                  {config.customBackgroundImage
                    ? 'Reemplazar Fondo Subido'
                    : 'Subir 08_fondo_miniatura_ai.jpg Propio'}
                </span>
                <input
                  type="file"
                  accept="image/png,image/webp,image/jpeg"
                  className="hidden"
                  onChange={handleBgUpload}
                />
              </label>
              {config.customBackgroundImage && (
                <button
                  onClick={() => onChange({ customBackgroundImage: null })}
                  className="mt-1.5 text-[11px] text-red-400 hover:underline w-full text-center"
                >
                  Restaurar sala de control cinematográfica original
                </button>
              )}
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 4: GRADING & FINAL COLOR */}
        {/* ========================================================= */}
        {activeTab === 'fx' && (
          <div className="space-y-5">
            <div className="p-4 bg-zinc-950 rounded-xl border border-zinc-800 space-y-4">
              <label className="block text-xs font-bold uppercase tracking-wider text-zinc-300">
                Ajuste de Color Cine 8K
              </label>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Contraste Dramático</span>
                  <span className="font-mono text-emerald-400 font-bold">{config.contrast}%</span>
                </div>
                <input
                  type="range"
                  min="100"
                  max="160"
                  value={config.contrast}
                  onChange={(e) => onChange({ contrast: Number(e.target.value) })}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Saturación Neón</span>
                  <span className="font-mono text-emerald-400 font-bold">{config.saturation}%</span>
                </div>
                <input
                  type="range"
                  min="80"
                  max="150"
                  value={config.saturation}
                  onChange={(e) => onChange({ saturation: Number(e.target.value) })}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-zinc-400">Brillo Global</span>
                  <span className="font-mono text-emerald-400 font-bold">{config.brightness}%</span>
                </div>
                <input
                  type="range"
                  min="75"
                  max="120"
                  value={config.brightness}
                  onChange={(e) => onChange({ brightness: Number(e.target.value) })}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-zinc-950/60 rounded-xl border border-zinc-800">
              <span className="text-xs text-zinc-400">Valores de Color</span>
              <button
                onClick={() => onChange({ contrast: 135, saturation: 115, brightness: 95 })}
                className="text-xs text-amber-400 hover:underline font-semibold"
              >
                Restablecer a Valores del Prompt
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="p-4 bg-zinc-950 border-t border-zinc-800 flex flex-col gap-2.5">
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onOpenPreview}
            className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-750 text-zinc-200 text-xs font-bold transition-all border border-zinc-700 shadow-sm"
          >
            <Eye className="w-4 h-4 text-red-500" />
            <span>Simulador YouTube</span>
          </button>

          <button
            onClick={onOpenCtrReport}
            className="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-xs font-bold transition-all border border-amber-500/40 shadow-sm"
          >
            <Flame className="w-4 h-4 text-amber-400" />
            <span>Auditoría de CTR</span>
          </button>
        </div>

        {/* Export Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onExport('png', '720p')}
            className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-black text-xs md:text-sm uppercase tracking-wider transition-all shadow-lg shadow-amber-500/25 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            <span>Descargar 1280x720 (YouTube Ready)</span>
          </button>

          <button
            onClick={() => onExport('png', '1080p')}
            className="px-3 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-bold border border-zinc-700 transition-all"
            title="Descargar en Full HD 1080p"
          >
            1080p
          </button>

          <button
            onClick={onReset}
            className="p-3 rounded-xl bg-zinc-850 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 transition-all"
            title="Reiniciar a configuración del prompt"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
