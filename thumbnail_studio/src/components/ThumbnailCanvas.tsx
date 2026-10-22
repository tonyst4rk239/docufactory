import React, { useRef, useImperativeHandle, forwardRef } from 'react';
import { toPng, toJpeg, toBlob } from 'html-to-image';
import { ThumbnailConfig } from '../types/thumbnail';
import { ControlRoomBackground } from './ControlRoomBackground';
import { HostIllustration } from './HostIllustration';
import { ViralTextLayer } from './ViralTextLayer';

export interface ThumbnailCanvasHandle {
  exportImage: (format: 'png' | 'jpeg', resolution: '1080p' | '720p') => Promise<void>;
  copyToClipboard: () => Promise<boolean>;
}

interface ThumbnailCanvasProps {
  config: ThumbnailConfig;
  onConfigChange?: (newConfig: Partial<ThumbnailConfig>) => void;
}

export const ThumbnailCanvas = forwardRef<ThumbnailCanvasHandle, ThumbnailCanvasProps>(
  ({ config }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);

    // Compute outline color style
    const getOutlineColor = () => {
      switch (config.hostOutlineColor) {
        case 'white':
          return '#ffffff';
        case 'cyan':
          return config.hostOutlineCustomColor || '#22d3ee';
        case 'yellow':
          return '#FFE600';
        case 'red':
          return '#ef4444';
        case 'none':
        default:
          return 'transparent';
      }
    };

    // Calculate Host Positioning style
    const getHostStyle = () => {
      const isRight = config.hostPosition === 'bottom-right';
      const isLeft = config.hostPosition === 'bottom-left';
      const isCenter = config.hostPosition === 'center-bottom';

      return {
        bottom: `${config.hostOffsetY}%`,
        right: isRight ? `${config.hostOffsetX * 0.4}%` : 'auto',
        left: isLeft ? `${config.hostOffsetX * 0.4}%` : isCenter ? '32%' : 'auto',
        transform: `scale(${config.hostScale}) ${config.hostFlipX ? 'scaleX(-1)' : ''}`,
        transformOrigin: 'bottom center',
      };
    };

    // Canvas Exporter using html-to-image (preserves host, uploaded images, SVGs, filters, and text)
    useImperativeHandle(ref, () => ({
      exportImage: async (format: 'png' | 'jpeg', resolution: '1080p' | '720p') => {
        const targetWidth = resolution === '1080p' ? 1920 : 1280;
        const targetHeight = resolution === '1080p' ? 1080 : 720;

        const element = containerRef.current;
        if (!element) return;

        const elemWidth = element.clientWidth || 1280;
        const pixelRatio = targetWidth / elemWidth;

        try {
          const exportFn = format === 'jpeg' ? toJpeg : toPng;
          const dataUrl = await exportFn(element, {
            quality: 0.95,
            pixelRatio: pixelRatio,
            canvasWidth: targetWidth,
            canvasHeight: targetHeight,
            backgroundColor: '#05080f',
            cacheBust: true,
          });

          const cleanName = (config.primaryText || 'miniatura')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9]/g, '_');

          const a = document.createElement('a');
          a.download = `miniatura_${cleanName}_${resolution}.${format}`;
          a.href = dataUrl;
          a.click();
        } catch (err) {
          console.warn('html-to-image fallo, utilizando renderizador de emergencia:', err);
          const canvas = document.createElement('canvas');
          canvas.width = targetWidth;
          canvas.height = targetHeight;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            renderCanvasDirect(ctx, targetWidth, targetHeight, config);
            const dataUrl = canvas.toDataURL(format === 'jpeg' ? 'image/jpeg' : 'image/png', 0.95);
            const a = document.createElement('a');
            a.download = `miniatura_${resolution}.${format}`;
            a.href = dataUrl;
            a.click();
          }
        }
      },

      copyToClipboard: async () => {
        const element = containerRef.current;
        if (!element) return false;
        try {
          const elemWidth = element.clientWidth || 1280;
          const blob = await toBlob(element, {
            pixelRatio: 1280 / elemWidth,
            backgroundColor: '#05080f',
            cacheBust: true,
          });
          if (blob && navigator.clipboard) {
            await navigator.clipboard.write([
              new ClipboardItem({ 'image/png': blob }),
            ]);
            return true;
          }
          return false;
        } catch (err) {
          console.error('Error copiando al portapapeles:', err);
          return false;
        }
      },
    }));

    // Helper direct canvas painter as fallback
    const renderCanvasDirect = (
      ctx: CanvasRenderingContext2D,
      w: number,
      h: number,
      cfg: ThumbnailConfig
    ) => {
      // Background dark fill
      ctx.fillStyle = '#05080f';
      ctx.fillRect(0, 0, w, h);

      // Cyan / Red gradients
      const gradCyan = ctx.createRadialGradient(w * 0.7, h * 0.3, 20, w * 0.7, h * 0.3, w * 0.6);
      gradCyan.addColorStop(0, 'rgba(8, 145, 178, 0.4)');
      gradCyan.addColorStop(1, 'transparent');
      ctx.fillStyle = gradCyan;
      ctx.fillRect(0, 0, w, h);

      const gradRed = ctx.createRadialGradient(w * 0.25, h * 0.7, 20, w * 0.25, h * 0.7, w * 0.5);
      gradRed.addColorStop(0, 'rgba(220, 38, 38, 0.5)');
      gradRed.addColorStop(1, 'transparent');
      ctx.fillStyle = gradRed;
      ctx.fillRect(0, 0, w, h);

      // Main Text
      ctx.save();
      ctx.translate(w * 0.08, h * 0.22);
      ctx.rotate((cfg.textRotation * Math.PI) / 180);

      const fontSize = Math.floor(h * 0.17 * cfg.textSize);
      ctx.font = `900 ${fontSize}px "Bebas Neue", "Arial Black", Impact, sans-serif`;
      ctx.textBaseline = 'top';

      // 3D Drop Shadow
      ctx.fillStyle = '#000000';
      for (let s = 1; s <= 12; s++) {
        ctx.fillText(cfg.primaryText, s, s);
      }

      // Stroke
      ctx.lineWidth = cfg.strokeWidth * (w / 1280);
      ctx.strokeStyle = '#000000';
      ctx.lineJoin = 'miter';
      ctx.strokeText(cfg.primaryText, 0, 0);

      // Fill
      ctx.fillStyle = cfg.primaryTextColor;
      ctx.fillText(cfg.primaryText, 0, 0);

      // Secondary text
      if (cfg.secondaryText) {
        const subFontSize = Math.floor(fontSize * 0.42);
        ctx.font = `900 ${subFontSize}px "Bebas Neue", Impact, sans-serif`;
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 8;
        ctx.strokeText(cfg.secondaryText, 0, fontSize * 0.95);
        ctx.fillStyle = cfg.secondaryTextColor;
        ctx.fillText(cfg.secondaryText, 0, fontSize * 0.95);
      }
      ctx.restore();
    };

    return (
      <div className="relative w-full aspect-video rounded-xl overflow-hidden shadow-2xl border border-zinc-800 bg-black select-none">
        {/* The 16:9 Inner Frame Container */}
        <div
          ref={containerRef}
          className="relative w-full h-full overflow-hidden"
          style={{
            filter: `contrast(${config.contrast}%) saturate(${config.saturation}%) brightness(${config.brightness}%)`,
          }}
        >
          {/* Layer 1: Background (Control Room / 08_fondo_miniatura_ai.jpg) */}
          <ControlRoomBackground
            preset={config.backgroundPreset}
            customImageSrc={config.customBackgroundImage}
            ambientLighting={config.ambientLighting}
            volumetricHaze={config.volumetricHaze}
            vignetteStrength={config.vignetteStrength}
            scanlines={config.scanlines}
            producerSilhouette={config.producerSilhouette}
            redAlertButtons={config.redAlertButtons}
            cctvGlitch={config.cctvGlitch}
          />

          {/* Layer 2: Host Layer (01_host_alerta.png) */}
          {config.hostVisible && (
            <div
              className="absolute z-10 pointer-events-none transition-all duration-150"
              style={getHostStyle()}
            >
              <div className="w-[38vw] max-w-[540px] min-w-[280px]">
                <HostIllustration
                  customImageSrc={config.hostCustomImage}
                  outlineColor={getOutlineColor()}
                  outlineWidth={config.hostOutlineWidth}
                  glowIntensity={config.hostGlowIntensity}
                  flipX={config.hostFlipX}
                />
              </div>
            </div>
          )}

          {/* Layer 3: High CTR Text & Badges Layer ("¡FUE UN FRAUDE!") */}
          <ViralTextLayer config={config} />
        </div>
      </div>
    );
  }
);
