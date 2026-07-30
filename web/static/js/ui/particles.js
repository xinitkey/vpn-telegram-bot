const COUNT = 4;
const RED_RATIO = 0.15;

function rand(min, max) { return min + Math.random() * (max - min); }

export function initParticles(container = document.querySelector('.bg-mesh'), count = COUNT) {
    if (!container) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const left = rand(2, 98);
        const w = rand(3, 8);
        const h = w * rand(1.5, 2.2);
        const dur = rand(6, 12);
        const delay = rand(0, 16);
        const isRed = Math.random() < RED_RATIO;

        const d = document.createElement('i');
        d.className = isRed ? 'droplet droplet-red' : 'droplet';
        d.style.cssText =
            `left:${left.toFixed(1)}%;` +
            `width:${w.toFixed(1)}px;height:${h.toFixed(1)}px;` +
            `--d-dur:${dur.toFixed(1)}s;--d-delay:${(-delay).toFixed(1)}s;`;
        frag.appendChild(d);
    }
    container.appendChild(frag);
}