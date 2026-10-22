import React from 'react';
import { ThumbnailConfig } from '../types/thumbnail';

interface ViralTextLayerProps {
  config: ThumbnailConfig;
}

export const ViralTextLayer: React.FC<ViralTextLayerProps> = ({ config }) => {
  const getFontFamily = () => {
    switch (config.fontStyle) {
      case 'impact':
        return 'Impact, "Arial Black", sans-serif';
      case 'montserrat':
        return '"Montserrat", sans-serif';
      case 'bebas':
      default:
        return '"Bebas Neue", "Impact", "Arial Black", sans-serif';
    }
  };

  const getPositionClasses = () => {
    switch (config.textPosition) {
      case 'top-right':
        return 'items-end text-right top-6 right-8';
      case 'center-top':
        return 'items-center text-center top-8 inset-x-8';
      case 'center':
        return 'items-center text-center inset-0 justify-center';
      case 'top-left':
      default:
        return 'items-start text-left top-8 left-8 max-w-[65%]';
    }
  };

  return (
    <div className="absolute inset-0 pointer-events-none select-none z-20 flex flex-col justify-between p-6 md:p-8">
      {/* Top Section: REC Badge & Secret Classification Stamp */}
      <div className="flex items-center justify-between w-full">
        {config.showRecBadge && (
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded bg-black/70 border border-red-500/40 backdrop-blur-md shadow-lg shadow-red-950/40">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-600"></span>
            </span>
            <span className="font-mono text-xs md:text-sm font-bold tracking-widest text-red-400 uppercase">
              REC • {config.recTimecode}
            </span>
          </div>
        )}

        {config.showSecretStamp && (
          <div
            className="px-3.5 py-1 border-2 border-red-500/90 text-red-500 font-mono font-black text-xs md:text-sm tracking-widest uppercase transform rotate-2 bg-red-950/30 backdrop-blur-sm shadow-xl"
            style={{
              textShadow: '0 0 10px rgba(239,68,68,0.7)',
              boxShadow: 'inset 0 0 12px rgba(239,68,68,0.2), 0 4px 15px rgba(0,0,0,0.8)',
            }}
          >
            ⚠️ {config.stampText}
          </div>
        )}
      </div>

      {/* Main Viral Text Block (High CTR Yellow #FFE600 with Black Outline & Deep 3D Shadow) */}
      <div className={`absolute ${getPositionClasses()}`}>
        {config.showSubtitleBanner && config.subtitleBannerText && (
          <div className="mb-2 inline-flex items-center gap-1.5 px-3.5 py-1 bg-red-600 text-white font-sans font-black text-xs md:text-sm uppercase tracking-wider shadow-2xl rounded-sm transform -rotate-1 border border-red-400/50">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse"></span>
            {config.subtitleBannerText}
          </div>
        )}

        {/* Primary Impact Headline: "¡FUE UN FRAUDE!" */}
        <h1
          className="leading-[0.88] tracking-tight uppercase"
          style={{
            fontFamily: getFontFamily(),
            fontSize: `clamp(3rem, ${config.textSize * 7}vw, 8.5rem)`,
            color: config.primaryTextColor, // #FFE600
            transform: `rotate(${config.textRotation}deg)`,
            WebkitTextStroke: config.primaryTextStroke ? `${config.strokeWidth}px #000000` : 'none',
            paintOrder: 'stroke fill',
            textShadow: `
              0 2px 0 #000,
              0 4px 0 #000,
              0 6px 0 #000,
              0 8px 0 #000,
              0 12px 25px rgba(0, 0, 0, ${config.textShadowIntensity / 100}),
              0 20px 40px rgba(0, 0, 0, 0.9)
            `,
          }}
        >
          {config.primaryText}
        </h1>

        {/* Secondary Subtitle / Punchline */}
        {config.secondaryText && (
          <p
            className="mt-1 leading-none tracking-wide uppercase font-black"
            style={{
              fontFamily: getFontFamily(),
              fontSize: `clamp(1.4rem, ${config.textSize * 3.2}vw, 3.8rem)`,
              color: config.secondaryTextColor,
              WebkitTextStroke: '6px #000000',
              paintOrder: 'stroke fill',
              textShadow: '0 4px 15px rgba(0,0,0,0.9), 0 0 20px rgba(255,255,255,0.4)',
              transform: `rotate(${config.textRotation * 0.7}deg)`,
            }}
          >
            {config.secondaryText}
          </p>
        )}
      </div>

      {/* Visual Clickbait Elements: Red Surveillance Circle & Arrow */}
      {config.showRedCircle && (
        <div
          className="absolute top-[22%] left-[42%] w-32 h-24 md:w-48 md:h-36 border-4 border-dashed border-red-500 rounded-[50%] pointer-events-none transform -rotate-12 animate-pulse"
          style={{
            boxShadow: '0 0 25px rgba(239,68,68,0.8), inset 0 0 15px rgba(239,68,68,0.3)',
            filter: 'drop-shadow(0 0 10px #ef4444)',
          }}
        >
          <span className="absolute -top-3 left-4 bg-red-600 text-white font-mono font-bold text-[10px] md:text-xs px-2 py-0.5 rounded shadow">
            FILTRADO
          </span>
        </div>
      )}

      {config.showClickbaitArrow && (
        <div
          className="absolute top-[32%] left-[34%] transform rotate-[25deg] pointer-events-none drop-shadow-[0_4px_12px_rgba(0,0,0,0.9)]"
        >
          <svg width="90" height="90" viewBox="0 0 100 100" fill="none">
            <path
              d="M 15 85 Q 40 50 65 35"
              stroke="#ef4444"
              strokeWidth="12"
              strokeLinecap="round"
              fill="none"
              filter="drop-shadow(0 0 8px #ef4444)"
            />
            {/* Arrow Head */}
            <polygon
              points="85,25 55,22 68,52"
              fill="#ef4444"
              stroke="#ffffff"
              strokeWidth="3"
              filter="drop-shadow(0 0 10px #ef4444)"
            />
          </svg>
        </div>
      )}

      {/* Subtle Bottom Film Watermark / Legal disclaimer */}
      <div className="w-full flex justify-between items-end text-[10px] font-mono text-zinc-400 opacity-60">
        <span>PRODUCCIÓN CONFIDENCIAL • CASO CERRADO</span>
        <span>16:9 • 4K UHD</span>
      </div>
    </div>
  );
};
