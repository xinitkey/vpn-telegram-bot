const COUNT = 8;
const RED_RATIO = 0.15;

function rand(min, max) { return min + Math.random() * (max - min); }

export function initParticles(container = document.querySelector('.bg-mesh'), count = COUNT) {
    if (!container) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const left = rand(2, 98);
        const w = rand(3, 9);
        const h = w * rand(1.5, 2.2);
        const dur = rand(5, 11);
        const delay = rand(0, 16);
        const isRed = Math.random() < RED_RATIO;
        const cls = isRed ? 'droplet droplet-red' : 'droplet';

        const d = document.createElement('i');
        d.className = cls;
        d.style.cssText =
            `left:${left.toFixed(1)}%;` +
            `width:${w.toFixed(1)}px;height:${h.toFixed(1)}px;` +
            `--d-dur:${dur.toFixed(1)}s;--d-delay:${(-delay).toFixed(1)}s;`;
        frag.appendChild(d);

        const ring = document.createElement('i');
        ring.className = isRed ? 'splash-ring splash-ring-red' : 'splash-ring';
        const ringStart = delay + dur * 0.82;
        ring.style.cssText =
            `left:${left.toFixed(1)}%;` +
            `--sr-dur:1.4s;--sr-delay:${(ringStart - 1.4).toFixed(1)}s;`;
        frag.appendChild(ring);

        const sprayCount = 2 + Math.floor(Math.random() * 2);
        for (let j = 0; j < sprayCount; j++) {
            const s = document.createElement('i');
            s.className = isRed ? 'spray spray-red' : 'spray';
            const spX = rand(-22, 22);
            const spY = rand(-18, -40);
            const sDur = rand(0.5, 0.9);
            const sDelay = dur * 0.84 + delay;
            s.style.cssText =
                `left:${(left + rand(-1, 1)).toFixed(1)}%;bottom:2px;` +
                `--sp-x:${spX.toFixed(1)}px;--sp-y:${spY.toFixed(1)}px;` +
                `--sp-dur:${sDur.toFixed(2)}s;--sp-delay:${(sDelay - sDur).toFixed(2)}s;`;
            frag.appendChild(s);
        }
    }
    container.appendChild(frag);
}