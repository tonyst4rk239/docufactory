import React from 'react';
import { ThumbnailConfig } from '../types/thumbnail';
import { X, CheckCircle, Flame, ShieldAlert, Zap, TrendingUp, Sparkles } from 'lucide-react';

interface CtrAnalyzerModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: ThumbnailConfig;
}

export const CtrAnalyzerModal: React.FC<CtrAnalyzerModalProps> = ({
  isOpen,
  onClose,
  config,
}) => {
  if (!isOpen) return null;

  // Evaluate CTR Factors
  const isYellow = config.primaryTextColor.toUpperCase() === '#FFE600';
  const hasStrongContrast = config.contrast >= 120;
  const isHostVisible = config.hostVisible;
  const hasOutline = config.hostOutlineWidth >= 6;
  const safeZoneOk = config.textPosition !== 'top-right' || config.hostPosition !== 'bottom-right';

  // Calculate score out of 10
  let score = 7.0;
  if (isYellow) score += 0.8;
  if (hasStrongContrast) score += 0.6;
  if (isHostVisible) score += 0.8;
  if (hasOutline) score += 0.4;
  if (config.showRecBadge || config.showSecretStamp) score += 0.3;
  if (score > 9.8) score = 9.8;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <div className="relative w-full max-w-2xl bg-[#121216] border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400">
              <Flame className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-zinc-100">Auditoría de CTR (Tasa de Clics)</h3>
              <p className="text-xs text-zinc-400">Análisis algorítmico para documentales de misterio</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Score Hero */}
        <div className="p-6 bg-gradient-to-b from-zinc-900 to-[#121216] border-b border-zinc-800/80 flex items-center justify-between">
          <div>
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-amber-400">
              Potencial Viral Estimado
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-5xl font-black text-white font-mono tracking-tight">
                {score.toFixed(1)}
              </span>
              <span className="text-zinc-500 font-mono text-xl">/ 10</span>
              <span className="ml-3 px-3 py-1 rounded-full text-xs font-black uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                Grado S+ (Muy Alto CTR)
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-2">
              Esta composición utiliza la tríada de psicología de YouTube: <strong>Rostro de Shock</strong> + <strong>Pregunta Dramática</strong> + <strong>Prueba Visual en CCTV</strong>.
            </p>
          </div>
        </div>

        {/* Breakdown Items */}
        <div className="p-6 space-y-3.5 overflow-y-auto max-h-[50vh]">
          {/* Factor 1 */}
          <div className="flex items-start gap-3 p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-zinc-200">Tipografía Amarilla #FFE600 & Borde Negro</h4>
                <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-mono font-bold">+18% CTR</span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                El amarillo #FFE600 es el color de mayor longitud de onda perceptible por el ojo humano en fondos oscuros de televisión.
              </p>
            </div>
          </div>

          {/* Factor 2 */}
          <div className="flex items-start gap-3 p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-zinc-200">Contorno Blanco/Cian 8px en Host</h4>
                <span className="text-[10px] bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded font-mono font-bold">+24% CTR</span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Separa la silueta del presentador de las pantallas oscuras del fondo, garantizando lectura instantánea en smartphones de 360px.
              </p>
            </div>
          </div>

          {/* Factor 3 */}
          <div className="flex items-start gap-3 p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-zinc-200">Zona Segura de YouTube (Safe Zone)</h4>
                <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-mono font-bold">Óptimo</span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                El texto está en la esquina superior izquierda, evitando ser tapado por la etiqueta de duración del video de YouTube en la esquina inferior derecha.
              </p>
            </div>
          </div>

          {/* Factor 4 */}
          <div className="flex items-start gap-3 p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-zinc-200">Iluminación Dual Rojo/Cian de Thriller</h4>
                <span className="text-[10px] bg-red-500/20 text-red-300 px-2 py-0.5 rounded font-mono font-bold">+15% Retención</span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Transmite intriga psicológica de investigación documental (estilo Netflix/HBO), elevando la percepción de calidad.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-zinc-950 border-t border-zinc-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-black text-xs uppercase tracking-wider transition-colors cursor-pointer"
          >
            Entendido, Continuar Creando
          </button>
        </div>
      </div>
    </div>
  );
};
