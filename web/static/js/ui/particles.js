// ── Background particles ────────────────────────────────────────────────
// Small dots slowly rising on the solid background. Negative animation
// delay pre-populates the field so motion is visible from the first frame.

const COUNT = 6;
const RED_RATIO = 0.28;

export function initParticles(container = document.querySelector('.bg-mesh'), count = COUNT) {
    if (!container) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const p = document.createElement('i');
        p.className = Math.random() < RED_RATIO ? 'particle particle-red' : 'particle';
        const size = 14 + Math.random() * 21;               // 14–35px
        const time = 40 + Math.random() * 40;               // 40–80s per rise
        p.style.cssText =
            `left:${(Math.random() * 100).toFixed(1)}%;` +
            `width:${size.toFixed(1)}px;height:${size.toFixed(1)}px;` +
            `--p-time:${time.toFixed(1)}s;` +
            `--p-delay:${(-Math.random() * time).toFixed(1)}s;` +
            `--p-drift:${(Math.random() * 12 - 6).toFixed(1)}vw;`;
        frag.appendChild(p);
    }
    container.appendChild(frag);
}
