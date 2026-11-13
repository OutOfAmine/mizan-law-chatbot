import {
  Component, ElementRef, OnDestroy, ViewEncapsulation,
  computed, effect, input, signal, untracked, viewChild,
} from '@angular/core';
import { BotState, Mascot } from './mascot';
import { Source, ask, segments } from './chat.service';

interface Msg {
  role: 'user' | 'bot';
  text: string;
  sources?: Source[];
  blocked?: boolean;
  pending?: boolean;
}

type Phase = 'closed' | 'opening' | 'open' | 'closing';

const MAX = 500;
const FONTS = 'https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Bricolage+Grotesque:opsz,wght@12..96,400;500;600&family=IBM+Plex+Sans+Arabic:wght@400;500;600&family=Amiri:wght@400;700&display=swap';

@Component({
  selector: 'mizan-chat',
  templateUrl: './app.html',
  styleUrl: './app.css',
  // Shadow DOM: the widget's CSS never leaks into (or breaks on) the host website
  encapsulation: ViewEncapsulation.ShadowDom,
})
export class App implements OnDestroy {
  /** Backend URL, e.g. <mizan-chat api="https://api.example.ma"> */
  api = input('http://localhost:8000');
  /** Lottie file of the character (one segment per state, see tools/build_mascot.py) */
  mascot = input('mizan.json');
  /** "inline" fills its container (for demos), "floating" = character in the corner */
  mode = input<'floating' | 'inline'>('floating');

  readonly max = MAX;
  open = signal(false);
  phase = signal<Phase>('closed');
  draft = signal('');
  busy = signal(false);
  state = signal<BotState>('idle');
  msgs = signal<Msg[]>([]);

  readonly questions = [
    'كم يوماً من العطلة السنوية يستحق الأجير؟',
    'كم مدة عطلة الأمومة؟',
    'لمن تعود الحضانة بعد الطلاق؟',
    'هل التعليم مجاني حسب الدستور؟',
  ];

  isOpen = computed(() => this.mode() === 'inline' || this.open());
  fresh = computed(() => this.msgs().length === 0);
  left = computed(() => MAX - this.draft().length);

  private canvas = viewChild<ElementRef<HTMLElement>>('stage');
  private list = viewChild<ElementRef<HTMLElement>>('list');
  private launch = viewChild<ElementRef<HTMLElement>>('launch');
  private launchBtn = viewChild<ElementRef<HTMLElement>>('launchBtn');
  private bot?: Mascot;
  private launcherBot?: Mascot;
  private ctrl?: AbortController;
  private raf = 0;
  private onMove = (e: PointerEvent) => {
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.launcherBot?.lookAt(e.clientX, e.clientY);
      this.bot?.lookAt(e.clientX, e.clientY);
    });
  };

  readonly segments = segments;

  constructor() {
    this.loadFonts();
    window.addEventListener('pointermove', this.onMove, { passive: true });

    // character inside the panel: mounted while the panel exists
    effect(() => {
      const host = this.canvas()?.nativeElement;
      if (host && !this.bot) {
        this.bot = new Mascot(host, this.mascot());
        this.bot.set(untracked(this.state));
      } else if (!host && this.bot) {
        this.bot.destroy();
        this.bot = undefined;
      }
    });
    // character in the corner (the launcher)
    effect(() => {
      const host = this.launch()?.nativeElement;
      if (host && !this.launcherBot) {
        this.launcherBot = new Mascot(host, this.mascot());
      } else if (!host && this.launcherBot) {
        this.launcherBot.destroy();
        this.launcherBot = undefined;
      }
    });
  }

  ngOnDestroy() {
    window.removeEventListener('pointermove', this.onMove);
    this.launcherBot?.destroy();
    this.bot?.destroy();
    this.ctrl?.abort();
  }

  private loadFonts() {
    // fonts declared on the page are usable inside the shadow root
    if (document.querySelector(`link[href="${FONTS}"]`)) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = FONTS;
    document.head.appendChild(l);
  }

  // ---------- open / close with the jump ----------
  private reduced() {
    return matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /** Next paint, with a timer fallback so a background tab never stalls the sequence. */
  private frame() {
    return new Promise<void>((r) => {
      requestAnimationFrame(() => r());
      setTimeout(r, 50);
    });
  }

  /** The visible square the character is drawn in (Lottie draws it bottom-centre). */
  private square(el: HTMLElement) {
    const r = el.getBoundingClientRect();
    const size = Math.min(r.width, r.height);
    return { cx: r.left + r.width / 2, cy: r.bottom - size / 2, size };
  }

  private fly(from: HTMLElement, to: HTMLElement, back: boolean): Animation | undefined {
    const btn = this.launchBtn()?.nativeElement;
    if (!btn) return;
    const a = this.square(back ? to : from); // launcher square (home)
    // measure the header where it will END UP, not mid "panel-in" animation
    const panel = (back ? from : to).closest<HTMLElement>('.panel');
    if (panel && !back) panel.style.animation = 'none';
    const b = this.square(back ? from : to); // header square
    if (panel && !back) panel.style.animation = '';
    const br = btn.getBoundingClientRect();
    btn.style.transformOrigin = `${a.cx - br.left}px ${a.cy - br.top}px`;
    const dx = b.cx - a.cx;
    const dy = b.cy - a.cy;
    const s = b.size / a.size;
    const home = 'translate(0px, 0px) scale(1)';
    const top = `translate(${dx}px, ${dy}px) scale(${s})`;
    const mid = `translate(${dx * 0.55}px, ${Math.min(dy, 0) * 0.55 - 110}px) scale(${(1 + s) / 2}) rotate(${back ? 8 : -8}deg)`;
    const frames = back ? [{ transform: top }, { transform: mid, offset: 0.45 }, { transform: home }]
                        : [{ transform: home }, { transform: mid, offset: 0.55 }, { transform: top }];
    return btn.animate(frames, { duration: back ? 620 : 720, easing: 'cubic-bezier(.45,.05,.25,1)' });
  }

  async toggle() {
    if (this.phase() === 'opening' || this.phase() === 'closing') return;
    if (!this.open()) await this.openPanel();
    else await this.closePanel();
  }

  private async openPanel() {
    this.open.set(true);
    if (this.reduced()) return this.phase.set('open');
    this.phase.set('opening');
    this.launcherBot?.react('happy'); // arms up for the jump
    await this.frame();
    await this.frame();
    const home = this.launch()?.nativeElement;
    const target = this.canvas()?.nativeElement;
    if (home && target) await this.fly(home, target, false)?.finished;
    this.phase.set('open');
    this.bot?.react('happy'); // lands and celebrates
  }

  private async closePanel() {
    if (this.reduced()) {
      this.open.set(false);
      return this.phase.set('closed');
    }
    const home = this.launch()?.nativeElement;
    const from = this.canvas()?.nativeElement;
    // start the flight while the corner copy is still hidden, so it appears already in the header
    const flight = home && from ? this.fly(from, home, true) : undefined;
    this.phase.set('closing');
    await flight?.finished;
    this.open.set(false);
    this.phase.set('closed');
    this.launcherBot?.react('happy'); // back home
  }

  // ---------- chat ----------
  newChat() {
    this.ctrl?.abort();
    this.busy.set(false);
    this.msgs.set([]);
    this.setState('idle');
  }

  private setState(s: BotState) {
    this.state.set(s);
    this.bot?.set(s);
  }

  onType(v: string) {
    this.draft.set(v.slice(0, MAX));
    if (!this.busy()) this.setState(v ? 'typing' : 'idle');
  }

  /** Leaving the field only resets Mizan's pose; the typed text stays (clicking Send blurs first). */
  onBlur() {
    if (!this.busy() && this.state() === 'typing') this.setState('idle');
  }

  send(text = this.draft()) {
    const q = text.trim();
    if (!q || this.busy()) return;
    this.draft.set('');
    this.busy.set(true);
    this.msgs.update((m) => [...m, { role: 'user', text: q }, { role: 'bot', text: '', pending: true }]);
    this.scroll();

    const patch = (fn: (m: Msg) => Msg) =>
      this.msgs.update((all) => [...all.slice(0, -1), fn(all[all.length - 1])]);

    this.ctrl = new AbortController();
    ask(this.api(), q, {
      state: (s) => {
        this.setState(s);
        if (s === 'refuse') patch((m) => ({ ...m, blocked: true }));
      },
      token: (t) => {
        patch((m) => ({ ...m, text: m.text + t, pending: false }));
        this.scroll();
      },
      reset: (t) => patch((m) => ({ ...m, text: t, blocked: true, pending: false })),
      restart: () => patch((m) => ({ ...m, text: '', pending: true })),
      done: (d) => {
        patch((m) => ({ ...m, sources: d.sources ?? [], pending: false }));
        this.busy.set(false);
        this.scroll();
        setTimeout(() => !this.busy() && this.setState('idle'), 2500);
      },
      error: (msg) => {
        patch((m) => ({ ...m, text: msg, pending: false, blocked: true }));
        this.setState('sad');
        this.busy.set(false);
      },
    }, this.ctrl.signal).catch(() => {
      patch((m) => ({ ...m, text: 'وقع خطأ، حاول مرة أخرى.', pending: false, blocked: true }));
      this.busy.set(false);
    });
  }

  key(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.send();
    }
  }

  private scroll() {
    requestAnimationFrame(() => {
      const el = this.list()?.nativeElement;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
  }

  /** Footnote number for an inline citation, matched to the message's source list. */
  note(m: Msg, cite: string) {
    const num = /Article\s+([\w-]+)/i.exec(cite)?.[1];
    const i = (m.sources ?? []).findIndex((s) => s.article.split(' ')[1] === num);
    return i >= 0 ? i + 1 : '';
  }

  /** Answers are in Arabic: lay them out right-to-left. */
  rtl(text: string) {
    return /[؀-ۿ]/.test(text);
  }

  page(url: string) {
    return /#page=(\d+)/.exec(url)?.[1];
  }

  stateLabel = computed(() => ({
    idle: 'متاح',
    typing: 'أستمع إليك…',
    thinking: 'أبحث في النصوص…',
    talking: 'أجيبك…',
    happy: 'وجدت الجواب',
    sad: 'لم أجد مصدراً',
    refuse: 'رفضت الطلب',
  })[this.state()]);
}
