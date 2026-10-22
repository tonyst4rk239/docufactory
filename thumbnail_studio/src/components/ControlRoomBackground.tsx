import React from 'react';
import { BackgroundPreset } from '../types/thumbnail';

interface ControlRoomBackgroundProps {
  preset: BackgroundPreset;
  customImageSrc?: string | null;
  ambientLighting: 'red-cyan' | 'pure-red' | 'cyber-cyan' | 'monochrome-cold';
  volumetricHaze: number; // 0 - 100
  vignetteStrength: number; // 0 - 100
  scanlines: boolean;
  producerSilhouette: boolean;
  redAlertButtons: boolean;
  cctvGlitch: boolean;
}

export const ControlRoomBackground: React.FC<ControlRoomBackgroundProps> = ({
  preset,
  customImageSrc,
  ambientLighting,
  volumetricHaze,
  vignetteStrength,
  scanlines,
  producerSilhouette,
  redAlertButtons,
  cctvGlitch,
}) => {
  // If user uploaded a custom background image (e.g. 08_fondo_miniatura_ai.jpg)
  if (customImageSrc) {
    return (
      <div className="absolute inset-0 w-full h-full overflow-hidden bg-black select-none pointer-events-none">
        <img
          src={customImageSrc}
          alt="Fondo Miniatura"
          className="w-full h-full object-cover"
        />
        {/* Atmospheric lighting overlay */}
        <div
          className="absolute inset-0 mix-blend-color-dodge pointer-events-none"
          style={{
            background: ambientLighting === 'red-cyan'
              ? 'radial-gradient(ellipse at 80% 30%, rgba(6,182,212,0.35) 0%, transparent 60%), radial-gradient(ellipse at 20% 70%, rgba(239,68,68,0.4) 0%, transparent 70%)'
              : ambientLighting === 'pure-red'
              ? 'radial-gradient(circle at 50% 50%, rgba(239,68,68,0.45) 0%, transparent 80%)'
              : 'radial-gradient(circle at 50% 50%, rgba(6,182,212,0.45) 0%, transparent 80%)',
          }}
        />
        {/* Vignette */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(circle at center, transparent 35%, rgba(0,0,0,${vignetteStrength / 100}) 95%)`,
          }}
        />
      </div>
    );
  }

  // Pure SVG/Canvas high-fidelity representation of the sinister CCTV control room
  return (
    <div className="absolute inset-0 w-full h-full overflow-hidden bg-[#05080f] select-none pointer-events-none">
      <svg
        viewBox="0 0 1920 1080"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full object-cover"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          {/* Volumetric Gradients */}
          <radialGradient id="cyanVolumetric" cx="70%" cy="30%" r="60%">
            <stop offset="0%" stopColor="#0891b2" stopOpacity="0.45" />
            <stop offset="50%" stopColor="#0e7490" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#05080f" stopOpacity="0" />
          </radialGradient>

          <radialGradient id="redVolumetric" cx="25%" cy="65%" r="55%">
            <stop offset="0%" stopColor="#dc2626" stopOpacity="0.5" />
            <stop offset="60%" stopColor="#991b1b" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#05080f" stopOpacity="0" />
          </radialGradient>

          <linearGradient id="consoleGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="40%" stopColor="#0f172a" />
            <stop offset="100%" stopColor="#020617" />
          </linearGradient>

          <linearGradient id="screenBezel" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="100%" stopColor="#0a0f1d" />
          </linearGradient>

          {/* CCTV Glitch Pattern */}
          <pattern id="cctvGrid" width="16" height="16" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="16" y2="0" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            <line x1="0" y1="0" x2="0" y2="16" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
          </pattern>

          {/* Scanlines Pattern */}
          <pattern id="scanlinePattern" width="100" height="4" patternUnits="userSpaceOnUse">
            <rect width="100" height="2" fill="rgba(0,0,0,0.35)" />
            <rect y="2" width="100" height="2" fill="rgba(255,255,255,0.02)" />
          </pattern>
        </defs>

        {/* --- DEEP BACKGROUND STUDIO STRUCTURE --- */}
        <rect width="1920" height="1080" fill="#05080e" />

        {/* Ambient Haze Layer */}
        <rect width="1920" height="1080" fill="url(#cyanVolumetric)" opacity={volumetricHaze / 100} />
        <rect width="1920" height="1080" fill="url(#redVolumetric)" opacity={volumetricHaze / 100} />

        {/* Studio Acoustic Panels & Ceiling Truss Wire Grid */}
        <g opacity="0.25">
          <line x1="0" y1="120" x2="1920" y2="120" stroke="#334155" strokeWidth="3" />
          <line x1="0" y1="80" x2="1920" y2="80" stroke="#1e293b" strokeWidth="2" />
          <line x1="200" y1="0" x2="200" y2="200" stroke="#1e293b" strokeWidth="2" />
          <line x1="500" y1="0" x2="500" y2="200" stroke="#1e293b" strokeWidth="2" />
          <line x1="900" y1="0" x2="900" y2="200" stroke="#1e293b" strokeWidth="2" />
          <line x1="1300" y1="0" x2="1300" y2="200" stroke="#1e293b" strokeWidth="2" />
          <line x1="1700" y1="0" x2="1700" y2="200" stroke="#1e293b" strokeWidth="2" />
        </g>

        {/* =========================================================================
            WALL OF CCTV SURVEILLANCE MONITORS & SECURITY FEEDS (REALITY SHOW DRAMA)
            ========================================================================= */}
        <g id="cctv-wall">
          {/* Main Huge Center Screen 1: The Survivor / Reality Contestant crying / distress */}
          <g transform="translate(480, 100)">
            {/* Monitor Outer Frame & Glowing Bezel */}
            <rect x="-8" y="-8" width="656" height="396" rx="6" fill="#0b1120" stroke="#0891b2" strokeWidth="2" opacity="0.8" />
            <rect x="0" y="0" width="640" height="380" rx="4" fill="#09131d" />

            {/* Simulated Reality Scene inside Main Monitor: Confesionario / Shock */}
            <g id="screen-1-reality">
              {/* Confession Booth Dark Background with dramatic spotlight */}
              <radialGradient id="confessionSpot" cx="50%" cy="30%" r="50%">
                <stop offset="0%" stopColor="#d97706" stopOpacity="0.85" />
                <stop offset="60%" stopColor="#78350f" stopOpacity="0.4" />
                <stop offset="100%" stopColor="#0c0a09" stopOpacity="0.95" />
              </radialGradient>
              <rect width="640" height="380" fill="url(#confessionSpot)" />

              {/* Survivor / Contestant Silhouette & Emotional Breakdown */}
              {/* Torso with survivor green buff */}
              <path d="M 220 380 C 230 290, 270 260, 320 260 C 370 260, 410 290, 420 380 Z" fill="#9a3412" opacity="0.85" />
              {/* Green Survivor Buff around neck */}
              <ellipse cx="320" cy="265" rx="52" ry="18" fill="#15803d" stroke="#166534" strokeWidth="3" />
              {/* Neck & Head with sweat/sand */}
              <path d="M 285 190 C 285 130, 355 130, 355 190 C 355 240, 285 240, 285 190 Z" fill="#b45309" />
              {/* Mud / sand marks on face */}
              <path d="M 290 170 C 300 165, 305 180, 300 195" stroke="#451a03" strokeWidth="5" strokeLinecap="round" opacity="0.8" />
              <path d="M 345 165 C 335 170, 340 185, 345 195" stroke="#451a03" strokeWidth="5" strokeLinecap="round" opacity="0.8" />
              {/* Exhausted / Pained Expression */}
              <ellipse cx="308" cy="180" rx="6" ry="4" fill="#1c1917" />
              <ellipse cx="332" cy="180" rx="6" ry="4" fill="#1c1917" />
              {/* Tear glint under spotlight */}
              <line x1="334" y1="184" x2="333" y2="202" stroke="#67e8f9" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M 314 208 Q 320 202 326 208" stroke="#292524" strokeWidth="3" fill="none" strokeLinecap="round" />

              {/* Spotlight Ray */}
              <polygon points="120,0 520,0 420,380 220,380" fill="rgba(254,240,138,0.08)" />
            </g>

            {/* CCTV Security Camera HUD Overlays */}
            <rect width="640" height="380" fill="url(#cctvGrid)" />
            <rect x="20" y="20" width="600" height="340" fill="none" stroke="rgba(6,182,212,0.3)" strokeWidth="1" strokeDasharray="6 4" />
            <circle cx="35" cy="40" r="6" fill="#ef4444" />
            <text x="50" y="44" fill="#ef4444" fontFamily="monospace" fontSize="13" fontWeight="bold">REC • LIVE 00:43:18</text>
            <text x="500" y="44" fill="#22d3ee" fontFamily="monospace" fontSize="12" fontWeight="bold">CAM 01 [CONFESIONARIO]</text>
            <text x="35" y="340" fill="#94a3b8" fontFamily="monospace" fontSize="11">MIC 01: -3.2dB | ISO 1600 | 4K LOG</text>
            <text x="470" y="340" fill="#facc15" fontFamily="monospace" fontSize="11" fontWeight="bold">ESTADO: CRISIS EMOCIONAL</text>

            {/* Target crosshair in center */}
            <path d="M 310 180 L 330 180 M 320 170 L 320 190" stroke="rgba(34,211,238,0.6)" strokeWidth="2" />
          </g>

          {/* Left Monitor Column (3 Monitors) */}
          {/* Top Left: Contestant Argument in Rain / Spotlight */}
          <g transform="translate(100, 70)">
            <rect width="340" height="195" rx="4" fill="#09101b" stroke="#334155" strokeWidth="2" />
            {/* Dramatic silhouette duel */}
            <rect width="340" height="195" fill="#1e1b4b" opacity="0.6" />
            <path d="M 60 195 C 70 140, 100 130, 110 90 C 130 90, 140 140, 130 195 Z" fill="#0f172a" />
            <path d="M 260 195 C 250 130, 220 120, 210 80 C 190 80, 180 130, 190 195 Z" fill="#0f172a" />
            <text x="15" y="28" fill="#f43f5e" fontFamily="monospace" fontSize="11" fontWeight="bold">🔴 CAM 02 [DISCUSIÓN PLAYA]</text>
            <text x="210" y="28" fill="#38bdf8" fontFamily="monospace" fontSize="10">23:59:12</text>
            <rect x="0" y="170" width="340" height="25" fill="rgba(0,0,0,0.6)" />
            <text x="15" y="186" fill="#f87171" fontFamily="sans-serif" fontSize="10" fontWeight="bold">AUDIO: "¡ESTÁ TODO ARREGLADO!"</text>
          </g>

          {/* Mid Left: Secret Night Vision CCTV Cam */}
          <g transform="translate(100, 285)">
            <rect width="340" height="195" rx="4" fill="#041f11" stroke="#059669" strokeWidth="2" />
            <rect width="340" height="195" fill="rgba(16,185,129,0.12)" />
            {/* Green Night Vision surveillance shapes */}
            <circle cx="170" cy="100" r="45" fill="rgba(52,211,153,0.3)" />
            <ellipse cx="170" cy="85" rx="20" ry="24" fill="#064e3b" />
            <text x="15" y="28" fill="#34d399" fontFamily="monospace" fontSize="11" fontWeight="bold">🟢 CAM 03 [CÁMARA OCULTA VESTUARIOS]</text>
            <text x="15" y="180" fill="#a7f3d0" fontFamily="monospace" fontSize="10">NIGHT VISION INFRARED • ENCRIPTADO</text>
          </g>

          {/* Right Monitor Column (3 Monitors) */}
          {/* Top Right: SMPTE Color Bars & Test Pattern (Interrupted feed) */}
          <g transform="translate(1160, 70)">
            <rect width="330" height="195" rx="4" fill="#09101b" stroke="#334155" strokeWidth="2" />
            {/* Color bars */}
            <rect x="0" y="0" width="47" height="140" fill="#fef08a" />
            <rect x="47" y="0" width="47" height="140" fill="#67e8f9" />
            <rect x="94" y="0" width="47" height="140" fill="#4ade80" />
            <rect x="141" y="0" width="47" height="140" fill="#f472b6" />
            <rect x="188" y="0" width="47" height="140" fill="#ef4444" />
            <rect x="235" y="0" width="47" height="140" fill="#3b82f6" />
            <rect x="282" y="0" width="48" height="140" fill="#1e1b4b" />
            <rect x="0" y="140" width="330" height="55" fill="#020617" />
            {/* Glitch error text */}
            <rect x="50" y="60" width="230" height="40" fill="#dc2626" rx="3" />
            <text x="65" y="85" fill="#ffffff" fontFamily="sans-serif" fontSize="13" fontWeight="900" letterSpacing="1">SEÑAL INTERRUMPIDA</text>
            <text x="15" y="175" fill="#f87171" fontFamily="monospace" fontSize="10">ERROR CODE: 0x98F4 [MANIPULATION]</text>
          </g>

          {/* Mid Right: Multiview Broadcast Grid */}
          <g transform="translate(1160, 285)">
            <rect width="330" height="195" rx="4" fill="#09101b" stroke="#0284c7" strokeWidth="2" />
            {/* 4 mini split-screen feeds */}
            <rect x="5" y="5" width="155" height="90" fill="#0f172a" />
            <text x="12" y="20" fill="#38bdf8" fontFamily="monospace" fontSize="9">CAM 05 ARENA</text>
            <circle cx="80" cy="50" r="18" fill="#1e293b" />

            <rect x="170" y="5" width="155" height="90" fill="#1e1b4b" />
            <text x="177" y="20" fill="#f43f5e" fontFamily="monospace" fontSize="9">CAM 06 CONTROL</text>
            <rect x="210" y="35" width="60" height="40" fill="#312e81" />

            <rect x="5" y="100" width="155" height="90" fill="#18181b" />
            <text x="12" y="115" fill="#facc15" fontFamily="monospace" fontSize="9">AUDIO MASTER</text>
            {/* Audio equalizer bars */}
            <rect x="20" y="140" width="6" height="35" fill="#22c55e" />
            <rect x="32" y="130" width="6" height="45" fill="#22c55e" />
            <rect x="44" y="120" width="6" height="55" fill="#eab308" />
            <rect x="56" y="110" width="6" height="65" fill="#ef4444" />
            <rect x="68" y="135" width="6" height="40" fill="#22c55e" />

            <rect x="170" y="100" width="155" height="90" fill="#0c0a09" />
            <text x="177" y="115" fill="#ef4444" fontFamily="monospace" fontSize="9">SPOILER LOG</text>
            <text x="177" y="135" fill="#78716c" fontFamily="monospace" fontSize="8">ELIMINADO: JUGADOR #4</text>
            <text x="177" y="150" fill="#ef4444" fontFamily="monospace" fontSize="8" fontWeight="bold">PACTO CON PRODUCCIÓN</text>
          </g>

          {/* Far edges additional monitors (giving feeling of "docenas de pantallas") */}
          <g transform="translate(-80, 150)" opacity="0.6">
            <rect width="160" height="280" fill="#09101b" stroke="#1e293b" strokeWidth="2" />
            <rect x="10" y="20" width="140" height="80" fill="#020617" />
            <circle cx="80" cy="60" r="15" fill="#3b82f6" />
          </g>
          <g transform="translate(1520, 150)" opacity="0.6">
            <rect width="180" height="280" fill="#09101b" stroke="#1e293b" strokeWidth="2" />
            <rect x="10" y="20" width="160" height="80" fill="#020617" />
            <circle cx="90" cy="60" r="15" fill="#ef4444" />
          </g>
        </g>

        {/* =========================================================================
            FOREGROUND MASTER BROADCAST SWITCHER & CONTROL CONSOLE (DESK)
            ========================================================================= */}
        <g id="master-console" transform="translate(0, 520)">
          {/* Main Control Desk Surface Angle */}
          <polygon
            points="0,220 1920,220 1920,560 0,560"
            fill="url(#consoleGrad)"
            stroke="#0f172a"
            strokeWidth="3"
          />
          <polygon
            points="0,140 1920,140 1920,220 0,220"
            fill="#1e293b"
            stroke="#334155"
            strokeWidth="2"
          />

          {/* Glowing Console Backlight Strip (Cyan and Red LED Underglow) */}
          <line x1="0" y1="140" x2="960" y2="140" stroke="#ef4444" strokeWidth="4" filter="drop-shadow(0 0 12px #ef4444)" />
          <line x1="960" y1="140" x2="1920" y2="140" stroke="#06b6d4" strokeWidth="4" filter="drop-shadow(0 0 12px #06b6d4)" />

          {/* Illuminated Broadcast Buttons & Warning Lamps (Buttons rojos de advertencia encendidos) */}
          {redAlertButtons && (
            <g id="alert-buttons" transform="translate(150, 180)">
              {/* Row of glowing red warning switches */}
              <rect x="0" y="0" width="70" height="28" rx="4" fill="#dc2626" stroke="#f87171" strokeWidth="2" filter="drop-shadow(0 0 10px #dc2626)" />
              <text x="12" y="19" fill="#ffffff" fontFamily="sans-serif" fontSize="10" fontWeight="900">ALERTA</text>

              <rect x="85" y="0" width="70" height="28" rx="4" fill="#dc2626" stroke="#f87171" strokeWidth="2" filter="drop-shadow(0 0 10px #dc2626)" />
              <text x="96" y="19" fill="#ffffff" fontFamily="sans-serif" fontSize="10" fontWeight="900">OVERRIDE</text>

              <rect x="170" y="0" width="70" height="28" rx="4" fill="#ef4444" stroke="#fca5a5" strokeWidth="2" filter="drop-shadow(0 0 12px #ef4444)" />
              <text x="180" y="19" fill="#ffffff" fontFamily="sans-serif" fontSize="10" fontWeight="900">CENSOR</text>

              <rect x="255" y="0" width="70" height="28" rx="4" fill="#7f1d1d" stroke="#b91c1c" strokeWidth="1" />
              <text x="272" y="19" fill="#fca5a5" fontFamily="sans-serif" fontSize="10" fontWeight="bold">MUTE</text>

              {/* Cyan & Yellow switcher matrix buttons */}
              <g transform="translate(360, 0)">
                {[...Array(8)].map((_, i) => (
                  <rect
                    key={i}
                    x={i * 35}
                    y={0}
                    width="26"
                    height="28"
                    rx="3"
                    fill={i === 2 ? '#eab308' : i === 5 ? '#06b6d4' : '#1e293b'}
                    stroke={i === 2 ? '#fef08a' : i === 5 ? '#67e8f9' : '#475569'}
                    strokeWidth="1.5"
                    filter={i === 2 ? 'drop-shadow(0 0 6px #eab308)' : i === 5 ? 'drop-shadow(0 0 6px #06b6d4)' : 'none'}
                  />
                ))}
              </g>
            </g>
          )}

          {/* Right Desk Elements: Faders & Sliders & Preview Screen */}
          <g transform="translate(1000, 180)">
            {/* T-Bar Video Switcher Handle */}
            <rect x="180" y="-10" width="16" height="50" rx="3" fill="#cbd5e1" stroke="#475569" strokeWidth="2" />
            <circle cx="188" cy="15" r="10" fill="#dc2626" filter="drop-shadow(0 0 8px #dc2626)" />

            {/* Audio Faders */}
            {[...Array(6)].map((_, i) => (
              <g key={i} transform={`translate(${i * 26}, 0)`}>
                <line x1="8" y1="0" x2="8" y2="40" stroke="#334155" strokeWidth="3" strokeLinecap="round" />
                <rect x="3" y={10 + (i % 3) * 8} width="10" height="12" rx="2" fill="#94a3b8" stroke="#0f172a" strokeWidth="1" />
              </g>
            ))}
          </g>

          {/* Desk Edge Highlights */}
          <line x1="0" y1="220" x2="1920" y2="220" stroke="#334155" strokeWidth="2" />
        </g>

        {/* =========================================================================
            PRODUCER SILHOUETTE (IN PRIMER PLANO: SILUETA OSCURA DE PRODUCTOR DE TV DE ESPALDAS)
            ========================================================================= */}
        {producerSilhouette && (
          <g id="producer-silhouette" transform="translate(620, 460)">
            {/* Ominous producer seated in studio chair with headphones, seen from back */}
            {/* Back rim light / volumetric spill in cyan & red */}
            <path
              d="M 120 450 C 130 330, 170 250, 220 230 C 270 230, 310 330, 320 450 Z"
              fill="none"
              stroke="#0891b2"
              strokeWidth="12"
              opacity="0.3"
              filter="drop-shadow(0 0 20px #06b6d4)"
            />

            {/* Dark Silhouette Body */}
            <path
              d="M 60 520 C 70 380, 130 300, 200 270 C 270 300, 330 380, 340 520 Z"
              fill="#020408"
            />
            {/* High-back Studio Chair */}
            <path
              d="M 90 560 L 110 310 C 120 280, 280 280, 290 310 L 310 560 Z"
              fill="#060911"
              stroke="#0f172a"
              strokeWidth="4"
            />

            {/* Producer Neck and Head */}
            <ellipse cx="200" cy="235" rx="36" ry="42" fill="#020408" />

            {/* Over-ear Studio Headphones */}
            {/* Headphone Arch */}
            <path
              d="M 154 235 C 150 185, 250 185, 246 235"
              stroke="#0f172a"
              strokeWidth="12"
              strokeLinecap="round"
            />
            {/* Left Ear Cushion with Cyan Edge Highlight */}
            <ellipse cx="156" cy="235" rx="10" ry="18" fill="#1e293b" stroke="#22d3ee" strokeWidth="2" />
            {/* Right Ear Cushion with Red Edge Highlight */}
            <ellipse cx="244" cy="235" rx="10" ry="18" fill="#1e293b" stroke="#ef4444" strokeWidth="2" />

            {/* Audio Cable draping down to console */}
            <path
              d="M 156 250 C 145 320, 160 380, 120 430"
              stroke="#0f172a"
              strokeWidth="4"
              fill="none"
            />

            {/* Rim lighting along producer's shoulders */}
            <path
              d="M 100 480 C 120 370, 150 330, 175 310"
              stroke="#22d3ee"
              strokeWidth="4"
              fill="none"
              strokeLinecap="round"
              opacity="0.6"
            />
            <path
              d="M 300 480 C 280 370, 250 330, 225 310"
              stroke="#f43f5e"
              strokeWidth="4"
              fill="none"
              strokeLinecap="round"
              opacity="0.6"
            />
          </g>
        )}

        {/* Scanlines layer */}
        {scanlines && (
          <rect width="1920" height="1080" fill="url(#scanlinePattern)" pointerEvents="none" />
        )}

        {/* Global Dark Vignette */}
        <radialGradient id="masterVignette" cx="50%" cy="50%" r="55%">
          <stop offset="35%" stopColor="#000000" stopOpacity="0" />
          <stop offset="75%" stopColor="#000000" stopOpacity={(vignetteStrength * 0.7) / 100} />
          <stop offset="100%" stopColor="#000000" stopOpacity={Math.min(1, (vignetteStrength * 1.2) / 100)} />
        </radialGradient>
        <rect width="1920" height="1080" fill="url(#masterVignette)" pointerEvents="none" />
      </svg>
    </div>
  );
};
