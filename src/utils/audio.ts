// Audio feedback utility with throttling and RSSI pitch scaling
// Throttled to at most one brief audio cue per second on fresh signal groups.

class AudioFeedbackManager {
  private ctx: AudioContext | null = null;
  private lastPlayTime: number = 0;
  public enabled: boolean = false;

  private initContext() {
    if (!this.ctx && typeof window !== 'undefined') {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  public playCueForRssi(rssi: number | null) {
    if (!this.enabled || rssi === null) return;

    const now = performance.now();
    // Throttle to at most one brief cue per second (1000ms)
    if (now - this.lastPlayTime < 1000) {
      return;
    }
    this.lastPlayTime = now;

    this.initContext();
    if (!this.ctx) return;

    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      // Pitch mapping: -100 dBm (low ~220Hz) to -30 dBm (high ~880Hz)
      const clampedRssi = Math.max(-100, Math.min(-30, rssi));
      const normalized = (clampedRssi - (-100)) / ((-30) - (-100)); // 0.0 to 1.0
      const freq = 220 + normalized * 660; // 220Hz to 880Hz

      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime);

      // Short 80ms gentle beep
      gain.gain.setValueAtTime(0.08, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + 0.08);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start();
      osc.stop(this.ctx.currentTime + 0.08);
    } catch {
      // Audio autoplay policy catch
    }
  }

  public clear() {
    this.lastPlayTime = 0;
  }
}

export const audioFeedback = new AudioFeedbackManager();
