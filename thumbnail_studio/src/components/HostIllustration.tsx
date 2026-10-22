import React from 'react';

interface HostIllustrationProps {
  customImageSrc?: string | null;
  outlineColor: string;
  outlineWidth: number;
  glowIntensity: number;
  className?: string;
  flipX?: boolean;
}

export const HostIllustration: React.FC<HostIllustrationProps> = ({
  customImageSrc,
  outlineColor,
  outlineWidth,
  glowIntensity,
  className = '',
  flipX = false,
}) => {
  // If custom uploaded image is provided, display it
  if (customImageSrc) {
    return (
      <div
        className={`relative inline-block select-none pointer-events-none ${className}`}
        style={{
          transform: flipX ? 'scaleX(-1)' : 'none',
          filter: outlineWidth > 0 
            ? `drop-shadow(0 0 ${glowIntensity}px ${outlineColor}) drop-shadow(0 0 ${outlineWidth}px ${outlineColor}) drop-shadow(0 0 2px ${outlineColor})` 
            : 'none',
        }}
      >
        <img
          src={customImageSrc}
          alt="Host Alerta"
          className="w-full h-auto object-contain max-h-[85vh] drop-shadow-2xl"
        />
      </div>
    );
  }

  // High-fidelity SVG vector rendition of the alerted cartoon host (01_host_alerta.png)
  // Matching the character: modern quiff hairstyle, dark navy sweater over white shirt,
  // terrified/shocked open mouth, raised alert palms.
  const filterId = `host-glow-${outlineColor.replace(/[^a-zA-Z0-9]/g, '')}`;

  return (
    <div
      className={`relative inline-block select-none pointer-events-none transition-transform duration-200 ${className}`}
      style={{
        transform: flipX ? 'scaleX(-1)' : 'none',
        filter: outlineWidth > 0
          ? `drop-shadow(0 0 ${outlineWidth * 1.2}px ${outlineColor}) drop-shadow(0 0 ${glowIntensity}px ${outlineColor}) drop-shadow(0 15px 30px rgba(0,0,0,0.8))`
          : 'drop-shadow(0 15px 35px rgba(0,0,0,0.8))',
      }}
    >
      <svg
        viewBox="0 0 540 680"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-auto max-h-[88vh] filter"
        style={{ overflow: 'visible' }}
      >
        <defs>
          <radialGradient id="skinGlow" cx="50%" cy="40%" r="55%">
            <stop offset="0%" stopColor="#ffdfc8" />
            <stop offset="70%" stopColor="#f5b895" />
            <stop offset="100%" stopColor="#d98965" />
          </radialGradient>
          <linearGradient id="hairGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#3d2c25" />
            <stop offset="50%" stopColor="#251b17" />
            <stop offset="100%" stopColor="#140e0b" />
          </linearGradient>
          <linearGradient id="sweaterGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2b3b52" />
            <stop offset="60%" stopColor="#1b2536" />
            <stop offset="100%" stopColor="#111824" />
          </linearGradient>
          <linearGradient id="shadowBody" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="transparent" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.4)" />
          </linearGradient>
        </defs>

        {/* Outline Stroke Duplicate Base (Simulates hard sticker border) */}
        {outlineWidth > 0 && (
          <path
            d="M 270 90 C 230 90, 190 120, 185 170 C 180 200, 190 230, 200 250 L 170 310 L 80 440 C 60 480, 70 540, 110 560 L 160 580 L 160 680 L 400 680 L 410 570 L 480 500 C 510 460, 490 400, 450 370 L 370 290 C 375 250, 385 190, 350 140 C 320 95, 290 90, 270 90 Z"
            fill={outlineColor}
            opacity="0.3"
            transform="scale(1.02) translate(-5, -5)"
          />
        )}

        {/* --- TORSO & SWEATER --- */}
        <g id="torso">
          {/* Main Body Sweater */}
          <path
            d="M 140 440 C 145 350, 210 330, 260 330 C 310 330, 375 350, 380 440 L 405 680 L 115 680 Z"
            fill="url(#sweaterGrad)"
            stroke="#0d141e"
            strokeWidth="5"
          />

          {/* Sweater folds & lighting */}
          <path
            d="M 230 400 C 250 430, 270 430, 290 400"
            stroke="#3a4f6e"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path
            d="M 180 470 C 220 510, 300 510, 340 470"
            stroke="#16202f"
            strokeWidth="5"
            strokeLinecap="round"
          />
          <path
            d="M 160 550 C 200 570, 320 570, 360 550"
            stroke="#131c2b"
            strokeWidth="4"
            strokeLinecap="round"
          />

          {/* White Shirt Collar */}
          <path
            d="M 222 320 L 260 370 L 250 326 Z"
            fill="#ffffff"
            stroke="#111824"
            strokeWidth="4"
          />
          <path
            d="M 298 320 L 260 370 L 270 326 Z"
            fill="#f3f4f6"
            stroke="#111824"
            strokeWidth="4"
          />
          <path
            d="M 260 370 L 260 410"
            stroke="#0f172a"
            strokeWidth="4"
            strokeLinecap="round"
          />
        </g>

        {/* --- NECK & HEAD --- */}
        <g id="head-and-neck">
          {/* Neck */}
          <path
            d="M 228 290 L 228 340 C 240 348, 280 348, 292 340 L 292 290 Z"
            fill="#d98965"
            stroke="#1a1412"
            strokeWidth="5"
          />
          {/* Neck shadow under jaw */}
          <path
            d="M 228 295 C 255 315, 275 315, 292 295 L 292 315 C 275 330, 245 330, 228 315 Z"
            fill="#b86948"
          />

          {/* Ears */}
          {/* Left Ear */}
          <path
            d="M 195 210 C 180 210, 175 235, 185 255 C 192 268, 202 265, 205 255 Z"
            fill="url(#skinGlow)"
            stroke="#221510"
            strokeWidth="4"
          />
          <path
            d="M 188 225 C 184 235, 188 245, 196 248"
            stroke="#c87754"
            strokeWidth="3"
            strokeLinecap="round"
          />
          {/* Right Ear */}
          <path
            d="M 325 210 C 340 210, 345 235, 335 255 C 328 268, 318 265, 315 255 Z"
            fill="url(#skinGlow)"
            stroke="#221510"
            strokeWidth="4"
          />
          <path
            d="M 332 225 C 336 235, 332 245, 324 248"
            stroke="#c87754"
            strokeWidth="3"
            strokeLinecap="round"
          />

          {/* Face Contour */}
          <path
            d="M 198 175 C 190 230, 205 295, 260 300 C 315 295, 330 230, 322 175 C 320 150, 200 150, 198 175 Z"
            fill="url(#skinGlow)"
            stroke="#20140e"
            strokeWidth="5"
          />

          {/* Terrified / Shocked Eyebrows - Raised high & curved */}
          <path
            d="M 210 178 C 225 162, 242 166, 248 174"
            stroke="#251b17"
            strokeWidth="6"
            strokeLinecap="round"
          />
          <path
            d="M 310 178 C 295 162, 278 166, 272 174"
            stroke="#251b17"
            strokeWidth="6"
            strokeLinecap="round"
          />

          {/* Wide Shocked Eyes */}
          {/* Left Eye */}
          <ellipse cx="232" cy="195" rx="14" ry="17" fill="#ffffff" stroke="#251b17" strokeWidth="4" />
          <ellipse cx="233" cy="194" rx="8" ry="9" fill="#3b271d" />
          <ellipse cx="233" cy="194" rx="4.5" ry="5.5" fill="#0b0806" />
          <circle cx="230" cy="190" r="3" fill="#ffffff" />
          <circle cx="235" cy="197" r="1.5" fill="#ffffff" />

          {/* Right Eye */}
          <ellipse cx="288" cy="195" rx="14" ry="17" fill="#ffffff" stroke="#251b17" strokeWidth="4" />
          <ellipse cx="287" cy="194" rx="8" ry="9" fill="#3b271d" />
          <ellipse cx="287" cy="194" rx="4.5" ry="5.5" fill="#0b0806" />
          <circle cx="284" cy="190" r="3" fill="#ffffff" />
          <circle cx="289" cy="197" r="1.5" fill="#ffffff" />

          {/* Sweat drop on temple (Panic detail) */}
          <path
            d="M 202 188 C 200 196, 204 200, 207 198 C 210 196, 208 190, 204 186 Z"
            fill="#38bdf8"
            opacity="0.9"
          />

          {/* Nose */}
          <path
            d="M 260 190 L 257 215 C 254 220, 266 220, 263 215"
            stroke="#b86948"
            strokeWidth="4"
            strokeLinecap="round"
            fill="none"
          />

          {/* Gaping Shocked Open Mouth ("¡FUE UN FRAUDE!") */}
          <g id="mouth">
            {/* Outer dark mouth cavity */}
            <path
              d="M 238 238 C 235 272, 285 272, 282 238 C 275 234, 245 234, 238 238 Z"
              fill="#180a0a"
              stroke="#20140e"
              strokeWidth="5"
            />
            {/* Upper Teeth */}
            <path
              d="M 244 240 Q 260 245 276 240 L 273 246 Q 260 248 247 246 Z"
              fill="#ffffff"
            />
            {/* Tongue */}
            <path
              d="M 248 266 C 255 258, 265 258, 272 266 C 265 272, 255 272, 248 266 Z"
              fill="#e15f65"
            />
          </g>

          {/* Chin crease */}
          <path
            d="M 252 284 Q 260 287 268 284"
            stroke="#b86948"
            strokeWidth="3.5"
            strokeLinecap="round"
          />

          {/* Hair - Stylish voluminous pompadour quiff */}
          <g id="hair">
            <path
              d="M 196 175 C 190 145, 195 110, 225 95 C 255 80, 290 85, 315 105 C 335 120, 335 150, 324 175 C 320 160, 310 145, 290 145 C 275 145, 265 155, 245 150 C 225 145, 215 160, 196 175 Z"
              fill="url(#hairGrad)"
              stroke="#130e0c"
              strokeWidth="5"
            />
            {/* Hair strands / highlights */}
            <path
              d="M 225 105 C 255 95, 285 105, 305 120"
              stroke="#5a4237"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <path
              d="M 240 125 C 265 118, 290 126, 300 138"
              stroke="#5a4237"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </g>
        </g>

        {/* --- ARMS AND RAISED ALARM HANDS (GESTURE OF PANIC / "NO!") --- */}
        <g id="raised-hands">
          {/* Left Arm & Sleeve */}
          <path
            d="M 140 440 C 130 400, 145 360, 185 340 L 220 370 L 195 440 Z"
            fill="url(#sweaterGrad)"
            stroke="#0d141e"
            strokeWidth="5"
          />
          {/* Left Wrist cuff */}
          <ellipse cx="230" cy="385" rx="16" ry="10" fill="#ffffff" stroke="#111824" strokeWidth="3" transform="rotate(-30 230 385)" />

          {/* Left Hand (raised palm pointing in alarm) */}
          <g transform="translate(190, 310)">
            {/* Palm */}
            <path
              d="M 30 50 C 20 40, 20 20, 35 10 C 45 5, 60 15, 65 30 L 65 60 C 50 65, 35 60, 30 50 Z"
              fill="url(#skinGlow)"
              stroke="#20140e"
              strokeWidth="4"
            />
            {/* Thumb */}
            <path
              d="M 30 35 C 15 30, 10 20, 18 15 C 25 10, 35 22, 35 28 Z"
              fill="url(#skinGlow)"
              stroke="#20140e"
              strokeWidth="3.5"
            />
            {/* Fingers pointing up-right */}
            <path
              d="M 40 15 C 38 -5, 48 -10, 52 10"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <path
              d="M 52 18 C 52 -2, 62 -5, 64 15"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <path
              d="M 64 25 C 68 8, 76 10, 74 25"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <path
              d="M 72 35 C 78 22, 85 25, 82 40"
              stroke="#20140e"
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </g>

          {/* Right Arm & Sleeve extending out to right */}
          <path
            d="M 380 440 C 420 410, 435 360, 415 330 L 385 360 L 360 430 Z"
            fill="url(#sweaterGrad)"
            stroke="#0d141e"
            strokeWidth="5"
          />
          {/* Right Wrist cuff */}
          <ellipse cx="435" cy="335" rx="16" ry="10" fill="#ffffff" stroke="#111824" strokeWidth="3" transform="rotate(35 435 335)" />

          {/* Right Hand (Splayed open palm in terror/alarm) */}
          <g transform="translate(390, 240)">
            {/* Palm */}
            <path
              d="M 35 70 C 45 60, 60 60, 70 75 C 75 85, 65 110, 45 105 Z"
              fill="url(#skinGlow)"
              stroke="#20140e"
              strokeWidth="4"
            />
            {/* Thumb */}
            <path
              d="M 28 80 C 10 75, 8 60, 20 62 C 30 65, 35 72, 35 78 Z"
              fill="url(#skinGlow)"
              stroke="#20140e"
              strokeWidth="3.5"
            />
            {/* Index Finger */}
            <path
              d="M 38 60 C 35 30, 48 30, 50 60"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            {/* Middle Finger */}
            <path
              d="M 52 58 C 55 20, 68 22, 65 58"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            {/* Ring Finger */}
            <path
              d="M 68 62 C 75 30, 86 35, 78 65"
              stroke="#20140e"
              strokeWidth="4"
              strokeLinecap="round"
            />
            {/* Pinky Finger */}
            <path
              d="M 80 72 C 92 48, 102 55, 88 80"
              stroke="#20140e"
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </g>
        </g>
      </svg>
    </div>
  );
};
