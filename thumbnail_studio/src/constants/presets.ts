import { ThumbnailConfig } from '../types/thumbnail';

export const DEFAULT_CONFIG: ThumbnailConfig = {
  // Main Viral Text
  primaryText: '¡FUE UN FRAUDE!',
  secondaryText: 'DOCUMENTAL DE INVESTIGACIÓN',
  primaryTextColor: '#FFE600', // Yellow requested by user
  secondaryTextColor: '#FFFFFF',
  primaryTextStroke: true,
  strokeWidth: 14,
  textRotation: -3,
  fontStyle: 'bebas',
  textSize: 1.15,
  textPosition: 'top-left',
  textShadowIntensity: 85,

  // Host Layer (01_host_alerta.png)
  hostVisible: true,
  hostPosition: 'bottom-right',
  hostScale: 1.05,
  hostOffsetX: 10,
  hostOffsetY: 0,
  hostFlipX: false,
  hostOutlineColor: 'cyan', // Subtle white/cyan 8px contour
  hostOutlineCustomColor: '#22d3ee',
  hostOutlineWidth: 8, // Exact 8px requested
  hostGlowIntensity: 18,
  hostCustomImage: null,

  // Background Layer (08_fondo_miniatura_ai.jpg)
  backgroundPreset: 'control_room_dark',
  customBackgroundImage: null,
  ambientLighting: 'red-cyan',
  volumetricHaze: 65,
  vignetteStrength: 75,
  scanlines: true,
  grain: true,
  producerSilhouette: true,
  redAlertButtons: true,
  cctvGlitch: true,

  // Badges & CTR
  showRecBadge: true,
  recTimecode: '00:43:18 [CAM 04]',
  showClickbaitArrow: true,
  arrowTarget: 'cctv',
  showRedCircle: true,
  showSecretStamp: true,
  stampText: 'CONFIDENCIAL',
  showSubtitleBanner: true,
  subtitleBannerText: 'LA VERDAD QUE LA TELEVISIÓN OCULTÓ',

  // Color grading
  contrast: 135,
  saturation: 115,
  brightness: 95,
};

export const QUICK_TITLES = [
  { text: '¡FUE UN FRAUDE!', tag: 'Recomendado' },
  { text: 'NOS ENGAÑARON', tag: 'Alto CTR' },
  { text: 'LO APAGARON EN VIVO', tag: 'Ramón Ayala' },
  { text: 'EL FIN DE SU CARRERA', tag: 'Natanael Cano' },
  { text: 'LA IA TOMÓ EL CONTROL', tag: 'IA Peligro' },
  { text: 'ACUSÓ A UN INOCENTE', tag: 'IA Homicidio' },
  { text: 'CONTRATOS SECRETOS', tag: 'Documental' },
  { text: 'EL GRAN MONTAJE', tag: 'Investigación' },
];

export const YOUTUBE_MOCKUP_METADATA = {
  videoTitle: 'El FRAUDE detrás del Reality Show más Visto del Mundo (Documental de Investigación)',
  channelName: 'Expediente Oscuro TV',
  verified: true,
  views: '1.8 M de vistas',
  uploadedTime: 'hace 3 días',
  duration: '38:42',
  subscribers: '840 K suscriptores',
};
