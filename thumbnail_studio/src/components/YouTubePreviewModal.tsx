import React, { useState } from 'react';
import { ThumbnailConfig } from '../types/thumbnail';
import { YOUTUBE_MOCKUP_METADATA } from '../constants/presets';
import { X, Smartphone, Monitor, Search, ThumbsUp, MessageSquare, Share2 } from 'lucide-react';

interface YouTubePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: ThumbnailConfig;
  thumbnailRenderNode: React.ReactNode;
}

export const YouTubePreviewModal: React.FC<YouTubePreviewModalProps> = ({
  isOpen,
  onClose,
  config,
  thumbnailRenderNode,
}) => {
  const [device, setDevice] = useState<'desktop' | 'mobile' | 'search'>('desktop');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <div className="relative w-full max-w-5xl bg-[#0f0f0f] border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-[#181818]">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-3 py-1 bg-red-600/20 text-red-500 rounded-lg text-xs font-bold border border-red-500/30">
              <span className="w-2 h-2 rounded-full bg-red-600 animate-ping"></span>
              Simulador de YouTube
            </div>
            <h3 className="text-sm md:text-base font-bold text-zinc-200">
              Prueba de Visibilidad en el Feed Real
            </h3>
          </div>

          <div className="flex items-center gap-3">
            {/* View Switchers */}
            <div className="flex bg-zinc-900 rounded-lg p-1 border border-zinc-800 text-xs">
              <button
                onClick={() => setDevice('desktop')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                  device === 'desktop' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <Monitor className="w-3.5 h-3.5" />
                <span>PC Feed</span>
              </button>
              <button
                onClick={() => setDevice('mobile')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                  device === 'mobile' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>Móvil (360px)</span>
              </button>
              <button
                onClick={() => setDevice('search')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                  device === 'search' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <Search className="w-3.5 h-3.5" />
                <span>Búsqueda</span>
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 bg-[#0f0f0f] flex justify-center items-start">
          {/* 1. DESKTOP HOME FEED SIMULATION */}
          {device === 'desktop' && (
            <div className="w-full max-w-4xl space-y-6">
              <div className="flex items-center justify-between text-xs text-zinc-500 pb-2 border-b border-zinc-800">
                <span>Tu video compitiendo con otros canales en la página de inicio de YouTube:</span>
                <span className="text-emerald-400 font-mono font-bold">CTR Test: Alto Impacto</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {/* YOUR THUMBNAIL (HERO CARD) */}
                <div className="group cursor-pointer">
                  <div className="relative rounded-xl overflow-hidden aspect-video ring-2 ring-amber-500/80 shadow-2xl shadow-amber-500/10">
                    {thumbnailRenderNode}
                    {/* YouTube Duration Pill in Bottom Right */}
                    <span className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/90 text-white font-mono text-[11px] font-bold rounded">
                      {YOUTUBE_MOCKUP_METADATA.duration}
                    </span>
                  </div>

                  <div className="flex gap-3 mt-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-red-600 to-amber-600 flex items-center justify-center font-black text-xs text-white shrink-0 shadow">
                      EO
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-bold text-zinc-100 line-clamp-2 leading-snug group-hover:text-amber-400 transition-colors">
                        {YOUTUBE_MOCKUP_METADATA.videoTitle}
                      </h4>
                      <p className="text-xs text-zinc-400 mt-1 flex items-center gap-1">
                        {YOUTUBE_MOCKUP_METADATA.channelName}
                        <span className="text-[10px] text-zinc-500">✓</span>
                      </p>
                      <p className="text-xs text-zinc-500">
                        {YOUTUBE_MOCKUP_METADATA.views} • {YOUTUBE_MOCKUP_METADATA.uploadedTime}
                      </p>
                    </div>
                  </div>
                </div>

                {/* DUMMY COMPETITOR 1 */}
                <div className="opacity-45 hover:opacity-85 transition-opacity">
                  <div className="relative rounded-xl overflow-hidden aspect-video bg-zinc-800 flex items-center justify-center text-zinc-600 border border-zinc-700/40">
                    <span className="text-xs font-mono">Video de la competencia #1</span>
                    <span className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 text-white font-mono text-[11px] rounded">
                      14:20
                    </span>
                  </div>
                  <div className="flex gap-3 mt-3">
                    <div className="w-9 h-9 rounded-full bg-zinc-700 shrink-0" />
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 line-clamp-2">
                        Resumen del reality show sin edición especial
                      </h4>
                      <p className="text-xs text-zinc-500 mt-1">Canal Estándar • 45 K vistas</p>
                    </div>
                  </div>
                </div>

                {/* DUMMY COMPETITOR 2 */}
                <div className="opacity-45 hover:opacity-85 transition-opacity">
                  <div className="relative rounded-xl overflow-hidden aspect-video bg-zinc-800 flex items-center justify-center text-zinc-600 border border-zinc-700/40">
                    <span className="text-xs font-mono">Video de la competencia #2</span>
                    <span className="absolute bottom-2 right-2 px-1.5 py-0.5 bg-black/80 text-white font-mono text-[11px] rounded">
                      22:05
                    </span>
                  </div>
                  <div className="flex gap-3 mt-3">
                    <div className="w-9 h-9 rounded-full bg-zinc-700 shrink-0" />
                    <div>
                      <h4 className="text-sm font-medium text-zinc-400 line-clamp-2">
                        ¿Qué pasó en la final del programa?
                      </h4>
                      <p className="text-xs text-zinc-500 mt-1">TV Noticia • 120 K vistas</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 2. MOBILE FEED SIMULATION (CRITICAL FOR CTR: ~70% of YouTube traffic is mobile) */}
          {device === 'mobile' && (
            <div className="w-full max-w-sm bg-black border-4 border-zinc-800 rounded-3xl p-3 shadow-2xl">
              <div className="w-24 h-4 bg-zinc-800 rounded-full mx-auto mb-3" />
              <div className="space-y-3">
                <div className="relative rounded-lg overflow-hidden aspect-video shadow-md">
                  {thumbnailRenderNode}
                  <span className="absolute bottom-1.5 right-1.5 px-1 py-0.5 bg-black/90 text-white font-mono text-[9px] font-bold rounded">
                    {YOUTUBE_MOCKUP_METADATA.duration}
                  </span>
                </div>
                <div className="flex gap-2.5 px-1">
                  <div className="w-8 h-8 rounded-full bg-red-600 flex items-center justify-center text-[10px] font-bold text-white shrink-0">
                    EO
                  </div>
                  <div className="flex-1">
                    <h5 className="text-xs font-bold text-zinc-100 line-clamp-2">
                      {YOUTUBE_MOCKUP_METADATA.videoTitle}
                    </h5>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      {YOUTUBE_MOCKUP_METADATA.channelName} • {YOUTUBE_MOCKUP_METADATA.views}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 3. SEARCH RESULTS SIMULATION */}
          {device === 'search' && (
            <div className="w-full max-w-3xl space-y-4">
              <div className="flex items-center gap-2 p-3 bg-zinc-900 rounded-xl border border-zinc-800">
                <Search className="w-4 h-4 text-zinc-400" />
                <span className="text-sm text-zinc-300 font-mono">
                  reality show fraude documental filtrado
                </span>
              </div>

              <div className="flex flex-col sm:flex-row gap-4 p-3 rounded-2xl bg-zinc-950/80 border border-zinc-800">
                <div className="sm:w-72 shrink-0 relative rounded-xl overflow-hidden aspect-video shadow">
                  {thumbnailRenderNode}
                  <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 bg-black/90 text-white font-mono text-[10px] font-bold rounded">
                    {YOUTUBE_MOCKUP_METADATA.duration}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-base font-bold text-zinc-100 line-clamp-2 leading-snug">
                    {YOUTUBE_MOCKUP_METADATA.videoTitle}
                  </h4>
                  <p className="text-xs text-zinc-400 mt-1">
                    {YOUTUBE_MOCKUP_METADATA.channelName} ✓ • {YOUTUBE_MOCKUP_METADATA.views} • {YOUTUBE_MOCKUP_METADATA.uploadedTime}
                  </p>
                  <p className="text-xs text-zinc-500 mt-2 line-clamp-2 leading-relaxed">
                    Investigación exhaustiva sobre la sala de control y manipulación de cámaras en los mayores programas de televisión. Revelamos las cláusulas secretas y confesiones nunca antes emitidas...
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
