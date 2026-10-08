// Aplica o nome (APP_TITLE) e a versão na tela de login. /api/branding é público e só devolve esses dois dados.
fetch('/api/branding').then(r => r.ok ? r.json() : null).then(b => {
  if (!b) return;
  if (b.version) document.querySelectorAll('[data-brand-version]').forEach(e => { e.textContent = 'version ' + b.version; e.hidden = false; });
  if (!b.title) return;
  document.querySelectorAll('[data-brand-title]').forEach(e => { e.textContent = b.title; });
  document.title = document.title.replace('Autoscaling Insights', b.title);
}).catch(() => {});
