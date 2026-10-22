export type HostPosition = 'bottom-right' | 'bottom-left' | 'center-bottom';
export type HostOutlineColor = 'white' | 'cyan' | 'yellow' | 'red' | 'none';
export type FontStyleOption = 'bebas' | 'impact' | 'montserrat';
export type BackgroundPreset = 'control_room_dark' | 'cctv_multiview' | 'reality_breakdown' | 'custom_upload';

export interface ThumbnailConfig {
  // Main Viral Text
  primaryText: string;
  secondaryText: string;
  primaryTextColor: string; // Default #FFE600
  secondaryTextColor: string; // Default #FFFFFF
  primaryTextStroke: boolean;
  strokeWidth: number; // 8 - 20px
  textRotation: number; // -10 to 10 deg
  fontStyle: FontStyleOption;
  textSize: number; // scale factor 0.8 - 1.4
  textPosition: 'top-left' | 'top-right' | 'center-top' | 'center';
  textShadowIntensity: number;

  // Host Layer (01_host_alerta.png)
  hostVisible: boolean;
  hostPosition: HostPosition;
  hostScale: number; // 0.7 - 1.4
  hostOffsetX: number; // -100 to 100
  hostOffsetY: number; // -50 to 50
  hostFlipX: boolean;
  hostOutlineColor: HostOutlineColor;
  hostOutlineCustomColor: string;
  hostOutlineWidth: number; // Default 8px
  hostGlowIntensity: number; // 0 to 30px
  hostCustomImage: string | null;

  // Background Layer (08_fondo_miniatura_ai.jpg)
  backgroundPreset: BackgroundPreset;
  customBackgroundImage: string | null;
  ambientLighting: 'red-cyan' | 'pure-red' | 'cyber-cyan' | 'monochrome-cold';
  volumetricHaze: number; // 0 to 100
  vignetteStrength: number; // 0 to 100
  scanlines: boolean;
  grain: boolean;
  producerSilhouette: boolean;
  redAlertButtons: boolean;
  cctvGlitch: boolean;

  // High CTR Badges & Stickers
  showRecBadge: boolean;
  recTimecode: string;
  showClickbaitArrow: boolean;
  arrowTarget: 'cctv' | 'console' | 'host';
  showRedCircle: boolean;
  showSecretStamp: boolean;
  stampText: string;
  showSubtitleBanner: boolean;
  subtitleBannerText: string;

  // Color grading
  contrast: number; // 100 - 160%
  saturation: number; // 80 - 150%
  brightness: number; // 80 - 120%
}
