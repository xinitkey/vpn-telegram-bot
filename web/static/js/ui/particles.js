const COUNT = 8;
const RED_RATIO = 0.15;

function rand(min, max) { return min + Math.random() * (max - min); }

export function initParticles(container = document.querySelector('.bg-mesh'), count = COUNT) {
    if (!container) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const d = document.createElement('i');
        d.className = Math.random() < RED_RATIO ? 'droplet droplet-red' : 'droplet';

        const left = rand(2, 98);
        const w = rand(3, 9);              // width, px
        const h = w * rand(1.5, 2.2);      // height, px
        const dur = rand(5, 11);
        const delay = rand(0, 16);

        d.style.cssText =
            `left:${left.toFixed(1)}%;` +
            `width:${w.toFixed(1)}px;height:${h.toFixed(1)}px;` +
            `--d-dur:${dur.toFixed(1)}s;` +
            `--d-delay:${(-delay).toFixed(1)}s;`;
        frag.appendChild(d);
    }
    container.appendChild(frag);
}