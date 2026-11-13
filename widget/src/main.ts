import { createApplication } from '@angular/platform-browser';
import { createCustomElement } from '@angular/elements';
import { provideZonelessChangeDetection } from '@angular/core';
import { App } from './app/app';

// Registers <mizan-chat> so ANY website can use it with one script tag:
//   <script type="module" src="https://.../mizan-chat.js"></script>
//   <mizan-chat api="https://your-backend"></mizan-chat>
(async () => {
  if (customElements.get('mizan-chat')) return;
  const app = await createApplication({ providers: [provideZonelessChangeDetection()] });
  customElements.define('mizan-chat', createCustomElement(App, { injector: app.injector }));
})().catch((err) => console.error('[mizan]', err));
