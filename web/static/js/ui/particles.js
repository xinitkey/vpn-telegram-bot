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

        const ring2 = document.createElement('i');
        ring2.className = isRed ? 'splash-ring-2 splash-ring-red-2' : 'splash-ring-2';
        ring2.style.cssText =
            `left:${left.toFixed(1)}%;` +
            `--sr2-dur:2s;--sr2-delay:${(ringStart - 2).toFixed(1)}s;`;
        frag.appendChild(ring2);

        const sprayCount = 3 + Math.floor(Math.random() * 3);
        for (let j = 0; j < sprayCount; j++) {
            const s = document.createElement('i');
            s.className = isRed ? 'spray spray-red' : 'spray';
            const spX = rand(-35, 35);
            const spY = rand(-15, -50);
            const sDur = rand(0.4, 1);
            const sSz = rand(1.5, 4);
            const sDelay = dur * 0.84 + delay;
            s.style.cssText =
                `left:${(left + rand(-1.5, 1.5)).toFixed(1)}%;bottom:2px;` +
                `width:${sSz.toFixed(1)}px;height:${sSz.toFixed(1)}px;` +
                `--sp-x:${spX.toFixed(1)}px;--sp-y:${spY.toFixed(1)}px;` +
                `--sp-dur:${sDur.toFixed(2)}s;--sp-delay:${(sDelay - sDur).toFixed(2)}s;`;
            frag.appendChild(s);
        }
    }
    container.appendChild(frag);
}