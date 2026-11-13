import lottie, { AnimationItem } from 'lottie-web/build/player/lottie_light';

export type BotState = 'idle' | 'typing' | 'thinking' | 'talking' | 'happy' | 'sad' | 'refuse';

/** Bot state -> segment name (markers inside mizan.json). */
const SEGMENT: Record<BotState, string> = {
  idle: 'idle',
  typing: 'listen',
  thinking: 'think',
  talking: 'talk',
  happy: 'happy',
  sad: 'sad',
  refuse: 'refuse',
};
const ONE_SHOT = new Set(['happy', 'sad', 'refuse']);
const MAX_LOOK = 10; // how far the pupils move, in Lottie units (comp is 400 wide)

interface Marker { tm: number; cm: string; dr: number }

/**
 * Drives the Lottie character from the chatbot's state.
 * The file holds one segment per state; "<name>_in" (if any) plays once
 * to ease into the pose, then "<name>" loops. One-shot reactions
 * (happy / sad / refuse) play once and go back to idle.
 * While idle, the pupils follow the mouse.
 */
export class Mascot {
  private anim?: AnimationItem;
  private seg = new Map<string, [number, number]>();
  private current = 'idle';
  private queue: string[] = [];
  private pupils?: SVGGElement | null;

  constructor(private host: HTMLElement, src: string) {
    fetch(src)
      .then((r) => r.json())
      .then((data) => {
        for (const m of (data.markers ?? []) as Marker[]) this.seg.set(m.cm, [m.tm, m.tm + m.dr - 1]);
        this.anim = lottie.loadAnimation({
          container: host,
          renderer: 'svg',
          loop: false,
          autoplay: false,
          animationData: data,
          rendererSettings: { preserveAspectRatio: 'xMidYMax meet' },
        });
        this.anim.setSubframe(false); // whole frames: segments never blend into each other
        this.anim.addEventListener('complete', () => this.next());
        this.anim.addEventListener('DOMLoaded', () => {
          this.pupils = host.querySelector<SVGGElement>('g.pupils');
          if (this.pupils) this.pupils.style.transition = 'translate .18s ease-out';
          this.play(this.current);
        });
      })
      .catch((e) => console.warn('[mizan] mascot failed to load', e));
  }

  set(state: BotState) {
    const name = SEGMENT[state];
    if (name === this.current && !ONE_SHOT.has(name)) return;
    this.play(name);
  }

  /** Plays a one-shot reaction (e.g. "happy" jump) then returns to idle. */
  react(name: 'happy' | 'sad' | 'refuse') {
    this.play(name);
  }

  /** Eyes look toward a point on screen (only while idle). */
  lookAt(x: number, y: number) {
    if (!this.pupils || this.current !== 'idle') return;
    const r = this.host.getBoundingClientRect();
    if (!r.width) return;
    // the drawn character is a square at the bottom-centre of the host
    const size = Math.min(r.width, r.height);
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height - size * 0.45; // eye line
    const dx = x - cx;
    const dy = y - cy;
    const d = Math.hypot(dx, dy) || 1;
    const k = Math.min(1, d / (size * 1.5)) * MAX_LOOK; // closer mouse = smaller move
    this.pupils.style.translate = `${((dx / d) * k).toFixed(2)}px ${((dy / d) * k * 0.8).toFixed(2)}px`;
  }

  private resetLook() {
    if (this.pupils) this.pupils.style.translate = '0px 0px';
  }

  private play(name: string) {
    this.current = name;
    if (name !== 'idle') this.resetLook();
    if (!this.anim) return;
    this.queue = this.seg.has(`${name}_in`) ? [`${name}_in`, name] : [name];
    this.next();
  }

  private next() {
    if (!this.anim) return;
    let name = this.queue.shift();
    if (!name) {
      // loop states replay; one-shot reactions settle back to idle
      if (ONE_SHOT.has(this.current)) return this.play('idle');
      name = this.current;
    }
    const s = this.seg.get(name);
    if (s) this.anim.playSegments(s, true);
  }

  /** Kept for API compatibility (the typing pose looks at the input). */
  look(_chars: number) {}

  destroy() {
    this.anim?.destroy();
  }
}
