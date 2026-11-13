import { BotState } from './mascot';

export interface Source {
  source: string;
  article: string;
  url: string;
  excerpt: string;
}

export interface StreamHandlers {
  state: (s: BotState) => void;
  token: (t: string) => void;
  reset: (t: string) => void;
  /** the server switched model mid-answer: clear the partial text */
  restart: () => void;
  done: (d: { sources?: Source[]; blocked?: string }) => void;
  error: (msg: string) => void;
}

/** POSTs the question and reads the server-sent events as they arrive. */
export async function ask(api: string, question: string, h: StreamHandlers, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`${api}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch {
    h.error('تعذر الاتصال بالخادم، حاول مرة أخرى.');
    return;
  }
  if (res.status === 429) {
    h.error('أسئلة كثيرة في وقت قصير، انتظر قليلاً.');
    return;
  }
  if (!res.ok || !res.body) {
    h.error('وقع خطأ، حاول مرة أخرى.');
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let cut: number;
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      const ev = /^event: (.+)$/m.exec(block)?.[1];
      const raw = /^data: (.*)$/m.exec(block)?.[1];
      if (!ev || raw === undefined) continue;
      const data = JSON.parse(raw);
      if (ev === 'state') h.state(data);
      else if (ev === 'token') h.token(data);
      else if (ev === 'reset') h.reset(data);
      else if (ev === 'restart') h.restart();
      else if (ev === 'done') h.done(data);
    }
  }
}

/**
 * Splits an answer into plain text and citation chips.
 * Rendered as text nodes only (never innerHTML) so a model answer can't inject HTML.
 */
export function segments(text: string): { kind: 'text' | 'cite' | 'bold'; value: string }[] {
  const out: { kind: 'text' | 'cite' | 'bold'; value: string }[] = [];
  // markdown list markers -> bullets; a lone "." after a citation joins its line
  text = text
    .replace(/^\s*[*-]\s+/gm, '• ')
    .replace(/\]\s*\n\s*\./g, '].')
    // a citation hugs the word before it (footnote style), even across a line break
    .replace(/\s+(\[[^\]]*?Article[^\]]*?\])/gi, '$1')
    .replace(/(\])\s*\n(?=\s*\[)/g, '$1')
    // "word [cite] ." -> "word[cite]."
    .replace(/\]\s+([.,،؛:!?])/g, ']$1');
  const re = /\[([^\]]*?Article[^\]]*?)\]|\*\*([^*]+)\*\*/gi;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push({ kind: 'text', value: text.slice(last, m.index) });
    out.push(m[1] ? { kind: 'cite', value: m[1] } : { kind: 'bold', value: m[2] });
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push({ kind: 'text', value: text.slice(last) });
  return out;
}
