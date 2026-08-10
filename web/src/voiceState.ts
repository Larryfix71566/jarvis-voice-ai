/**
 * Shared voice-state for the console's visual layers.
 *
 * The full-viewport VoiceWave is the primary voice display; the readout
 * label and agent satellites in OrbField use the same state. (This used
 * to live in Orb.tsx as OrbState — the orb was removed when the SILO
 * wave took over voice display.)
 */
export type VoiceState = "offline" | "connecting" | "listening" | "speaking";
